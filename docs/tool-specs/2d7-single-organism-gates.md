# Backlog 2d.7a: relax single-organism gates on the locus-tag tools

Mode B (four tools). Origin: a single-organism gate audit on 2026-11-18, which followed the
spock_osnat hli analysis gaps. `genes_by_metabolite` is split out as **2d.7b** (see the end).

## Why

Locus tags are unique across the KG: none of the 330,531 genes shares a locus tag with a gene in
another organism (checked 2026-11-18). On a locus-tag tool, `organism` therefore adds no identity
check. Today it either is required for no reason, or blocks a mixed batch that would be a plain
union of per-gene rows. On two tools a tag from another organism is also misreported (live,
release KG, `organism="MED4"`, tags `PMM0001` + MIT9313 `PMT0419`):

| Tool | Today | Problem |
|---|---|---|
| `gene_ontology_terms` | `organism` required. PMT0419 listed in `no_terms` | Says the gene has no terms. It has them, but in MIT9313 |
| `metabolites_by_gene` | `organism` required. PMT0419 listed in `not_found.locus_tags` | Says the gene does not exist |
| `gene_clusters_by_gene` | `organism` optional. Mixed tags raise "span multiple organisms" | Rows are per gene; nothing needs one organism |
| `gene_derived_metrics` | Same | Same |

## Rules shared by all four

1. **`organism` is optional** (`str | None = None`). On `gene_ontology_terms` and
   `metabolites_by_gene` it is the second positional parameter today, so a default keeps
   existing positional calls working.
2. **`organism` given + a tag from another organism → `ValueError`** naming the tags and their
   organisms. This is the existing `_validate_organism_inputs` behaviour, already used by
   `differential_expression_by_gene`, `gene_clusters_by_gene` and `gene_derived_metrics`. It
   replaces the misreports above. Unknown tags still go to `not_found` as today.
3. **`organism` omitted → inferred from the tags.** What a mixed batch does depends on the tool
   (below).

## Per tool

### `gene_ontology_terms`: mixed batches allowed

- Each builder's `MATCH (g:Gene {organism_name: $org})` becomes `MATCH (g:Gene)` plus
  `AND ($org IS NULL OR g.organism_name = $org)` on the existing
  `WHERE g.locus_tag IN $locus_tags`, in both `build_gene_ontology_terms` and
  `build_gene_ontology_terms_summary`, every branch (leaf / rollup × bridge / flat / pfam /
  hierarchical). The locus-tag index still drives the lookup.
- The API passes `organism_name=None` when `organism` is omitted, or the resolved name when it
  is given.
- New envelope key `by_organism: [{organism_name, gene_count}]` (genes with ≥1 row), sorted by
  gene_count desc, then name. Row `organism_name` stays verbose.

### `gene_clusters_by_gene` and `gene_derived_metrics`: mixed batches allowed

- Without `organism`, the single-organism check is skipped. With `organism`, it still runs
  (rule 2).
- New envelope key `by_organism: [{organism_name, count}]` (rows per organism), sorted by count
  desc, then name.
- New verbose row column `organism_name` (`g.organism_name`).
- The docstrings lose "Single organism enforced."

### `metabolites_by_gene`: organism inferred, mixed batches still raise

- Its organism-wide counts (`organism_catalyst_gene_count`, ...) and the stereo hint are
  organism-scoped, so a mixed batch has no single meaning there. Mixed tags keep raising
  "locus_tags span multiple organisms — call once per organism".
- With `organism` omitted, it is resolved from the tags (`_validate_organism_inputs(None,
  locus_tags, None)`), and the rest of the function runs unchanged on the resolved name.
- With `organism` given, rule 2 applies, replacing today's `not_found.locus_tags` misreport.
  The zero-match organism word path (empty envelope with `not_found.organism`) stays.

## Degenerate inputs (no organism, empty or unknown gene list)

With the organism filter gone, the gene list is the only thing that bounds the query. These
rules apply to all four tools, and each row is an edge-case scenario plus a unit test.

| Input | Today (release KG) | After |
|---|---|---|
| `locus_tags=[]` or `None` | `ValueError` "must not be empty" on 3 tools. `metabolites_by_gene` with `organism` returns an empty envelope | `ValueError` "locus_tags must not be empty." on all four, checked before any organism logic. `metabolites_by_gene` changes. |
| No `locus_tags` and no `organism` | `TypeError` (missing args) | `TypeError` from the signature (`locus_tags` stays required). Unchanged. |
| All tags unknown (`["NOPE"]`, `[""]`), no `organism` | GO / metabolites: `TypeError` (organism required). Clusters / metrics: `ValueError` "at least one of organism, locus_tags, or experiment_ids is required", a bug | An empty envelope with every tag in `not_found` (`not_found.locus_tags` on `metabolites_by_gene`), totals 0, no raise. `by_organism` is `[]`. |
| Some tags unknown, no `organism` | n/a | Known tags answer normally, the unknown ones go to `not_found`, and the organism is inferred from the known ones only. |
| All tags unknown + `organism` given | As today | As today (organism validated, then empty envelope with `not_found`). |

Two Cypher guards follow from this:
- No builder may run with `locus_tags` empty or null. The API raises first. The builders also
  keep `g.locus_tag IN $locus_tags` as the first predicate on every gene MATCH, so `$org IS NULL`
  can never widen a query beyond the tag list. A unit test asserts that every gene MATCH in both
  GO-terms builders carries `g.locus_tag IN $locus_tags`.
- `$org` is always present in params (`None` when unscoped), so the parameter can never be
  missing.

Checked by EXPLAIN on the release KG: with `$org` null or set, the go_bp leaf, go_bp rollup
and kegg rollup detail and summary queries all start from `NodeIndexSeek` on the locus-tag index,
as before. There is no label scan.

## Out of scope: 2d.7b `genes_by_metabolite` across organisms

Making `organism` optional here is a different design. ATP alone reaches 16,145 genes in 118
organisms through the metabolism arm. The organism-wide counts, the stereo hint and the
`not_matched` semantics would all need per-organism forms. It stays in the backlog as its own L
item. It needs a design, probably a per-organism summary mode before any row mode.

## Verified Cypher (release KG alpha.9, 2026-11-18)

For `gene_ontology_terms`, the builders' output was rewritten with the two string replacements
above and run with `$org = null` on `PMM0001`, `PMM1404` (MED4), `PMT0419` (MIT9313) and
`SYNW0001` (WH8102). Each query had exactly one `{organism_name: $org}` site:

| ontology / mode | rows | genes | time |
|---|---|---|---|
| go_bp leaf | 4 | all 4 | 0.05 s |
| go_bp rollup level 2 | 4 | all 4 | 0.13 s |
| kegg rollup level 1 | 3 | 3 (PMM1404 has no KEGG) | 0.06 s |
| pfam leaf | 7 | 3 | 0.02 s |
| cyanorak_role rollup level 1 | 4 | all 4 | 0.07 s |

The implementation must also check that `$org` set to the resolved name gives the same rows as
today on a single-organism batch (regression goldens), and that the summary builder's
`not_found` / `no_terms` bookkeeping stays per tag with `$org` null.

`gene_clusters_by_gene` / `gene_derived_metrics` have no organism in their builders. The change
is in the API gate plus one `g.organism_name` column, so there is no new MATCH to verify.

## Docs

- Tool yamls (all four): remove "one organism" wording where it no longer holds. Add a
  `mistakes` line: pass `organism` only to scope or check; a tag from another organism raises.
  `metabolites_by_gene`: one call per organism.
- Pydantic `organism` Field descriptions: "Optional. Inferred from locus_tags when omitted; when
  given, every tag must belong to it."
- CHANGELOG `### Changed`: the two misreports become a ValueError. Callers that relied on
  `no_terms` / `not_found` for another organism's tags get an error instead.

## Tests

- Unit: builders with `organism_name=None` contain `$org IS NULL OR` and no
  `{organism_name: $org}`. API: `organism` optional on all four; a mixed batch works on three
  and raises on `metabolites_by_gene`; `organism` + a foreign tag raises on all four;
  `by_organism` present. Wrappers: `organism` optional; the new envelope models.
- Edge-case scenarios: add a mixed-organism batch scenario for the three tools that accept it,
  and `expects_error=ToolError` for `metabolites_by_gene`.
- Regression: single-organism goldens unchanged except the new `by_organism` key
  (`dispatch: api` cases) and the verbose `organism_name` column. One new mixed-batch case per
  tool.
- Contract tests (`test_api_contract.py`): add `by_organism` to the expected envelope keys.
