# KG-side asks for Chemistry MCP slice 1 (and forward-coordination notes)

**Date:** 2026-05-01
**Audience:** KG team conversation
**Companion to:** `multiomics_explorer/docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md`
**Verification state:** all current-state facts checked against live KG (`bolt://localhost:7687`) on 2026-05-01.

**Acceptance update (2026-05-01, post initial filing):** all 5 TCDB-S coordination suggestions and MET-M4 below have been **accepted into the TCDB-CAZy spec scope** by the KG team — see `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md` (the property-changes summary table cross-references TCDB-S1..S5 by name, and `evidence_sources` is documented as the open-ended set-membership-filter pattern from MET-M4). M1/M2/M3/M5 remain pre-spec for whenever the metabolomics-DM spec is written.

**Build update (2026-05-02):** all 4 direct asks (KG-A1..A4) **landed in the live KG**. Verified live: `Gene.reaction_count` populated on 97,513 genes (21,117 > 0; max 39); `Gene.metabolite_count` populated (max 66); `Metabolite.elements` populated (1,212 N-bearing, 695 P-bearing, 538 with both); `KeggTerm.reaction_count` / `metabolite_count` populated (ko00910 = 23 reactions / 18 metabolites). Chemistry slice-1 explorer build is unblocked.

This is the KG-side concentrate of the chemistry-slice-1 design. It collects:

1. **Direct asks** — small, mechanical schema additions the chemistry slice 1 explorer surface depends on. Solution-shaped because the patterns are unambiguous (mirrors of existing rollups).
2. **Coordination suggestions** for the in-flight TCDB-CAZy spec — where chemistry slice 1 needs hooks that fit naturally into TCDB scope. *All 5 accepted as of 2026-05-01.*
3. **Pre-spec suggestions** for the future metabolomics-DM spec — placeholder shape so the chemistry slice 1 row classes stay forward-compatible. *M4 (open-ended enum) confirmed in TCDB-CAZy doc; M1/M2/M3/M5 remain pre-spec.*

Slice 1 explorer code is **forward-compatible via `coalesce`** with everything below — KG asks land first, in parallel, or slightly after; nothing in the explorer is blocked.

## Summary of asks

| # | Item | Class | Severity | Status |
|---|---|---|---|---|
| **KG-A1** | `Gene.reaction_count: int` post-import rollup | Schema addition (post-import) | HIGH for explorer slice-1 | direct ask |
| **KG-A2** | `Gene.metabolite_count: int` post-import rollup, **defined as UNION across catalysis + transport paths** | Schema addition (post-import) | HIGH for explorer slice-1 | direct ask |
| **KG-A3** | `Metabolite.elements: list[str]` build-time Hill-parsed presence list | Schema addition (adapter) | HIGH for explorer slice-1 | direct ask |
| **KG-A4** | `KeggTerm.reaction_count` / `metabolite_count: int` pathway-level post-import rollups | Schema addition (post-import) | MED — not consumed in slice-1 explorer surface, but landing now avoids an extra rebuild later | direct ask |
| **TCDB-S1** | `Gene.tcdb_family_count: int` post-import rollup | TCDB-CAZy spec scope add | MED | coordination suggestion |
| **TCDB-S2** | `Gene.cazy_family_count: int` post-import rollup | TCDB-CAZy spec scope add | MED | coordination suggestion |
| **TCDB-S3** | Coordinate `Gene.metabolite_count` (KG-A2) UNION-across-paths definition | Cross-spec coordination | HIGH (avoids semantic divergence) | coordination suggestion |
| **TCDB-S4** | `TcdbFamily.metabolite_count: int` post-import rollup | TCDB-CAZy spec scope add | MED | coordination suggestion |
| **TCDB-S5** | (Optional) `TcdbFamily.tc_class_id: str \| None` sparse pointer | TCDB-CAZy spec scope add | LOW | coordination suggestion |
| **MET-M1** | `Metabolite.measurement_count: int` post-import rollup | Future metabolomics-DM spec | — pre-spec | suggestion |
| **MET-M2** | `Metabolite.compartments_observed: list[str]` post-import rollup | Future metabolomics-DM spec | — pre-spec | suggestion |
| **MET-M3** | `Metabolite.experiment_count: int` (optional) | Future metabolomics-DM spec | — pre-spec | suggestion |
| **MET-M4** | Formalize `evidence_sources` value `"metabolomics"` | Future metabolomics-DM spec | — pre-spec | suggestion |
| **MET-M5** | Edge structure: `Derived_metric_quantifies_metabolite` family + Metabolite-as-single-node rule | Future metabolomics-DM spec | — pre-spec | suggestion |

---

## Direct asks (chemistry slice 1)

### KG-A1 — `Gene.reaction_count: int` post-import rollup

**Friction.** `gene_overview` has no way to surface "this gene catalyzes reactions" as a routing signal. The LLM has to expand `Gene_catalyzes_reaction` per gene to find out — defeats the rollup-based routing pattern that the rest of the tool uses (`expression_edge_count`, `numeric_metric_count`, `cluster_membership_count`, etc.).

**Verification.** Live query 2026-05-01 confirms `Gene.reaction_count` does not exist:

```
WARNING: The label Gene does not have the following properties: reaction_count, metabolite_count.
```

`PMM0807` (pyruvate kinase) carries 26 Gene properties; chemistry-related rollups absent.

**Desired affordance.** `gene_overview(locus_tags=[...])` returns a `reaction_count: int` per row, defaulting to 0, that the LLM uses to route to `gene_metabolic_role` when > 0. Mirrors `expression_edge_count` semantics exactly.

**Resolution.** Single-hop count via `Gene_catalyzes_reaction`. Slot in Group 3 of `scripts/post-import.sh` next to the existing Gene rollups (lines 519-529 for `expression_edge_count` are the closest pattern):

```cypher
MATCH (g:Gene)
CALL {
  WITH g
  OPTIONAL MATCH (g)-[r:Gene_catalyzes_reaction]->()
  WITH g, count(r) AS rxn_count
  SET g.reaction_count = rxn_count
} IN TRANSACTIONS OF 1000 ROWS;
```

`count(r)` returns 0 on no-match — no separate defaults block needed (genes without chemistry edges land at 0 cleanly).

**Schema declaration:** add `reaction_count: int` to the `gene` entry in `config/schema_config.yaml`.

**Cost.** ~5 lines; one rollup pass over all ~81K Gene nodes. Fast.

---

### KG-A2 — `Gene.metabolite_count: int` post-import rollup, defined as UNION across all gene-reaching paths

**Friction.** Two problems in one ask.

*Problem 1 (today):* No `gene_overview` routing signal for "how many distinct metabolites does this gene's reactions touch". Same issue as KG-A1 — the rollup-based pattern needs a value here.

*Problem 2 (forward):* When the TCDB-CAZy spec ships, genes will reach metabolites via a *second* path (`Gene → TcdbFamily → Metabolite`). If `Gene.metabolite_count` is defined as catalysis-only, then either (a) it stays catalysis-only forever and a *second* property has to ship for the union (semantic mess), or (b) the definition silently changes when TCDB lands (breaking change for anyone consuming the catalysis-only number). Best to define the semantics correctly *up front*.

**Verification.** Same as KG-A1 — `Gene.metabolite_count` does not exist on Gene today.

**Desired affordance.** `gene_overview` returns a `metabolite_count: int` per row defined as:

> distinct count of `Metabolite` nodes reachable from this gene via *any* gene-reaching edge path — currently that's `Gene_catalyzes_reaction → Reaction → Reaction_has_metabolite`; on TCDB landing, also `Gene_has_tcdb_family → ... → Tcdb_family_transports_metabolite`.

Today's value reflects catalysis only because transport edges don't exist yet; on TCDB landing the count grows automatically without any explorer-side change.

**Resolution (slice 1 — catalysis only).** 2-hop DISTINCT count. Mirrors `Gene.compartments_observed`'s 2-hop pattern (lines 671-678 of `scripts/post-import.sh`).

```cypher
MATCH (g:Gene)
CALL {
  WITH g
  OPTIONAL MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)
                 -[:Reaction_has_metabolite]->(m:Metabolite)
  WITH g, count(DISTINCT m) AS met_count
  SET g.metabolite_count = met_count
} IN TRANSACTIONS OF 1000 ROWS;
```

**Resolution (post TCDB landing).** Same property; replace OPTIONAL MATCH with two arms unioned:

```cypher
MATCH (g:Gene)
CALL {
  WITH g
  OPTIONAL MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)
                 -[:Reaction_has_metabolite]->(m:Metabolite)
  WITH g, collect(DISTINCT m) AS catalysis_metabolites
  OPTIONAL MATCH (g)-[:Gene_has_tcdb_family]->(:TcdbFamily)
                 -[:Tcdb_family_is_a_tcdb_family*0..]->(:TcdbFamily {level_kind: 'tc_specificity'})
                 -[:Tcdb_family_transports_metabolite]->(t:Metabolite)
  WITH g, catalysis_metabolites + collect(DISTINCT t) AS all_metabolites
  SET g.metabolite_count = size(apoc.coll.toSet(all_metabolites))
} IN TRANSACTIONS OF 1000 ROWS;
```

(Exact form to be determined when TCDB-CAZy ships; this sketch shows the union pattern.)

**Schema declaration:** add `metabolite_count: int` to the `gene` entry in `config/schema_config.yaml` along with KG-A1.

**Cost.** ~8 lines today; 2-hop traversal over all ~81K Gene nodes; mirrors existing 2-hop rollup pattern.

**Coordination note:** see TCDB-S3 below — if the TCDB-CAZy spec lands first, this property must be defined as UNION-across-paths there to avoid a brief window of semantic divergence.

---

### KG-A3 — `Metabolite.elements: list[str]` build-time Hill-parsed presence list

**Friction.** Slice-1 chemistry tools want a clean element-presence filter (the N-source workflow's primitive: "metabolites that contain N"). Cypher `formula CONTAINS 'N'` is a footgun because `Cl`, `Na`, `Ne` all contain `N` as a substring and `C5H7N2O5` matches both `'C'` and `'Cl'` falsely. A regex-based fallback is doable in the query builder but every consumer reinvents it.

**Verification.** `Metabolite.formula` is populated on 2,157/2,188 nodes (98.6%) — clean Hill-notation strings (`H2O`, `C10H12N5O13P3`, `O2`). 31 metabolites lack `formula` (likely macromolecules / generic compounds).

**Desired affordance.** `Metabolite.elements: list[str]` — sorted unique element symbols present in `formula`. Per metabolite. Empty list when `formula` is null.

| `formula` | `elements` |
|---|---|
| `H2O` | `["H", "O"]` |
| `C10H12N5O13P3` | `["C", "H", "N", "O", "P"]` |
| `NaCl` (hypothetical) | `["Cl", "Na"]` (no false `["C", "H", "N"]`) |

Filter becomes trivial Cypher: `WHERE 'N' IN m.elements` — no regex, no element-clash footgun, no Hill-notation prose to maintain in tool descriptions.

**Resolution.** Build-time, in `metabolism_adapter.py` (or wherever `Metabolite.formula` is emitted). Hill parsing is a one-liner regex per formula:

```python
import re

_HILL_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")

def parse_elements(formula: str | None) -> list[str]:
    if not formula:
        return []
    return sorted({sym for sym, _ in _HILL_TOKEN.findall(formula) if sym})
```

**Schema declaration:** add `elements: list[str]` to the `metabolite` entry in `config/schema_config.yaml`.

**Cost.** ~30 minutes of build-time engineering; storage ~10 elements max per metabolite (negligible).

**Forward-compatible:** `element_counts: map<str,int>` can be added later if a threshold-filtering workflow ever arrives. Slice-1 does not need counts.

---

### KG-A4 — `KeggTerm.reaction_count` / `metabolite_count: int` pathway-level post-import rollups

**Friction.** Pathway-anchored chemistry exploration lacks at-a-glance "how much chemistry coverage does this pathway have in the KG" metadata. The data is already in the graph (via `Reaction_in_kegg_pathway` and `Metabolite_in_pathway` edges); it's just not pre-aggregated.

**Verification.** Live query 2026-05-01:
- `Reaction_in_kegg_pathway` covers 6,349 edges to 155 distinct pathways.
- `Metabolite_in_pathway` covers 8,095 edges to 310 distinct pathways.
- Pathway-level `KeggTerm` nodes have no chemistry rollups today.

**Desired affordance.** `KeggTerm.reaction_count: int` and `KeggTerm.metabolite_count: int` populated on pathway-level KeggTerms (filter by `level_kind` indicating pathway). Single-hop counts. Slice-1 explorer surface does NOT consume these directly — they're for the Tier-2 follow-up that surfaces them in `list_metabolites.by_pathway` envelope rows. The ask is filed now to avoid an extra rebuild when Tier-2 ships.

**Resolution.** Slot next to existing chemistry rollups in `scripts/post-import.sh` (lines 723-762):

```cypher
// Pathway-level filter — confirm the right level_kind value with KG team
MATCH (p:KeggTerm)
WHERE <pathway-level filter, e.g. p.level_kind = 'pathway' or p.id STARTS WITH 'kegg.pathway:'>
CALL {
  WITH p
  OPTIONAL MATCH (r:Reaction)-[:Reaction_in_kegg_pathway]->(p)
  WITH p, count(r) AS rxn_count
  SET p.reaction_count = rxn_count
} IN TRANSACTIONS OF 100 ROWS;

MATCH (p:KeggTerm)
WHERE <pathway-level filter>
CALL {
  WITH p
  OPTIONAL MATCH (m:Metabolite)-[:Metabolite_in_pathway]->(p)
  WITH p, count(m) AS met_count
  SET p.metabolite_count = met_count
} IN TRANSACTIONS OF 100 ROWS;
```

**Schema declaration:** add the two int properties to whichever `keggTerm` or pathway-level entry is the right home in `config/schema_config.yaml`.

**Open question for KG team:** what's the exact `level_kind` (or other discriminator) for pathway-level KeggTerms today? The chemistry layer doc says pathways live as `kegg.pathway:ko*` IDs — happy to use that string-prefix filter if `level_kind` isn't first-class.

**Cost.** ~10 lines; counts over ~310 pathway nodes; trivial.

---

## Coordination suggestions for the TCDB-CAZy spec (pre-development)

Reference: `multiomics_biocypher_kg/docs/superpowers/specs/2026-05-01-tcdb-cazy-ontologies-design.md`.

These are *additions to TCDB-CAZy spec scope* (small, high-leverage if they fit the natural authoring shape of that spec) plus one cross-spec coordination point.

### TCDB-S1 — `Gene.tcdb_family_count: int` post-import rollup

**Friction.** Without it, `gene_overview` has no routing signal for "this gene has TCDB annotations" — same issue as KG-A1 for catalysis. The LLM has to expand `Gene_has_tcdb_family` per gene.

**Affordance wanted.** Mirrors `expression_edge_count` / `numeric_metric_count` / KG-A1. The `Gene.annotation_types` extension already proposed in the TCDB-CAZy design spec adds `'tcdb'` as a presence flag — but presence-only doesn't give the LLM a *quantity* signal (e.g. "this gene has 3 TCDB family memberships across 2 levels").

**Resolution shape.** Single-hop count via `Gene_has_tcdb_family`, pattern-identical to KG-A1.

### TCDB-S2 — `Gene.cazy_family_count: int` post-import rollup

Same justification as TCDB-S1, paired. Single-hop count via `Gene_has_cazy_family`.

### TCDB-S3 — Coordinate `Gene.metabolite_count` (KG-A2) UNION-across-paths definition

**Friction.** If chemistry slice 1 ships KG-A2 with catalysis-only semantics and TCDB-CAZy ships first with a separate `Gene.transport_metabolite_count` (or similar), there's a brief window where consumers can't tell whether to sum two properties or use one. A property rename later would be a breaking change.

**Resolution.** Define `Gene.metabolite_count` as **UNION across catalysis + transport paths** in whichever spec lands first (chemistry slice 1's KG-A2 already does this). Today's value is catalysis-only because transport edges don't exist yet; on TCDB landing the count grows automatically without an explorer-side change. No second property needed.

**Action:** if TCDB-CAZy spec adds a `Gene.metabolite_count`-shaped property under any name, please use the chemistry-slice-1 KG-A2 definition (UNION). If TCDB-CAZy decides catalysis-only is wrong/right after considering this, please push back here so chemistry slice 1 can adjust.

### TCDB-S4 — `TcdbFamily.metabolite_count: int` post-import rollup

**Friction.** When `gene_ontology_terms(ontology="tcdb")` and `search_ontology` (existing MCP tools that auto-pick-up TcdbFamily nodes per the TCDB-CAZy design spec) surface results, there's no at-a-glance "how many distinct substrates does this family transport" rollup. Every other ontology has `gene_count` populated; TCDB families should have *both* `gene_count` (proposed in TCDB-CAZy spec) AND a substrate-side equivalent.

**Affordance wanted.** Distinct metabolites this family transports — including subtree (so `tc_class` nodes show total substrate breadth across descendants), mirrors how `BriteCategory.gene_count` is computed via subtree traversal.

**Resolution shape.** Subtree-aware count via `Tcdb_family_transports_metabolite` edges, walking through `Tcdb_family_is_a_tcdb_family*0..` from each TcdbFamily node. Pattern matches lines 704-721 in current `scripts/post-import.sh` (BriteCategory subtree rollup).

### TCDB-S5 — (Optional) `TcdbFamily.tc_class_id: str | None` sparse pointer

**Friction.** Class-level filtering ("show me everything under tc_class 1: Channels and Pores") today requires `MATCH (tf)-[:Tcdb_family_is_a_tcdb_family*0..]->(:TcdbFamily {tcdb_id: '1'})`. Variable-length traversals are expensive and the pattern is repetitive across queries.

**Affordance wanted.** Pre-computed sparse pointer to root `tc_class` per node. Allows `WHERE tf.tc_class_id = 'tcdb:3'` without traversal.

**Resolution shape.** BRITE precedent — `BriteCategory.tree` and `tree_code` are sparse class-level pointers. `TcdbFamily.tc_class_id` would be the analog (sparse on non-class nodes, self on class nodes).

**Defer if not naturally in scope.** Cypher traversal works for the slice-1 use case; this is a UX-and-perf nicety.

### Coordination note: removed `Gene.transporter_classification` array property

When TCDB-CAZy lands and removes `Gene.transporter_classification`, the explorer-side `gene_details` tool may surface this property today (uses `g{.*}` pattern). Verify and update that tool as part of the TCDB landing — orthogonal to chemistry slice 1.

---

## Pre-spec suggestions for the future metabolomics-DM spec

No metabolomics-DM spec exists yet. These are *pre-spec suggestions* — shape we'd like to see, will firm up when the spec gets written. Filed here so the chemistry slice 1 row classes stay forward-compatible (slice 1 row schema and filter slots accommodate a third evidence path without code change).

### MET-M1 — `Metabolite.measurement_count: int` post-import rollup

Routing signal for `list_metabolites` ("how many DM measurements touch this metabolite"). Mirrors `Reaction.gene_count` / `Gene.expression_edge_count`.

### MET-M2 — `Metabolite.compartments_observed: list[str]` post-import rollup

Distinct compartments where measured. Mirrors the existing `Gene.compartments_observed` pattern (DM-derived). Lets `list_metabolites` add a `compartment` filter cleanly when slice-N adds it.

### MET-M3 — `Metabolite.experiment_count: int` (optional)

Distinct experiments where measured. Less load-bearing than M1/M2.

### MET-M4 — Formalize `evidence_sources` value `"metabolomics"`

Coordinate with TCDB-CAZy spec (which introduces `"metabolism"` and `"transport"`) to use a stable enum across all three values. Chemistry slice 1 already accepts `"metabolomics"` as a forward-compatible filter value.

### MET-M5 — Edge structure for measurements

Likely `Derived_metric_quantifies_metabolite` / `_flags_metabolite` / `_classifies_metabolite` mirroring the existing Gene-DM family. Preserve direction-agnostic semantics (consistent with both chemistry-layer `Reaction_has_metabolite` and TCDB `Tcdb_family_transports_metabolite`). Preserve the rule "every measured metabolite is a `Metabolite` node, never a parallel type" — keeps slice-1 explorer tools' single-source-of-truth assumption intact.

---

## Build sequencing — KG side

1. **KG-A3** (`Metabolite.elements`) — adapter-time, smallest. Single PR; full rebuild required.
2. **KG-A1 + KG-A2 + KG-A4** — `scripts/post-import.sh` additions. Single PR; another full rebuild OR roll into the same rebuild as KG-A3 if convenient.

KG asks land before, in parallel with, or slightly after the explorer slice-1 PRs. Explorer code uses `coalesce(g.<prop>, 0)` to remain forward-compatible across timing variations.

The TCDB-CAZy spec is independent and lands on its own schedule; chemistry slice 1 adds *no* hard dependency on TCDB-CAZy timing — it adds *forward-compatibility hooks* (`evidence_source`, `evidence_sources`, `transporter_count` fields and filter slots) that populate gracefully when TCDB-CAZy ships.

The metabolomics-DM spec doesn't exist yet; the slice-1 row classes accept `"metabolomics"` as a value but no row will ever carry it until that KG spec ships.

---

## What we're explicitly NOT asking for

- **`Reaction_has_metabolite.role`** (substrate vs product) — would require external authoritative direction (Rhea reaction direction, manual curation, or thermodynamic computation). Not parsable from KEGG `name` (equation order is arbitrary). Out of scope until external data warrants.
- **`Reaction.equation` / `Reaction.systematic_name` parsing** — initially considered to recover direction info; user correction confirmed KEGG equation order is arbitrary, so the parsing would not buy what we wanted. Tools surface raw `Reaction.name` and document the compound `<systematic_name>; <equation>` format.
- **Substrate evidence quality flags** on TCDB substrates — TCDB substrates have varying evidence quality but slice 1 doesn't need this distinction. Defer until a real workflow demands it.
- **`Reaction.elements` / `OrganismTaxon.elements_observed`** rollups — derivable at query time via existing edges + KG-A3. Not worth materializing.
- **HMDB / InChI scalar indexes on Metabolite** — defer until a HMDB-by-ID or InChI-by-key lookup workflow is real.
- **`Metabolite.element_counts: map<str,int>`** — threshold filters ("metabolites with ≥3 N atoms") are nice-to-have; slice 1 only needs presence (KG-A3). Add later if a real workflow demands counts.

---

## References

- Chemistry layer (live): `multiomics_biocypher_kg/docs/kg-changes/metabolism-chemistry-layer.md`
- Chemistry slice 1 explorer design: `multiomics_explorer/docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md`
- TCDB-CAZy spec (KG-side, pre-development): `multiomics_biocypher_kg/docs/superpowers/specs/2026-05-01-tcdb-cazy-ontologies-design.md`
- TCDB-CAZy explorer-facing summary: `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`
- Prior KG-side asks (different topic, friction-first format precedent): `multiomics_explorer/docs/superpowers/specs/2026-05-01-kg-side-frictions-reframed.md`
