# LLM-review 2b.5 — schema diet — design

Backlog 2b.5 (pre-cut, decided 2026-08-30). Shrinks what an MCP client pays for on
`tools/list` and what the model reads per session, and aligns parameter names to the
house style, without changing any response shape. Zero golden diff expected.

Measured on `main` 2026-08-30 (42 tools): descriptions ≈ 9.9k tok (74–517 per tool);
`tools/list` 523 KB, of which `outputSchema` 355 KB; 27 `organism` params carry 25
distinct description texts (66–314 chars).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | `output_schema=None` on all 42 tools. | The Anthropic tool definition has only `name` / `description` / `input_schema`; the host never passes `outputSchema` to the model, and nothing in the stack validates against it. POC: 523 → 168 KB, `structuredContent` still returned on every call. |
| D2 | Every tool description follows the five-slot template, ≤ 600 chars (≈150 tok), lint-enforced. | The "Returns" slot is the only response-shape text the model ever sees. |
| D3 | Shared `Annotated` param types in `mcp_server/params.py`. | One text per shared concept instead of 12–25 drifted variants. Tool-specific caveats move to description slot 3 or a YAML `mistakes` bullet. |
| D4 | Parameter names aligned to the house style (rules R1–R4 below). MCP schemas show canonical names only; the Python API accepts the old keyword for one release with a `DeprecationWarning`. | The model reads the live schema, so aliases in the schema would only re-inflate it. Scripts need the grace period. |
| D5 | `has_p_value` surface unchanged. | Decided 2026-08-30 — ROI too small pre-cut. |
| D6 | Naming rules + template go to `.claude/skills/layer-rules` (Layer 3) and `references/layer-boundaries.md`, enforced by a unit test. Not to `docs://guide/conventions`. | Authoring rules, not consumer-facing; don't inflate outfacing docs. |

Out of scope: tool merges (2b.6); `treatment_type` / `background_factors` filters on the
DE tools (query change — own S item, still pre-cut); envelope or row changes.

## Naming rules (R1–R4, from the 2026-08-30 inventory)

- **R1 ranges are `min_x` / `max_x`** (17 params today). Outliers to rename:
  `value_min/max` → `min_value/max_value`, `metric_percentile_min/max` →
  `min_percentile/max_percentile`, `rank_by_metric_max` → `max_rank`
  (`metabolites_by_quantifies_assay`); `mass_min/max` → `min_mass/max_mass` (`list_metabolites`).
- **R2 vocabulary filters use the KG property name, typed `list[str]`**: `treatment_type`,
  `background_factors`, `growth_phases`, `omics_type`, `compartment`. Fix: `list_publications`
  (`treatment_type`, `background_factors`, `growth_phases` are `str`), `omics_type` `str` on
  `list_clustering_analyses` / `list_derived_metrics`, `gene_response_profile.treatment_types`.
- **R3 ID batches are plural** (`locus_tags`, `experiment_ids`, `metabolite_ids`, …). Fix:
  `publication_doi` → `publication_dois` on 11 tools.
- **R4 a filter is named after the row field it filters.** Fix: `genes_by_numeric_metric.bucket`
  → `metric_bucket`; `genes_by_boolean_metric.flag` → `flag_value`;
  `genes_by_function.category: str` → `gene_categories: list[str]`.
- Also: `ontology` typed from one shared `Literal` — `enum` on single-ontology tools,
  `list[enum] | enum` on multi (`search_ontology` currently untyped, `list_filter_values` bare
  `str`); `direction` accepts `both` on all three tools (`differential_expression_by_ortholog`
  lacks it); defaults unchanged.
- Legitimate pairs kept: `organism` / `organisms` (single vs cross-organism), `source` /
  `sources` (homolog DB vs trust ladder), `analysis_id` / `analysis_ids` (required one vs
  filter), `categories` on `genes_by_categorical_metric` (DM categories).

## Description template (D2)

1. **Does** — one line, input → output.
2. **Use when / not when** — names the sibling tool to route to instead.
3. **Key filters** — parameter names only; semantics live in the param descriptions.
4. **Returns** — envelope keys + what one row is.
5. **Pointer** — `docs://tools/{name}`; the `summary=True` habit where the tool has it.

Content that no longer fits goes to the tool YAML (`mistakes` / `chaining`) if not
already there. Lint: `build_about_content.py --lint` fails on > 600 chars; a unit test
pins the same bound.

## Shared param types (D3)

`OrganismParam`, `LimitParam`, `OffsetParam`, `SummaryParam`, `VerboseParam`,
`TreatmentTypeParam`, `BackgroundFactorsParam`, `GrowthPhasesParam`, `OmicsTypeParam`,
`CompartmentParam`, `PublicationDoisParam`, `MetaboliteIdsParam` (coercion note once),
`InformativeOnlyParam`, the five trust filters (`SourcesParam`, `EvidenceParam`,
`MaxTierParam`, `MinEvidenceScoreParam`, `CallClassParam`), `OntologyLiteral`. A tool
that genuinely differs (e.g. `limit` default) overrides the default only, not the text.

## Alias mechanism (D4)

`api/functions.py`: the old keyword stays in the signature as a deprecated parameter;
one helper `_deprecated_alias(old, new, old_name, new_name)` merges it (warns
`DeprecationWarning`; both given → `ValueError`; `str` given where `list[str]` is
declared → wrapped as a one-element list, which also resolves backlog 3.18's
bare-string trap for these params). Removal slated for alpha.6. MCP wrappers pass
canonical names only. CHANGELOG `Breaking` lists every rename; it feeds the KG-side A1
`breaking_changes` stamp.

## Generator and outputSchema (D1)

`register_tools` decorates through `partial(mcp.tool, output_schema=None)`.
`scripts/build_about_content.py::get_tool_schemas` builds `output_schema` from the
function's return-annotation model (`model_json_schema()`), so the generated response
sections are byte-identical. Layer-rules Layer 3 text "FastMCP auto-generates
`outputSchema`" is replaced by the new policy.

## Verification

- Unit: naming-rule test over `tools/list` (R1–R4 + `ontology` typing); description-length
  test; `outputSchema is None` for all tools; alias tests (warn / conflict / str→list).
- `-m kg` after renaming params in `tests/integration`, `cases.yaml`, and the research
  repo's evals / examples (grep both repos for every old name).
- Regression `--force-regen`: expected zero diff on goldens.
- Docs regenerated, `--lint` clean; `refresh_examples.py` where an example used a renamed
  param; `/mcp` restart + one live call of a renamed tool through the MCP client.

Branch `llm-review-2b5`; one commit per section (D1, D3, D4 renames, D2 descriptions,
D6 rules + tests).
