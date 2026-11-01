"""Unit tests for scripts/refresh_examples.py — parser, comparator, trimmer
and the text-level YAML block replacement. No KG needed."""

import textwrap
from pathlib import Path

import pytest

from scripts import refresh_examples as rx

# ---------------------------------------------------------------------------
# parse_call
# ---------------------------------------------------------------------------


def test_parse_call_simple():
    name, kwargs = rx.parse_call('resolve_gene(identifier="dnaN", organism="MED4")')
    assert name == "resolve_gene"
    assert kwargs == {"identifier": "dnaN", "organism": "MED4"}


def test_parse_call_no_args():
    assert rx.parse_call("list_organisms()") == ("list_organisms", {})


def test_parse_call_lists_dicts_bools_none_numbers():
    name, kwargs = rx.parse_call(
        "t(a=[\"x\", 'y'], b={'k': [1, 2.5]}, c=True, d=None, e=3, f=-0.6)"
    )
    assert kwargs == {
        "a": ["x", "y"], "b": {"k": [1, 2.5]}, "c": True, "d": None, "e": 3, "f": -0.6,
    }


def test_parse_call_multiline_with_hash_comments():
    call = textwrap.dedent('''
        list_metabolites(
          organism_names=["Prochlorococcus MED4"],
          exclude_metabolite_ids=[
            "kegg.compound:C00002",  # ATP
            "kegg.compound:C00001",  # H2O
          ],
          search_text="glut#amate",   # a hash inside a string survives
        )
    ''')
    name, kwargs = rx.parse_call(call)
    assert name == "list_metabolites"
    assert kwargs["exclude_metabolite_ids"] == ["kegg.compound:C00002", "kegg.compound:C00001"]
    assert kwargs["search_text"] == "glut#amate"


def test_parse_call_rejects_expressions():
    with pytest.raises(ValueError):
        rx.parse_call("t(a=__import__('os'))")
    with pytest.raises(ValueError):
        rx.parse_call("not a call")


# ---------------------------------------------------------------------------
# parse_shown_response
# ---------------------------------------------------------------------------


def test_parse_shown_json_with_ellipses_and_comments():
    block = '''
      {
        "total_matching": 15,  # a comment
        "by_organism": [{"organism_name": "MED4", "count": 1}, ...],
        "results": [
          {"locus_tag": "PMM0001", "gene_name": "dnaN", ...},
          ...
        ],
        "trust_axes": {"merops": ["a", "b"]}, "...": "..."
      }
    '''
    data = rx.parse_shown_response(block)
    assert data["total_matching"] == 15
    assert data["by_organism"] == [{"organism_name": "MED4", "count": 1}]
    assert data["results"] == [{"locus_tag": "PMM0001", "gene_name": "dnaN"}]
    assert data["trust_axes"] == {"merops": ["a", "b"]}
    assert "..." not in data


def test_parse_shown_yaml_flow_style():
    block = '''
      total_matching: 20  # 18 quantifies + 2 flags
      by_organism: [4 organisms — MED4, MIT9301]
      metabolites_matched: 1
      not_found: []
    '''
    data = rx.parse_shown_response(block)
    assert data["total_matching"] == 20
    assert data["not_found"] == []


def test_parse_shown_unparseable_returns_none():
    assert rx.parse_shown_response("{ this is: not, [json") is None
    assert rx.parse_shown_response("   ") is None
    assert rx.parse_shown_response("just a sentence") is None


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

LIVE = {
    "total_matching": 43,
    "returned": 5,
    "truncated": True,
    "score": 0.123456,
    "by_organism": [
        {"organism_name": "A", "count": 1},
        {"organism_name": "B", "count": 2},
        {"organism_name": "C", "count": 3},
    ],
    "results": [{"locus_tag": "X1", "product": "a very long product name indeed"}],
    "nested": {"deep": {"k": "v"}},
}


def test_compare_ok_on_subset_and_rounding():
    shown = {
        "total_matching": 43,
        "truncated": True,
        "score": 0.12,
        "by_organism": [{"organism_name": "A", "count": 1}],
        "results": [{"locus_tag": "X1", "product": "a very long..."}],
        "nested": {"deep": {"k": "v"}},
    }
    assert rx.compare(shown, LIVE) == []


def test_compare_reports_paths():
    shown = {
        "total_matching": 15,
        "by_organism": [{"organism_name": "A", "count": 1}, {"organism_name": "Z", "count": 2}],
        "nested": {"deep": {"k": "w"}},
        "missing_key": 1,
    }
    diffs = {d.path: (d.shown, d.live) for d in rx.compare(shown, LIVE)}
    assert diffs["$.total_matching"] == (15, 43)
    assert diffs["$.by_organism[1].organism_name"] == ("Z", "B")
    assert diffs["$.nested.deep.k"] == ("w", "v")
    assert diffs["$.missing_key"] == (1, "<missing>")
    assert len(diffs) == 4


def test_compare_list_longer_than_live_is_drift():
    diffs = rx.compare({"results": [{"a": 1}, {"a": 2}]}, {"results": [{"a": 1}]})
    assert [d.path for d in diffs] == ["$.results[1]"]


def test_compare_prose_placeholder_is_ignored():
    shown = {"by_organism": "4 organisms — MED4, MIT9301", "results": ["polymorphic rows"]}
    assert rx.compare(shown, LIVE) == []


def test_compare_bool_vs_string_key():
    # YAML flow `{false: 2}` → key False; live rollups use string keys
    assert rx.compare([{False: 2}], [{"false": 2}]) == []
    assert rx.compare({"truncated": "true"}, {"truncated": True}) == []


def test_is_empty_response():
    assert rx.is_empty_response({"total_matching": 0, "results": []})
    assert rx.is_empty_response({"results": [], "not_found": ["x"]})
    assert not rx.is_empty_response({"total_matching": 3, "results": []})
    assert not rx.is_empty_response({"total_matching": 3, "results": [{}]})
    assert not rx.is_empty_response({"verdict": "ok"})


# ---------------------------------------------------------------------------
# trim_response / format_response
# ---------------------------------------------------------------------------


def test_trim_response_rules():
    live = {
        "total_matching": 100,
        "long": "x" * 300,
        "by_organism": [{"n": i} for i in range(8)],
        "top_terms": [{"t": i, "genes": list(range(10))} for i in range(2)],
        "results": [{"r": i, "s": "y" * 200} for i in range(7)],
    }
    t = rx.trim_response(live)
    assert t["total_matching"] == 100
    assert len(t["long"]) == rx.MAX_STRING_LEN and t["long"].endswith("...")
    assert t["by_organism"] == [{"n": i} for i in range(3)] + ["..."]
    assert t["top_terms"][0]["genes"] == [0, 1, 2, "..."]
    cut = "y" * (rx.MAX_STRING_LEN - 3) + "..."
    assert t["results"][:3] == [{"r": i, "s": cut} for i in range(3)]
    assert t["results"][3] == "..." and len(t["results"]) == 4
    # small results list is untouched
    assert rx.trim_response({"results": [{"a": 1}]})["results"] == [{"a": 1}]


def test_trim_response_elides_nulls_in_rows_only_above_threshold():
    row = {"locus_tag": "PMM1", "a": None, "b": None, "c": None, "n": 0}
    t = rx.trim_response({"results": [row], "top_genes": [row], "scalar_null": None})
    expected = {"locus_tag": "PMM1", "n": 0, "...": "3 null fields omitted (a, b, c)"}
    assert t["results"] == [expected]
    assert t["top_genes"] == [expected]
    assert t["scalar_null"] is None  # envelope-level nulls are kept
    # below the threshold nulls stay visible
    few = {"locus_tag": "PMM1", "gene_name": None, "x": None}
    assert rx.trim_response({"results": [few]})["results"] == [few]
    # a non-list dict (envelope mapping) keeps its nulls
    assert rx.trim_response({"nf": {"a": None, "b": None, "c": None}})["nf"] == {"a": None, "b": None, "c": None}


def test_trim_response_caps_mapping_valued_envelope_fields():
    live = {"by_x": {f"k{i}": i for i in range(10)}, "small": {"a": 1}}
    t = rx.trim_response(live)
    assert list(t["by_x"])[: rx.MAX_DICT_KEYS] == [f"k{i}" for i in range(rx.MAX_DICT_KEYS)]
    assert t["by_x"]["..."] == f"+{10 - rx.MAX_DICT_KEYS} more"
    assert t["small"] == {"a": 1}


def test_trim_response_wide_rollup_entries_keep_one_exemplar():
    wide = {f"f{j}": j for j in range(rx.WIDE_ENTRY_KEYS + 1)}
    narrow = {"category": "x", "gene_count": 1}
    t = rx.trim_response({"top_genes": [wide] * 4, "top_cats": [narrow] * 4, "results": [wide] * 4})
    assert t["top_genes"] == [wide, "..."]
    assert t["top_cats"] == [narrow] * 3 + ["..."]
    assert t["results"] == [wide] * 3 + ["..."]  # results rows follow max_rows only


def test_trim_response_elides_empty_envelope_fields():
    live = {
        "total_matching": 0, "a": [], "b": None, "results": [],
        "c": {}, "not_found": [], "d": 1,
    }
    t = rx.trim_response(live)
    assert list(t) == ["total_matching", "...", "results", "not_found", "d"]
    assert t["..."] == "3 empty fields omitted (a, b, c)"
    # fewer than the threshold: shown as-is
    assert rx.trim_response({"a": [], "b": None, "d": 1}) == {"a": [], "b": None, "d": 1}


def test_trim_response_keeps_not_classified_tail_bucket():
    rows = [{"kegg_functional_category": f"c{i}", "count": 9 - i} for i in range(6)]
    rows.append({"kegg_functional_category": "not classified", "count": 42})
    live = {"by_kegg_functional_category": rows}
    t = rx.trim_response(live)
    assert t["by_kegg_functional_category"] == rows[:3] + ["...", rows[-1]]
    # the head + tail form still checks clean against live; a wrong tail drifts
    shown = rx.parse_shown_response(rx.format_response(live))
    assert rx.compare(shown, live) == []
    bad = {"by_kegg_functional_category": rows[:3] + [{"kegg_functional_category": "not classified", "count": 1}]}
    assert rx.compare(bad, live)


def test_trim_config_is_configurable():
    cfg = rx.TrimConfig(max_rows=1, max_items=2, max_dict_keys=1, min_nulls_to_elide=1, max_string_len=10)
    t = rx.trim_response(
        {"results": [{"a": None}] * 3, "l": [1, 2, 3], "d": {"x": 1, "y": 2}, "s": "z" * 20}, cfg
    )
    assert t["results"] == [{"...": "1 null fields omitted (a)"}, "..."]
    assert t["l"] == [1, 2, "..."]
    assert t["d"] == {"x": 1, "...": "+1 more"}
    assert t["s"] == "z" * 7 + "..."


def test_trimmed_response_parses_back_as_subset_and_is_idempotent():
    live = {
        "total_matching": 9,
        "by_x": {f"k{i}": i for i in range(9)},
        "top": [{"id": i, "a": None, "b": None, "c": None, "ec": list(range(6))} for i in range(5)],
        "results": [{"locus_tag": f"P{i}", **{c: None for c in "abcde"}} for i in range(5)],
    }
    text = rx.format_response(live)
    assert '"...": "3 null fields omitted (a, b, c)"' in text and '"...": "+3 more"' in text
    assert '"...": "5 null fields omitted"' in text  # > MAX_NAMED_ELISIONS: count only
    shown = rx.parse_shown_response(text)
    assert shown is not None
    assert rx.compare(shown, live) == []  # every shown leaf matches live
    assert shown["results"] == [{"locus_tag": f"P{i}"} for i in range(3)]
    assert rx.format_response(live) == text  # deterministic
    # the generator lint sees real envelope keys only
    import re
    keys = set(re.findall(r'(?:"|\b)([A-Za-z_][A-Za-z0-9_]*)"?\s*:', text))
    assert {"total_matching", "by_x", "top", "results"} <= keys


def test_format_response_is_pretty_json_with_bare_ellipsis():
    text = rx.format_response({"results": [{"a": 1}] * 4, "truncated": True})
    assert text == '{\n  "results": [{"a": 1}, {"a": 1}, {"a": 1}, ...],\n  "truncated": true\n}'
    # a long results list breaks one row per line, short dicts stay inline
    text = rx.format_response({"results": [{"locus_tag": f"PMM{i:04d}", "product": "x" * 40} for i in range(4)]})
    assert '    {"locus_tag": "PMM0000", "product": "' in text and "\n    ...\n" in text
    assert rx.format_response({"a": [1, 2], "b": {"c": None}}) == '{\n  "a": [1, 2],\n  "b": {"c": null}\n}'
    # round-trips through the lenient parser
    text = rx.format_response({"results": [{"a": 1}] * 4, "truncated": True})
    assert rx.parse_shown_response(text) == {"results": [{"a": 1}] * 3, "truncated": True}


# ---------------------------------------------------------------------------
# replace_response_block — byte-for-byte outside the block
# ---------------------------------------------------------------------------

YAML_DOC = textwrap.dedent('''\
    # header comment
    examples:
      - title: First
        call: t(a=1)
        response: |
          {
            "old": 1
          }

      - title: Second   # keep me
        call: |
          t(
            a=2,  # comment
          )
        response: |
          {"old": 2}
        # trailing comment on the item

      - title: Third
        steps: |
          Step 1: t()

    chaining:
      - "t → u"
    ''')


def test_replace_response_block_only_touches_target():
    out = rx.replace_response_block(YAML_DOC, 1, '{\n  "new": 2\n}')
    expected = YAML_DOC.replace('    response: |\n      {"old": 2}\n',
                                '    response: |\n      {\n        "new": 2\n      }\n')
    assert out == expected
    # first block untouched, both parse
    import yaml
    data = yaml.safe_load(out)
    assert data["examples"][0]["response"].strip() == '{\n  "old": 1\n}'
    assert data["examples"][1]["response"].strip() == '{\n  "new": 2\n}'
    assert data["examples"][1]["call"].startswith("t(")
    assert data["chaining"] == ["t → u"]


def test_replace_response_block_multiline_target():
    out = rx.replace_response_block(YAML_DOC, 0, '{"new": 1}')
    assert '      {\n        "old": 1\n      }\n' not in out
    assert '    response: |\n      {"new": 1}\n\n  - title: Second' in out


def test_replace_response_block_errors():
    with pytest.raises(ValueError, match="no `response: |`"):
        rx.replace_response_block(YAML_DOC, 2, "{}")
    with pytest.raises(ValueError, match="out of range"):
        rx.replace_response_block(YAML_DOC, 9, "{}")


# ---------------------------------------------------------------------------
# load_examples — skip rules
# ---------------------------------------------------------------------------


def test_load_examples_skip_reasons(tmp_path: Path):
    p = tmp_path / "mytool.yaml"
    p.write_text(textwrap.dedent('''\
        examples:
          - title: live
            call: t(a=1)
            response: |
              {}
          - title: illustrative
            call: t(a=1)
            response: |
              {}
            illustrative: true
          - title: narrative
            steps: |
              Step 1
          - title: no call
            response: |
              {}
          - title: no response
            call: t(a=1)
        '''))
    exs = rx.load_examples(p)
    assert [e.tool for e in exs] == ["mytool"] * 5
    assert [e.skip_reason for e in exs] == [
        None, "illustrative", "steps narrative", "no call", "no response block",
    ]
    assert exs[0].id == "mytool[0] live"


def test_check_example_skips_without_runner():
    ex = rx.Example(tool="t", index=0, title="x", call="t()", response=None)
    res = rx.check_example(ex, runner=None)  # type: ignore[arg-type]
    assert res.status == rx.STATUS_SKIPPED


def test_check_example_classifies_with_fake_runner():
    class Runner:
        def __init__(self, out=None, exc=None):
            self.out, self.exc = out, exc

        def call(self, tool, kwargs):
            if self.exc:
                raise self.exc
            return self.out

    ex = rx.Example(tool="t", index=0, title="x", call='t(a="b")', response='{"total_matching": 2}')
    assert rx.check_example(ex, Runner({"total_matching": 2})).status == rx.STATUS_OK
    drift = rx.check_example(ex, Runner({"total_matching": 3}))
    assert drift.status == rx.STATUS_DRIFT and "shown=2 live=3" in drift.describe()
    assert rx.check_example(ex, Runner({"total_matching": 0})).status == rx.STATUS_EMPTY
    assert rx.check_example(ex, Runner(exc=RuntimeError("boom"))).status == rx.STATUS_ERROR
    bad = rx.Example(tool="t", index=0, title="x", call="t()", response="[not json")
    assert rx.check_example(bad, Runner({"a": 1})).status == rx.STATUS_UNPARSEABLE
    assert rx.summarize([drift]) == "examples=1 ok=0 drift=1 error=0 empty=0 unparseable=0 skipped=0"


def test_empty_live_is_ok_when_shown_documents_empty():
    class Runner:
        def call(self, tool, kwargs):
            return {"total_matching": 0, "returned": 0, "results": [], "warnings": ["w"]}

    ex = rx.Example(tool="t", index=0, title="x", call="t()",
                    response='{"returned": 0, "results": [], "warnings": ["w"]}')
    assert rx.check_example(ex, Runner()).status == rx.STATUS_OK
    ex2 = rx.Example(tool="t", index=0, title="x", call="t()", response='{"returned": 3}')
    assert rx.check_example(ex2, Runner()).status == rx.STATUS_EMPTY


def test_keep_exempts_keys_from_dict_cap_and_empty_fold():
    live = {"params": {f"k{i}": i for i in range(10)},
            "a": [], "b": None, "c": {}, "by_level": [], "results": []}
    plain = rx.trim_response(live)
    assert "..." in plain["params"] and "by_level" not in plain
    kept = rx.trim_response(live, keep=("params", "by_level"))
    assert kept["params"] == live["params"]
    assert kept["by_level"] == []
    assert "..." in kept  # the other empties still fold


def test_load_examples_reads_keep(tmp_path):
    p = tmp_path / "some_tool.yaml"
    p.write_text("examples:\n  - title: t\n    call: some_tool()\n    keep: [enrichment_params]\n    response: |\n      {}\n")
    (ex,) = rx.load_examples(p)
    assert ex.keep == ("enrichment_params",)
