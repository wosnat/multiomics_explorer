# LLM-review 2b.4 — discovery layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the docs surface discoverable and cheap to enter: a generated `docs://index` with sizes, brief tool pages at `docs://tools/{name}` with the full pages behind `/full`, conventions/start_here trimmed to canonical homes, a new `docs://analysis/expression` page, and scenario TOCs on the example scripts.

**Architecture:** Two mechanical generator/registration tasks (brief/full emission in `scripts/build_about_content.py`; `mcp_server/server.py` registration + a generated index + new instructions), then three hand-authored content moves (conventions → analysis pages; start_here recipes; python_api → analysis/expression), then examples TOC + wrap-up. Nothing is deleted — content moves; every move leaves a pointer.

**Tech Stack:** Python 3.12, FastMCP 3.1 (FunctionResource), pytest (`tests/unit/`, no Neo4j needed anywhere in this plan), `scripts/build_about_content.py`.

**Spec:** `docs/superpowers/specs/2026-08-31-llm-review-2b4-discovery-layer-design.md` (D1–D7).

## Global Constraints

- Branch `llm-review-2b4` off `main` in a worktree (`git reset --hard main` right after entering); never merge, never push.
- No tool, parameter, envelope key or row field changes of any kind. `mcp_server/tools.py` and `api/` are untouched.
- Nothing deleted: every section that leaves a page lands verbatim on its destination page in the same commit, then may be tightened in place; the source keeps a one-paragraph pointer.
- Outfacing text: no dates, no changelog words ("now", "previously", "renamed", "was", "deprecated") — existing lints enforce; CHANGELOG and backlog exempt.
- Full pages must be byte-identical to today's `docs://tools/{name}` output (only their path/URI changes).
- Token budgets (1 tok = 4 chars): each brief page ≤ 2,000 tok (8,000 chars); `docs://index` ≤ 800 tok; conventions ≤ 5,000 tok; start_here ≤ 4,000 tok — all lint- or test-enforced.
- Every task ends with `uv run python scripts/build_about_content.py && uv run python scripts/build_about_content.py --lint` clean and `uv run pytest tests/unit -q -p no:cacheprovider` green; regenerated md committed with the task.
- Commit per task with trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Brief/full emission in the generator

**Files:**
- Modify: `scripts/build_about_content.py` — `render_about` (`:246`, becomes the FULL renderer, unchanged output), new `render_brief`, `build_tool` (`:645`), the `--lint` path list (`:1330-1345`), new `lint_brief_size`
- Test: `tests/unit/test_about_content.py`

**Interfaces:**
- Produces: `render_brief(tool_name: str, schema: dict, input_data: dict | None) -> str`; `FULL_OUTPUT_DIR = OUTPUT_DIR / "full"`; `build_tool` writes brief to `OUTPUT_DIR/{name}.md` AND full to `FULL_OUTPUT_DIR/{name}.md`; `BRIEF_MAX_CHARS = 8000`; `lint_brief_size(paths) -> list[str]`. Task 2 registers `FULL_OUTPUT_DIR` and indexes both.

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_about_content.py`, reusing its existing schema/input helpers — read the top of the file for their names):

```python
BRIEF_SECTIONS = ["## What it does", "## Parameters", "## Example", "## Response sketch", "## Common mistakes"]


def test_brief_page_structure_and_pointer():
    schemas = _get_schemas()
    name = "resolve_gene"
    input_data = yaml.safe_load((INPUTS_DIR / f"{name}.yaml").read_text())
    brief = render_brief(name, schemas[name], input_data)
    for section in BRIEF_SECTIONS:
        assert section in brief, section
    assert f"docs://tools/{name}/full" in brief
    assert len(brief) <= 8000


def test_full_render_unchanged():
    """The full page is exactly what render_about produced before the split."""
    schemas = _get_schemas()
    name = "resolve_gene"
    input_data = yaml.safe_load((INPUTS_DIR / f"{name}.yaml").read_text())
    assert render_about(name, schemas[name], input_data) == (
        FULL_OUTPUT_DIR / f"{name}.md").read_text()


def test_every_tool_has_brief_and_full():
    briefs = {p.stem for p in ABOUT_DIR.glob("*.md")}
    fulls = {p.stem for p in (ABOUT_DIR / "full").glob("*.md")}
    assert briefs == fulls
    assert len(briefs) == 42
```

(Adjust `_get_schemas` / `INPUTS_DIR` / `ABOUT_DIR` to the module's real helper and constant names — do not invent parallel ones.)

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_about_content.py -q -p no:cacheprovider -k "brief or full_render or brief_and_full"` → FAIL (no `render_brief`, no `full/` dir).

- [ ] **Step 3: Implement `render_brief`.** In `scripts/build_about_content.py`, after `render_about`:

```python
def render_brief(tool_name: str, schema: dict, input_data: dict | None) -> str:
    """Brief page: what/params/one example/response sketch/top mistakes/chaining + /full pointer."""
    lines = [f"# {tool_name}", ""]
    lines += ["## What it does", "", schema["description"], ""]

    # Parameters + Discovery hints: reuse render_about's logic by extracting it
    # into a helper `_params_section(schema) -> list[str]` used by both renderers
    # (move the existing block from render_about verbatim; do not duplicate it).
    lines += _params_section(schema)

    examples = (input_data or {}).get("examples") or []
    if examples:
        ex = examples[0]
        lines += ["## Example", "", f"### {ex['title']}", "", "```python", ex["call"].strip(), "```", ""]

    # Response sketch: envelope keys + row field names, no descriptions.
    envelope, result_fields = extract_response_fields(schema)
    lines += ["## Response sketch", "", "```expected-keys"]
    always = [f["name"] for f in envelope if f["name"] not in CONDITIONAL_ENVELOPE_KEYS]
    lines.append(", ".join(always) + (", results" if result_fields else ""))
    if result_fields:
        row = [f["name"] for f in result_fields][:12]
        more = "" if len(result_fields) <= 12 else ", …"
        lines.append(f"result row: {', '.join(row)}{more}")
    lines += ["```", ""]

    mistakes = ((input_data or {}).get("mistakes") or [])[:3]
    if mistakes:
        lines += ["## Common mistakes", ""]
        lines += [f"- {m}" for m in mistakes] + [""]

    chaining = (input_data or {}).get("chaining") or []
    if chaining:
        lines += ["## Chaining patterns", ""]
        lines += [f"- {c}" for c in chaining] + [""]

    lines += [f"Full reference (all examples, full response format, verbose fields): `docs://tools/{tool_name}/full`", ""]
    return "\n".join(lines)
```

Check the real YAML shapes first (`mistakes` / `chaining` entries may be dicts with `title`/`text` — open `inputs/tools/resolve_gene.yaml` and render them the way `render_about` does, reusing its formatting helpers). If a brief page exceeds `BRIEF_MAX_CHARS`, drop the chaining section first, then mistakes beyond the first — deterministically, inside `render_brief`.

- [ ] **Step 4: Wire `build_tool`.** Add `FULL_OUTPUT_DIR = OUTPUT_DIR / "full"` next to `OUTPUT_DIR`; in `build_tool` write `render_about(...)` to `FULL_OUTPUT_DIR / f"{tool_name}.md"` and `render_brief(...)` to `OUTPUT_DIR / f"{tool_name}.md"` (mkdir parents for both).

- [ ] **Step 5: Lints.** `lint_brief_size(paths)` returns `"{name}: brief {n} chars > 8000"` per violation; in `main()`'s `--lint` block add `FULL_OUTPUT_DIR` globs to `paths` and run `lint_brief_size(sorted(OUTPUT_DIR.glob('*.md')))` alongside the other lints. Also update the tool-scoped lint path resolution (`:1315-1320`) to include the tool's full page.

- [ ] **Step 6: Rebuild + run.** `uv run python scripts/build_about_content.py` (writes 42 briefs + 42 fulls); the three tests → PASS; `uv run pytest tests/unit -q -p no:cacheprovider` → green (some existing tests read `ABOUT_DIR/*.md` expecting full content — update them to read from `full/` where they assert example blocks; list every such change in the commit body); `--lint` clean.

- [ ] **Step 7: Commit** (`git add scripts/build_about_content.py tests/unit/test_about_content.py multiomics_explorer/skills`):

```bash
git commit -m "feat(docs): brief tool pages by default; full pages under tools/full/ (llm-review 2b.4 D2)"
```

---

### Task 2: `docs://index`, registration, instructions

**Files:**
- Modify: `scripts/build_about_content.py` — new `render_docs_index`, called at the end of a default build
- Modify: `multiomics_explorer/mcp_server/server.py:66-160` — instructions text, `_DOC_DIRS`, registration order, `/full` and index registration
- Test: `tests/unit/test_mcp_server.py`, `tests/unit/test_docs_lint.py`

**Interfaces:**
- Consumes: `FULL_OUTPUT_DIR` from Task 1.
- Produces: `references/index.md` (generated); resources `docs://index`, `docs://tools/{name}/full`; new server `instructions` string. `render_docs_index() -> str` and `lint_index_fresh() -> list[str]` in the generator.

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_mcp_server.py`, following its existing async resource-listing pattern at `:150-200`):

```python
def test_docs_index_registered_and_fresh():
    uris = _all_resource_uris()          # reuse/extract the module's existing listing helper
    assert "docs://index" in uris
    index_text = (_SKILLS_DIR / "index.md").read_text()
    for uri in uris:
        if uri.startswith("docs://") and uri != "docs://index":
            assert uri in index_text, f"{uri} missing from docs://index"


def test_full_tool_pages_registered():
    uris = _all_resource_uris()
    briefs = [u for u in uris if u.startswith("docs://tools/") and not u.endswith("/full")]
    fulls = [u for u in uris if u.startswith("docs://tools/") and u.endswith("/full")]
    assert len(briefs) == len(fulls) == 42


def test_resource_order_guides_first():
    # _all_resource_uris() must return uris in registration order (extract it
    # from the module's existing async listing pattern as an ordered list; the
    # other new tests may treat it as a set).
    uris = [u for u in _all_resource_uris() if u.startswith("docs://")]
    assert uris[0] == "docs://index"
    assert uris.index("docs://guide/start_here") < uris.index("docs://tools/resolve_gene")


def test_instructions_mention_index_and_summary_habit():
    from multiomics_explorer.mcp_server.server import mcp
    assert "docs://index" in mcp.instructions
    assert "summary=True" in mcp.instructions
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: `render_docs_index`.** In the generator:

```python
def render_docs_index() -> str:
    """One row per docs:// resource: URI, ~size in tokens, one-line read-when."""
    lines = ["# docs://index — every page, its size, when to read it", ""]
    refs = OUTPUT_DIR.parent          # .../references
    sections = [
        ("Guides", "docs://guide", sorted((refs / "guide").glob("*.md"))),
        ("Tools (brief; append /full for the complete page)", "docs://tools", sorted(OUTPUT_DIR.glob("*.md"))),
        ("Tool full pages", "docs://tools", sorted(FULL_OUTPUT_DIR.glob("*.md"))),
        ("Analysis", "docs://analysis", sorted((refs / "analysis").glob("*.md"))),
        ("Ontologies", "docs://ontologies", sorted((refs / "ontologies").glob("*.md"))),
    ]
    for title, prefix, files in sections:
        lines += [f"## {title}", ""]
        for f in files:
            tok = len(f.read_bytes()) // 4
            uri = f"{prefix}/{f.stem}/full" if f.parent.name == "full" else f"{prefix}/{f.stem}"
            lines.append(f"- `{uri}` — ~{tok} tok — {_read_when(f)}")
        lines.append("")
    lines += ["## Examples", ""]
    for f in sorted((refs.parent.parent.parent / "examples").glob("*.py")):
        tok = len(f.read_bytes()) // 4
        lines.append(f"- `docs://examples/{f.name}` — ~{tok} tok — {_read_when(f)}")
    return "\n".join(lines) + "\n"


def _read_when(path: Path) -> str:
    """First sentence of the page's first prose paragraph, ≤110 chars (reuse _summary_sentence)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip().lstrip("# ").strip()
        if s and not s.startswith(("|", "-", "`", "<", "\"\"\"", "#!", "import")):
            return _summary_sentence(s)
    return path.stem
```

Full-page rows may summarize as "all worked examples + full response format for {stem}" instead of reading the file — hardcode that template in the full-pages section. Write the file at the end of every default (`--all`/no-args) build: `(refs / "index.md").write_text(render_docs_index(), ...)`. Add `lint_index_fresh()`: re-render and compare to the file on disk; a mismatch is a lint failure ("index stale — rerun build"). Enforce ≤ 3,200 chars (800 tok) — if over, shorten `_read_when` output, never drop rows.

- [ ] **Step 4: Registration.** In `server.py`: register `docs://index` FIRST (a `FunctionResource` reading `references/index.md`, description "Directory of every docs:// page with size and read-when"); reorder `_DOC_DIRS` to guide → tools → analysis → ontologies; after the brief-tools loop add:

```python
_FULL_DIR = _SKILLS_DIR / "tools" / "full"
for md_file in sorted(_FULL_DIR.glob("*.md")):
    mcp.add_resource(FunctionResource.from_function(
        fn=_make_reader(md_file),
        uri=f"docs://tools/{md_file.stem}/full",
        name=f"{md_file.stem}_full",
        description=f"Full reference for the {md_file.stem} tool (all examples, full response format)",
        mime_type="text/plain",
    ))
```

(hoist `_make_reader` out of the loop so both loops share it).

- [ ] **Step 5: Instructions.** Replace the `instructions=` string with (~120 words):

```
Multi-omics knowledge graph for Prochlorococcus and Alteromonas (42 read-only tools).

First call: kg_release_info — KG identity + compatibility verdict.
Directory: docs://index — every docs:// page with its ~token size and when to read it. Start with docs://guide/start_here (~4k tok) to pick a tool.

Habits: summary=True first on list/discovery tools (cheap envelope, no rows); docs://tools/{tool} is a ~1k-tok brief — append /full only when you need every worked example; docs://guide/conventions (~5k) for cross-tool semantics; docs://analysis/{enrichment,metabolites,annotation_evidence,expression,derived_metrics} for methodology.
```

- [ ] **Step 6: Rebuild, run all tests, lint.** Full unit suite green; `--lint` clean.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_about_content.py multiomics_explorer/mcp_server/server.py tests/unit/test_mcp_server.py multiomics_explorer/skills
git commit -m "feat(mcp): docs://index + /full registration + size-aware instructions (llm-review 2b.4 D1/D5)"
```

---

### Task 3: conventions diet (chemistry + trust sections move to their canonical homes)

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/guide/conventions.md` (hand-authored)
- Modify: `references/analysis/metabolites.md`, `references/analysis/annotation_evidence.md` (hand-authored)
- Test: `tests/unit/test_guide_about_content.py`

**Interfaces:** none new; Task 2's index regen picks up new sizes.

- [ ] **Step 1: Failing test** (append to `tests/unit/test_guide_about_content.py`):

```python
def test_conventions_within_budget_and_pointers_present():
    text = (GUIDE_DIR / "conventions.md").read_text()
    assert len(text) <= 20000, f"conventions.md {len(text)} chars > 20k (~5k tok)"
    for moved, home in [
        ("Transport trust ladder", "docs://analysis/metabolites"),
        ("Metabolite ID forms", "docs://analysis/metabolites"),
        ("Annotation-trust surface", "docs://analysis/annotation_evidence"),
    ]:
        assert home in text, f"pointer to {home} missing"
        assert f"## {moved}" not in text, f"section '{moved}' should have moved to {home}"
```

- [ ] **Step 2: Run** → FAIL (file is ~47k chars).

- [ ] **Step 3: Move.** Cut these `##` sections from `conventions.md` and append them verbatim (as `##` sections, adjusting only the heading level to fit the destination's structure) to their homes: `Transport trust ladder (chemistry)`, `Direction-agnosticism in chemistry`, `Metabolite ID forms (chemistry + metabolomics tools)` → `analysis/metabolites.md`; `Annotation-trust surface (ontology tools)` → `analysis/annotation_evidence.md` (merge with its existing coverage — where the destination already states a fact, keep the destination's wording and drop the duplicate, listing every dropped-as-duplicate paragraph in the commit body). In `conventions.md`, each removed section becomes one paragraph: what the topic is + `see docs://analysis/…`. Then tighten the remaining conventions sections only where sentences duplicate the moved material. If still > 20k chars, trim the two largest remaining sections (`Response shape`, `Filter semantics`) by moving their worked examples into the pointer style — never delete a rule.

- [ ] **Step 4: Run tests** (the moved text may trip existing lints in its new home — fix forward, e.g. heading levels); rebuild docs (regenerates `index.md` sizes); full unit suite; `--lint` clean.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills tests/unit/test_guide_about_content.py
git commit -m "docs(guide): conventions diet — chemistry + trust sections live on their analysis pages (llm-review 2b.4 D3, absorbs 3.15)"
```

---

### Task 4: start_here recipes + trim

**Files:**
- Modify: `references/guide/start_here.md` (hand-authored)
- Test: `tests/unit/test_guide_about_content.py`

- [ ] **Step 1: Failing test:**

```python
def test_start_here_budget_and_recipes():
    text = (GUIDE_DIR / "start_here.md").read_text()
    assert len(text) <= 16000, f"start_here.md {len(text)} chars > 16k (~4k tok)"
    assert "cross-feeding" in text.lower()
    assert "ontology_landscape" in text
```

- [ ] **Step 2: Run** → FAIL (missing recipes; ~21k chars).

- [ ] **Step 3: Edit.** Keep `## The ten tool families` and `## Decision tree` (reconcile each route with the tools' five-slot descriptions — the sibling named in a tool's "not for … use X" line must match the tree's answer; fix the tree where they disagree and note each fix in the commit body). Add two decision-tree entries with 2–3-step recipes: **cross-feeding** ("which metabolites does organism A make that organism B can take up?" → `list_metabolites(organism_names=[A])` per-row `transporter_gene_count` → `genes_by_metabolite(organism=B)` → compare; cite `docs://analysis/metabolites`) and **DE by functional class** ("are transporters as a class responding?" → `genes_by_ontology(ontology='tcdb', level=0)` TERM2GENE → `differential_expression_by_gene(locus_tags=…)` or `pathway_enrichment(ontology='tcdb')`). Add a **step 0 for enrichment** line at the top of the enrichment branch: "run `ontology_landscape` first to pick ontology × level". Trim `## Two-step pattern` and `## Where to go next` to pointer paragraphs (`docs://index` now carries the directory).

- [ ] **Step 4: Run** tests, rebuild (index sizes), full suite, `--lint`.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills tests/unit/test_guide_about_content.py
git commit -m "docs(guide): start_here recipes (cross-feeding, DE-by-class, enrichment step 0) + trim (llm-review 2b.4 D4)"
```

---

### Task 5: `docs://analysis/expression` + python_api trim

**Files:**
- Create: `references/analysis/expression.md` (hand-authored)
- Modify: `references/guide/python_api.md` (lines ~81, 156, 202-360 — the `response_matrix` / `gene_set_compare` material)
- Modify: `multiomics_explorer/mcp_server/server.py` — none (instructions from Task 2 already name `expression`)
- Test: `tests/unit/test_guide_about_content.py`

- [ ] **Step 1: Failing test:**

```python
def test_expression_analysis_page():
    text = (ANALYSIS_DIR / "expression.md").read_text()   # FileNotFoundError = RED
    for term in ("response_matrix", "gene_set_compare", "differential_expression_by_gene",
                 "table_scope", "docs://guide/python_api"):
        assert term in text
    api = (GUIDE_DIR / "python_api.md").read_text()
    assert "## Cross-experiment summarization" not in api
    assert "docs://analysis/expression" in api
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Write the page.** `expression.md` structure (hand-authored, mirroring `analysis/derived_metrics.md`'s voice): intro (the three DE tools + when each), the moved `## Cross-experiment summarization (response_matrix + gene_set_compare)` section verbatim from `python_api.md:202-…` (find its end with the next `## ` heading), the `pandas.DataFrame` return-shape subsection from `:156`, a short "reading `table_scope` before interpreting missing rows" paragraph (source: the `differential_expression_by_gene` YAML mistakes bullet — restate, don't move). In `python_api.md` leave: the utilities' names in the import-topology list (`:81`) plus one pointer paragraph. Update the CLAUDE.md line listing analysis docs only if it enumerates them (check; the tool table does not change).

- [ ] **Step 4: Run** tests, rebuild, full suite, `--lint` (new file joins the analysis glob automatically).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills tests/unit/test_guide_about_content.py
git commit -m "docs(analysis): expression page — DE tools + response_matrix/gene_set_compare (llm-review 2b.4 D6, absorbs 3.14)"
```

---

### Task 6: examples TOC, backlog, CHANGELOG, wrap-up

**Files:**
- Modify: `examples/pathway_enrichment.py`, `examples/metabolites.py`, `examples/ontology_terms.py`, `examples/annotation_evidence.py` (TOC comment block after the module docstring)
- Modify: `docs/backlog.md` (delete rows 2b.4, 3.14, 3.15), `CHANGELOG.md` (`### Added`/`### Changed` under `[Unreleased]`)
- Test: `tests/unit/test_examples_about_content.py`

- [ ] **Step 1: Failing test:**

```python
def test_examples_have_scenario_toc():
    for name in ("pathway_enrichment", "metabolites", "ontology_terms", "annotation_evidence"):
        text = (EXAMPLES_DIR / f"{name}.py").read_text()
        assert "# CONTENTS" in text[:2000], name
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: TOCs.** In each script, after the module docstring add a `# CONTENTS` comment block: one line per scenario/section (`#   3. Tier-2 substrate profile — genes_by_metabolite … (line ~120)`), derived from the script's real section markers (grep each file for its `SCENARIO`/`# ---` markers). No line numbers if the file lacks stable markers — name the scenario functions instead.

- [ ] **Step 4: Backlog + CHANGELOG.** Delete rows 2b.4 (from §1), 3.14, 3.15 (from §3). CHANGELOG `[Unreleased]` — `### Added`: `docs://index`, `docs://tools/{name}/full`, `docs://analysis/expression`, example TOCs; `### Changed`: brief tool pages by default, conventions/start_here diets, size-aware server instructions.

- [ ] **Step 5: Final verification.** Full unit suite green; `--lint` clean; rebuild and re-run `test_docs_index_registered_and_fresh`; manual read of `references/index.md` + the briefs for `genes_by_ontology`, `resolve_gene`, `metabolites_by_quantifies_assay` (spot-check the three sketches against their Pydantic models); `git diff --stat main` touches only `scripts/`, `mcp_server/server.py`, `skills/`, `examples/`, tests, backlog, CHANGELOG.

- [ ] **Step 6: Commit**

```bash
git add examples docs/backlog.md CHANGELOG.md tests/unit/test_examples_about_content.py multiomics_explorer/skills
git commit -m "docs: example scenario TOCs; close backlog 2b.4/3.14/3.15 (llm-review 2b.4 D7)"
```

Then hand off via `superpowers:finishing-a-development-branch` (merge to `main` locally; no push). The live `/mcp` check (index resource visible, brief page served, `/full` reachable) rides the same post-restart pass as 2b.5.
