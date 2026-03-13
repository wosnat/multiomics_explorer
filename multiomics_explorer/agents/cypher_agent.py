"""NL→Cypher translation agent using LangChain GraphCypherQAChain.

Stage 2 core: translates natural language questions into Cypher queries,
executes them against the KG, and generates natural language answers.
"""

from pathlib import Path
from typing import Any

import yaml
from langchain.chat_models import init_chat_model
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph

from multiomics_explorer.config.settings import Settings, get_settings
from multiomics_explorer.kg.queries import FEW_SHOT_EXAMPLES


def _load_system_prompt() -> str:
    """Load the cypher translation system prompt from prompts.yaml."""
    prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    with open(prompts_path) as f:
        prompts = yaml.safe_load(f)
    return prompts["system_prompts"]["cypher_translation"]


def _format_few_shot_examples() -> str:
    """Format few-shot examples for prompt injection."""
    lines = []
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
        lines.append(f"Example {i}:")
        lines.append(f"Question: {ex['question']}")
        lines.append(f"Cypher:\n{ex['cypher']}")
        lines.append(f"Note: {ex['explanation']}\n")
    return "\n".join(lines)


class CypherAgent:
    """Agent that translates natural language to Cypher and answers questions."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._graph = None
        self._chain = None

    @property
    def graph(self) -> Neo4jGraph:
        if self._graph is None:
            auth = self._settings.neo4j_auth
            self._graph = Neo4jGraph(
                url=self._settings.neo4j_uri,
                username=auth[0] if auth else "",
                password=auth[1] if auth else "",
            )
        return self._graph

    @property
    def chain(self) -> GraphCypherQAChain:
        if self._chain is None:
            llm = init_chat_model(
                self._settings.model,
                model_provider=self._settings.model_provider,
                temperature=self._settings.model_temperature,
            )

            system_prompt = _load_system_prompt()
            few_shot = _format_few_shot_examples()

            self._chain = GraphCypherQAChain.from_llm(
                llm=llm,
                graph=self.graph,
                verbose=True,
                return_intermediate_steps=True,
                top_k=50,
                cypher_prompt_extra=f"\n{system_prompt}\n\n## Examples\n\n{few_shot}",
            )
        return self._chain

    def query(self, question: str) -> dict[str, Any]:
        """Translate a natural language question to Cypher and return results.

        Returns dict with keys:
        - answer: Natural language answer
        - cypher: Generated Cypher query
        - results: Raw query results
        """
        result = self.chain.invoke({"query": question})

        # Extract intermediate steps
        cypher = ""
        raw_results = []
        if "intermediate_steps" in result:
            steps = result["intermediate_steps"]
            if len(steps) > 0:
                cypher = steps[0].get("query", "")
            if len(steps) > 1:
                raw_results = steps[1].get("context", [])

        return {
            "answer": result.get("result", ""),
            "cypher": cypher,
            "results": raw_results,
        }
