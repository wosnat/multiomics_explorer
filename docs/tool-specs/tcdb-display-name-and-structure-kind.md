# Tool spec: TCDB display names + metabolite structure_kind (Mode B)

Backlog 2c.20–2c.23, from the KG dialog
`docs/kg-specs/2026-10-29-transport-small-followups-explorer-asks.md` (absorbed 0764dd1,
build 2026-10-31T12:27:06Z).

## Purpose

1. **One TCDB name everywhere (2c.20).** 1,632 `TcdbFamily` nodes (1,248 subfamilies, 384
   systems) have no TCDB name: `name = tcdb_id`. They carry 39% of gated gene→TCDB edges
   (28,352 of 72,451), so rows today read `term_name: "3.A.1.118"`. The KG's new dense
   `display_name` equals `name` except on those nodes, where it borrows the nearest named
   ancestor: `"The ATP-binding Cassette (ABC) Superfamily — subfamily 3.A.1.118"`. The explorer
   **switches every TCDB name it shows to `display_name`** — no second field. The suffix
   `— subfamily <id>` / `— system <id>` already tells the reader the name is borrowed.
2. **Class substrates are visible on gene↔metabolite rows (2c.21).** `genes_by_metabolite` /
   `metabolites_by_gene` rows gain `metabolite_structure_kind`, so a TCDB substrate that is a
   ChEBI class (alpha-amino acid, peptide, fatty acid) reads as a class, not a molecule.
3. **Docs (2c.22, 2c.23).** Transport analysis doc covers class substrates; `genes_by_function`
   gets a mistakes entry for the new `[tcdb_best_hit]` description lines.

## Out of scope

- No KG ask. The KG keeps TCDB's own `name` for its direction rules and `tcdbFamilyFullText`;
  the explorer only changes what it displays.
- No new parameters, no filter on `structure_kind` in the two chemistry tools
  (`list_metabolites(structure_kind=...)` already filters).
- `list_metabolites` (already has `structure_kind`) and the three assay tools (all 135 measured
  metabolites are `defined`) are unchanged.
- Search is unchanged: `search_ontology` still matches TCDB's own names only (see Docs).

## Status

- [x] No KG change needed (`display_name` dense on all 9,725 nodes; differs from `name` on
      exactly the 1,632 `name = tcdb_id` nodes — verified live)
- [x] Scope reviewed with user (2026-10-31: single name, not a second field)
- [x] Result-size controls: unchanged (no new rows; one new compact column on 2 tools)
- [x] Spec frozen (2026-10-31, branch `tcdb-display-name-structure-kind` off main d01bbf5)

## Tools touched (Mode B)

| # | Tool | Change |
|---|---|---|
| 1 | `gene_ontology_terms` | TCDB `term_name` (rows; `by_term` envelope) → display name |
| 2 | `genes_by_ontology` | TCDB `term_name` (rows; per-term envelope) → display name |
| 3 | `search_ontology` | TCDB `name` → display name |
| 4 | `ontology_term_details` | TCDB `name`, `parents[].name`, `children[].name` → display name. Verbose `properties` (`t{.*}`) keeps both raw props |
| 5 | `ontology_landscape` | TCDB example-term names → display name |
| 6 | `pathway_enrichment` / `cluster_enrichment` | TCDB `term_name` (from `build_genes_by_ontology_per_term`) → display name. No code change beyond the builder |
| 7 | `genes_by_metabolite` | `tcdb_family_name` (rows + `top_tcdb_families`) → display name; new row column `metabolite_structure_kind` |
| 8 | `metabolites_by_gene` | same as 7 |
| 9 | `genes_by_function` | YAML mistakes entry only |

## Design

### D1. Config-driven name expression (queries_lib.py)

Add to the `tcdb` entry of `ONTOLOGY_CONFIG`:

```python
"display_name_prop": "display_name",
```

and one helper:

```python
def _term_name_cypher(cfg: dict, var: str = "t") -> str:
    """Cypher for a term's display name: `coalesce(<var>.<display_name_prop>, <var>.name)`
    when the ontology declares one (TCDB), else `<var>.name`."""
```

Every ontology-builder site that projects a term name uses the helper with the right variable,
so only TCDB's Cypher changes and no other label is asked for a property it lacks (the explorer's
own `run_cypher` validator warns on that; Neo4j does not, since the key exists in the DB). Sites
(line numbers at 0764dd1):

| Builder | Line(s) | Var |
|---|---|---|
| `build_search_ontology` (browse + 3 search branches) | 4368, 4399, 4408, 4423 | `t` |
| `build_genes_by_ontology_detail` | 4768 | `t` |
| `build_ontology_term_details` (name, parents, children) | 5009, 4998, 5004 | `t`, `p`, `c` |
| `build_genes_by_ontology_per_term` | 5246 | `t` |
| `build_gene_ontology_terms_summary` (`by_term`) | 5525, 5531, 5583, 5589 | `t` |
| `build_gene_ontology_terms` (rollup + leaf) | 5775, 5827 | `t` |
| `build_ontology_landscape` | 8359 | `t` |

Chemistry sites (TCDB-only, so the expression is written directly, `tf` var):

| Builder | Line |
|---|---|
| `_tcdb_transport_return` | 1421 |
| `build_genes_by_metabolite_summary` (row map; `top_tcdb_families` reads `row.tcdb_family_name`) | 10502 |
| `build_metabolites_by_gene_summary` (same) | 11354 |
| any other `tf.name AS tcdb_family_name` the implementer finds (grep `tf.name`) | — |

Output column names do not change (`term_name`, `name`, `tcdb_family_name`).

### D2. `metabolite_structure_kind` (2c.21)

Every row-producing builder of `genes_by_metabolite` / `metabolites_by_gene` that projects
`metabolite_formula` adds, right after `metabolite_chebi_id`:

```cypher
m.structure_kind AS metabolite_structure_kind
```

(map projections: `metabolite_structure_kind: m.structure_kind`). Sites: 1429-1431, 1671-1673,
10023-10025, 10507, 10889-10891, 11359, plus any other `metabolite_formula` projection in those
two tools. On rows whose target is a `ChemicalRole` (`target_kind = 'chemical_role'`) the value
is `null` (roles carry no `structure_kind`, as they carry no formula / mass). Compact column
(short categorical), all arms.

Pydantic (`GeneReactionMetaboliteTriplet`, after `metabolite_chebi_id`):

```python
metabolite_structure_kind: Literal["defined", "generic", "polymer"] | None = Field(
    default=None,
    description="'defined' (one molecule), 'generic' (a compound class, e.g. 'Peptide', "
    "'Fatty acid') or 'polymer'. Null on chemical-role targets. A generic substrate "
    "means 'a class of compounds', not one molecule.")
```

### D3. Pydantic description fixes (tools.py)

- `GbmTopTcdbFamily.tcdb_family_name` and the `metabolites_by_gene` twin (lines ~1019, ~1490)
  currently say subfamily / system names "fall back to the `tcdb_id`". Replace with: "TCDB name;
  for a subfamily or system TCDB left unnamed, the nearest named ancestor's name plus
  '— subfamily <id>' / '— system <id>'."
- Row `tcdb_family_name` (~774) and the TCDB-facing `term_name` / `name` descriptions where they
  describe TCDB: same sentence, kept ≤ 250 chars.

### D4. Docs (doc-updater)

- `config/schema_baseline.yaml`: `TcdbFamily.display_name: string`; `_NODE_PROP_NOTES` gains
  `display_name` in `scripts/build_about_content.py` (unit test
  `test_node_prop_notes_cover_every_ontology_label_prop`). **Ownership:** doc-updater owns both.
- `inputs/ontologies/tcdb.yaml`: one pitfall — names shown are `display_name`; an unnamed
  subfamily/system reads "<ancestor> — subfamily <id>" and does **not** inherit that ancestor's
  `direction`; search matches TCDB's own names only, so "ABC Superfamily" finds the family node,
  and `genes_by_ontology(term_ids=[family])` expands to its unnamed subfamilies.
- `references/analysis/transport.md` "Catch-all substrates": extend to ChEBI structural
  classes (`structure_kind = 'generic'`: alpha-amino acid, peptide, lipid, fatty acid,
  nucleoside) → "a class of compounds"; read `metabolite_structure_kind`. Same applies to the
  `[tcdb_substrates]` clause of a `[tcdb_best_hit]` description line.
- `inputs/tools/genes_by_function.yaml` mistakes: a hit on a `[tcdb_best_hit]` line of
  `alternate_functional_descriptions` is homology to a characterised TCDB system ("best TCDB
  hit"), not proof the gene transports the listed substrates — the trust surface is the
  `Gene_has_tcdb_family` edge (`tcdb_call`, `tcdb_gate`, `identity`); search a TCDB id as a quoted
  phrase (the analyzer splits `3.A.1.4.4`).
- `inputs/tools/genes_by_metabolite.yaml` / `metabolites_by_gene.yaml`: `metabolite_structure_kind`
  in response examples comes from `refresh_examples.py --write`; add one mistakes line ("a
  `generic` substrate is a compound class").
- KG dialog `docs/kg-specs/2026-10-29-transport-small-followups-explorer-asks.md`: append a
  correction to E2 — the explorer shows `display_name` in place of `name` (no second field);
  nothing needed KG-side.
- `docs/backlog.md`: delete 2c.20–2c.23 when shipped; CHANGELOG `[Unreleased]` entry.

## Verified Cypher (live KG, build 2026-10-31T12:27:06Z)

```cypher
// display_name dense, differs exactly on unnamed nodes
MATCH (t:TcdbFamily) RETURN count(t), sum(CASE WHEN t.display_name IS NULL THEN 1 ELSE 0 END),
  sum(CASE WHEN t.display_name <> t.name THEN 1 ELSE 0 END),
  sum(CASE WHEN t.name = t.tcdb_id THEN 1 ELSE 0 END)
// → 9725, 0, 1632, 1632

// gene rows on unnamed nodes: MED4 PMM0010 → tcdb:3.A.5.7
//   old term_name '3.A.5.7' → 'The General Secretory Pathway (Sec) Family — subfamily 3.A.5.7'
MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})-[r:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE r.tcdb_gate IN ['direct','annotated'] AND t.name = t.tcdb_id
RETURN g.locus_tag, t.id, coalesce(t.display_name, t.name) AS term_name

// gated edges by level / named: tc_subfamily unnamed 28,352; tc_system unnamed 21

// structure_kind on MED4 direct transport rows: defined 93, generic 23
//   (Fatty acid, Peptide, Fe(III)-complexed siderophore, Glycolipid, ...)
// TCDB substrate targets: defined 996, generic 298, polymer 17
```

## Tests

- **Query builders:** TCDB builders emit `coalesce(t.display_name, t.name)` (and `p.`/`c.` in
  term details); a non-TCDB ontology (e.g. `go_bp`, `pfam`) emits plain `t.name` and no
  `display_name`; chemistry builders emit `coalesce(tf.display_name, tf.name) AS
  tcdb_family_name` and `m.structure_kind AS metabolite_structure_kind`.
- **API / wrappers:** `metabolite_structure_kind` passes through; Pydantic accepts `null` on
  chemical-role rows.
- **Integration (`-m kg`):** MED4 `gene_ontology_terms(['PMM0010'], ontology='tcdb')` has a
  `term_name` ending "— subfamily 3.A.5.7"; no TCDB row in that call has `term_name ==
  term_id` minus prefix; `genes_by_metabolite` MED4 rows include at least one
  `metabolite_structure_kind == 'generic'`; chemical-role rows have it `null`.
- **Edge cases:** no new scenarios needed (no new params / inputs); existing scenarios must stay
  green.
- **Regression:** goldens with TCDB names or gbm/mbg rows move — regenerate after classifying
  (`term_name` / `name` / `tcdb_family_name` value changes and the new
  `metabolite_structure_kind` key only).
