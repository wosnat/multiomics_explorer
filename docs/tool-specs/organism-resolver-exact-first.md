# Spec: organism resolver — exact name first, no Cypher re-matching (backlog 2.8, Mode B)

**Date:** 2026-11-19
**Mode:** B — cross-tool fix, no new tool, no new parameters, no envelope changes.
**Size:** L (≈18 tools, ≈26 builders). **Status: FROZEN 2026-11-19.**

## Problem (measured on the live dev KG)

Organism text is matched as "every space-split word is a substring of `preferred_name` or
a synonym". Two gene-bearing strain names are substrings of others:

| Input (exact canonical name) | Also matches |
|---|---|
| `Alteromonas mediterranea AltDE` | `Alteromonas mediterranea AltDE1` |
| `Prochlorococcus PAC1` | `Prochlorococcus EQPAC1` |

Two failure modes:

1. **Single-organism tools can't select the strain at all.** `_validate_organism_inputs` /
   `_gbo_resolve_organism_scope` raise "matches multiple organisms" on the exact canonical
   name: `genes_by_ontology`, `kegg_module_completeness`, enrichment, `ontology_landscape`,
   DE by gene, `gene_response_profile`, `genes_by_metabolite`, … are unusable for PAC1 /
   AltDE.
2. **Discovery / filter tools leak the other strain.** Fourteen tools pass the raw text
   into Cypher, which re-matches word-by-word, so results silently pool both strains:
   `genes_by_function('photosystem', organism='Prochlorococcus PAC1')` → PAC1 + EQPAC1 genes;
   `list_experiments` / `list_derived_metrics` / `list_organisms` likewise. Even tools that
   resolve first (DE by gene, `genes_by_metabolite`) re-match the canonical name in Cypher
   and leak.

Not affected: coculture partner names (no collisions); `OrganismTaxon.organism_name` on
`Experiment` / `DerivedMetric` / `MetaboliteAssay` / `ClusteringAnalysis` is always a
gene-bearing canonical name (verified: 0 rows otherwise), so exact matching loses nothing.

## Out of scope

- `coculture_partner` filter matching (partner names don't collide; separate rule incl.
  gene-less treatment taxa).
- `list_metabolites(organism_names=…)` (already exact).
- New warnings on discovery tools when an organism matches nothing (still 0 rows, as today).
- Renaming organisms KG-side.

## Fix

### 1. Tiered resolver (`build_resolve_organism_for_organism`) — verified against live KG

Match candidates against `[preferred_name] + name_synonyms`, lower-cased; take the **best
tier only**:

1. **exact** — the whole input equals a name or synonym;
2. **whole word** — every input word equals a space-separated word of a name / synonym;
3. **substring** — today's rule (every input word is a substring).

Only gene-bearing organisms resolve (unchanged). The builder also returns
`geneless_matches` (gene-less taxa the input matched at any tier) and `match_tier`, for a
better error.

```cypher
MATCH (o:OrganismTaxon)
WITH o, toLower(trim($organism)) AS ql,
     [x IN split(toLower(trim($organism)), ' ') WHERE x <> ''] AS words,
     [a IN [o.preferred_name] + coalesce(o.name_synonyms, []) | toLower(a)] AS aliases
WITH o, CASE WHEN ql IN aliases THEN 1
             WHEN ALL(w IN words WHERE ANY(a IN aliases WHERE w IN split(a, ' '))) THEN 2
             WHEN ALL(w IN words WHERE ANY(a IN aliases WHERE a CONTAINS w)) THEN 3 END AS tier
WITH collect(CASE WHEN tier IS NOT NULL
                  THEN {n: o.preferred_name, t: tier, g: coalesce(o.gene_count, 0) > 0} END) AS cands
WITH cands, reduce(b = null, c IN cands | CASE WHEN c.g AND (b IS NULL OR c.t < b) THEN c.t ELSE b END) AS best
RETURN apoc.coll.sort([c IN cands WHERE c.g AND c.t = best | c.n]) AS organisms,
       best AS match_tier,
       apoc.coll.sort([c IN cands WHERE NOT c.g | c.n]) AS geneless_matches
```

(Aggregates without a grouping key so a no-match input still returns one row.)

Verified:
- `Prochlorococcus PAC1` → [PAC1] (tier 1); `PAC1` → [PAC1] (2).
- `Alteromonas mediterranea AltDE` → [AltDE] (1); `AltDE` → [AltDE] (2).
- `alteromonas` → all 11 gene-bearing Alteromonas (2), geneless [`Alteromonas`].
- `MED4` / `med4` → [MED4] (2); `9312` → [MIT9312] (3).
- `Meiothermus taiwanensis` → [Meiothermus ruber] (synonym, 1).
- `Escherichia coli` → [] with geneless [`Escherichia coli`].

**Back-compat check:** all 44 organism strings used in tests, eval cases, tool yaml
and docs resolve identically under old and new rules (11 tier 1, 14 tier 2, 19 tier 3 / no
match). Every canonical name and synonym self-resolves uniquely.

### 2. Error text (`_validate_organism_inputs`)

When `organisms` is empty and `geneless_matches` is not: "'Escherichia coli' is in the KG
as a taxon without genes (a coculture partner or treatment taxon); it cannot be the
organism here. Use list_organisms to see organisms with genes." Otherwise unchanged
("no organism matching …", "matches multiple organisms … be more specific").

### 3. One shared filter resolver (api)

`_resolve_organism_filter(organism: str | None, conn, *, include_geneless: bool = False) -> list[str] | None`: None → None (no
filter); str → the resolver's `organisms` (may be several: a genus pools strains, as
today; may be empty → 0 rows, as today); `include_geneless=True` (only `list_publications`)
appends `geneless_matches`. Lists (`organisms=[...]`) resolve per entry, union,
first-seen order; entries resolving to nothing feed `not_found_organisms` exactly as today.

### 4. Builders match exact canonical names

Every builder that word-matches an organism today switches to
`<node>.organism_name IN $organism_names` (null → no filter). Builder kwarg becomes
`organism_names: list[str] | None` (internal API; existing builder tests that assert the
`CONTAINS word` text are updated — the one deliberate test change in this build).

| Tool (api function) | Builder(s) / where helper | Resolves today? |
|---|---|---|
| `resolve_gene` | `build_resolve_gene` (organism filter only; identifier matching unchanged) | no |
| `genes_by_function` | `_genes_by_function_filter_clause` | no |
| `list_experiments` | `_list_experiments_where` (profiled organism; not `coculture_partner`) | no |
| `list_publications` | its experiment-organism filter (via `_list_experiments_where` or own) | no |
| `differential_expression_by_gene`, `gene_response_profile` | `_differential_expression_where` | yes, then re-matches |
| `genes_by_homolog_group` | `build_genes_by_homolog_group{,_summary,_by_clade,_diagnostics}` | no (list) |
| `differential_expression_by_ortholog` | `_differential_expression_by_ortholog_where`, `build_differential_expression_by_ortholog_membership_counts`, `_build_de_by_ortholog_organism_diagnostics` | no (list) |
| `list_clustering_analyses`, `gene_clusters_by_gene` (if it filters) | `_clustering_analysis_where` | no |
| `genes_in_cluster` | `build_genes_in_cluster{,_summary}` | no |
| `list_derived_metrics` | `_list_derived_metrics_where` | no |
| `genes_by_metabolite` | `_genes_by_metabolite_{metabolism,shared,go_transport}_where` | yes, then re-matches |
| `metabolites_by_gene` | `_metabolites_by_gene_{metabolism,shared,go_transport}_where` | yes, then re-matches |
| `list_metabolite_assays` | `_list_metabolite_assays_where` | no |
| `metabolites_by_quantifies_assay` | `_metabolites_by_quantifies_assay_where` (today: plain `CONTAINS $organism` on the whole input) | no |
| `metabolites_by_flags_assay` | `_metabolites_by_flags_assay_where` (same) | no |
| `assays_by_metabolite` | `_assays_by_metabolite_branch_conditions` (same) | no |
| `list_publications` | `_list_publications_where`: `ANY(o IN p.organisms WHERE o IN $organism_names)` (today: whole-input `CONTAINS` on `p.organisms`). **Names = `organisms` + `geneless_matches`**: `p.organisms` also lists gene-less taxa (`Phage`, `Escherichia coli`, `Vibrio parahaemolyticus`, `Thalassiosira pseudonana` — all OrganismTaxon nodes, verified), so `organism='Phage'` keeps finding its papers. | no |
| `list_organisms(organism_names=…)` | resolver only (gains tiers automatically) | yes |
| all single-organism tools (`genes_by_ontology`, enrichment, `ontology_landscape`, `kegg_module_completeness`, …) | resolver only | yes |

The list-param tools' `not_matched_organisms` (organism exists, no genes in the groups)
keeps its meaning; only how an entry maps to organisms changes.

## Tests

- **Unit:** resolver Cypher shape (three tiers, `geneless_matches`, no grouping key);
  `_resolve_organism_filter` (None / str / list, union order, empty); error text for
  gene-less taxa; each listed builder emits `IN $organism_names` and no `CONTAINS word` for
  organism; api functions pass resolved names. Existing builder tests asserting the old
  clause are updated, nothing else rebaselined.
- **Integration (`-m kg`), live:** for PAC1 and AltDE by exact name — every listed tool
  returns only that strain (`genes_by_function`, `list_experiments`, `list_derived_metrics`,
  `list_organisms`, DE by gene, `genes_by_metabolite`, `genes_by_homolog_group(organisms=['AltDE'])`, …);
  `genes_by_ontology` / `kegg_module_completeness` / `pathway_enrichment` accept the exact
  name (no ambiguity raise); `organism='Alteromonas'` on discovery tools still pools every
  strain; `9312` still resolves; `Escherichia coli` raises the gene-less message.
- **Edge cases:** scenario per changed tool with a colliding name.
- **Regression:** expect **zero golden diffs** (no case uses a colliding name) — any diff is a
  regression to investigate, not to regen.

## Docs

- `guide/conventions.md` "Organism naming": replace "word match — every space-split input
  word must be a case-insensitive substring" with the three tiers (exact → whole word →
  substring, best tier wins), note `"AltDE"` / `"PAC1"` now select one strain, and the
  gene-less message. Budget is within 10 chars — trim to fit.
- `guide/concepts.md` line ~89, CLAUDE.md `list_organisms` / `genes_by_homolog_group` rows,
  tool yaml that say "word match" (`genes_by_homolog_group`, `differential_expression_by_gene`,
  `genes_by_metabolite`, `genes_by_ontology`, `kegg_module_completeness`) and the
  `OrganismScopeParam` / organism Field descriptions in `tools.py`: "word-matched" →
  "matched by name (exact first, then whole words, then partial)".
- CHANGELOG `Fixed`: exact strain names now select one strain (AltDE / PAC1), with the tool
  list. Backlog: delete 2.8.

## Decisions (FROZEN 2026-11-19, user-approved)

1. Tier rule exact → whole word → substring, best tier only (substring kept so `9312` works).
2. Tier 3 (substring) stays silent — no warning.
3. Discovery tools keep pooling a multi-strain match (`organism='Alteromonas'` → all
   strains); single-organism tools keep raising on ambiguity.
4. Folded backlog housekeeping: KG ask E6 (PCC 7942 psbD / K02706 has no KO → no M00161
   edge) and item `best_module_type` in `ontology_landscape`; delete 2.8 on ship.

## Build note (2026-11-19)

The back-compat check missed one golden: `genes_by_function_synechococcus_filter`.
`Synechococcus` now resolves at tier 2 to the 53 Synechococcus strains and no longer pulls in
`Thermosynechococcus vestitus BP-1` (tier 3), −94 rows. A KG-wide sweep found only five words
the whole-word tier narrows: `altde`, `pac1` (intended), `synechococcus`, `pcc` (drops
`Cyanobium PCC6307` / `PCC7001`, written without a space), `sp.` (drops `subsp.`). All follow the
frozen tier rule; golden regenerated, noted in the CHANGELOG.

Code review added one site the §4 table missed: `genes_by_{numeric,boolean,categorical}_metric`
filtered DM diagnostics with a Python word match (`_classify_dm_organism_mismatch`), so PAC1
pulled EQPAC1's `sbp_nutrient_class` DM. Now resolved once via `_resolve_organism_filter` and
filtered by exact name; live test added. Also: blank `organism` = no filter and no warning;
`list_publications` documented as the one tool where gene-less taxa match.
