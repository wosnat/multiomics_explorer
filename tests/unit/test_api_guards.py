"""Bare-str listify on list[str] Python-API params (backlog 3.18)."""
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
