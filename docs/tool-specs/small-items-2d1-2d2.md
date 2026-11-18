# Backlog 2d.1 + 2d.2: DE `product` compact, homolog-group `by_clade`

Mode B (two tools, small additive changes). Origin: spock_osnat gaps docs
(`analyses/2026-11-03-ntca_urea_response`, `analyses/2026-11-16-hli_light_stress`).

## 2d.1: `differential_expression_by_gene` returns `product` on compact rows

### Purpose

`product` is verbose-only on this tool, so analysis code that reads `row["product"]` without
`verbose=True` raises KeyError. Almost every other tool that returns gene rows has `product` as a
compact column (`genes_by_function`, `genes_by_homolog_group`, `genes_by_ontology`,
`genes_in_cluster`, `gene_derived_metrics`, the metabolite tools, ...). Here it is the exception.

### Change

- Builder `build_differential_expression_by_gene`: move `g.product AS product` from
  `verbose_cols` into the compact RETURN, right after `gene_name`. Compact goes from 15 to 16 keys.
- API docstring: `product` goes into the compact per-result list and comes out of "verbose adds".
- Pydantic result model: `product` is no longer a verbose-only field (it keeps its description;
  null when the gene has no product).
- `inputs/tools/differential_expression_by_gene.yaml`: drop `product` from `verbose_fields`.
- No parameter, filter, sort or envelope change. `differential_expression_by_ortholog` and
  `gene_response_profile` are untouched.

### Cost

About 30 extra characters per row. A 5000-row page grows by roughly 150 kB in Python. MCP calls
are capped by `limit`, so their size barely changes.

### Verified Cypher (live KG, 2026-11-18)

This is a column move with no change to the MATCH or WHERE, so row counts cannot change and there
is no new Cypher to verify. Regression goldens confirm it.

## 2d.2: `genes_by_homolog_group` gains a `by_clade` envelope rollup

### Purpose

Asking how widely an ortholog group spreads across ecotypes ("how many HL vs LL genomes carry
it?") needs a `list_organisms` join today, and the denominator (genomes in that clade in the KG)
is a separate query. The hli analysis also inferred HL/LL from strain names before finding
`OrganismTaxon.clade`.

### Change

A new envelope key, `by_clade`, holds one entry per (genus, clade) among matched genes:

| Field | Type | Semantics |
|---|---|---|
| `genus` | `str \| None` | `OrganismTaxon.genus` |
| `clade` | `str \| None` | `OrganismTaxon.clade`; null where the KG has no clade (Alteromonas, heterotrophs, 2 S. elongatus) |
| `organism_count` | `int` | Distinct organisms in this genus + clade that have ≥1 matched gene (union across input groups) |
| `organisms_in_clade` | `int` | All KG organisms with `gene_count > 0` in this genus + clade (the denominator; ignores the `organisms` filter) |
| `gene_count` | `int` | Matched gene × group rows in this genus + clade |

- The key is (genus, clade), because bare clade labels repeat across genera: `III` in
  Synechococcus and Parasynechococcus, `5.2` in Synechococcus and Cyanobium.
- Sorted by genus, then clade (nulls last). Not capped (≤ ~40 entries).
- The `organisms` filter applies to the numerators. The denominator stays the whole KG.
- With several `group_ids`, counts are a union over the batch. For per-group breadth, call
  once per group. The docstring and yaml say so.
- Present on summary and detail calls alike. Empty list when nothing matched.
- A new builder, `build_genes_by_homolog_group_by_clade` (same `group_ids` / `organisms` params
  and the same organism word-match as the summary builder), run as one extra query by the API.
  The existing summary builder is untouched.
- Docs: a yaml `mistakes` line: use `by_clade` / `list_organisms` `clade` for ecotype, never
  parse strain names. Also a `chaining` line for per-group breadth.

### Verified Cypher (live KG, 2026-11-18)

```cypher
UNWIND $group_ids AS gid
MATCH (og:OrthologGroup {id: gid})<-[:Gene_in_ortholog_group]-(g:Gene)
      -[:Gene_belongs_to_organism]->(o:OrganismTaxon)
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_name) CONTAINS word)))
WITH o.genus AS genus, o.clade AS clade,
     count(DISTINCT o) AS organism_count, count(g) AS gene_count
CALL {
  WITH genus, clade
  MATCH (t:OrganismTaxon)
  WHERE t.gene_count > 0 AND t.genus = genus
    AND ((clade IS NULL AND t.clade IS NULL) OR t.clade = clade)
  RETURN count(t) AS organisms_in_clade
}
RETURN genus, clade, organism_count, organisms_in_clade, gene_count
ORDER BY genus, clade
```

(The KG's Neo4j rejects `CALL (x) { }`, so the subquery imports with `WITH`.)

Checks run:
- `cyanorak:CK_00002025` (PMM1404's hli group, 78 members / 43 organisms): 8 Prochlorococcus
  clade rows. Gene counts sum to 78 and organism counts to 43. HLII 18/19, HLI 3/4, every LL
  clade complete.
- `eggnog:1GI80@1117` (8 members / 5 organisms): HLI 3/4, HLII 2/19.
- `eggnog:COG0592@2` (broad): 34 rows, 10 ms.
- Implementation must also check: a null-genus organism (genus `None` → entry with
  `genus: null`); the `organisms` filter narrows numerators only; a not-found group → `[]`.

## Tests

- Unit: the DE builder has `product` in compact RETURN and not in verbose; the DE wrapper
  accepts compact rows with `product`; the new by_clade builder (params, organism filter,
  `WITH`-import subquery); the API attaches `by_clade` on summary and detail; the wrapper
  response model has `by_clade: list[HomologGroupCladeBreakdown]`.
- Regression: `--force-regen` the DE-by-gene goldens (new compact column) and the
  `genes_by_homolog_group` goldens (new envelope key), with a classified diff.
- Edge cases: existing scenarios for both tools cover the input axes. `by_clade` must be `[]` on
  the not-found / not-matched scenarios (the invariant oracle checks it).
- Examples: `refresh_examples.py --write --tool differential_expression_by_gene` and
  `--tool genes_by_homolog_group`.
