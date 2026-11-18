"""Python-API input guards (backlog 3.18, 2d.9).

The MCP layer validates list params through Pydantic; the Python API does
not, so a bare ``str`` passed where ``list[str]`` is declared would iterate
per character and silently match 0 rows. ``listify_bare_str`` wraps it as a
one-element list instead. It also drops repeated values from every
``list``-only param, on both the MCP and the Python path, so a repeated id
cannot double rows and totals.
"""
from __future__ import annotations

import functools
import inspect
import types
import typing
from typing import Callable


def _list_only_params(fn: Callable) -> frozenset[str]:
    """Params whose annotation admits ``list`` but not ``str``."""
    names = set()
    for name, hint in typing.get_type_hints(fn).items():
        if typing.get_origin(hint) in (typing.Union, types.UnionType):
            args = typing.get_args(hint)
        else:
            args = (hint,)
        if str not in args and any(typing.get_origin(a) is list for a in args):
            names.add(name)
    return frozenset(names)


def _dedup(values: list) -> list | None:
    """First-seen de-duplicated copy, or None when nothing repeats or an
    element is unhashable (the input is left as passed)."""
    try:
        unique = list(dict.fromkeys(values))
    except TypeError:
        return None
    return unique if len(unique) < len(values) else None


def listify_bare_str(fn: Callable) -> Callable:
    """Normalise ``list``-only params: wrap a bare ``str`` as ``[value]``
    and drop repeated values (first-seen order kept).

    Every list param is a set of ids or filter values, so a repeat carries
    no meaning; left in, it doubles rows and totals on the builders that
    ``UNWIND`` the list (``locus_tags``, ``cluster_ids``, ...). Params that
    also admit ``str`` are left untouched. A changed list is a new copy;
    the caller's list is never mutated.
    """
    sig = inspect.signature(fn)
    checked: frozenset[str] | None = None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        nonlocal checked
        if checked is None:
            checked = _list_only_params(fn)
        bound = sig.bind_partial(*args, **kwargs)
        changed = False
        for name in checked:
            value = bound.arguments.get(name)
            if isinstance(value, str):
                bound.arguments[name] = [value]
                changed = True
            elif isinstance(value, list):
                unique = _dedup(value)
                if unique is not None:
                    bound.arguments[name] = unique
                    changed = True
        if not changed:
            return fn(*args, **kwargs)
        return fn(*bound.args, **bound.kwargs)

    return wrapper
