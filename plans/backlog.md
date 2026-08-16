# Explorer backlog

Deferred work with the reason for deferral and the trigger that should revive it.
Mirrors `multiomics_biocypher_kg/plans/backlog.md`.

---

## From the InterPro + TCDB integration (2026-08-16)

Scoping context: [docs/kg-specs/2026-08-16-interpro-tcdb-asks.md](../docs/kg-specs/2026-08-16-interpro-tcdb-asks.md)
and its [followup](../docs/kg-specs/2026-08-16-interpro-tcdb-followup-asks.md).
KG-side design: `multiomics_biocypher_kg/docs/superpowers/specs/2026-08-16-vocabulary-contract-design.md`.

### B-01 — `Pfam_in_interpro_entry` bridge (carved out of W1)

**What:** 5,972 `Pfam → InterproEntry` member-of edges linking the existing eggNOG Pfam
layer to the new InterPro layer. A link, explicitly **not** a merge.

**Deferred:** 2026-08-16, at scoping. W1 ships InterPro as a standalone ontology
(`InterproEntry` nodes, `Gene_has_interpro_entry`, is-a hierarchy, `(interpro_type, level)`
ORA stratification) without cross-layer traversal.

**Why:** the bridge is the one part of W1 that is not additive-in-isolation — it invites
`gene → Pfam → InterproEntry` and `gene → InterproEntry → Pfam` traversals whose precision
is unestablished, and the two layers are ~88% redundant by construction (InterPro
integrates Pfam). Shipping the ontology first lets us see whether anyone needs the bridge
before designing guardrails for it.

**Trigger:** a concrete question that needs Pfam↔InterPro crosswalk — e.g. "which Pfam
domains does this InterPro family integrate?" — or evidence users are hand-rolling the
join through `run_cypher`.

**Note:** the circularity caveat in `interpro-two-layer.md` applies if this ever lands —
eggNOG-Pfam and InterPro-Pfam are the *same* signal and must not be counted as two
independent sources.

### B-02 — W2: provenance filters on gene→ontology tools

**What:** `source_filter` / `evidence_filter` parameters on `genes_by_ontology`,
`gene_ontology_terms`, `pathway_enrichment`, `cluster_enrichment`, reading the new edge
`sources` / `evidence` / `evidence_score`.

**Deferred:** 2026-08-16. **Read-only surfacing of `evidence` / `sources` is NOT deferred**
— it moved into W4 as a regression fix, because the 45,226 InterPro-inferred GO edges
already change existing tool output invisibly. Only the *filter parameters* are backlogged.

**Why:** filtering is new capability; surfacing is a correctness fix for output users
already receive. Separating them keeps W4 shippable.

**Trigger:** users asking "curated only" questions once `evidence` is visible in results —
which surfacing will reveal.

**Depends on:** KG-IPT-008 (relationship property index on `evidence`) becomes worth
requesting at this point: the filters run over `Gene_involved_in_biological_process`
(539,873 edges) and `Gene_has_pfam` (177,453). Explicitly not requested for the current
release.

### B-03 — W3: ontology→ontology router edges

**What:** six edge types — `Interpro_entry_related_to_{ec_number,cazy_family}` (6,854 +
122) and `Tcdb_family_{has_pfam_domain, involved_in_biological_process,
enables_molecular_function, located_in_cellular_component}` (1,856 + 2,588 + 2,266 +
1,708).

**Deferred:** 2026-08-16, confirmed twice.

**Why:** recall-biased and direction-load-bearing. Forward (family known → does the xref
agree?) is 85% corroborating; reverse (gene has the domain → is it a transporter?) is
~31%. They add no gene-level annotation, and exposing them safely needs an explicit
opt-in "candidate/router" mode that can never leak into annotation tools.

**Trigger:** a real user need for candidate-function questions.

**Note:** the KG deleted both Layer-A edge properties at design rev 4–5 (`ambiguous` was
uniformly false and derivable; `source_db` was a hardcoded constant), so these edges now
carry **no properties** — the edge type is the entire fact. Any future design starts from
that.

### B-05 — W4: TCDB / metabolite-count regression bucket

**What:** five unrelated items sharing only a trigger (the KG two-source upgrade). See
§"Release-coupling" below — they do **not** share a deadline.

| # | Item | Nature | Release-coupled? |
|---|---|---|---|
| a | `transport_confidence` derived from `level_kind='tc_specificity'` → must read `substrate_depth` (`most_specific`), or adopt `Gene.transport_substrate_resolution` | semantic | **yes** |
| b | `gene_overview.metabolite_count` narrowed to catalysis-only; needs `transported_metabolite_count` as its own column | new column | **yes** |
| c | `list_metabolites.transporter_count` redefined (244 → 1,462 non-zero) | verify rollups | no — verification only |
| d | `genes_by_boolean_metric` docs claim `flag=False` returns 0 rows; 938 `false` edges exist | docs, 4 sites + CLAUDE.md | no — but wrong today |
| e | Surface `evidence` / `sources` as row fields (45,226 inferred GO edges are invisible) | new row fields | no |

**Deferred:** 2026-08-16, by scoping decision — InterPro integration is scoped and built
alone, so W1 is not held up by items with different gates.

> **Commitment (agreed 2026-08-16): W4 is done BEFORE the coordinated release, not after.**
> This entry is a sequencing deferral, not a drop. The explorer raised that (a) and (b)
> are release-coupled — shipping without them would put a knowingly-wrong
> `transport_confidence` and `metabolite_count` into the released MCP — and the agreed
> plan is InterPro first, then W4, then cut the release. **The release must not be cut
> with this entry still open.** Treat an open B-05 at release-preflight as a blocker, not
> a nice-to-have.

**Release-coupling — the reason this entry exists.** Items (a) and (b) are not
pre-existing bugs that can wait; they are **caused by** the KG change this release
delivers. If the coordinated KG + MCP release ships without them, the released MCP
reports `family_inferred` for ~96% of substrate edges that are not, and reports
`metabolite_count = 0` for 25,491 genes that carry transporter chemistry. `mcp_min_version`
does not protect against this — it guards old-MCP-against-new-KG, whereas this is the
newly-released MCP being wrong against the KG it shipped with.

(c) is verification, (d) is a doc edit, (e) is genuinely new capability.

**Trigger:** W1 (InterPro) landing. W4 is the next piece of work after it, ahead of the
release cut. (c) is verification that can fold in cheaply at that point; (e) is the only
item that may legitimately slip past the release, being new capability rather than a
regression.

**Release-preflight check.** Before cutting the coordinated release, confirm all of:

```cypher
// (a) no query builder still derives transport confidence from level_kind
```
```bash
grep -rn "tc_specificity" multiomics_explorer/api/functions.py multiomics_explorer/kg/queries_lib.py
#   expect: no hits in the transport_confidence derivation (functions.py:~5718, queries_lib.py:~6954)
grep -rn "always 0 in the current KG\|dm_false_count=0\|flag_false_count=0" multiomics_explorer/ CLAUDE.md
#   expect: no hits  — (d)
grep -n "transported_metabolite_count" multiomics_explorer/kg/queries_lib.py
#   expect: present in gene_overview + list_organisms builders — (b)
```

### B-04 — Adopt the `ControlledVocabulary` contract as the source of truth

**What:** make `list_filter_values` and the Pydantic `Literal` types data-driven off the
KG's `ControlledVocabulary` nodes, and check `Schema_info.controlled_vocabularies_hash`
in `kg_release_info` to detect vocabulary drift.

**Deferred:** 2026-08-16 — the contract does not exist in a deployed build yet.

**Why:** this is the payoff of KG-IPT-001. Until it lands, the explorer hard-codes the
vocabularies and drifts silently when the KG adds a value.

**Trigger:** the rebuilt KG ships `ControlledVocabulary` nodes + the hash.
