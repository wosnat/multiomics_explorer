# KG Changes for find_gene Improvements

Changes to make in `multiomics_biocypher_kg`. Once applied, rebuild KG and update explorer code to match.

---

## Gene Property Availability by Organism Group

Data from live KG (35,226 genes total).

### Core annotation fields

| Property | Alteromonas (12,195) | Prochlorococcus (17,098) | Synechococcus (5,933) |
|----------|---------------------|--------------------------|----------------------|
| `gene_summary` | 100% | 100% | 100% |
| `product` (non-hypothetical) | 89% (10,834) | 96% (16,365) | 92% (5,460) |
| `product` = "hypothetical protein" | 11% (1,361) | 4% (733) | 8% (473) |
| `gene_name` (real, not locus_tag) | **98%** (11,998) | 82% (14,015) | 43% (2,555) |
| `function_description` (non-null, non-"-") | **89%** (10,825) | 83% (14,209) | 71% (4,202) |
| `product_cyanorak` | **0%** | 87% (14,950) | 96% (5,708) |
| `gene_synonyms` | 99% (12,022) | 91% (15,545) | 86% (5,111) |
| `alternate_functional_descriptions` | 100% | 100% | 100% |

### Indexed text fields (currently in fulltext index)

| Property | Alteromonas | Prochlorococcus | Synechococcus | In index? |
|----------|-------------|-----------------|---------------|-----------|
| `gene_summary` | 100% | 100% | 100% | YES |
| `gene_synonyms` | 99% | 91% | 86% | YES |
| `product_cyanorak` | **0%** | 87% | 96% | YES |
| `alternate_functional_descriptions` | 100% | 100% | 100% | YES |
| `go_term_descriptions` | **0%** | 52% (8,887) | 57% (3,371) | YES |
| `pfam_names` | 87% (10,642) | 70% (11,955) | 68% (4,010) | YES |
| `pfam_descriptions` | **0%** | 63% (10,806) | 69% (4,104) | YES |
| `eggnog_og_descriptions` | **0%** | 63% (10,781) | 70% (4,158) | YES |

### Candidate fields NOT in index

| Property | Alteromonas | Prochlorococcus | Synechococcus | In index? |
|----------|-------------|-----------------|---------------|-----------|
| `product` | 100% | 100% | 100% | no |
| `gene_name` | 100% | 100% | 100% | no |
| `function_description` | 89% | 83% | 71% | no |

### Structured annotation (for annotation_quality scoring)

| Property | Alteromonas | Prochlorococcus | Synechococcus |
|----------|-------------|-----------------|---------------|
| `go_terms` | **70%** (8,514) | 63% (10,820) | 62% (3,679) |
| `kegg_ko` | 57% (6,976) | 51% (8,660) | 45% (2,671) |
| `ec_numbers` | 37% (4,472) | 39% (6,607) | 34% (2,003) |
| `pfam_ids` | 28% (3,363) | 62% (10,680) | 68% (4,012) |
| `cog_category` | 89% (10,825) | 83% (14,209) | 71% (4,202) |

### Functional role fields (for gene_category)

| Property | Alteromonas | Prochlorococcus | Synechococcus |
|----------|-------------|-----------------|---------------|
| `cyanorak_Role` | **0%** | 62% (10,622) | 67% (3,994) |
| `tIGR_Role` | **0%** | 74% (12,726) | 90% (5,311) |
| `cog_category` | 89% (10,825) | 83% (14,209) | 71% (4,202) |
| `cluster_number` | **0%** | 87% (14,949) | 96% (5,708) |

---

## Key Takeaways from the Data

1. **4 indexed fields are 0% for Alteromonas**: `product_cyanorak`, `go_term_descriptions`, `pfam_descriptions`, `eggnog_og_descriptions`. Alteromonas genes are effectively indexed on only `gene_summary`, `gene_synonyms`, `alternate_functional_descriptions`, and `pfam_names`.

2. **`product` and `gene_name` are 100% populated** across all organisms but not indexed. They're only searchable indirectly via `gene_summary`.

3. **`function_description` is 71-89% populated** and not indexed. For Alteromonas this is the richest text field (UniProt paragraphs).

4. **Alteromonas `gene_name` is misleading**: 98% "has real gene_name" but many are NCBI-style RefSeq locus tags (e.g., "ALTBGP6_RS00025") not biological gene names. These look different from locus_tag but aren't meaningful names.

5. **For `annotation_quality` scoring**: Alteromonas has 70% GO coverage (highest of the three groups!) but only 28% Pfam IDs. Prochlorococcus has the reverse: 62% Pfam IDs but 63% GO. The scoring formula should count any 2-of-4 (GO, KEGG, EC, Pfam) rather than requiring specific ones.

6. **For `gene_category`**: Alteromonas has 0% Cyanorak/TIGR roles but 89% COG categories. COG should be primary source for Alteromonas, with Cyanorak/TIGR for cyanobacteria.

---

## 1. Fulltext Index: Update Indexed Properties

### How `gene_summary` is built

```python
# gene_name :: product :: best_description
# best_description = first non-null of: uniprot_function, eggnog_desc, cyanorak_product, ncbi_product
# if best_description == product, it's dropped to avoid duplication
```

This means `gene_summary` already contains the full text of `gene_name`, `product`, AND `function_description` (the best available description). Nothing is truncated — full UniProt paragraphs are included.

### Current index (`geneFullText` on `:Gene`):
```
gene_summary, gene_synonyms, product_cyanorak, alternate_functional_descriptions,
go_term_descriptions, pfam_names, pfam_descriptions, eggnog_og_descriptions
```

### Proposed index:
```
gene_summary, gene_synonyms, alternate_functional_descriptions, pfam_names
```

### Changes:

**Remove 4 fields:**
- **Remove `product_cyanorak`** — 0% for Alteromonas, nearly identical to `product` for cyanobacteria, and `product` text is already in `gene_summary`.
- **Remove `go_term_descriptions`** — 0% for Alteromonas, only 52-57% for cyanobacteria. GO term names are already in `alternate_functional_descriptions` for genes that have them.
- **Remove `pfam_descriptions`** — 0% for Alteromonas, 63-69% for cyanobacteria. Pfam info is covered by `pfam_names` (better coverage) and `alternate_functional_descriptions`.
- **Remove `eggnog_og_descriptions`** — 0% for Alteromonas, 63-70% for cyanobacteria. eggNOG text is already in `gene_summary` (as `best_desc`) and `alternate_functional_descriptions`.

**Don't add `product`, `gene_name`, or `function_description`:**
All three are already fully contained in `gene_summary`. Adding them separately would only help with Lucene field-level score boosting (e.g., `product:photosystem^3`), which would also require query syntax changes in the explorer. Not worth the complexity.

**Net effect:** 4 indexed fields instead of 8. Better Alteromonas coverage (all 4 fields are populated vs only 4 of 8 before). Less redundancy, smaller index.

Keep `standard-no-stop-words` analyzer.

---

## 2. Clean Up `gene_summary` Construction

The `gene_name :: product :: best_desc` structure is good — keep it. Two fixes:

**a) Skip gene_name when it's just an identifier:**
- When `gene_name == locus_tag` (57% of Synechococcus, 18% of Prochlorococcus) — redundant
- When `gene_name` matches RefSeq pattern like `ALTBGP6_RS00025` — not a biological name, just a different identifier format

```python
gene_name = result.get("gene_name", "")
locus_tag = result.get("locus_tag", "")
if gene_name == locus_tag or re.match(r'^[A-Z]+\d+_RS\d+$', gene_name):
    gene_name = ""
```

**b) Skip best_desc when it's a "domain of unknown function" description:**
- eggNOG sometimes returns "Protein of unknown function (DUF3464)" which is less informative than the product itself
- Current priority chain (uniprot > eggnog > cyanorak > ncbi) picks this over nothing, but it adds noise

```python
if best_desc and re.match(r'^(Protein |Domain )of unknown function', best_desc):
    best_desc = ""
```

**Examples of improvement:**

| Before | After |
|--------|-------|
| `SYNW1033 :: photosystem II assembly factor, PAM68-like protein :: Protein of unknown function (DUF3464)` | `photosystem II assembly factor, PAM68-like protein` |
| `ALTBGP6_RS00025 :: type II toxin-antitoxin system death-on-curing family toxin :: Fic/DOC family` | `type II toxin-antitoxin system death-on-curing family toxin :: Fic/DOC family` |
| `SYNW1029 :: 23S rRNA (guanosine2251-2^-O)-methyltransferase :: Belongs to the class IV-like SAM-binding methyltransferase superfamily...` | `rlmB :: 23S rRNA (guanosine2251-2^-O)-methyltransferase :: Belongs to the class IV-like SAM-binding methyltransferase superfamily...` (unchanged — real gene name) |

---

## 3. Fix `annotation_quality` Scoring

**Current state:** All 35,226 genes have `annotation_quality = 2`.

**Proposed scoring** (compute during gene node creation):

| Score | Criteria | Expected counts |
|-------|----------|-----------------|
| 0 | `product` is "hypothetical protein" AND `function_description` is null/empty/"-" | ~1,000–1,500 |
| 1 | `product` is "hypothetical"/"conserved hypothetical" BUT has real `function_description` | ~1,000–1,500 |
| 2 | Has real product name (not hypothetical) | ~15,000–20,000 |
| 3 | Has real product AND at least 2 of: `go_terms`, `kegg_ko`, `ec_numbers`, `pfam_ids` (non-null, non-empty) | ~10,000–15,000 |

Notes from the data:
- The 2-of-4 threshold for level 3 works across organisms. Alteromonas leans on GO+KEGG (70%+57%), Prochlorococcus on Pfam+GO (62%+63%).
- `cog_category` is intentionally excluded from the level 3 check — it's very broad (89% Alteromonas coverage) and would inflate quality 3 too much.

---

## 4. Consider: `gene_category` Property (Lower Priority)

**Source priority** (use first non-null):
1. `cyanorak_Role[0]` — 62-67% for cyanobacteria, 0% Alteromonas
2. `tIGR_Role[0]` — 74-90% cyanobacteria, 0% Alteromonas
3. COG category from `cog_category[0]` — **89% Alteromonas**, 71-83% cyanobacteria
4. "Unknown" fallback

This gives ~90% coverage for Alteromonas (via COG) and ~90%+ for cyanobacteria (via Cyanorak/TIGR roles).

Normalize to ~20–30 controlled categories.

---

## 5. Consider: Vector Embeddings (Future)

Store a vector embedding on each Gene node for semantic similarity search. Neo4j vector indexes are supported since 5.11.

**What to embed:** Concatenate `product`, `function_description`, and `alternate_functional_descriptions` into a single text block per gene. Deduplicate across sources first (ncbi and cyanorak often say the same thing).

**Model options:**
- `text-embedding-3-small` (OpenAI) — cheap, good quality, 1536 dims
- `nomic-embed-text` — open source, runs locally, 768 dims

**Cost:** ~35K genes, average ~200 tokens each = ~7M tokens. Under $1 with OpenAI.

**Neo4j setup:**
```cypher
-- After loading embeddings as gene.embedding property:
CREATE VECTOR INDEX geneEmbedding FOR (g:Gene) ON (g.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}}
```

This enables queries like "genes involved in protecting against oxidative damage" matching genes annotated with "superoxide dismutase", "catalase", "peroxiredoxin" etc. — connections that lexical search misses.

---

## 6. Future Tool: Find Genes by GO / KEGG / EC (No KG Change Needed)

Gene nodes already have ID properties (`go_terms`, `kegg_ko`, `ec_numbers`) and edges to ontology nodes (`Gene_involved_in_biological_process → BiologicalProcess`, `Gene_catalyzes_ec_number → EcNumber`, `Gene_has_kegg_ko → KeggOrthologousGroup`). The ontology nodes have human-readable `name` properties.

**No need to add `_descriptions` properties** for these. The existing per-organism `go_term_descriptions` and `kegg_ko_descriptions` are only populated for Prochlorococcus/Synechococcus (0% Alteromonas), and the edge traversal works for all organisms.

**Proposed tool design** (explorer-side, no KG changes):

```
find_genes_by_function(
    search_text: str,          # e.g. "DNA replication", "2.7.7.7", "K02338"
    ontology: str | None,      # "go", "kegg", "ec" or None (search all)
    organism: str | None,
)
```

Query pattern:
1. If input looks like an ID (GO:*, K\d+, \d+\.\d+\.\d+\.\d+) → exact match on ontology node
2. If input is text → fulltext or CONTAINS search on ontology node `name`
3. Then traverse edges back to Gene nodes

Example Cypher for text search:
```cypher
MATCH (bp:BiologicalProcess)
WHERE bp.name CONTAINS $search_text
MATCH (g:Gene)-[:Gene_involved_in_biological_process]->(bp)
WHERE ($organism IS NULL OR g.organism_strain CONTAINS $organism)
RETURN g.locus_tag, g.gene_name, g.product, g.organism_strain,
       collect(bp.name) AS matching_processes
ORDER BY g.locus_tag
```

This is a graph-native approach — no denormalization, works across all organisms, always consistent with the ontology nodes.

---

## Summary Checklist

- [ ] Update fulltext index: remove `product_cyanorak`, `go_term_descriptions`, `pfam_descriptions`, `eggnog_og_descriptions`
- [ ] Clean up `gene_summary` construction: skip identifier-style gene_names, skip DUF best_desc
- [ ] Recompute `annotation_quality` with 0/1/2/3 scoring logic
- [ ] (Optional) Add `gene_category` property
- [ ] (Future) Add vector embeddings + vector index
- [ ] Rebuild KG
- [ ] Notify explorer repo to update `find_gene` results fields and `min_quality` docstring
