"""One-release keyword aliases for renamed Python-API parameters (spec 2b.5 D4).

Every alias here is scheduled for removal in explorer 0.1.0-alpha.6. The MCP
layer never uses these names — MCP schemas expose canonical names only.
"""
from __future__ import annotations

import warnings
from typing import Any


def deprecated_alias(
    *, old: Any, new: Any, old_name: str, new_name: str, listify: bool = False
) -> Any:
    """Resolve a renamed keyword: returns the value to use for ``new_name``.

    ``old`` set → DeprecationWarning and ``old`` is used. Both set → ValueError.
    ``listify=True`` wraps a bare ``str`` as a one-element list (the parameter is
    declared ``list[str]``; a bare string would otherwise iterate per character).
    """
    if old is not None and new is not None:
        raise ValueError(
            f"Pass either {new_name!r} or the deprecated {old_name!r}, not both."
        )
    if old is not None:
        warnings.warn(
            f"{old_name!r} is deprecated and will be removed in 0.1.0-alpha.6; "
            f"use {new_name!r}.",
            DeprecationWarning,
            stacklevel=3,
        )
        value = old
    else:
        value = new
    if listify and isinstance(value, str):
        value = [value]
    return value
