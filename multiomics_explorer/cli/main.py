"""Command-line interface for the multiomics explorer."""

import json

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="multiomics-explorer",
    help="Query and reason over the Prochlorococcus/Alteromonas multi-omics knowledge graph.",
)
console = Console()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit", is_eager=True),
):
    if version:
        from importlib.metadata import version as pkg_version
        console.print(pkg_version("multiomics-explorer"))
        raise typer.Exit()


@app.command()
def schema(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Print the knowledge graph schema."""
    from multiomics_explorer.kg.connection import GraphConnection
    from multiomics_explorer.kg.schema import load_schema_from_neo4j

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        graph_schema = load_schema_from_neo4j(conn)

        if json_output:
            data = {
                "nodes": {
                    label: {"count": n.count, "properties": n.properties}
                    for label, n in graph_schema.nodes.items()
                },
                "relationships": {
                    rt: {
                        "source_labels": r.source_labels,
                        "target_labels": r.target_labels,
                        "properties": r.properties,
                    }
                    for rt, r in graph_schema.relationships.items()
                },
            }
            console.print(json.dumps(data, indent=2))
        else:
            console.print(graph_schema.to_prompt_string())


@app.command("schema-snapshot")
def schema_snapshot(
    output: str = typer.Option(None, "--output", "-o", help="Output path (default: config/schema_baseline.yaml)"),
):
    """Capture the live KG schema as a versioned baseline."""
    from pathlib import Path

    from multiomics_explorer.kg.connection import GraphConnection
    from multiomics_explorer.kg.schema import BASELINE_PATH, load_schema_from_neo4j, save_baseline

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        graph_schema = load_schema_from_neo4j(conn)
        path = Path(output) if output else BASELINE_PATH
        save_baseline(graph_schema, path)

        n_nodes = len(graph_schema.nodes)
        n_rels = len(graph_schema.relationships)
        console.print(f"[green]Baseline saved:[/green] {path}")
        console.print(f"  {n_nodes} node types, {n_rels} relationship types")


@app.command("schema-validate")
def schema_validate(
    baseline: str = typer.Option(None, "--baseline", "-b", help="Baseline file path (default: config/schema_baseline.yaml)"),
    strict: bool = typer.Option(False, "--strict", help="Fail on any change (including additions)"),
):
    """Compare the live KG schema against the saved baseline."""
    from pathlib import Path

    from multiomics_explorer.kg.connection import GraphConnection
    from multiomics_explorer.kg.schema import (
        BASELINE_PATH,
        diff_schemas,
        load_baseline,
        load_schema_from_neo4j,
    )

    path = Path(baseline) if baseline else BASELINE_PATH
    if not path.exists():
        console.print(f"[red]No baseline found at {path}. Run 'schema-snapshot' first.[/red]")
        raise typer.Exit(1)

    baseline_schema, meta = load_baseline(path)
    console.print(f"[dim]Baseline from {meta['captured_at']}[/dim]\n")

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        live_schema = load_schema_from_neo4j(conn)

    diff = diff_schemas(baseline_schema, live_schema)

    if not diff.has_changes:
        console.print("[green]Schema matches baseline. No drift detected.[/green]")
        return

    has_breaking = bool(diff.removed_nodes or diff.removed_relationships)

    if diff.added_nodes:
        console.print("[yellow]Added node types:[/yellow]")
        for n in diff.added_nodes:
            console.print(f"  + {n}")
    if diff.removed_nodes:
        console.print("[red]Removed node types:[/red]")
        for n in diff.removed_nodes:
            console.print(f"  - {n}")
    if diff.added_relationships:
        console.print("[yellow]Added relationship types:[/yellow]")
        for r in diff.added_relationships:
            console.print(f"  + {r}")
    if diff.removed_relationships:
        console.print("[red]Removed relationship types:[/red]")
        for r in diff.removed_relationships:
            console.print(f"  - {r}")
    for label, changes in diff.node_property_changes.items():
        console.print(f"[yellow]Node '{label}' property changes:[/yellow]")
        for c in changes:
            console.print(f"  ~ {c}")
    for rt, changes in diff.relationship_property_changes.items():
        console.print(f"[yellow]Relationship '{rt}' property changes:[/yellow]")
        for c in changes:
            console.print(f"  ~ {c}")

    if has_breaking or strict:
        console.print("\n[red]Schema validation failed.[/red]")
        raise typer.Exit(1)
    else:
        console.print("\n[yellow]Schema has non-breaking changes. Update baseline with 'schema-snapshot'.[/yellow]")


@app.command()
def cypher(
    query: str = typer.Argument(help="Cypher query to execute"),
    limit: int = typer.Option(25, help="Max rows to display (injected automatically if absent)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Execute a Cypher query directly against the knowledge graph."""
    from multiomics_explorer.api.functions import run_cypher
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = run_cypher(query, limit=limit, conn=conn)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Query error: {e}[/red]")
            raise typer.Exit(1)

        for warning in result["warnings"]:
            console.print(f"[yellow]Warning: {warning}[/yellow]")

        results = result["results"]

        if not results:
            console.print("[yellow]No results.[/yellow]")
            return

        if json_output:
            console.print(json.dumps(results, indent=2, default=str))
        else:
            table = Table(show_lines=True)
            keys = list(results[0].keys())
            for k in keys:
                table.add_column(k)
            for row in results:
                table.add_row(*[str(row.get(k, "")) for k in keys])
            console.print(table)

        if result["truncated"]:
            console.print(f"[dim]Showing {result['returned']} rows (may be more — increase --limit)[/dim]")


@app.command()
def stats():
    """Show basic knowledge graph statistics."""
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        s = conn.get_basic_stats()

        console.print(f"\n[bold]Total nodes:[/bold] {s['total_nodes']:,}")
        console.print(f"[bold]Node labels:[/bold] {len(s['node_labels'])}")
        console.print(f"[bold]Relationship types:[/bold] {len(s['relationship_types'])}\n")

        table = Table(title="Node Counts")
        table.add_column("Label")
        table.add_column("Count", justify="right")
        for label, count in sorted(s["label_counts"].items(), key=lambda x: -x[1]):
            table.add_row(label, f"{count:,}")
        console.print(table)


if __name__ == "__main__":
    app()
