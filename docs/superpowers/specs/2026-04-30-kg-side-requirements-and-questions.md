# KG-side requirements and open questions

**Date:** 2026-04-30
**Sources consolidated:**
- `multiomics_research/analyses/2026-04-29-1025-axenic_up_hypotheticals_med4/gaps_and_friction.md` (F1–F6)
- `multiomics_explorer/docs/superpowers/specs/2026-04-29-mcp-usability-audit.md` (F-AUDIT-6)
**Verification state:** all items checked against the live KG (`bolt://localhost:7687`)
2026-04-30. Each item carries the live count / coverage fact below the gap statement.
**Audience:** KG-team conversation — what the explorer side needs from the KG, what's
already there but unsurfaced, and what's a genuine missing-data ask vs a normalize-at-
import ask vs a re-run-pipeline ask vs a schema-addition ask.

This is a requirements + questions doc, not a build plan. Each item includes:
gap, verification fact, severity, proposed remediation shape, open questions for the
KG team. Some items have shifted classification *because* of verification — flagged
explicitly where so.

## Summary of asks

| # | Item | Class | Severity |
|---|---|---|---|
| **KG-1** | Replace `"Alternative locus ID"` placeholder in `Gene.function_description` | Data-quality (import) | HIGH |
| **KG-2** | Replace `"N/A"` literal strings in `GeneCluster` description fields with NULL | Data-quality (import) | HIGH |
| **KG-3** | Re-run cyanorak / eggNOG / cluster pipelines on the full locus-tag set (PMM ∪ TX50_RS) | Pipeline rerun | MED |
| **KG-4** | Add term-level informativeness signal (catch-all term flag or curated list) | Schema addition (or shared curation) | MED |
| **KG-5** | Track per-Gene "processed by which pipelines" so empty results disambiguate | Schema addition | MED |
| **KG-6** | Improve curated cluster-description coverage on under-curated analyses; flag non-functional clustering analyses | Data-quality + schema | MED |
| **KG-7** | Add bioinformatics layers (AA sequence string, InterPro, AlphaFold) | Schema + import | LOW–MED, scoped |
| **MCP-7** | *(reclassified from F1 KG-ask)* Surface existing Polypeptide bio-layer fields via the explorer (`signal_peptide`, `transmembrane_regions`, etc.) | MCP-side, not KG | MED |

Items marked HIGH are scaled — they touch thousands of nodes and pollute basic identity
or grouping fields. MED items affect specific workflows. LOW items are scoped additions
worth pricing before committing.

---

## KG-1 — `Gene.function_description` placeholder pollution

**Gap.** `Gene.function_description` carries the literal string `"Alternative locus ID"` for genes
where no real description exists. The string is meaningless as a function description but is
treated as content by readers who don't recognize it as a stub.

**Verification (2026-04-30).**

```cypher
MATCH (g:Gene) WHERE g.function_description = "Alternative locus ID"
RETURN g.organism_name, count(*) ORDER BY count(*) DESC
```

**7,440 genes across 19 organisms** carry the placeholder. Top organisms:
- Prochlorococcus RSP50: 801
- Prochlorococcus MIT9312: 771
- Prochlorococcus MED4: **763**
- Prochlorococcus MIT9301: 761
- Prochlorococcus AS9601: 760
- … (other Pro strains: 600–700 each)
- Synechococcus strains: 25–27 each
- Alteromonas HOT1A3: 1

**Severity:** HIGH — pervasive across the KG (most Prochlorococcus genomes carry
600–800 polluted genes each); pollutes a primary identity field that every per-gene
tool surfaces.

**Proposed remediation.** Either:
- (a) **Replace placeholder with NULL** at import — preferred. The string is unambiguously
  a stub and consumers should test for absence, not for presence-of-stub.
- (b) Populate with curated text where available; replace remaining occurrences with NULL.

**Open questions for the KG team:**
1. Where does the placeholder originate — UniProt import? eggNOG? a synthetic fallback in
  the BioCypher build? Identifying the upstream import path is the cleanest fix point.
2. Are there other placeholder strings of the same shape on this field (e.g.
  `"Uncharacterized"`, `"Hypothetical"`)? Worth a fishing-expedition query
  to enumerate distinct values that occur >100 times before single-string fix lands.

**Companion fix already planned on the explorer side:** F-AUDIT-1 from the usability audit
removes the placeholder from Pydantic field examples (so the schema doesn't *teach*
the LLM to expect it). The KG fix removes it from the data; both ship independently.

---

## KG-2 — `GeneCluster` description fields use literal `"N/A"` instead of NULL

**Gap.** `GeneCluster.functional_description`, `GeneCluster.expression_dynamics`,
`GeneCluster.temporal_pattern` all return the literal three-character string `"N/A"`
when un-curated. No NULLs in the underlying data — every uncurated row is `"N/A"`.

**Verification (2026-04-30).**

```cypher
MATCH (c:GeneCluster) RETURN
  count(*) AS total,
  sum(CASE WHEN c.functional_description = "N/A" THEN 1 ELSE 0 END) AS func_NA,
  sum(CASE WHEN c.expression_dynamics = "N/A" THEN 1 ELSE 0 END) AS dyn_NA,
  sum(CASE WHEN c.temporal_pattern = "N/A" THEN 1 ELSE 0 END) AS pat_NA,
  sum(CASE WHEN c.functional_description IS NULL THEN 1 ELSE 0 END) AS func_null
```

| field | "N/A" count | NULL count | total |
|---|---:|---:|---:|
| `functional_description` | **52** | 0 | 93 |
| `expression_dynamics` | 47 | 0 | 93 |
| `temporal_pattern` | 46 | 0 | 93 |

**56 % of GeneCluster nodes have a stub `functional_description`.** No NULLs anywhere —
the convention is uniformly "N/A" string literal.

**Severity:** HIGH — every consumer that filters on `IS NULL` / `pd.isna(...)` /
`field is None` mis-classifies stubs as content. Affects every dossier-style or
cluster-aggregation tool that surfaces these fields.

**Proposed remediation.** Replace `"N/A"` with NULL at import. One-shot migration
on the existing 145 stub instances; preventive change on the ingest path.

**Open question for the KG team:**
1. Are there other GeneCluster string fields that follow the same convention but
  weren't sampled here? `name`, `id`, `organism_name` should be safe but worth
  a uniformity check.

---

## KG-3 — Re-run ortholog and cluster pipelines on the full locus-tag set

**Gap.** Late-added RefSeq locus tags (TX50_RS prefix) were never folded into the
cyanorak / eggNOG ortholog grouping pipelines or any clustering analyses. The genes
exist in the KG but have empty results across multiple per-gene tools — not because
the pipelines found nothing, but because the pipelines never ran on these locus tags.

**Verification (2026-04-30).**

```cypher
MATCH (g:Gene) WHERE g.locus_tag STARTS WITH "TX50_RS"
WITH count(g) AS tx50_total
MATCH (g:Gene) WHERE g.locus_tag IN ["TX50_RS09500", "TX50_RS09520", "TX50_RS09860"]
OPTIONAL MATCH (g)-[:Gene_in_ortholog_group]->(og)
OPTIONAL MATCH (gc:GeneCluster)-[:Gene_in_gene_cluster]->(g)
RETURN g.locus_tag, tx50_total, count(DISTINCT og) AS ogs,
       count(DISTINCT gc) AS clusters, size(g.annotation_types) AS ontology
```

| locus_tag | tx50_total in KG | OG count | cluster count | ontology sources |
|---|---:|---:|---:|---:|
| TX50_RS09500 | 14 | 0 | 0 | 0 |
| TX50_RS09520 | 14 | 0 | 0 | 0 |
| TX50_RS09860 | 14 | 1 | 0 | 0 |

14 RefSeq-only locus tags total in the KG (small absolute number, but the full-floor
case where all axes are empty is over-represented in the candidate set of any
"hypothetical upregulated" analysis).

**Severity:** MED — the affected gene set is small (14), but each gene is a true
floor case for downstream analyses. The fix unlocks per-gene tools that
otherwise return empty across the board.

**Proposed remediation.** Re-run the upstream pipelines (cyanorak ortholog grouping,
eggNOG inference at all taxonomic levels, plus any MED4 clustering analyses that
should logically include these genes) with the current full locus-tag set
(PMM ∪ TX50_RS). Whether all 14 will end up in *any* cluster / OG depends on
sequence; some may stay floor-case after rerun, but the rerun resolves "did we even
look?" vs "did we look and find nothing?".

**Open questions for the KG team:**
1. Where do TX50_RS tags originate (RefSeq automated annotation, presumably) and
  what's the canonical locus-tag scope policy going forward — are these treated
  as second-class to PMM, or first-class on rerun?
2. What's the cost of pipeline rerun? If the cyanorak side requires manual
  curation, the realistic remediation may be eggNOG-only.

**Companion explorer-side change:** see KG-5 — once pipeline-scope tracking exists,
even the "looked but found nothing" case stops being silent.

---

## KG-4 — Term-level informativeness signal

**Gap.** Ontology terms with content like "Function unknown", "Conserved hypothetical
proteins", "Hypothetical proteins / Conserved", "Domain of unknown function (DUF*)",
"Protein of unknown function*", "uncharacterized protein" are catch-all stubs — they
mean "we have no informative annotation for this gene" rather than carrying functional
content. F2 in the trigger analysis was a direct consequence: the LLM partitioned
candidates by *source presence* (cog/cyanorak/tigr) under the assumption "all terms
from these sources are catch-all", which is wrong — sources mostly carry catch-alls
but each carries a small tail of informative terms.

The right partition is at the **term** level. There is currently no flag, list, or
relation in the KG that distinguishes catch-all terms from informative terms.

**Verification (2026-04-30).**

```cypher
MATCH (n) WHERE labels(n)[0] IN
  ["CogFunctionalCategory","CyanorakRole","TigrRole","Pfam","KeggTerm","BriteCategory","GeneOntology"]
RETURN labels(n)[0] AS label, keys(n) AS properties
```

Across all seven ontology label types, no property names suggest informativeness
tracking (no `is_uninformative`, `is_catchall`, `is_stub`, `informativeness_class`).
Confirmed against the schema dump.

**Severity:** MED — the catch-all term set is small (probably 10–30 terms across
all sources), but the partition shows up in every "what does this hypothetical
gene do?" analysis.

**Proposed remediation — open design choice:**
- (a) **KG-side flag.** Add `is_uninformative: bool` (or `informativeness_class: str`
  with values `"informative" | "catchall_unknown" | "catchall_hypothetical"` etc.)
  property on selected ontology term nodes. Curated once, used everywhere.
  Strengths: single source of truth; consumable by Cypher and by every downstream
  tool. Weakness: requires curation and ongoing maintenance.
- (b) **Explorer-side static list.** Maintain a curated list of catch-all term IDs
  in the explorer; surface via a filter on `gene_ontology_terms` and as an envelope
  rollup on `gene_overview`. Strengths: cheap to ship; no KG schema change.
  Weakness: scattered across consumers; drifts from KG.
- (c) **Hybrid.** Curate the list in a structured artifact (YAML / JSON) checked
  into both repos, but apply at query time on the KG-build side as well as in the
  explorer.

**Open questions for the KG team:**
1. Which ontology sources carry the most catch-all terms in scope? (TIGR roles
  carry "Hypothetical proteins / Conserved" + "Not Found"; COG carries "Function
  unknown"; Cyanorak carries "Other > Conserved hypothetical proteins"; Pfam
  carries DUF* and "Protein of unknown function*". Worth confirming the
  full canonical list.)
2. Is the catch-all set stable across organisms? (Likely yes — these are
  ontology-vocabulary-level designations, not strain-specific.)
3. Preferred remediation style — flag on node, separate node label
  (`:UninformativeOntologyTerm`), or external curated list?

**Companion explorer-side change:** F-AUDIT-2 (audit) — proposed
`informative_annotation_types` per-gene field + envelope rollup. Whether this is
computed from a KG flag (option a) or a static list (option b) drives where the
work lives.

---

## KG-5 — Per-gene pipeline-scope tracking

**Gap.** When a per-gene tool returns 0 rows, the LLM cannot distinguish:
- (a) Gene exists in KG; pipeline ran on it; pipeline found no result.
- (b) Gene exists in KG; pipeline never ran on this gene (out-of-scope of upstream).
- (c) Gene doesn't exist in KG.

Cases (a) and (c) are already disambiguated (`not_found` envelope). Cases (a) and (b)
are conflated. KG-3 fixes the specific TX50_RS instance, but the structural problem
will recur whenever the pipeline scope and the gene scope diverge (any new locus-tag
addition, any pipeline that runs on a strict subset of organisms, etc.).

**Verification (2026-04-30).** Schema scan — no Gene property tracks per-pipeline
processing scope. No `processed_by_pipelines: list`, `pipeline_scope: list`, or
relationship to a `Pipeline` / `Analysis` node tracking which pipelines covered
which genes.

**Severity:** MED — the structural-coverage question recurs whenever pipelines run
on partial gene sets. Affects all `_by_X` tools that return empty rows.

**Proposed remediation.** Add a per-Gene property listing pipelines that processed
the gene:

```
Gene.processed_by_pipelines: list[str]
```

Values like `["cyanorak_orthogrouping", "eggnog_v5", "kegg_ko_assignment", "pfam_v36",
"tigr_role_assignment", "cyanorak_role_assignment", "cog_assignment"]`. Per-pipeline
boolean tracking lets the explorer return `out_of_pipeline_scope` rows on tools that
otherwise emit empty.

**Open questions for the KG team:**
1. Is this list bounded and stable (current pipelines) or expected to grow
  significantly?
2. Per-pipeline metadata (version, run date) — worth tracking, or just a presence
  list?
3. Should the property live on Gene, or on a per-(Gene, Pipeline) edge to a
  `:Pipeline` node? Edge form is cleaner if metadata is non-trivial.

**Companion explorer-side change:** F-AUDIT-6 (audit) — surface as
`out_of_pipeline_scope` envelope key on relevant tools. Wait on KG-5 design before
shipping.

---

## KG-6 — Cluster description curation coverage is uneven across analyses

**Gap.** Some clustering analyses have 100% curated functional descriptions; others
have 0 %. The analyses with the most candidate-set impact are often the worst
curated.

**Verification (2026-04-30).**

```cypher
MATCH (a:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->(c:GeneCluster)
RETURN a.name, a.organism_name, count(c) AS clusters,
       sum(CASE WHEN c.functional_description IS NOT NULL
                  AND c.functional_description <> "N/A" THEN 1 ELSE 0 END) AS curated,
       toFloat(curated) / count(c) AS rate
ORDER BY clusters DESC
```

| analysis | organism | clusters | curated | rate |
|---|---|---:|---:|---:|
| MED4 diel cycling expression clusters | MED4 | 18 | 11 | 61 % |
| NATL2A dark-tolerant strain diel | NATL2A | 15 | 0 | **0 %** |
| NATL2A parental strain diel | NATL2A | 15 | 0 | **0 %** |
| MED4 K-means N-starvation clusters | MED4 | 9 | 9 | 100 % |
| MIT9313 K-means N-starvation clusters | MIT9313 | 7 | 4 | 57 % |
| MED4 gene expression level classification | MED4 | 6 | 3 | 50 % |
| MIT9301 fuzzy c-means thermal acclimation | MIT9301 | 5 | 5 | 100 % |
| BP-1 transcript clusters by light condition | BP-1 | 4 | 2 | 50 % |
| BP-1 transcript clusters by oxygen condition | BP-1 | 4 | 2 | 50 % |
| M. ruber transcript clusters by light condition | M. ruber | 4 | 1 | 25 % |
| M. ruber transcript clusters by oxygen condition | M. ruber | 4 | 2 | 50 % |
| MED4 phage-upregulated transcription groups | MED4 | 2 | 2 | 100 % |

**Three analyses sit at 0–25 %; four sit at 100 %; the rest are 50–61 %.**
NATL2A diel analyses (30 clusters total) carry zero curated descriptions.

**Severity:** MED — affects "potential role" anchoring on cluster axes for the
worst-curated analyses. The trigger analysis hit this where 5 / 10 top-FC candidates
had a single cluster axis (the under-curated MED4 expression-level analysis).

**Proposed remediation — open design choice:**
- (a) **Curate the empty analyses.** NATL2A diel + others. Operational cost, but
  closes the gap. Worth scoping per-analysis effort.
- (b) **Flag analyses as "non-functional clustering"** where appropriate. The MED4
  expression-level classification (VEG / HEG / MEG / LEG / NEG) is a per-gene
  expression-bin classifier, not a functional grouping — so absence of `functional_description`
  may be by design. Add a `clustering_intent: "functional" | "expression_bin" | "other"`
  field on `ClusteringAnalysis` so consumers can filter accordingly.
- (c) **Add bin-meaning metadata** on per-cluster nodes for non-functional analyses
  (e.g., "VEG = top RPKM quartile" rather than `"N/A"`).

(b) + (c) together are probably the cleanest — recognize that some analyses don't
have functional content per cluster, and document what their content *is*.

**Open questions for the KG team:**
1. Which clustering analyses are intentionally non-functional? (Candidate: MED4 expression
  level classification. Others?)
2. Curation pipeline — manual editing in BioCypher source files, or does curation
  feed from external metadata?

---

## KG-7 — Bioinformatics annotation layers (scoped, after verification)

The trigger analysis F1 listed five batch-bioinformatics layers as candidate adds:
**Pfam, InterPro, SignalP, TMHMM, AlphaFold structure summaries**, plus AA sequence.
Verification reframes this list significantly:

**Verification (2026-04-30).**

```cypher
MATCH (p:Polypeptide) RETURN
  count(*) AS total_polypeptides,
  sum(CASE WHEN p.sequence_length IS NOT NULL THEN 1 ELSE 0 END) AS has_seqlen,
  sum(CASE WHEN p.transmembrane_regions IS NOT NULL
            AND size(p.transmembrane_regions) > 0 THEN 1 ELSE 0 END) AS has_tm,
  sum(CASE WHEN p.signal_peptide IS NOT NULL THEN 1 ELSE 0 END) AS has_signal_peptide
```

| field | populated | total | coverage |
|---|---:|---:|---:|
| `sequence_length` | 55,862 | 55,863 | ~100 % |
| `transmembrane_regions` | 11,626 | 55,863 | 21 % |
| `signal_peptide` | 3,954 | 55,863 | 7 % |

Plus on the schema: `Polypeptide.pfam_ids: list[str]`, `Polypeptide.keywords: list`,
`Polypeptide.go_biological_processes: list`, `Polypeptide.eggnog_ids: str`,
`Polypeptide.refseq_ids: list`, `Polypeptide.string_ids: str`,
`Polypeptide.is_reviewed: str`, `Polypeptide.annotation_score: float`.

### Reclassification

The original F1 list collapses into three buckets:

| Item | KG state | Class |
|---|---|---|
| Pfam | Present (Gene_has_pfam edges + Polypeptide.pfam_ids) | Already in KG |
| TMHMM | Present (Polypeptide.transmembrane_regions, ~21% coverage) | **Already in KG; not surfaced via MCP — see MCP-7** |
| SignalP | Present (Polypeptide.signal_peptide, ~7% coverage) | **Already in KG; not surfaced via MCP — see MCP-7** |
| InterPro | Absent | KG-7 ask |
| AlphaFold structure summaries | Absent | KG-7 ask |
| AA sequence string | Absent (only sequence_length) | KG-7 ask |

The "missing batch-bio layers" framing in F1 was based on the assumption that
TMHMM/SignalP weren't in the KG. In fact they are — they're just not currently
surfaced through the explorer (`gene_details` doesn't traverse `Gene_encodes_protein
→ Polypeptide`). That's an MCP-side gap, not a KG-side gap.

The remaining KG-side asks are:

### KG-7a — Amino-acid sequence string

**Gap.** `Polypeptide.sequence_length` is populated, but no `aa_sequence` /
`sequence` field stores the actual primary sequence. Per F1, this is "absent due
to per-node size limits".

**Severity:** LOW–MED — primary sequence enables ad-hoc downstream analyses
(domain re-scans, structural prediction) that aren't pre-computable. Not blocking
any current analysis but unlocks future ones.

**Open questions for the KG team:**
1. Is the per-node size limit still binding in current Neo4j? Many configurations
  allow strings up to 4 GB.
2. Alternative: separate `:Sequence` node per protein with `Polypeptide-[:HAS_SEQUENCE]->Sequence`
  edge, decoupling sequence storage from Polypeptide property bloat.
3. Source — UniProt / RefSeq sequence files? Versioning policy?

### KG-7b — InterPro domain annotations

**Gap.** Pfam is exposed (single domain database). InterPro aggregates Pfam +
PROSITE + SMART + PANTHER + others — typically increases domain annotation
coverage on hypothetical proteins.

**Severity:** LOW — incremental over existing Pfam.

**Open questions:** import path; size of resulting node count.

### KG-7c — AlphaFold structure summaries

**Gap.** No structural predictions currently in the KG. Predicted secondary-
structure / fold class would help characterize otherwise un-annotated hypotheticals.

**Severity:** LOW — speculative. Unclear how often a structure summary distinguishes
biological function in the absence of any sequence-similarity hit.

**Open question:** is there a downstream analysis that would use this if it were
present? If not, defer.

---

## MCP-7 — *(Reclassified from F1 KG-ask)* Surface existing Polypeptide fields via the explorer

This is **not** a KG-side ask, but is included here because it was originally framed
as one in F1 of the trigger analysis. Documented for cross-reference.

**Gap.** `gene_details` projects `g{.*}` from the Gene node only — it does not
traverse `Gene_encodes_protein → Polypeptide` and so cannot return
`signal_peptide`, `transmembrane_regions`, `is_reviewed`, `annotation_score`,
`molecular_mass`, etc. The trigger analysis Q2 (proteome/transcriptome discordance)
needs these fields for axis 2 (protein size), axis 3 (architecture/localization),
and axis 11 (annotation quality at the Polypeptide level).

**Severity:** MED — directly blocks Q2 axes 2/3/11 from KG-side data; analyst has to
write Cypher.

**Proposed remediation.** Extend `gene_details` to optionally join Polypeptide
fields. F-AUDIT-4 (the audit's typed-`GeneDetailResult` finding) already proposes
giving `gene_details` a typed schema; that work and this fold together.

**Status:** explorer-side action; not in the KG-team scope. Added to the
explorer-side fix list, not this doc's primary asks.

---

## Cross-cutting notes for the KG team

**Pattern: stub strings instead of NULL.** KG-1 and KG-2 are the same shape:
the import path writes a placeholder string when no real content exists, instead
of leaving the field NULL. This pattern is worth a one-time sweep for similar cases
on other string fields — a query like:

```cypher
MATCH (n) UNWIND keys(n) AS k WITH labels(n)[0] AS label, k, n[k] AS v
WHERE v IS NOT NULL AND toString(v) IN ["N/A", "Alternative locus ID", "TBD", "None", "null", ""]
RETURN label, k, toString(v) AS stub_value, count(*) AS instances
ORDER BY instances DESC
```

would surface any other field/string-stub pair worth fixing. (Worth running once
on the next KG build.)

**Pattern: explorer can't tell "no data" from "out of scope".** KG-3 + KG-5 cover
the immediate case (TX50_RS) and the structural fix (per-Gene pipeline tracking).
Worth pairing in a single design conversation since KG-5 makes KG-3-style cases
self-documenting.

**Pattern: source-level proxies are tempting but term-level is correct.** KG-4
(informativeness flag) is the canonical instance, but the same pattern recurs in
analyses' temptation to assume "all entries from source X are content-bearing."
KG-side flagging at the term level eliminates the temptation cleanly.

---

## What's NOT in this doc

- **Explorer-side fixes** (boundary normalization of `"N/A"` and
  `"Alternative locus ID"` strings; F-AUDIT-1 / F-AUDIT-2 / F-AUDIT-3 / F-AUDIT-4
  / F-AUDIT-7 / F-AUDIT-8 from the usability audit). These ship independently
  on the explorer side.
- **Methodology / skill changes** (F7-A2/A3/B1–B5/C1–C4 in the trigger analysis).
  Lives in `multiomics_research` skill repo.

## Summary — per-item status

| # | Item | Class | Verified gap exists | Severity | Open design Qs |
|---|---|---|---|---|---|
| KG-1 | `function_description` placeholder | Data fix | ✓ 7,440 genes | HIGH | Other stub strings? Origin? |
| KG-2 | `GeneCluster` "N/A" → NULL | Data fix | ✓ 56% of clusters | HIGH | Other fields with same convention? |
| KG-3 | Re-run pipelines on TX50_RS set | Pipeline rerun | ✓ 14 genes affected | MED | Cyanorak rerun cost? |
| KG-4 | Term-level informativeness | Schema or list | ✓ no flag exists | MED | Where lives — KG flag, list, or hybrid? |
| KG-5 | Per-gene pipeline-scope tracking | Schema add | ✓ no tracking | MED | Property vs edge form? Stable list? |
| KG-6 | Cluster description curation | Data fix + schema flag | ✓ 0%–100% spread | MED | Which analyses are intentionally non-functional? |
| KG-7a | AA sequence string | Schema add | ✓ absent | LOW–MED | Per-node size limit still binding? |
| KG-7b | InterPro | Schema add | ✓ absent | LOW | Demand evidence? |
| KG-7c | AlphaFold | Schema add | ✓ absent | LOW | Demand evidence? |
| MCP-7 | Surface Polypeptide fields | Explorer-side | ✓ not surfaced | MED | (Not for KG team) |
