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


@app.command()
def cypher(
    query: str = typer.Argument(help="Cypher query to execute"),
    limit: int = typer.Option(25, help="Max rows to display"),
):
    """Execute a Cypher query directly against the knowledge graph."""
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        results = conn.execute_query(query)

        if not results:
            console.print("[yellow]No results.[/yellow]")
            return

        # Build a rich table from the results
        table = Table(show_lines=True)
        keys = list(results[0].keys())
        for k in keys:
            table.add_column(k)

        for row in results[:limit]:
            table.add_row(*[str(row.get(k, "")) for k in keys])

        console.print(table)
        if len(results) > limit:
            console.print(f"[dim]Showing {limit} of {len(results)} results[/dim]")


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


@app.command()
def query(
    question: str = typer.Argument(help="Natural language question about the knowledge graph"),
):
    """Ask a natural language question (NL->Cypher->Answer)."""
    from multiomics_explorer.agents.cypher_agent import CypherAgent

    agent = CypherAgent()
    result = agent.query(question)

    console.print(f"\n[bold]Generated Cypher:[/bold]")
    console.print(f"[cyan]{result['cypher']}[/cyan]\n")
    console.print(f"[bold]Answer:[/bold]")
    console.print(result["answer"])

    if result["results"]:
        console.print(f"\n[dim]({len(result['results'])} raw results returned)[/dim]")


@app.command()
def interactive():
    """Start an interactive query session (REPL)."""
    console.print("[bold]Multiomics Explorer - Interactive Mode[/bold]")
    console.print("Type 'quit' to exit, 'cypher:' prefix for direct Cypher.\n")

    from multiomics_explorer.kg.connection import GraphConnection

    conn = GraphConnection()
    if not conn.verify_connectivity():
        console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
        raise typer.Exit(1)

    agent = None  # lazy init

    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            console.print("Bye!")
            break

        if user_input.lower().startswith("cypher:"):
            cypher_query = user_input[7:].strip()
            try:
                results = conn.execute_query(cypher_query)
                for row in results[:25]:
                    console.print(row)
                if len(results) > 25:
                    console.print(f"[dim]... {len(results)} total results[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        else:
            if agent is None:
                from multiomics_explorer.agents.cypher_agent import CypherAgent
                agent = CypherAgent()
            try:
                result = agent.query(user_input)
                console.print(f"\n[cyan]{result['cypher']}[/cyan]\n")
                console.print(result["answer"])
                console.print()
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    conn.close()


if __name__ == "__main__":
    app()
