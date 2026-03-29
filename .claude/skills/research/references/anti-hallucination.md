# Anti-hallucination patterns

Concrete failure modes observed in LLM-driven omics analysis and
how to prevent them. Each pattern includes a real or realistic
example from this KG.

---

## Category 1: Gene identity errors

These are the most dangerous because they produce plausible but
wrong biological conclusions.

### 1.1 Paralog conflation

**What happens:** Multiple locus tags share a gene name. The LLM
groups them as "the same gene" and merges their expression data
into a single narrative.

**Real example (catalase analysis):** "katA is downregulated by
starvation (log2FC -7.8) then partially recovers at day 89
(log2FC +1.8)." Wrong — the downregulation is ACZ81_02025, the
"recovery" is ACZ81_11985. Different genes, opposite behaviors,
same name.

**Prevention:**
- After `resolve_gene` or `genes_by_function`, check if multiple
  locus tags share a gene name
- If yes: treat each locus tag as a separate entity throughout
- Never aggregate expression data across locus tags that share
  a name without explicitly noting they are paralogs
- In tables: always include locus_tag column; add a suffix like
  "katA-1", "katA-2" when presenting results

### 1.2 Ortholog cluster conflation

**What happens:** Genes in the same ortholog cluster are treated
as interchangeable. "katB" in one strain is reported using data
from "katE" in another strain because they share a cluster.

**Real example:** MIT1002_02513 (katE) and MIT1002_03530 (katB)
are both in cluster 4644E. The analysis reported katE expression
values as "katB" because the cluster matched.

**Prevention:**
- When reporting per-gene expression, use locus tags, not cluster
  membership
- Ortholog clusters are for cross-organism comparison of
  *conserved function*, not for within-organism gene equivalence
- If a gene has no expression data, say so — don't substitute
  a cluster-mate's data

### 1.3 Inventing gene functions

**What happens:** The LLM knows from training data that "gene X
is involved in pathway Y" and states this without querying the KG.
The KG may have different or no annotation for that gene.

**Prevention:**
- Gene function claims must come from `gene_overview`,
  `gene_ontology_terms`, or `genes_by_function` output
- Prefix intrinsic knowledge with: "Based on general knowledge
  (not from this KG)..."
- If the KG annotation disagrees with intrinsic knowledge, report
  the KG annotation and note the discrepancy

---

## Category 2: Narrative fabrication

The LLM constructs a coherent biological story that goes beyond
what the data supports.

### 2.1 Causal claims from correlational data

**What happens:** Expression data shows co-regulation. The LLM
writes "gene X regulates gene Y" or "condition A causes pathway B
to activate."

**Prevention:**
- Differential expression shows *association*, not causation
- Use language: "co-regulated", "correlated", "respond similarly"
- Reserve causal language for claims backed by specific evidence
  (which this KG does not contain — no ChIP-seq, no knockouts)

### 2.2 Cherry-picking from truncated results

**What happens:** MCP returns 50 rows (limit). The LLM reports
"the top 5 genes are..." without noting that 750 other genes
were not examined. Or worse: "gene X is NOT differentially
expressed" when it was simply outside the returned rows.

**Prevention:**
- Always check `truncated` and `total_matching` in MCP output
- Never infer absence from a truncated result set
- When summarizing: "Of {total_matching} significant genes, the
  top {n} by |log2FC| are..."
- For absence claims: must use a non-truncated result or a
  specific query for that gene

### 2.3 Selective reporting of duplicate entries

**What happens:** The KG has two entries for the same gene in the
same condition (different contrasts from the original DESeq2
analysis). The LLM reports only the significant one.

**Real example:** katG (ACZ81_16125) at day 89 in coculture has
two entries: +1.26 (padj 3e-4) and -1.16 (padj 0.29). Only the
significant one was reported.

**Prevention:**
- When multiple entries exist for the same gene/condition, report
  all of them
- Note that they likely represent different statistical contrasts
- If you cannot determine which contrast is relevant, flag the
  ambiguity rather than choosing one

### 2.4 Strength of language vs strength of evidence

**What happens:** The LLM uses confident language for weak evidence.
"katB is significantly downregulated" when padj = 0.050.
"Consistent with ROS detoxification" when there are no p-values.

**Prevention:**
- padj < 0.001: "strongly significant" / "highly significant"
- padj < 0.01: "significant"
- padj < 0.05: "nominally significant" or "borderline significant"
- padj = 0.05: "at the conventional threshold" — flag explicitly
- No padj: "fold-change of X (no statistical test available)"
- Never write "consistent with [mechanism]" for data without
  statistical support — use "suggestive of" or "potentially
  related to"

---

## Category 3: Data handling errors

### 3.1 Counting from truncated lists

**What happens:** `len(results)` used instead of `total_matching`.
"There are 50 genes responding to nitrogen stress" when there are
actually 823.

**Prevention:**
- Counts come from summary fields (`total_matching`,
  `total_entries`), never from `len(results)`
- If you need to count subcategories not in summary fields,
  extract full data first

### 3.2 Cross-study p-value comparison

**What happens:** "katA is more significantly affected by
starvation (padj 2e-11) than by coculture (padj 0.015)."
These p-values come from different studies with different designs,
sample sizes, and statistical power. They are not comparable.

**Prevention:**
- P-values are within-study measures — never compare across studies
- Compare effect sizes (log2FC) across studies if needed, but note
  the caveat
- For cross-study claims, use direction and rough magnitude, not
  precise p-value ranking

### 3.3 Fabricating summary statistics

**What happens:** The LLM computes a mean or percentage from
incomplete data in context and presents it as a finding.
"On average, catalase genes are downregulated 6.2-fold under
starvation" — computed from whatever rows were visible.

**Prevention:**
- Summary statistics must be computed in scripts over complete
  data, not eyeballed from MCP output
- If you report a summary statistic, cite the script that
  computed it
- For quick estimates in chat, explicitly say "rough estimate
  from the top N results" and never present as a finding

---

## Category 4: Knowledge boundary violations

### 4.1 Asserting absence

**What happens:** "Prochlorococcus does not have catalase genes."
True in this KG, but the LLM may state it as a universal fact
when it's a property of the KG's gene set.

**Prevention:**
- "No catalase genes are annotated in the KG for Prochlorococcus"
- Not: "Prochlorococcus lacks catalase"
- The KG reflects what was annotated and loaded — absence in the
  KG does not prove biological absence (though in this case the
  biological absence is well-established, that knowledge comes
  from training data, not the KG)

### 4.2 Assuming KG completeness

**What happens:** "All nitrogen-responsive genes in MED4 are..."
when the KG only contains results from specific experiments under
specific conditions.

**Prevention:**
- Qualify scope: "In experiment X, N genes were differentially
  expressed under nitrogen limitation"
- Not: "MED4 has N nitrogen-responsive genes"
- Always anchor claims to specific experiments and conditions

### 4.3 Literature claims without KG support

**What happens:** The LLM knows from training data that "gene X
has been shown to [function] in [organism] (Smith et al. 2020)"
but this publication is not in the KG and the claim cannot be
verified from the data.

**Prevention:**
- Clearly separate KG-derived findings from literature context
- Use a distinct format: "**From the KG:** ... **From the
  literature (not verified in this KG):** ..."
- If the user needs literature support, say so — this system is
  a KG explorer, not a literature review tool
- Never cite a specific paper from intrinsic knowledge as if
  it were a KG reference

---

## Quick self-check

Before presenting any finding, ask:

1. **Where did this number come from?** → Must name a tool call
   or script output
2. **Am I using a gene name or a locus tag?** → Must be locus tag
3. **Is this from complete data or truncated?** → Check `truncated`
4. **Am I comparing across studies?** → Can compare direction and
   magnitude, not p-values
5. **Am I claiming absence?** → Qualify with "in the KG" / "in
   this experiment"
6. **Is this KG data or my training knowledge?** → Label which is
   which
7. **Would a different paralog assignment change this conclusion?**
   → If yes, verify the assignment
