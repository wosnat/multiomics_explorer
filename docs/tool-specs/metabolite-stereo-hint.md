# Tool spec: metabolite stereo-form hint (backlog 2c.8 part 3)

Mode B (cross-tool change): `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`.

## Purpose

The KG keeps a stereo-unspecified metabolite ("Cysteine" `C00736`) and its stereo-specified
forms (L-Cysteine `C00097`, D-Cysteine `C00793`) as separate nodes. It links them by
`Metabolite_is_stereo_form_of` (specific → unspecified, directed, 76 edges) and
`Metabolite_is_enantiomer_of` (symmetric, 28). **No count rolls up across either edge.**

The two evidence sources reach different nodes:
- **TCDB substrate lists name compounds generically.** Transport sits on the unspecified
  node: Cysteine has 3,197 transporter genes and 0 catalysts.
- **KEGG reactions name the specific form.** Catalysis sits there: L-Cysteine has 652
  catalysts.
- **Measured compounds with an unqualified paper name** are placed on the most-catalysed
  form (`stereo_assignment = dominant_form_assumed`). So their transport mostly sits on the
  generic node: L-Ala has 395 transporter genes, Ala `C01401` has 2,655.

A transport ↔ catalysis join that stays on one node silently misses the other half. This
change makes the generic ↔ specific hop visible, and lets `genes_by_metabolite` cross it on
request.

## Out of scope

- **Enantiomer (L ↔ D) hints and expansion.** They are different compounds with different
  enzymes (peptidoglycan D-Ala, racemases). Enantiomers are listed only as labelled facts in
  `list_metabolites`. On live data, every hint that would come only through an enantiomer
  edge (10 of 78) points a D-amino acid at its L-form. This deliberately narrows the
  KG-dialog work list (§27: enantiomers + 2-hop siblings). The 2-hop sibling path
  (D-Ala → Ala → L-Ala) is out for the same reason.
- **Assay tools:** `stereo_assignment` already marks assumed forms there. The KG dialog
  (§14) agreed they don't get the hint.
- **Genome context for transport substrates** ("which of this ABC transporter's substrates
  are plausible in this genome"): backlog 2c.9, a bigger change.
- **Missing stereo edges** (mannose, isoleucine, glucose, …): KG ask 8 in
  `docs/kg-specs/2026-10-15-metabolite-stereo-merge-asks.md`. This change works off
  whatever edges exist.
- `include_stereo_forms` on `list_metabolites` (search already returns all forms by name;
  per-row `stereo_relatives` carries the counts) or on `metabolites_by_gene` (the gene isn't
  linked to the relative, so there is nothing to add).

## Status / Prerequisites

- [x] KG D1 landed (2026-10-15 rebuilds, absorbed)
- [x] Scope reviewed with user (2026-10-16)
- [x] Cypher verified against live KG (Neo4j 5.15)
- [ ] Spec frozen

## KG dependencies

- `(:Metabolite)-[:Metabolite_is_stereo_form_of]->(:Metabolite)`, start = stereo-specified
  form, end = unspecified / broader form.
- `(:Metabolite)-[:Metabolite_is_enantiomer_of]-(:Metabolite)` (`list_metabolites` only),
  query undirected.
- `Metabolite.catalyst_gene_count`, `.transporter_gene_count` (KG-wide, precomputed).
- Live sizing: 157 metabolites have ≥ 1 relative, at most 3 relatives each.

## Shared vocabulary

`relation` is what the relative is to the metabolite it is attached to:

| Edge | `relation` |
|---|---|
| `(m)-[:Metabolite_is_stereo_form_of]->(o)` | `unspecified_form` |
| `(o)-[:Metabolite_is_stereo_form_of]->(m)` | `specific_form` |
| `(m)-[:Metabolite_is_enantiomer_of]-(o)` | `enantiomer` (`list_metabolites` only) |

Relatives are sorted by `relation`, then by `metabolite_id`. A generic node's `specific_form`
relatives can include a D-form (Ala → L-Ala **and** D-Ala). They are named, never filtered:
the agent picks.

**Organism-scoped relative entry** (`StereoRelative`, used by `genes_by_metabolite` and
`metabolites_by_gene`):

| Field | Type | Meaning |
|---|---|---|
| `metabolite_id` | str | Relative's id; pass it to `genes_by_metabolite(metabolite_ids=…)` |
| `name` | str | |
| `relation` | str | `specific_form` / `unspecified_form` |
| `reaction_count` | int | Distinct reactions with genes in this organism, under the call's filters |
| `transporter_count` | int | Distinct TCDB families, same scope |
| `gene_count` | int | Distinct genes across both arms, same scope |

The three counts are exactly the relative's `by_metabolite` entry from
`genes_by_metabolite(metabolite_ids=[relative], organism=…)` with the same filters. Only
relatives with `gene_count > 0` are listed.

---

## Shared pieces

### Query builder: `build_metabolite_stereo_relatives`

```python
def build_metabolite_stereo_relatives(
    *, metabolite_ids: list[str], exclude_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """RETURN keys: metabolite_id, relative_id, relative_name, relation.
    1-hop over Metabolite_is_stereo_form_of only (both directions)."""
```

Verified against live KG:

```cypher
UNWIND $metabolite_ids AS mid
MATCH (m:Metabolite {id: mid})-[r:Metabolite_is_stereo_form_of]-(o:Metabolite)
WHERE NOT o.id IN $exclude_ids
RETURN m.id AS metabolite_id, o.id AS relative_id, o.name AS relative_name,
       CASE WHEN startNode(r) = m THEN 'unspecified_form' ELSE 'specific_form' END AS relation
ORDER BY metabolite_id, relation, relative_id
```

### API helper: `_stereo_relatives_in_organism`

`_stereo_relatives_in_organism(conn, metabolite_ids, organism, *, exclude_ids, gbm_filters, arms)`
returns `dict[str, list[StereoRelative]]`:
1. If `metabolite_ids` is empty, return `{}` (no query).
2. Run `build_metabolite_stereo_relatives`. If no rows, return `{}`.
3. Run the existing `build_genes_by_metabolite_summary` on the distinct relative ids, with
   the same organism, `gbm_filters` (`ec_numbers`, `mass_balance`,
   `metabolite_pathway_ids`, `gene_categories`, `substrate_depth`) and `arms`;
   `exclude_metabolite_ids=None`.
4. Join each relative to its `by_metabolite` entry, drop relatives with no entry
   (`gene_count = 0`), and group by the source metabolite id. Drop sources left with no
   relatives.

So the cost is at most 2 extra queries per call, and 0 when nothing in scope has a stereo
edge.

### Warning (both gene-side tools)

One warning per call, listing at most 5 sources:

`"Stereo forms hold more rows: Cysteine (kegg.compound:C00736) → L-Cysteine (kegg.compound:C00097): 13 reactions, 3 transporter families; Glutamate (kegg.compound:C00302) → L-Glutamate (…): 43 reactions …, and N more. Counts never combine across stereo forms, see stereo_relatives."`

`genes_by_metabolite` appends:
`"Re-run with include_stereo_forms=True to add them (rows tagged via_stereo_form_of)."`

The stereo warning goes **first** in `warnings`.

---

## 1. `list_metabolites`: per-row `stereo_relatives` (KG-wide, all relations)

New compact, sparse column: stripped when empty, so absent on ~3,050 rows. The entry is
`MetaboliteStereoRelative`:

| Field | Type |
|---|---|
| `metabolite_id` | str |
| `name` | str |
| `relation` | `specific_form` / `unspecified_form` / `enantiomer` |
| `catalyst_gene_count` | int (KG-wide, same meaning as the row field) |
| `transporter_gene_count` | int (KG-wide) |

`build_list_metabolites`: both branches append the column from a module constant
`_METABOLITE_STEREO_RELATIVES_COLUMN`. Docstring: "one bounded 1-hop `COLLECT` (stereo
relatives); everything else is direct property reads". Not in the summary builder.

Verified (all 3,214 metabolites in 0.10 s; 157 non-empty):

```cypher
COLLECT {
  MATCH (m)-[r:Metabolite_is_stereo_form_of|Metabolite_is_enantiomer_of]-(o:Metabolite)
  WITH o, CASE WHEN type(r) = 'Metabolite_is_enantiomer_of' THEN 'enantiomer'
               WHEN startNode(r) = m THEN 'unspecified_form'
               ELSE 'specific_form' END AS relation
  ORDER BY relation, o.id
  RETURN {metabolite_id: o.id, name: o.name, relation: relation,
          catalyst_gene_count: coalesce(o.catalyst_gene_count, 0),
          transporter_gene_count: coalesce(o.transporter_gene_count, 0)}
} AS stereo_relatives
```

Verified rows:
- `C00736` Cysteine → `[{C00097 L-Cysteine, specific_form, 652, 2554}, {C00793 D-Cysteine, specific_form, 12, 0}]`
- `C00097` L-Cysteine → `[{C00793, enantiomer}, {C00736, unspecified_form}]`
- `C00086` Urea → stripped (absent)

Field description: "Other stereo forms of this metabolite (1 hop). Counts never combine
across stereo forms: a 0 here can be non-zero on a relative. Absent when none."

---

## 2. `genes_by_metabolite`: hint + `include_stereo_forms`

### New parameter

`include_stereo_forms: bool = False`. Description: "Also query the generic ↔ specific
stereo forms of each metabolite_id (e.g. Cysteine ↔ L-Cysteine; TCDB lists generic names,
KEGG reactions use specific forms). Added rows carry via_stereo_form_of. Enantiomers are
never added."

### Hint (`include_stereo_forms=False`)

- Sources: the input `metabolite_ids` that exist (minus `not_found`).
- `exclude_ids` = `metabolite_ids` ∪ `exclude_metabolite_ids`: relatives you already
  passed or excluded are never hinted.
- Envelope `stereo_relatives: dict[str, list[StereoRelative]]` (default `{}`), keyed by
  input id.
- `by_metabolite[*].stereo_relative_ids: list[str]` (sparse): the locality marker next to
  the counts.
- One warning, as above. It covers inputs in `not_matched` too, which have no
  `by_metabolite` entry.
- Fires whenever a relative has rows in this organism, not only when the input has zero
  (the measured-L-form case).

### Expansion (`include_stereo_forms=True`)

1. After canonicalisation, call `build_metabolite_stereo_relatives` for the inputs (same
   `exclude_ids`) and add the relative ids to `metabolite_ids`. Keep
   `added: dict[relative_id, source_id]`. A relative reached from two inputs takes the first
   input, in input order.
2. Run the existing flow unchanged on the expanded list.
3. Tag rows and `by_metabolite` entries whose `metabolite_id` is in `added` with
   `via_stereo_form_of: <source_id>` (sparse).
4. Envelope `stereo_forms_added: dict[str, list[str]]` (source → added ids; default `{}`).
   `not_matched` covers only the ids the caller passed: added ids with no rows are dropped
   silently, because `stereo_forms_added` already records them.
5. No hint and no stereo warning (the relatives are in the result).

### MCP

- New `StereoRelative` model.
- `GbmByMetabolite` gains sparse `stereo_relative_ids` and `via_stereo_form_of`.
- `GeneReactionMetaboliteTriplet` gains sparse `via_stereo_form_of`.
- `GenesByMetaboliteResponse` gains `stereo_relatives` and `stereo_forms_added`.
- The `warnings` description adds the stereo warning.
- Both new keys are also on the organism-unresolved short-circuit envelope (`{}`).

### Verified (MED4)

- `genes_by_metabolite(['C00736'], 'MED4')`: Cysteine has 0 reactions and 5 transporter
  families. The relative summary gives L-Cysteine 13 / 3 / 38 genes. D-Cysteine has no
  MED4 rows, so it is not hinted.

---

## 3. `metabolites_by_gene`: hint only

- Sources: every metabolite in the filtered slice that has a stereo edge. The summary
  builder gains one column, `stereo_linked_metabolite_ids`:
  `collect(DISTINCT CASE WHEN EXISTS { (m)-[:Metabolite_is_stereo_form_of]-() } THEN m.id END)`.
  It's bounded by the ~157 linked nodes.
- `_stereo_relatives_in_organism(…, exclude_ids=[], gbm_filters=None, arms=both)`. Relatives
  are counted for the whole organism: the question is "where else does this compound have
  genes", not "this gene's rows".
- Envelope `stereo_relatives: dict[str, list[StereoRelative]]` keyed by slice
  metabolite id. Detail rows carry sparse `stereo_relative_ids`. One warning.

Verified: 6 MED4 genes that transport Cysteine reach 523 metabolites, 26 of them
stereo-linked. Hinted relatives include:
- Cysteine → L-Cysteine (13 reactions);
- Glutamate `C00302` → L-Glutamate (43) and D-Glutamate (2);
- Alanine `C01401` → L-Ala (13) and D-Ala (2);
- L-Cysteine → Cysteine (5 transporter families, 33 genes).

Relatives with no MED4 rows drop out.

### MCP

- `MetabolitesByGeneResponse` gains `stereo_relatives`.
- The detail row model gains sparse `stereo_relative_ids`.
- The `warnings` description is updated, and the short-circuit envelope carries `{}`.

---

## Tests

- **Unit, query builders:**
  - `build_list_metabolites`: the column is in both branches.
  - `TestBuildMetaboliteStereoRelatives`: params, `RETURN` keys, `ORDER BY`, the exclude
    list, and that only `Metabolite_is_stereo_form_of` is traversed (no enantiomer).
  - `build_metabolites_by_gene_summary` returns `stereo_linked_metabolite_ids`.
- **Unit, api:**
  - `list_metabolites` strips an empty `stereo_relatives`.
  - `_stereo_relatives_in_organism`:
    - no query when there are no ids;
    - no summary query when there are no relatives;
    - relatives with no rows are dropped.
  - `genes_by_metabolite`:
    - the hint fires when an input has rows too (not only on zero);
    - relatives in the input list or in `exclude_metabolite_ids` are not hinted;
    - `not_matched` inputs are hinted;
    - the stereo warning comes first;
    - `include_stereo_forms=True` expands, tags rows and entries, fills
      `stereo_forms_added`, emits no hint, and keeps added ids out of `not_matched`;
    - a relative shared by two inputs is tagged with the first input;
    - the short-circuit envelope carries both keys.
  - `metabolites_by_gene`: the hint over slice ids; row tags are sparse.
- **Unit, wrappers:** new models and fields; the param is forwarded; populated dicts
  validate.
- **Integration (`-m kg`):**
  - `list_metabolites(metabolite_ids=['C00736'])` has L-Cysteine as `specific_form`; the
    urea row has no key;
  - `genes_by_metabolite(['C00736'], 'MED4')` hints C00097, not C00793;
  - `genes_by_metabolite(['C00736', 'C00097'], 'MED4')`: no hint;
  - `genes_by_metabolite(['C00736'], 'MED4', include_stereo_forms=True)` has
    metabolism rows tagged `via_stereo_form_of='kegg.compound:C00736'`;
  - `genes_by_metabolite(['C00086'], 'MED4')`: no hint;
  - `metabolites_by_gene(<a MED4 Cys transporter>, 'MED4')` hints Cysteine → L-Cysteine.
- **Edge cases:**
  - `genes_by_metabolite` with a stereo-linked input in an organism where no relative has
    rows: valid envelope, no hint;
  - `include_stereo_forms=True` with an input that has no relatives.
- **Regression:** goldens for `list_metabolites` (new column), and for `genes_by_metabolite`
  / `metabolites_by_gene` cases whose metabolites have relatives (warnings, new keys), so
  run `--force-regen` with a classified diff.

## Docs (MCP-facing; these are the main deliverable alongside the code)

- **`references/analysis/metabolites.md`:** a new section, **"Stereo forms: generic vs
  specific nodes"**:
  - why the split exists (TCDB generic names vs KEGG specific forms vs dominant-form
    measured names);
  - that counts never combine across forms;
  - the Cysteine and Alanine worked examples with live numbers;
  - how to read `stereo_relatives` / the warning;
  - when to use `include_stereo_forms` (transport ↔ catalysis joins) and when not to
    (exact-form questions, D-amino-acid biology);
  - that a generic's specific forms can include D-forms;
  - that enantiomers are never added;
  - that the edges are incomplete (mannose, isoleucine, glucose have no link yet), so a
    missing hint is not proof of no relative; search by name (`list_metabolites`).
- **`inputs/tools/genes_by_metabolite.yaml`:**
  - a `mistakes` entry: "0 reactions on a generic substrate ≠ no enzymes";
  - a chaining example: `metabolites_by_gene` → `genes_by_metabolite(include_stereo_forms=True)`;
  - an example with the warning and `stereo_relatives`.
- **`inputs/tools/metabolites_by_gene.yaml`:** a `mistakes` entry plus an example showing
  `stereo_relatives`.
- **`inputs/tools/list_metabolites.yaml`:** a `mistakes` entry (a 0 `catalyst_gene_count`
  on a generic form → read `stereo_relatives`).
- **`docs://guide/conventions`:** one paragraph, "Stereo forms are separate nodes; no
  rollup crosses them", pointing to the analysis section.
- **`CLAUDE.md` tool table:** mention `stereo_relatives` / `include_stereo_forms` on the
  three rows.
- **`docs/backlog.md`:** delete 2c.8 when shipped.
