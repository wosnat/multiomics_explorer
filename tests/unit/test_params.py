"""OntologyKey stays in lockstep with ONTOLOGY_CONFIG (llm-review 2b.5 R2).

Also covers D3: every shared param carries exactly one description text,
reused verbatim on every tool that has that parameter, and (controller
ruling) that sharing a description never widens/narrows a parameter's
JSON-schema type relative to spec baseline commit 8b8f16d.
"""
import json
from pathlib import Path
from typing import get_args

from multiomics_explorer.api.functions import ONTOLOGY_CONFIG
from multiomics_explorer.mcp_server.params import OntologyKey


def test_ontology_key_matches_registry():
    assert get_args(OntologyKey) == tuple(ONTOLOGY_CONFIG)


# ---------------------------------------------------------------------------
# D3: shared Annotated param types.
# ---------------------------------------------------------------------------

from tests.unit.test_tool_wrappers import _all_tool_input_schemas  # noqa: E402

# A handful of params (organism, limit, metabolite_ids, publication_dois)
# have a required (non-Optional) variant on some tools and an Optional one
# on others at baseline — both variants must carry the identical text.
_SHARED = {
    "organism": ["OrganismParam", "OrganismRequiredParam"],
    "limit": ["LimitParam", "LimitOptionalParam"],
    "offset": ["OffsetParam"],
    "summary": ["SummaryParam"], "verbose": ["VerboseParam"],
    "treatment_type": ["TreatmentTypeParam"], "background_factors": ["BackgroundFactorsParam"],
    "growth_phases": ["GrowthPhasesParam"], "omics_type": ["OmicsTypeParam"],
    "publication_dois": ["PublicationDoisParam", "PublicationDoisRequiredParam"],
    "metabolite_ids": ["MetaboliteIdsParam", "MetaboliteIdsRequiredParam"],
    "exclude_metabolite_ids": ["ExcludeMetaboliteIdsParam"],
    "informative_only": ["InformativeOnlyParam"],
    "sources": ["SourcesParam"], "evidence": ["EvidenceParam"], "max_tier": ["MaxTierParam"],
    "min_evidence_score": ["MinEvidenceScoreParam"], "call_class": ["CallClassParam"],
}


def test_shared_params_have_one_description_each():
    from multiomics_explorer.mcp_server import params
    schemas = _all_tool_input_schemas()
    for pname, tnames in _SHARED.items():
        descs = {params.__dict__[t].__metadata__[0].description for t in tnames}
        assert len(descs) == 1, f"{pname}: variant types disagree on text: {descs}"
        expected = descs.pop()
        texts = {n: s["properties"][pname].get("description") for n, s in schemas.items() if pname in s["properties"]}
        drift = {n: t for n, t in texts.items() if t != expected}
        assert not drift, f"{pname}: {list(drift)}"


# ---------------------------------------------------------------------------
# D3 controller ruling: no parameter may be retyped by sharing a
# description. Snapshot of every tool's per-param JSON-schema
# type/anyOf/items/enum + required at spec baseline commit 8b8f16d
# (multiomics_explorer/mcp_server/tools.py as of that commit, before this
# task touched it) — descriptions are intentionally excluded.
# ---------------------------------------------------------------------------

_BASELINE_FIXTURE = Path(__file__).parent / "fixtures" / "input_schema_types_8b8f16d.json"
_TYPE_SIG_KEYS = ("type", "anyOf", "items", "enum")


def _type_sig(node):
    """Recursively keep only type/anyOf/items/enum at every nesting level
    (anyOf branches, items) — the same shape saved in the baseline fixture."""
    if not isinstance(node, dict):
        return node
    result = {}
    for k in _TYPE_SIG_KEYS:
        if k not in node:
            continue
        v = node[k]
        if k == "anyOf":
            result[k] = [_type_sig(b) for b in v]
        elif k == "items":
            result[k] = _type_sig(v)
        else:
            result[k] = v
    return result


def test_param_types_match_baseline():
    """No tool's parameter JSON-schema type or required-ness drifted from
    spec baseline commit 8b8f16d. Regression guard for the D3 shared-param
    refactor: sharing one description string across tools must never widen
    a required `str` to `str | None`, an `int` to `int | None`, etc."""
    baseline = json.loads(_BASELINE_FIXTURE.read_text())
    assert baseline, "baseline fixture is empty — this test would pass vacuously"
    schemas = _all_tool_input_schemas()
    diffs = []
    for tool, tool_params in baseline.items():
        schema = schemas[tool]
        current_props = schema["properties"]
        current_required = set(schema.get("required", []))
        for pname, binfo in tool_params.items():
            prop = current_props.get(pname)
            if prop is None:
                diffs.append(f"{tool}.{pname}: missing in current schema")
                continue
            cinfo = {"type_sig": _type_sig(prop), "required": pname in current_required}
            if cinfo != binfo:
                diffs.append(f"{tool}.{pname}: base={binfo} cur={cinfo}")
    assert not diffs, "\n".join(diffs)
