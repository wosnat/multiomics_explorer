# Agent Logic & Tool Definitions

This document outlines the specialized tools and reasoning strategies used by the Agent to interpret microbial interactions.

## Reasoning Strategy: GraphRAG
The agent does not just "search"; it follows a **Plan-and-Execute** pattern:
1. **Entity Extraction:** Identify genes (e.g., *ntcA*, *amtB*), metabolites, and strains from the user query.
2. **Pathfinding:** Query the KG for relationships (e.g., `UPREGULATED_IN`) under specific environmental stressors (e.g., $N$-starvation).
3. **Mechanism Synthesis:** Compare retrieved data against the four primary interaction models.

## 🔧 Toolset Definitions

### 1. `cypher_query_tool`
- **Purpose:** Executes read-only Cypher queries to retrieve quantitative omics data.
- **Guardrail:** Automatically appends `WHERE r.adj_pvalue < 0.05` to ensure statistical significance.

### 2. `biological_context_tool` (Vector Search)
- **Purpose:** Searches the `Neo4jVector` index for unstructured text from the 19 transcriptome papers.
- **Use Case:** "Why is 2-oxoglutarate important for C/N balance?"

### 3. `id_mapper_tool`
- **Purpose:** Translates common gene names to `locus_tag` or `CLOG_id` to prevent query failure.

## 🔬 Interaction Mechanisms to Identify
The agent is specifically prompted to look for these "Transcriptomic Signatures":

| Mechanism | Prochlorococcus Markers | Alteromonas Markers |
| :--- | :--- | :--- |
| **ROS Detox** | $hli$ genes, $SOD$ | $katG$ (Catalase) |
| **N-Recycling** | $ntcA$, $amtB$, $glnA$ | Proteases, Peptidases |
| **Cross-feeding** | BCAA Synthesis | BCAA Transporters |

## ⚖️ Evaluation Rubric (LLM-as-a-Judge)
Final answers are scored (1-5) based on:
- **Faithfulness:** Does the answer contradict the `log2FoldChange` in the graph?
- **Specificity:** Are exact locus tags and strain IDs provided?
- **Context:** Does it correctly identify the metabolic "Black Queen" dependency?
