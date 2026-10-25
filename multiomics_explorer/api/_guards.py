"""Python-API input guards (backlog 3.18).

The MCP layer validates list params through Pydantic; the Python API does
not, so a bare ``str`` passed where ``list[str]`` is declared would iterate
per character and silently match 0 rows. ``listify_bare_str`` wraps it as a
one-element list instead.
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


def listify_bare_str(fn: Callable) -> Callable:
    """Wrap a bare ``str`` passed to a ``list`` param as ``[value]``."""
    sig = inspect.signature(fn)
    checked: frozenset[str] | None = None

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        nonlocal checked
        if checked is None:
            checked = _list_only_params(fn)
        bound = sig.bind_partial(*args, **kwargs)
        hits = [n for n in checked
                if isinstance(bound.arguments.get(n), str)]
        if not hits:
            return fn(*args, **kwargs)
        for name in hits:
            bound.arguments[name] = [bound.arguments[name]]
        return fn(*bound.args, **bound.kwargs)

    return wrapper
