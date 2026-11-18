"""Bare-str listify and de-duplication on list[str] Python-API params
(backlog 3.18, 2d.9)."""
import inspect
from unittest.mock import MagicMock, patch

from multiomics_explorer import api
from multiomics_explorer.api._guards import _list_only_params, listify_bare_str


@listify_bare_str
def _f(ids: list[str], *, opt: list[str] | None = None,
       either: str | list[str] | None = None, n: int = 0):
    return ids, opt, either, n


def test_list_only_params_skips_str_unions_and_scalars():
    assert _list_only_params(_f.__wrapped__) == {"ids", "opt"}


def test_bare_str_wrapped_keyword_and_positional():
    assert _f("PMM0001", opt="x") == (["PMM0001"], ["x"], None, 0)
    assert _f(ids="PMM0001") == (["PMM0001"], None, None, 0)


def test_lists_none_and_str_unions_untouched():
    assert _f(["a"], opt=None, either="go", n=3) == (["a"], None, "go", 3)


def test_list_experiments_bare_omics_type_reaches_builder_as_list():
    conn = MagicMock()
    with patch.object(
        api.functions, "build_list_experiments_summary",
        side_effect=RuntimeError("stop"),
    ) as builder:
        try:
            api.list_experiments(omics_type="RNASEQ", summary=True, conn=conn)
        except RuntimeError:
            pass
    assert builder.call_args.kwargs["omics_type"] == ["RNASEQ"]


def test_every_public_function_with_list_params_is_guarded():
    unguarded = [
        name for name in api.__all__
        if inspect.isfunction(fn := getattr(api, name))
        and _list_only_params(fn)
        and not hasattr(fn, "__wrapped__")
    ]
    assert unguarded == []


# -- de-duplication of list params (backlog 2d.9) ----------------------

def test_duplicate_list_values_collapse_first_seen_order():
    assert _f(["PMM0001", "PMM0002", "PMM0001"], opt=["x", "x"]) == (
        ["PMM0001", "PMM0002"], ["x"], None, 0)


def test_bare_str_then_dedup_is_noop():
    assert _f("PMM0001") == (["PMM0001"], None, None, 0)


def test_unique_list_passes_through_unchanged():
    ids = ["a", "b"]
    assert _f(ids)[0] == ["a", "b"]


def test_input_list_not_mutated():
    ids = ["a", "a"]
    _f(ids)
    assert ids == ["a", "a"]


def test_str_union_params_not_deduped():
    # `either` admits str, so it is outside the guarded set and untouched.
    assert _f(["a"], either=["go", "go"])[2] == ["go", "go"]


def test_unhashable_elements_left_alone():
    @listify_bare_str
    def g(rows: list[dict]):
        return rows
    rows = [{"a": 1}, {"a": 1}]
    assert g(rows) == [{"a": 1}, {"a": 1}]


def test_gene_overview_duplicate_locus_tags_reach_builder_once():
    conn = MagicMock()
    with patch.object(
        api.functions, "build_gene_overview_summary",
        side_effect=RuntimeError("stop"),
    ) as builder:
        try:
            api.gene_overview(
                locus_tags=["PMM0315", "PMM0315", "PMM0001"], conn=conn)
        except RuntimeError:
            pass
    assert builder.call_args.kwargs["locus_tags"] == ["PMM0315", "PMM0001"]


def test_genes_in_cluster_duplicate_cluster_ids_reach_builder_once():
    conn = MagicMock()
    with patch.object(
        api.functions, "build_genes_in_cluster_summary",
        side_effect=RuntimeError("stop"),
    ) as builder:
        try:
            api.genes_in_cluster(cluster_ids=["c1", "c1"], conn=conn)
        except RuntimeError:
            pass
    assert builder.call_args.kwargs["cluster_ids"] == ["c1"]
