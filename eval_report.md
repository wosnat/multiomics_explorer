# MCP Evaluation Report

## Summary

- **Accuracy**: 10/10 (100.0%)
- **Average Duration**: 21.6s

---

### Task 1 ✅

**Question**: A Prochlorococcus MED4 gene shows the most extreme transcriptional upregulation in the entire knowledge graph under nutrient limitation conditions. This gene's log2 fold change exceeds 160. What is the EC number assigned to this gene? Respond in the format X.X.X.X (e.g., 1.2.3.4).

**Expected**: `3.1.3.1`

**Actual**: `3.1.3.1`

**Duration**: 39.8s

**Summary**: I queried `differential_expression_by_gene` for Prochlorococcus MED4 with `direction=up`, sorted by |log2FC|. The top result was PMM0708 (probable alkaline phosphatase) with log2FC = 162.295 under phosphate starvation (nutrient limitation). I then used `gene_ontology_terms` with `ontology=ec` to retrieve its EC number: **3.1.3.1** (alkaline phosphatase).

**Feedback**: Both tools worked well. The `differential_expression_by_gene` tool efficiently surfaced the top upregulated gene across all experiments when filtering by direction. The `gene_ontology_terms` tool with `ontology=ec` cleanly returned the EC annotation.

---

### Task 2 ✅

**Question**: Among the Prochlorococcus strains in the knowledge graph, genome sizes vary considerably between high-light and low-light adapted ecotypes. Which Prochlorococcus strain has the largest number of genes? Respond with the strain name only (e.g., MED4).

**Expected**: `MIT9313`

**Actual**: `MIT9313`

**Duration**: 18.4s

**Summary**: Used `list_organisms` to retrieve all organisms with gene counts. Filtered for Prochlorococcus strains and compared gene counts: MIT9313 (LLIV clade) had 2948 genes, the highest among all Prochlorococcus strains listed.

**Feedback**: The tool worked perfectly for this query — `list_organisms` returns gene counts directly, making strain comparison straightforward in a single call.

---

### Task 3 ✅

**Question**: Prochlorococcus strains are classified into light-adaptation clades (HLI, HLII, LLII, LLIV). The strain with the most differential expression experiments in the knowledge graph belongs to one of these clades. What is its clade designation? Respond with the clade abbreviation only.

**Expected**: `HLI`

**Actual**: `HLI`

**Duration**: 21.0s

**Summary**: Used `list_organisms` to retrieve all organisms with their experiment counts and clade designations. Prochlorococcus MED4 had the highest experiment count (46) among all Prochlorococcus strains, and its clade field shows "HLI".

**Feedback**: The tool worked perfectly for this query — organism listing with clade and experiment_count in a single call was exactly what was needed.

---

### Task 4 ✅

**Question**: A landmark 2007 study published in Nature examined genome-wide expression dynamics during cyanophage infection of a marine cyanobacterium, revealing features of host-virus co-evolution. Who is the first author of this publication? Respond with their last name only.

**Expected**: `Lindell`

**Actual**: `Lindell`

**Duration**: 18.9s

**Summary**: Used `list_publications` with a free-text search for "cyanophage infection genome-wide expression." The first result matched perfectly: a 2007 Nature paper on genome-wide expression dynamics during cyanophage infection of Prochlorococcus MED4, with Debbie Lindell as the first author.

**Feedback**: The tool worked well — a single call with targeted search text returned the exact publication as the top hit with full author list.

---

### Task 5 ✅

**Question**: The gene rbcL encodes the large subunit of the key carbon-fixing enzyme in cyanobacteria. In Prochlorococcus MED4 (locus tag PMM0550), this gene is annotated with a GO cellular component term indicating the subcellular structure where carbon fixation occurs. What is the name of this cellular compartment? Respond with the GO term name.

**Expected**: `carboxysome`

**Actual**: `carboxysome`

**Duration**: 15.6s

**Summary**: I used `gene_ontology_terms` with locus_tag `PMM0550` filtered to `go_cc` (GO cellular component). The result returned a single term: GO:0031470 "carboxysome".

**Feedback**: The tool worked perfectly for this single-step lookup — direct and efficient.

---

### Task 6 ✅

**Question**: One experiment in the knowledge graph has far more differential expression edges (Changes_expression_of relationships) than any other, with nearly 27,000 edges. This experiment studies a dark-tolerant co-culture phenotype. What is the full organism name profiled in this experiment? Respond with the complete organism name as it appears in the KG.

**Expected**: `Alteromonas macleodii MIT1002`

**Actual**: `Alteromonas macleodii MIT1002`

**Duration**: 19.4s

**Summary**: Used `list_experiments` with `search_text="dark tolerant"` to find experiments matching the dark-tolerant co-culture phenotype. The first result showed experiment ID `10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq` with `gene_count: 26992` (nearly 27,000), profiling `organism_name: "Alteromonas macleodii MIT1002"`.

**Feedback**: The `list_experiments` tool worked perfectly for this query — the `search_text` filter found the relevant experiments immediately, and the verbose output provided all needed details including organism name and gene count in a single call.

---

### Task 7 ✅

**Question**: Catalase is a critical enzyme for degrading hydrogen peroxide. In the knowledge graph, genes functionally annotated as "catalase" are found exclusively in organisms of one bacterial genus — none of the picocyanobacteria encode this enzyme. What is that genus? Respond with the genus name only.

**Expected**: `Alteromonas`

**Actual**: `Alteromonas`

**Duration**: 15.7s

**Summary**: Used `genes_by_function` with `search_text="catalase"` and `summary=true` to get the breakdown by organism. The results showed all 14 matches belong to Alteromonas macleodii strains, with zero hits in any Prochlorococcus (picocyanobacteria) organism.

**Feedback**: The tool worked perfectly for this query — the `by_organism` summary field in the response made it immediately clear which genus exclusively encodes catalase without needing to paginate through individual results.

---

### Task 8 ✅

**Question**: The Cyanorak curated ortholog group for the ribulose bisphosphate carboxylase large subunit (rbcL) contains members across picocyanobacterial genomes. Using differential expression data framed by this ortholog group, how many distinct experiments have expression measurements for its members? Respond with the number only.

**Expected**: `26`

**Actual**: `26`

**Duration**: 28.9s

**Summary**: 1. Searched for the Cyanorak rbcL ortholog group using `search_homolog_groups` with source=cyanorak, identifying `cyanorak:CK_00000681`.
2. Called `differential_expression_by_ortholog` with summary=true for that group ID, which returned `experiment_count: 26` directly in the summary fields.

**Feedback**: The tools worked smoothly. `search_homolog_groups` quickly identified the correct group, and `differential_expression_by_ortholog` with `summary=true` returned the experiment count directly without needing to paginate through results.

---

### Task 9 ✅

**Question**: An experiment studying Prochlorococcus MIT9313's transcriptomic response to viral dissolved organic matter (vDOM) is a time-course study that spans from sub-hour to multi-day intervals. How many distinct timepoints were measured in this experiment? Respond with the number only.

**Expected**: `9`

**Actual**: `9`

**Duration**: 17.2s

**Summary**: Used `list_experiments` with `search_text="vDOM viral dissolved organic matter"` and `organism="MIT9313"` to find the experiment. The result returned one matching experiment with a `timepoints` array containing 9 entries (0.5h, 1h, 2h, 4h, 8h, 12h, 24h, 48h, 72h).

**Feedback**: The tool worked well for this query. The `timepoints` array in the experiment result directly provided the count without needing additional queries.

---

### Task 10 ✅

**Question**: The gene petB is found in both cyanobacteria and heterotrophic bacteria in the knowledge graph. In Prochlorococcus, its product is annotated as "cytochrome b6", but in Alteromonas the annotation differs. What is the exact product name for petB in Alteromonas? Respond with the product name exactly as it appears in the KG.

**Expected**: `cytochrome b`

**Actual**: `cytochrome b`

**Duration**: 20.9s

**Summary**: I used `resolve_gene` with identifier "petB" filtered by organism "Alteromonas". All three Alteromonas strains (EZ55, HOT1A3, MIT1002) consistently annotate petB with the product name "cytochrome b", distinct from Prochlorococcus's "cytochrome b6".

**Feedback**: The `resolve_gene` tool was perfect for this — it returned product names directly in the results, no need for a follow-up `gene_details` call. The organism filter worked well to isolate Alteromonas entries.

---
