# What changed in v3

## v1 → v3

v1 was the initial implementation: monolithic tools returning JSON
strings, no layered architecture, no skills.

| Area | v1 | v3 |
|---|---|---|
| **Architecture** | Single-layer: queries + formatting in tools.py | 3 layers: kg/ (builders) → api/ (dict assembly) → mcp_server/ (Pydantic validation) |
| **Return type** | JSON string (`str`) | Pydantic response models (FastMCP auto-generates `outputSchema`) |
| **Response shape** | Varies per tool — some return lists, some dicts, some formatted text | Uniform: dict with summary fields + `results` list, always |
| **Summary fields** | None — full result set or nothing | Always present: `total_matching`, `returned`, `truncated`, breakdowns |
| **Limit** | Client-side slicing or none | Server-side `ORDER BY ... LIMIT` in Cypher; MCP default=5, api/ default=None |
| **Error handling** | Return error strings | `ToolError` (MCP), `ValueError` (api/), FastMCP auto-converts |
| **Logging** | `logger.info()` to stderr | `await ctx.info/warning/error()` (client-facing) + server-side usage logging |
| **Parameters** | Inconsistent naming, positional | Standard names (`locus_tags`, `experiment_ids`), keyword-only in builders, `Annotated[type, Field(...)]` in MCP |
| **ID params** | Mix of singular and list | Always lists (`locus_tags`, not `locus_tag`) |
| **Batch tools** | Silent skip on missing IDs | `not_found` field lists unmatched input IDs |
| **Verbose** | Not available | `verbose` bool controls per-row detail (compact vs heavy text) |
| **Tool names** | `get_homologs`, `search_genes`, `get_gene_details`, `query_expression`, `get_schema` | `gene_homologs`, `genes_by_function`, retired, `differential_expression_by_gene/ortholog`, `kg_schema` |
| **Tool organization** | Flat list | 3-phase workflow: Orientation → Gene work → Expression |
| **Homology** | Single `get_homologs` tool | Triplet: `search_homolog_groups` → `genes_by_homolog_group` → `gene_homologs` |
| **Expression** | Single `query_expression` (removed) | Two tools: `by_gene` (same-organism) + `by_ortholog` (cross-organism) |
| **About content** | None | Auto-generated from Pydantic models + input YAML, served as MCP resources |
| **Skills** | None | Dev skills (layer-rules, add-tool, testing, code-review) + research skills (tool wrapper, pipeline, inversion) |
| **FastMCP** | Not used (raw `mcp` package) | `fastmcp>=3.0`: `Annotated`, `Field`, `Literal`, `ToolError`, `tags`, `annotations`, Pydantic `outputSchema` |
| **Tests** | Basic integration tests | 4-tier: unit (builders, api, wrappers) + integration + regression (golden files) + about content |
| **Analysis artifacts** | Chat responses only | `analyses/{name}/` with data/, scripts/, results/, README.md, methods.md |
| **KG schema** | EnvironmentalCondition nodes, split expression edges | Experiment nodes, unified `Changes_expression_of` edges, precomputed stats |
| **APOC** | Not used | Used for breakdowns (`frequencies`), dynamic maps, JSON property parsing |

---

## v2 → v3

v2 introduced the layered architecture and was partially
implemented. v3 refines the conventions based on learnings from
building the first tools.

### Response shape

| v2 | v3 |
|---|---|
| `mode: Literal["summary", "detail"]` string param | `summary: bool` (sugar for `limit=0`) |
| Summary mode: `results=[]`, detail mode: results populated | Same — but `summary` is just a convenience; `limit=0` does the same thing |
| Three modes: summary, detail, about | Two params (`summary`, `limit`) + about via MCP resources (not a mode) |
| MCP computes `returned`, `truncated` from api/ result | api/ assembles the **complete** response dict; MCP just does `Response(**data)` |
| api/ returns `list[dict]` or `dict` | api/ always returns `dict` with summary fields + `results` list |

### Parameters

| v2 | v3 |
|---|---|
| `gene_id` (singular) for single-gene tools, `gene_ids` for batch | Always `locus_tags` (list). No singular ID params. |
| `mode` at MCP layer, `summary: bool` at api/ | `summary: bool` at both layers (same params everywhere) |
| MCP default `limit=50` | MCP default `limit=5` (summary fields + a few example rows) |
| No `not_found` field | Batch tools (accept ID lists) include `not_found: list[str]` |
| Mixed: some tools have `verbose`, some don't | Guideline: any tool with secondary columns gets `verbose` |

### Batch tools

| v2 | v3 |
|---|---|
| No explicit batch tool concept | **Any tool accepting an ID list is a batch tool** — supports `limit`, `summary`, summary fields, `not_found` |
| `gene_overview` listed as "always small" | `gene_overview` has rich summary fields (batch input can be large) |

### About content

| v2 | v3 |
|---|---|
| Hand-written markdown with `example-call`, `expected-keys` tagged blocks | Auto-generated from Pydantic models + human-authored input YAML (`inputs/tools/{name}.yaml`) |
| `mode="about"` parameter on tools | MCP resources at `docs://tools/{tool_name}` (not a tool parameter) |
| Tests parse tagged blocks | Tests verify generated content matches Pydantic models |

### Tool names (target)

| v2 name | v3 name | Status |
|---|---|---|
| `get_homologs` | `gene_homologs` | Rename pending |
| `search_genes` | `genes_by_function` | Rename pending |
| `get_gene_details` | retired | `gene_overview` covers it |
| `get_schema` | `kg_schema` | Rename pending |
| `query_expression` (removed in v2) | `differential_expression_by_gene` | To build |
| — | `differential_expression_by_ortholog` | To build (new) |
| — | `search_homolog_groups` | To build (new) |
| — | `genes_by_homolog_group` | To build (new) |

### Tool framework

| v2 | v3 |
|---|---|
| Flat tool list | 3-phase workflow: Orientation → Gene work → Expression |
| Homology: single tool | Homology triplet (mirrors ontology triplet) |
| Expression: placeholder for future rebuild | Two tools with defined output schemas (gene-centric + ortholog-centric) |
| Output schemas not specified | Long-form output schemas defined per tool in `tool_framework.md` |

### Architecture conventions

| v2 | v3 |
|---|---|
| Summary design guidelines in architecture doc | Per-tool summary fields in `tool_framework.md`, design rules in architecture |
| Skill directory trees duplicated in methodology + architecture | Methodology references architecture; single source per topic |
| init-claude output duplicated | Methodology references architecture for details |
| APOC: `apoc.coll.frequencies()` only | Full APOC guidance: `frequencies`, `map.fromPairs`, `convert.fromJsonMap`, `coll.max/min/sort` |
| Precomputed stats on Experiment nodes | Also on OrthologGroup nodes (`expression_experiment_count`, `conservation_pattern`) |

### Analysis artifacts

| v2 | v3 |
|---|---|
| `README.md` — question, method, conclusion | `README.md` (summary + navigation) + `methods.md` (publication-ready methods document with required sections) |

### Skills (dev)

| v2 | v3 |
|---|---|
| Templates use `mode: Literal["summary", "detail"]` | Templates use `summary: bool` |
| MCP template computes `returned`/`truncated` | MCP template does `Response(**data)` — api/ owns all fields |
| API template returns `list[dict]` | API template returns `dict` with complete response |
| No batch tool template | Batch tool template with `not_found` |
| `EXPECTED_TOOLS` has old names | Target names documented with transition notes |
| `limit=50` in MCP templates | `limit=5` in MCP templates |

### Logging

| v2 | v3 |
|---|---|
| `logger.info()` for both client and server | `ctx.info/warning/error` (client-facing) + separate server-side usage logging |
| Usage logging not scoped | Usage logging disabled during tests; storage mechanism TBD |
