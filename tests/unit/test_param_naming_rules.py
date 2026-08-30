"""Layer-3 parameter naming rules R1-R4 (spec 2026-08-30 llm-review 2b.5), checked on tools/list."""
import re
import pytest
from tests.unit.test_tool_wrappers import _all_tool_input_schemas

SCHEMAS = _all_tool_input_schemas()
ALL_PARAMS = {(tool, p): prop for tool, s in SCHEMAS.items() for p, prop in s["properties"].items()}
VOCAB = {"treatment_type", "background_factors", "growth_phases", "omics_type"}
# Names that legitimately break a rule (each with the reason kept in the spec).
ALLOW = {"organism", "organisms", "source", "sources", "analysis_id", "analysis_ids", "categories"}


def _is_list(prop):
    if prop.get("type") == "array":
        return True
    return any(_is_list(x) for x in prop.get("anyOf", []))


def test_r1_ranges_are_min_max_prefixed():
    bad = [p for (_, p) in ALL_PARAMS if re.search(r"_(min|max)$", p)]
    assert bad == [], bad


def test_r2_vocab_filters_are_lists_named_by_property():
    bad = [(t, p) for (t, p), prop in ALL_PARAMS.items() if p in VOCAB and not _is_list(prop)]
    assert bad == [], bad
    assert not any(p == "treatment_types" for (_, p) in ALL_PARAMS)


def test_r3_id_batches_are_plural():
    bad = [(t, p) for (t, p), prop in ALL_PARAMS.items()
           if _is_list(prop) and re.search(r"_(id|doi|tag)$", p) and p not in ALLOW]
    assert bad == [], bad


def test_r4_filters_match_row_fields():
    for tool, p in (("genes_by_numeric_metric", "bucket"), ("genes_by_boolean_metric", "flag"), ("genes_by_function", "category")):
        assert (tool, p) not in ALL_PARAMS, (tool, p)
