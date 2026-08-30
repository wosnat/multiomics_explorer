"""OntologyKey stays in lockstep with ONTOLOGY_CONFIG (llm-review 2b.5 R2)."""
from typing import get_args

from multiomics_explorer.api.functions import ONTOLOGY_CONFIG
from multiomics_explorer.mcp_server.params import OntologyKey


def test_ontology_key_matches_registry():
    assert get_args(OntologyKey) == tuple(ONTOLOGY_CONFIG)
