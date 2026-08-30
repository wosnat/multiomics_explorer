"""OntologyKey stays in lockstep with ONTOLOGY_CONFIG (llm-review 2b.5 R2).

Also covers D3: every shared param carries exactly one description text,
reused verbatim on every tool that has that parameter.
"""
from typing import get_args

from multiomics_explorer.api.functions import ONTOLOGY_CONFIG
from multiomics_explorer.mcp_server.params import OntologyKey


def test_ontology_key_matches_registry():
    assert get_args(OntologyKey) == tuple(ONTOLOGY_CONFIG)


# ---------------------------------------------------------------------------
# D3: shared Annotated param types.
# ---------------------------------------------------------------------------

from tests.unit.test_tool_wrappers import _all_tool_input_schemas  # noqa: E402

_SHARED = {
    "organism": "OrganismParam", "limit": "LimitParam", "offset": "OffsetParam",
    "summary": "SummaryParam", "verbose": "VerboseParam",
    "treatment_type": "TreatmentTypeParam", "background_factors": "BackgroundFactorsParam",
    "growth_phases": "GrowthPhasesParam", "omics_type": "OmicsTypeParam",
    "publication_dois": "PublicationDoisParam", "metabolite_ids": "MetaboliteIdsParam",
    "exclude_metabolite_ids": "ExcludeMetaboliteIdsParam", "informative_only": "InformativeOnlyParam",
    "sources": "SourcesParam", "evidence": "EvidenceParam", "max_tier": "MaxTierParam",
    "min_evidence_score": "MinEvidenceScoreParam", "call_class": "CallClassParam",
}


def test_shared_params_have_one_description_each():
    from multiomics_explorer.mcp_server import params
    schemas = _all_tool_input_schemas()
    for pname, tname in _SHARED.items():
        expected = params.__dict__[tname].__metadata__[0].description
        texts = {n: s["properties"][pname].get("description") for n, s in schemas.items() if pname in s["properties"]}
        drift = {n: t for n, t in texts.items() if t != expected}
        assert not drift, f"{pname}: {list(drift)}"
