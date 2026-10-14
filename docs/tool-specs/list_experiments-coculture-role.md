# Tool spec: list_experiments coculture role surface (+ list_filter_values `partner_role`)

Backlog 2c.6. Contract: `docs/kg-specs/2026-10-13-coculture-partner-list-explorer-asks.md`
(CCP-002 / CCP-004 / CCP-005). Mode B (2 tools named), but `list_filter_values` is a one-entry
registry change; `list_experiments` is the template.

## Purpose

The KG (2026-10-13T13:51Z build) records every organism sharing an experiment's culture:
`Experiment.coculture_partner` is a dense sorted `str[]`, and each partner has one
`Tests_coculture_with` edge carrying `partner_role ∈ {treatment, background}`. The explorer
already matches partner names against the list. This change adds the **role**:

1. `list_experiments(coculture_role=...)`: keep experiments with a partner of that role; with
   `coculture_partner=` the role and the name are tested on **the same partner**.
2. Verbose rows gain `coculture_partners: [{name, role, organism_id, organism_type}]`.
3. Summary envelope gains `by_coculture_role`.
4. `list_filter_values('partner_role')` serves the edge vocabulary.

## Out of Scope

- Role on `differential_expression_by_gene` / `differential_expression_by_ortholog`: they keep
  the flat `coculture_partner` list and route to `list_experiments(experiment_ids=…, verbose=True)`.
- `coculture_role` as a list (only 2 values; `None` already means "any").
- Any KG change. Everything below reads the live dev build.

## Status / Prerequisites

- [x] KG changes landed (13:51Z build; absorbed in `de44d71`)
- [x] Scope reviewed with user (2c.6 scope, 2026-10-14)
- [x] Cypher verified against live KG
- [x] Spec frozen (user approval 2026-10-14; D1 + D2 accepted)

## Use cases

- "Pro experiments cultured with Alteromonas but studying something else":
  `list_experiments(organism="Prochlorococcus", coculture_partner="Alteromonas", coculture_role="background")`.
- "Coculture-vs-axenic contrasts with HOT1A3": `coculture_role="treatment"`. Unlike
  `treatment_type=['coculture']`, this also scopes to the named partner and includes phage
  infection (role `treatment`, `treatment_type=['viral']`).
- Envelope triage: `list_experiments(coculture_partner="Alteromonas", summary=True)` →
  `by_coculture_role` = 5 treatment / 48 background.
- Chain: DE tool row (`coculture_partner` list) → `list_experiments(experiment_ids=[…], verbose=True)`
  → `coculture_partners[].role`.

## KG dependencies

`(e:Experiment)-[r:Tests_coculture_with {partner_role}]->(o:OrganismTaxon)`; `o.preferred_name`,
`o.id`, `o.organism_type`. KG invariant (validity-tested KG-side): `e.coculture_partner ==
sorted(o.preferred_name)` over the edges; no experiment mixes roles; `partner_role` is set on every
edge. `ControlledVocabulary {applies_to: 'Tests_coculture_with', property: 'partner_role'}`
(`applies_to_kind: edge`, values `treatment` / `background`, with `value_descriptions`).

---

## Tool Signature changes

### `list_experiments` — new param

```python
coculture_role: Annotated[Literal["treatment", "background"] | None, Field(
    description="Keep experiments with a coculture partner of this role: 'treatment' "
    "(the partner's presence is the contrast — coculture vs axenic, or phage infection) or "
    "'background' (the culture was a coculture; the contrast is something else). With "
    "coculture_partner=, role and name must hold for the same partner.",
)] = None,
```

Placed right after `coculture_partner`. API: `coculture_role: str | None = None`; raises
`ValueError` on any other value (message lists the two valid values). Threaded through
`build_list_experiments`, `build_list_experiments_summary`, and `_list_experiments_where`.

### `list_experiments` — new verbose field (row)

`coculture_partners: list[CoculturePartner]` (verbose only; `[]` when axenic), sorted by `name`.

```python
class CoculturePartner(BaseModel):
    name: str            # OrganismTaxon.preferred_name (matches the coculture_partner list)
    role: str            # 'treatment' | 'background' (Tests_coculture_with.partner_role)
    organism_id: str     # OrganismTaxon.id, e.g. 'insdc.gcf:GCF_001578515.1', 'ncbitaxon:10239'
    organism_type: str   # 'genome_strain' | 'reference_proteome_match' | 'treatment' —
                         # genome_strain partners have genes in the KG (gene tools work on them)
```

The compact `coculture_partner: list[str]` stays unchanged.

### `list_experiments` — new summary field (envelope)

`by_coculture_role: list[{coculture_role: str, count: int}]` — matching experiments per role (an
experiment counts once per distinct role across its partners; axenic experiments count in none).
Always present (also on `summary=False`, like the other `by_*` rollups); `[]` when no matching
experiment has a partner. Sorted count desc (same `apoc.coll.frequencies` → rename pattern as
`by_background_factors`).

### `list_filter_values` — new `filter_type`

`"partner_role"` added to the `Literal` and to `_MULTI_LABEL_VOCABS`:

```python
"partner_role": ("partner_role", ("Tests_coculture_with",), "edge"),
```

Rows: `value`, `applies_to=['Tests_coculture_with']`, `description`, `source`. Same read-then-pivot
rule as `detection_status` (pivot = distinct `r.partner_role` over the edge type + a warning if the
CV node is missing). Docstring + MCP `filter_type` description mention it.

## Result-size controls

Unchanged (`list_experiments`: summary / verbose / limit / offset; 209 experiments total).

**Sort key:** unchanged — `p.publication_year DESC, e.organism_name, e.name, e.id` (search_text:
`score DESC, …`). The new filter is a WHERE condition, so paging stays unique-keyed.

## Special handling

- **Variable shadowing fix (riders along):** the current partner condition binds the list
  variable `p`, which is also the `Publication` variable in the MATCH. Rename to `cp`:
  `ANY(cp IN e.coculture_partner WHERE toLower(cp) CONTAINS toLower($partner))`. Update the
  query-builder unit assertion accordingly.
- No caching, no multi-query orchestration change, no Lucene change.

---

## Query Builder

**File:** `kg/queries_lib.py`. All Cypher below **verified against live KG** (13:51Z build).

### `_list_experiments_where` — partner / role conditions

```python
if coculture_role:
    params["coculture_role"] = coculture_role
    if coculture_partner:
        conditions.append(
            "EXISTS { (e)-[r:Tests_coculture_with]->(o:OrganismTaxon)"
            " WHERE r.partner_role = $coculture_role"
            " AND toLower(o.preferred_name) CONTAINS toLower($partner) }"
        )
        params["partner"] = coculture_partner
    else:
        conditions.append(
            "EXISTS { (e)-[r:Tests_coculture_with]->(:OrganismTaxon)"
            " WHERE r.partner_role = $coculture_role }"
        )
elif coculture_partner:
    conditions.append(
        "ANY(cp IN e.coculture_partner"
        " WHERE toLower(cp) CONTAINS toLower($partner))"
    )
    params["partner"] = coculture_partner
```

Partner-only keeps the list predicate (no edge traversal); by the KG invariant it equals the edge
form (verified: both 53 for 'alteromonas').

Live counts (209 experiments):

| Filter | Rows |
|---|---|
| `coculture_partner='Alteromonas'` | 53 |
| + `coculture_role='treatment'` | 5 (all `treatment_type=['coculture']`: ismej.2016.70 ×3 + 2025.11.24 MED4 + ismej.2016.82 NATL2A) |
| + `coculture_role='background'` | 48 |
| `coculture_role='treatment'` alone | 44 (36 coculture + 8 phage) |
| `coculture_role='background'` alone | 78 |
| both roles on one experiment | 0 |

### `build_list_experiments` — verbose column

Appended to `verbose_cols`:

```cypher
COLLECT { MATCH (e)-[r:Tests_coculture_with]->(o:OrganismTaxon)
          RETURN {name: o.preferred_name, role: r.partner_role,
                  organism_id: o.id, organism_type: o.organism_type}
          ORDER BY o.preferred_name } AS coculture_partners
```

Verified: Moreno Marinobacter-side → 2 background partners (`Alteromonas (MarRef v6)`
`reference_proteome_match`, `Synechococcus sp. BL107` `genome_strain`); Lindell phage →
`[{Phage, treatment, ncbitaxon:10239, treatment}]`; axenic → `[]`; names equal the
`coculture_partner` list in every case.

### `build_list_experiments_summary` — `by_coculture_role`

Added to `collect_cols` / `return_cols`:

```cypher
apoc.coll.flatten(collect(COLLECT { MATCH (e)-[r:Tests_coculture_with]->(:OrganismTaxon)
                                    RETURN DISTINCT r.partner_role })) AS roles
...
apoc.coll.frequencies(roles) AS by_coculture_role
```

Verified: partner 'Alteromonas' → `total_matching` 53, `by_coculture_role`
`[{treatment: 5}, {background: 48}]` (sums to 53 because no experiment mixes roles; in general the
sum can exceed `total_matching` by the mixed count and be below it by the axenic count — document
in the field description). API renames `item` → `coculture_role`.

**Edge cases (verified / to scenario):** role with a partner that never has that role
(`coculture_partner='Marinobacter', coculture_role='treatment'` → 0 rows, `by_coculture_role []`);
role combined with `treatment_type=['coculture']` + `coculture_role='background'` → 0 rows
(consistent, not an error); unknown role → `ValueError` (API) / validation error (MCP).

---

## Implementation Order (file owners)

| Agent | File | What |
|---|---|---|
| test-updater | `tests/unit/test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py`, `tests/integration/edge_cases/scenarios.py`, `tests/integration/test_mcp_tools.py` | RED tests: role conditions (3 branches) + `cp` rename; verbose `coculture_partners` column; summary `by_coculture_role`; API role validation + rename; wrapper param forwarding + models; `list_filter_values('partner_role')` registry/Literal; list_experiments edge scenarios (role-empty combo); live smoke (5 / 48 split, phage = treatment) |
| query-builder | `kg/queries_lib.py` | `_list_experiments_where` + both builders |
| api-updater | `api/functions.py` | `coculture_role` param + validation; `by_coculture_role` rename; `_MULTI_LABEL_VOCABS['partner_role']`; docstrings |
| tool-wrapper | `mcp_server/tools.py` | `coculture_role` param; `CoculturePartner` model + verbose field on `ExperimentResult`; `by_coculture_role` on the response; `list_filter_values` Literal + description |
| doc-updater | `inputs/tools/list_experiments.yaml`, `list_filter_values.yaml`, `differential_expression_by_gene.yaml`, `differential_expression_by_ortholog.yaml`, `references/guide/conventions.md`, `CLAUDE.md`, `CHANGELOG.md` | see Docs |

## Docs

- `list_experiments.yaml`: replace the example `treatment_type=["coculture"], coculture_partner="Alteromonas"`
  with `coculture_partner="Alteromonas"` + a `coculture_role="background"` example; mistakes:
  (a) the partner list holds treatment **and** background partners — `treatment_type=['coculture']`
  keeps coculture-vs-axenic contrasts only, use `coculture_role` to choose; (b)
  `background_factors` containing both `axenic` and `coculture` marks a pooled design (Barreto
  2022), so a background partner there was in some arms, not all; (c) phage infection is role
  `treatment` with `treatment_type=['viral']`. `verbose_fields` += `coculture_partners`. Chaining:
  DE row → `list_experiments(experiment_ids, verbose=True)` for roles.
- `list_filter_values.yaml`: `partner_role` in the filter_type list.
- DE YAMLs: `coculture_partner` is a list of all culture partners; roles via `list_experiments`.
- `conventions.md` "Organism naming": one sentence on `coculture_role=` (file is at its 28k
  budget — trim to fit, don't raise the budget).
- `CLAUDE.md` `list_experiments` row: mention `coculture_role=` (and `list_filter_values` row:
  `partner_role`).
- `CHANGELOG.md` `[Unreleased]` → Added.
- Regenerate: `uv run python scripts/build_about_content.py`; `refresh_examples.py --write
  list_experiments list_filter_values` for new examples.

## Decisions for the gate

- **D1 — `organism_type` in `coculture_partners`** (beyond the contract's `{name, role,
  organism_id}`). Recommended: it tells the caller whether the partner has genes in the KG
  (`genome_strain`) and so whether gene tools can follow, which `organism_id` alone doesn't.
- **D2 — `by_coculture_role` summary rollup** (not in the original 2c.6 list). Recommended: it is
  one extra collect in the existing summary query and answers "how many of these are
  coculture-vs-axenic contrasts" without a second call.
