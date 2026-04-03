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


@app.command("list-clustering-analyses")
def list_clustering_analyses_cmd(
    search_text: str = typer.Option(None, "--search", "-s", help="Full-text search"),
    organism: str = typer.Option(None, "--organism", "-o", help="Filter by organism"),
    cluster_type: str = typer.Option(None, "--cluster-type", help="Filter by cluster type"),
    treatment_type: list[str] = typer.Option(None, "--treatment-type", help="Filter by treatment type"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List clustering analyses, with optional search and filters."""
    from multiomics_explorer.api.functions import list_clustering_analyses
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = list_clustering_analyses(
                search_text=search_text,
                organism=organism,
                cluster_type=cluster_type,
                treatment_type=treatment_type or None,
                summary=summary,
                verbose=verbose,
                limit=limit,
                conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Query error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Total entries:[/bold] {result.get('total_entries', 'N/A')}")
            console.print(f"[bold]Total matching:[/bold] {result.get('total_matching', 'N/A')}")
            if result.get("by_organism"):
                console.print("[bold]By organism:[/bold]")
                for item in result["by_organism"]:
                    console.print(f"  {item['organism_name']}: {item['count']}")
            if result.get("by_cluster_type"):
                console.print("[bold]By cluster type:[/bold]")
                for item in result["by_cluster_type"]:
                    console.print(f"  {item['cluster_type']}: {item['count']}")
            results = result.get("results", [])
            if results:
                table = Table(show_lines=True)
                keys = list(results[0].keys())
                for k in keys:
                    table.add_column(k)
                for row in results:
                    table.add_row(*[str(row.get(k, "")) for k in keys])
                console.print(table)
            elif not summary:
                console.print("[yellow]No results.[/yellow]")
            if result.get("truncated"):
                console.print(f"[dim]Showing {result['returned']} results (increase --limit for more)[/dim]")


@app.command("gene-clusters-by-gene")
def gene_clusters_by_gene_cmd(
    locus_tags: list[str] = typer.Argument(help="Gene locus tags"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(20, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Look up gene cluster memberships for one or more genes."""
    from multiomics_explorer.api.functions import gene_clusters_by_gene
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = gene_clusters_by_gene(
                locus_tags=locus_tags,
                summary=summary,
                verbose=verbose,
                limit=limit,
                conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Query error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Genes with clusters:[/bold] {result.get('genes_with_clusters', 'N/A')}")
            console.print(f"[bold]Genes without clusters:[/bold] {result.get('genes_without_clusters', 'N/A')}")
            console.print(f"[bold]Total matching:[/bold] {result.get('total_matching', 'N/A')}")
            if result.get("not_found"):
                console.print(f"[yellow]Not found:[/yellow] {', '.join(result['not_found'])}")
            if result.get("not_matched"):
                console.print(f"[yellow]Not matched:[/yellow] {', '.join(result['not_matched'])}")
            if result.get("by_cluster_type"):
                console.print("[bold]By cluster type:[/bold]")
                for item in result["by_cluster_type"]:
                    console.print(f"  {item['cluster_type']}: {item['count']}")
            results = result.get("results", [])
            if results:
                table = Table(show_lines=True)
                keys = list(results[0].keys())
                for k in keys:
                    table.add_column(k)
                for row in results:
                    table.add_row(*[str(row.get(k, "")) for k in keys])
                console.print(table)
            elif not summary:
                console.print("[yellow]No results.[/yellow]")
            if result.get("truncated"):
                console.print(f"[dim]Showing {result['returned']} results (increase --limit for more)[/dim]")


@app.command("genes-in-cluster")
def genes_in_cluster_cmd(
    cluster_ids: list[str] = typer.Argument(None, help="GeneCluster node IDs"),
    analysis_id: str = typer.Option(None, "--analysis-id", "-a",
        help="ClusteringAnalysis ID (alternative to cluster_ids)"),
    organism: str = typer.Option(None, "--organism", "-o", help="Filter by organism"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(20, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List genes belonging to one or more gene clusters."""
    from multiomics_explorer.api.functions import genes_in_cluster
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = genes_in_cluster(
                cluster_ids=cluster_ids or None,
                analysis_id=analysis_id,
                organism=organism,
                summary=summary,
                verbose=verbose,
                limit=limit,
                conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Query error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Total matching:[/bold] {result.get('total_matching', 'N/A')}")
            if result.get("analysis_name"):
                console.print(f"[bold]Analysis:[/bold] {result['analysis_name']}")
            if result.get("by_organism"):
                console.print("[bold]By organism:[/bold]")
                for item in result["by_organism"]:
                    console.print(f"  {item['organism_name']}: {item['count']}")
            if result.get("not_found_clusters"):
                console.print(f"[yellow]Not found:[/yellow] {', '.join(result['not_found_clusters'])}")
            if result.get("not_matched_clusters"):
                console.print(f"[yellow]Not matched:[/yellow] {', '.join(result['not_matched_clusters'])}")
            results = result.get("results", [])
            if results:
                table = Table(show_lines=True)
                keys = list(results[0].keys())
                for k in keys:
                    table.add_column(k)
                for row in results:
                    table.add_row(*[str(row.get(k, "")) for k in keys])
                console.print(table)
            elif not summary:
                console.print("[yellow]No results.[/yellow]")
            if result.get("truncated"):
                console.print(f"[dim]Showing {result['returned']} results (increase --limit for more)[/dim]")


if __name__ == "__main__":
    app()
