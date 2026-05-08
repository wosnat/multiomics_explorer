"""Tests for hand-written analysis about-content consistency.

Validates that:
- Parameter names in markdown tables match actual function signatures
- Import paths in code examples resolve
- Function names and keyword arguments in code examples match real signatures
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

import multiomics_explorer.analysis as analysis_pkg

ABOUT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer"
    / "skills"
    / "multiomics-kg-guide"
    / "references"
    / "analysis"
)

# All public analysis functions (name → callable).
ANALYSIS_FUNCTIONS: dict[str, callable] = {
    name: getattr(analysis_pkg, name) for name in analysis_pkg.__all__
}


def _get_about_files() -> list[Path]:
    if not ABOUT_DIR.exists():
        return []
    return sorted(ABOUT_DIR.glob("*.md"))


def _get_function_params(fn: callable) -> set[str]:
    """Return parameter names excluding internal ones (conn, ctx)."""
    sig = inspect.signature(fn)
    return {
        name
        for name, p in sig.parameters.items()
        if name not in ("conn", "ctx", "self")
    }


# ---------------------------------------------------------------------------
# Extract helpers
# ---------------------------------------------------------------------------


def _extract_param_table_names(content: str) -> list[str]:
    """Extract parameter names from markdown tables (| Name | ... rows)."""
    names = []
    in_table = False
    for line in content.split("\n"):
        if "| Name |" in line or "| Name |" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("| "):
            m = re.match(r"^\| `?(\w+)`? \|", line)
            if m:
                names.append(m.group(1))
        elif in_table and not line.startswith("|"):
            in_table = False
    return names


def _extract_python_blocks(content: str) -> list[str]:
    """Extract content of ```python ... ``` fenced code blocks."""
    blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
    return blocks


def _extract_imports(code: str) -> list[tuple[str, list[str]]]:
    """Parse 'from X import Y, Z' statements. Returns [(module, [names])]."""
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [alias.name for alias in node.names]
            results.append((node.module, names))
    return results


def _extract_function_calls(code: str) -> list[tuple[str, set[str]]]:
    """Parse function calls, returning [(func_name, {kwarg_names})]."""
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Get function name from simple calls like foo() or module.foo()
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
            results.append((name, kwargs))
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalysisAboutContent:
    """Verify analysis about files match actual function signatures."""

    @pytest.mark.parametrize("path", _get_about_files(), ids=lambda p: p.stem)
    def test_param_table_names_valid(self, path):
        """Parameter names in tables match some analysis function signature."""
        content = path.read_text()
        table_params = _extract_param_table_names(content)
        if not table_params:
            pytest.skip("no parameter table found")

        # Collect all valid param names across all analysis functions
        all_valid = set()
        for fn in ANALYSIS_FUNCTIONS.values():
            all_valid |= _get_function_params(fn)
        # Also allow conn (documented but excluded from _get_function_params)
        all_valid.add("conn")

        unknown = set(table_params) - all_valid
        assert not unknown, (
            f"{path.name}: unknown params in table: {unknown}. "
            f"Valid: {sorted(all_valid)}"
        )

    @pytest.mark.parametrize("path", _get_about_files(), ids=lambda p: p.stem)
    def test_imports_resolve(self, path):
        """Import paths in code examples are importable."""
        content = path.read_text()
        blocks = _extract_python_blocks(content)
        if not blocks:
            pytest.skip("no python code blocks")

        errors = []
        for i, block in enumerate(blocks, 1):
            for module, names in _extract_imports(block):
                try:
                    mod = __import__(module, fromlist=names)
                except ImportError:
                    errors.append(f"block {i}: cannot import module '{module}'")
                    continue
                for name in names:
                    if not hasattr(mod, name):
                        errors.append(
                            f"block {i}: '{name}' not found in '{module}'"
                        )
        assert not errors, f"{path.name}:\n" + "\n".join(f"  - {e}" for e in errors)

    @pytest.mark.parametrize("path", _get_about_files(), ids=lambda p: p.stem)
    def test_function_calls_use_valid_kwargs(self, path):
        """Function calls in code examples use valid keyword arguments."""
        content = path.read_text()
        blocks = _extract_python_blocks(content)
        if not blocks:
            pytest.skip("no python code blocks")

        errors = []
        for i, block in enumerate(blocks, 1):
            calls = _extract_function_calls(block)
            for func_name, kwargs in calls:
                if func_name not in ANALYSIS_FUNCTIONS:
                    # Might be an API function — check there too
                    import multiomics_explorer as top_pkg

                    if hasattr(top_pkg, func_name):
                        fn = getattr(top_pkg, func_name)
                    else:
                        # Built-in or variable method call (e.g. df.to_csv) — skip
                        continue
                else:
                    fn = ANALYSIS_FUNCTIONS[func_name]

                if not kwargs:
                    continue

                # Pydantic BaseModel subclasses report `**data` as the
                # only signature parameter — fall back to model_fields.
                if hasattr(fn, "model_fields"):
                    valid_params = set(fn.model_fields.keys())
                else:
                    valid_params = set(inspect.signature(fn).parameters.keys())
                invalid = kwargs - valid_params
                if invalid:
                    errors.append(
                        f"block {i}: {func_name}() got unexpected kwargs "
                        f"{invalid}. Valid: {sorted(valid_params)}"
                    )
        assert not errors, f"{path.name}:\n" + "\n".join(f"  - {e}" for e in errors)

    @pytest.mark.parametrize("path", _get_about_files(), ids=lambda p: p.stem)
    def test_function_names_in_examples_exist(self, path):
        """Function names called in examples exist as analysis or API functions."""
        content = path.read_text()
        blocks = _extract_python_blocks(content)
        if not blocks:
            pytest.skip("no python code blocks")

        import multiomics_explorer as top_pkg
        import multiomics_explorer.api.functions as api_mod

        api_functions = set(api_mod.__all__) if hasattr(api_mod, "__all__") else set()
        top_functions = set(top_pkg.__all__) if hasattr(top_pkg, "__all__") else set()
        known = set(ANALYSIS_FUNCTIONS.keys()) | api_functions | top_functions
        # Common builtins / pandas methods to ignore
        skip = {"print", "len", "sorted", "list", "dict", "set", "range", "enumerate"}

        errors = []
        for i, block in enumerate(blocks, 1):
            calls = _extract_function_calls(block)
            for func_name, _ in calls:
                if func_name in skip:
                    continue
                # Skip attribute calls (method calls on objects)
                if func_name not in known:
                    # Check if it's from a different import in this block
                    imports = _extract_imports(block)
                    imported_names = {
                        n for _, names in imports for n in names
                    }
                    if func_name not in imported_names:
                        continue  # method call like df.to_csv — OK
                    errors.append(
                        f"block {i}: '{func_name}' not found in analysis or "
                        f"API functions"
                    )
        assert not errors, f"{path.name}:\n" + "\n".join(f"  - {e}" for e in errors)


# ---------------------------------------------------------------------------
# Outfacing-doc lint gates: analysis md + analysis function docstrings
# ---------------------------------------------------------------------------

from multiomics_explorer._outfacing_lint import (
    lint_lines as _lint_lines,
    lint_python_docstrings as _lint_py,
)

_ANALYSIS_PKG_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "analysis"
)


def _analysis_md_files() -> list[Path]:
    return sorted(ABOUT_DIR.glob("*.md"))


def _analysis_public_functions() -> list[tuple[str, Path, int, int]]:
    """Top-level public functions and classes across analysis/*.py.

    Returns (name, source_file, start_line, end_line) tuples. Classes
    are included because their docstrings (e.g. ``EnrichmentResult``)
    are also part of the Python-API outfacing surface.
    """
    out = []
    target_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for py_file in sorted(_ANALYSIS_PKG_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        tree = ast.parse(py_file.read_text())
        for node in tree.body:
            if isinstance(node, target_types):
                if not node.name.startswith("_"):
                    out.append((node.name, py_file, node.lineno, node.end_lineno))
    return out


@pytest.mark.parametrize(
    "md_path",
    _analysis_md_files(),
    ids=lambda p: p.stem,
)
def test_analysis_md_lint_clean(md_path: Path):
    violations = _lint_lines([md_path])
    if violations:
        msg_lines = [f"{md_path.name} has outfacing-doc violations:"]
        for path, line_no, line, token in violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))


@pytest.mark.parametrize(
    "spec",
    _analysis_public_functions(),
    ids=lambda spec: f"{spec[1].stem}.{spec[0]}",
)
def test_analysis_function_docstring_lint_clean(spec):
    name, src_file, start, end = spec
    violations = _lint_py([src_file])
    fn_violations = [v for v in violations if start <= v[1] <= end]
    if fn_violations:
        msg_lines = [
            f"{name} ({src_file.name}:{start}-{end}) has outfacing-doc violations:",
        ]
        for path, line_no, line, token in fn_violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))
