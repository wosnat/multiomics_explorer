"""Example: working with metabolites in the KG.

Demonstrates the three Metabolite-source pipelines (transport / gene reaction /
metabolomics) and the workflow patterns for each. See
docs://analysis/metabolites for the LLM-facing guide; this script is its
runnable companion.

Each scenario function names the source(s) it touches and the metabolite-source
caveat it surfaces. Print intermediate envelope state to teach the LLM how to
read responses, not just consume detail rows.

Run with: uv run python examples/metabolites.py --scenario <name>

Scenarios: see CONTENTS below.

Notes:
- Metabolite IDs: bare / xref forms (`C00064`, `CHEBI:...`, `HMDB...`, `MNXM...`)
  are coerced to canonical `kegg.compound:C00064` and reported in
  `resolved_aliases`; the canonical prefixed form skips coercion.
- evidence_sources filter is needed to narrow at-scale; per-row schema is union
  (metabolism rows have reaction_id/ec_numbers; TCDB transport rows have
  tcdb_route/tcdb_family_id/tcdb_identity/tcdb_calls; cross-arm fields default to
  explicit None).
- TCDB transport rows are direct by default (the gene's own call onto a TCDB
  system). include_tcdb_family_substrates=True adds family-level rows for
  genes TCDB could not place in a system (a recall expansion).
- list_metabolites passes through `measured_assay_count`, `measured_paper_count`,
  `measured_organisms`, `measured_compartments` per row. Use these to find
  measured-and-transport-able metabolites in one call.
"""
# CONTENTS
#   1. scenario_discover            — element + organism filter (line ~74)
#   2. scenario_compound_to_genes   — evidence_source split on glutamine (line ~113)
#   3. scenario_gene_to_metabolites — element signature + top_metabolite_pathways (line ~204)
#   4. scenario_cross_feeding       — bridge MED4 -> ALT (line ~257)
#   5. scenario_n_source_de         — N-source primitive -> DE (line ~396)
#   6. scenario_tcdb_chain          — direct vs family TCDB rows (line ~515)
#   7. scenario_measurement         — P-stress metabolomics via MetaboliteAssay tools (line ~610)
from __future__ import annotations

import argparse
import sys
from typing import Callable

from multiomics_explorer import (
    assays_by_metabolite,
    gene_response_profile,
    genes_by_metabolite,
    genes_by_ontology,
    list_metabolite_assays,
    list_metabolites,
    metabolites_by_flags_assay,
    metabolites_by_gene,
    metabolites_by_quantifies_assay,
    search_ontology,
)


CURRENCY_METABOLITES_MIN8: frozenset[str] = frozenset({
    "kegg.compound:C00001",  # H2O
    "kegg.compound:C00011",  # CO2
    "kegg.compound:C00002",  # ATP
    "kegg.compound:C00008",  # ADP
    "kegg.compound:C00020",  # AMP
    "kegg.compound:C00009",  # Orthophosphate (Pi)
    "kegg.compound:C00013",  # Diphosphate (PPi)
    "kegg.compound:C00003",  # NAD+
    "kegg.compound:C00004",  # NADH
    "kegg.compound:C00005",  # NADPH
    "kegg.compound:C00006",  # NADP+
})


def scenario_discover() -> None:
    """Use this when the user asks 'what N-bearing metabolites does the KG track?'

    Sources: reaction + transport (both annotation arms surface chemistry).
    Caveat surfaced: none specific (this is a discovery primitive).
    """
    print("=== Scenario: discover ===")
    print("Question class: 'what metabolites match these chemistry filters?'")
    print()

    result = list_metabolites(
        elements=["N"],
        organism_names=["Prochlorococcus MED4"],
        limit=5,
    )
    print(f"returned={result['returned']}  truncated={result['truncated']}  "
          f"total_matching={result.get('total_matching')}")

    top_paths = result.get("top_metabolite_pathways") or []
    print(f"top_metabolite_pathways: {[p.get('metabolite_pathway_name') for p in top_paths][:5]}")

    by_es = result.get("by_evidence_source") or []
    print(f"by_evidence_source: {[(e.get('evidence_source'), e.get('count')) for e in by_es]}")

    top_orgs = result.get("top_organisms") or []
    print(f"top_organisms: {[(o.get('organism_name'), o.get('count')) for o in top_orgs][:5]}")
    print(f"xref_coverage: {result.get('xref_coverage')}")
    print()
    print("First metabolites (id | name | catalyst_gene_count | transporter_gene_count | evidence_sources):")
    for row in result["results"][:5]:
        print(
            f"  {str(row.get('metabolite_id', '?'))[:18]:<18} "
            f"{str(row.get('name', '?'))[:30]:<30} "
            f"catalyst_gene_count={row.get('catalyst_gene_count')}  "
            f"transporter_gene_count={row.get('transporter_gene_count')}  "
            f"evidence={row.get('evidence_sources')}"
        )


def scenario_compound_to_genes() -> None:
    """Use this when the user asks 'which MED4 genes act on glutamine?'

    Sources: reaction + transport (response is split by evidence_source).
    Caveat surfaced: metabolism vs transport semantics differ; row counts
    are not comparable (a reaction row and a transporter row answer
    different questions). Per-row schema is union — metabolism rows carry
    reaction_id/ec_numbers; TCDB rows carry tcdb_route/tcdb_family_id/
    tcdb_identity/tcdb_calls.

    Two-step chain: name → metabolite_id (via list_metabolites search)
    → genes (via genes_by_metabolite). Most user-facing questions arrive
    by metabolite NAME, not by KEGG ID, so the search step is the
    realistic entry point.
    """
    print("=== Scenario: compound_to_genes ===")
    print("Question class: 'which genes catalyse / transport this compound?'")
    print()

    # Step 1: name → KEGG ID via free-text search.
    print("Step 1: resolve name → KEGG ID via list_metabolites(search_text='glutamine')")
    name_lookup = list_metabolites(search_text="glutamine", limit=5)
    print(f"  returned={name_lookup['returned']}  total_matching={name_lookup['total_matching']}")
    for row in name_lookup["results"][:5]:
        print(f"  {row['metabolite_id']:<25} {row['name']}")
    # Pick the canonical L-Glutamine match (KEGG C00064) — N-bearing; in MED4
    # it has metabolism rows and no direct TCDB transporter (the envelope's
    # tcdb_family_substrates_not_shown counts the family-level candidates).
    canonical_id = next(
        (row["metabolite_id"] for row in name_lookup["results"]
         if row.get("name") == "L-Glutamine"),
        None,
    )
    if canonical_id is None:
        print("(L-Glutamine not found in KG — try a different name)")
        return
    print(f"  → picked canonical match: {canonical_id}")
    print()

    # Step 2: genes_by_metabolite on the canonical ID.
    print(f"Step 2: genes_by_metabolite(metabolite_ids=[{canonical_id!r}], organism='MED4')")
    result = genes_by_metabolite(
        metabolite_ids=[canonical_id],
        organism="MED4",
        limit=10,
    )
    print(f"returned={result['returned']}  total_matching={result.get('total_matching')}  "
          f"truncated={result['truncated']}")

    by_es = result.get("by_evidence_source") or []
    print(f"by_evidence_source: {[(e.get('evidence_source'), e.get('count')) for e in by_es]}")
    by_route = result.get("by_tcdb_route") or []
    print(f"by_tcdb_route: {[(e.get('tcdb_route'), e.get('count')) for e in by_route]}")
    print(f"tcdb_family_substrates_not_shown: {result.get('tcdb_family_substrates_not_shown')}")
    top_genes = result.get("top_genes") or []
    print("top_genes (tcdb_assignment_count is a gene-level KG count, not per row):")
    for g in top_genes[:5]:
        print(
            f"  {g.get('locus_tag', '?'):<12} "
            f"tcdb_direct_rows={g.get('tcdb_direct_rows')}  "
            f"tcdb_assignment_count={g.get('tcdb_assignment_count')}"
        )
    print(f"warnings: {result.get('warnings', [])}")
    print()
    print("First 10 (gene, evidence_source, [reaction|transport-specific fields]):")
    for row in result["results"][:10]:
        es = row.get("evidence_source", "?")
        if es == "metabolism":
            ecs = row.get("ec_numbers") or []
            print(
                f"  {row.get('locus_tag', '?'):<12} metabolism  "
                f"reaction={str(row.get('reaction_id', '?'))[:25]:<25} "
                f"ec={ecs[:2] if ecs else '-'}"
            )
        elif es == "transport":
            print(
                f"  {row.get('locus_tag', '?'):<12} transport   "
                f"route={str(row.get('tcdb_route', '?')):<7} "
                f"identity={row.get('tcdb_identity')}  "
                f"calls={row.get('tcdb_calls')}  "
                f"system={str(row.get('tcdb_family_id', '?'))}"
            )
        else:
            print(f"  {row.get('locus_tag', '?'):<12} {es}")
    print()
    print("LESSON: rows have UNION shape — different fields per evidence_source.")
    print("        Counts NOT comparable across arms (reaction vs transporter evidence).")
    print("        TCDB rows: direct = the gene's own system call; rank by tcdb_identity,")
    print("        then tcdb_calls (eggnog + a DIAMOND kind = independent agreement).")


def scenario_gene_to_metabolites() -> None:
    """Use this when the user asks 'what metabolites does PMM0001 act on?'

    Sources: reaction + transport.
    Caveat surfaced: chemistry-side `top_metabolite_pathways`
    (Reaction-anchored) is NOT the same surface as gene-KO pathways from
    `genes_by_ontology(ontology='kegg')`.
    """
    print("=== Scenario: gene_to_metabolites ===")
    print("Question class: 'what does this gene act on (chemistry)?'")
    print()

    result = metabolites_by_gene(
        locus_tags=["PMM0001"],
        organism="MED4",
        limit=10,
    )
    print(f"returned={result['returned']}  total_matching={result.get('total_matching')}")

    by_el = result.get("by_element") or []
    print(f"by_element (chemistry signature): "
          f"{[(e.get('element'), e.get('metabolite_count')) for e in by_el[:6]]}")
    print()
    chem_pathways = result.get("top_metabolite_pathways") or []
    print("top_metabolite_pathways (chemistry-side, via Reaction → KeggTerm):")
    for p in chem_pathways[:5]:
        print(
            f"  {str(p.get('metabolite_pathway_id', '?'))[:24]:<24} "
            f"{str(p.get('metabolite_pathway_name', '?'))[:40]:<40} "
            f"genes={p.get('gene_count')}"
        )
    print()
    print("NOTE: this is NOT the same surface as gene-KO pathways from")
    print("      genes_by_ontology(ontology='kegg', term_ids=...) — that's KO-anchored.")
    print()
    print("First 10 (metabolite, evidence_source, [arm-specific]):")
    for row in result["results"][:10]:
        es = row.get("evidence_source", "?")
        if es == "metabolism":
            print(
                f"  {str(row.get('metabolite_id', '?'))[:18]:<18} "
                f"{str(row.get('metabolite_name', '?'))[:30]:<30} "
                f"metabolism  reaction={str(row.get('reaction_id', '?'))[:18]}"
            )
        elif es == "transport":
            print(
                f"  {str(row.get('metabolite_id', '?'))[:18]:<18} "
                f"{str(row.get('metabolite_name', '?'))[:30]:<30} "
                f"transport   route={row.get('tcdb_route', '?')} "
                f"identity={row.get('tcdb_identity')}"
            )


def scenario_cross_feeding() -> None:
    """Use this when the user asks 'what could MED4 produce that ALT might consume?'

    Sources: reaction + transport (annotation-only).

    Workflow B′ has THREE structural confounders that compound; each requires
    a workflow-side mitigation:

    1. Currency-cofactor flooding (metabolism arm) — top_metabolites is sorted
       by gene_count, which is exactly the wrong sort for cross-feeding because
       the highest-reach metabolites are universal cofactors (H2O, ATP, ADP,
       Pi, PPi, NAD(P)(H)). Mitigation: pass CURRENCY_METABOLITES_MIN8 directly
       as `exclude_metabolite_ids=` on metabolites_by_gene / genes_by_metabolite
       (tool-side set-difference; exclude wins on overlap; envelope rollups
       also benefit). Extend the blacklist if H+, glutamate/
       glutamine, or coenzyme A dominate results in your seed. The printed
       output deliberately keeps H+ outside the minimal-8 blacklist — proton
       channels (MotA/TolQ/ExbB family) surface in the transport arm and
       demonstrate when extension is warranted.
    2. Family-level reach (transport arm) — family rows
       (include_tcdb_family_substrates=True) carry a whole family's curated
       range, not a per-gene substrate. Mitigation: keep the default direct
       rows on Step 2 and rank them by tcdb_identity, then tcdb_calls.
    3. Transport polarity is node-level at best — TCDB rows carry
       tcdb_direction (uptake / export / unknown), stated by TCDB for the
       node, not measured per gene; most nodes read unknown. Even with
       clean filters, the result is 'compatible with cross-feeding',
       never confirmed.

    Seed choice: 6 MED4 N-metabolism genes derived live from
    genes_by_ontology(ontology='kegg', term_ids=['kegg.pathway:ko00910']).
    The cyn cluster (cynABDS) is biologically motivated for cross-feeding —
    cyanate is a small N-bearing solute bacteria can release/consume. Both
    arms exercised: 3 transporters + 3 metabolism genes (cynS + glnA + glsF).
    """
    print("=== Scenario: cross_feeding (Workflow B') ===")
    print("Question class: 'between-organism metabolic coupling candidates'")
    print()

    print("Step 0: derive a biologically-motivated seed via KEGG N-metabolism pathway")
    seed_query = genes_by_ontology(
        organism="MED4",
        ontology="kegg",
        term_ids=["kegg.pathway:ko00910"],  # Nitrogen metabolism
    )
    seed_locus_tags = sorted({row["locus_tag"] for row in seed_query["results"]})
    print(f"  → {len(seed_locus_tags)} MED4 N-metabolism genes:")
    for row in seed_query["results"][: len(seed_locus_tags)]:
        print(
            f"    {row['locus_tag']:<10} {(row.get('gene_name') or '?'):<8} "
            f"{(row.get('product') or '')[:55]}"
        )
    print()

    print(f"Step 1: MED4 chemistry for {len(seed_locus_tags)} N-metabolism genes")
    print("  (exclude_metabolite_ids=CURRENCY_METABOLITES_MIN8 — confounder #1, tool-side)")
    med4 = metabolites_by_gene(
        locus_tags=seed_locus_tags,
        organism="MED4",
        exclude_metabolite_ids=list(CURRENCY_METABOLITES_MIN8),
        summary=True,
    )
    by_es_med4 = med4.get("by_evidence_source") or []
    print(f"  total_matching={med4.get('total_matching')}  "
          f"by_evidence_source={[(e['evidence_source'], e['count']) for e in by_es_med4]}")
    top_metabs = med4.get("top_metabolites") or []

    print("  top_metabolites (currency already excluded by the tool):")
    for r in top_metabs:
        print(
            f"    {r['metabolite_id']:<22} {(r.get('name') or '?'):<32} "
            f"metab={r.get('metabolism_rows')} "
            f"tcdb_direct={r.get('tcdb_direct_rows')} "
            f"tcdb_family={r.get('tcdb_family_rows')}"
        )

    metabolite_ids = [
        m["metabolite_id"] for m in top_metabs if m.get("metabolite_id")
    ]
    print(f"  → {len(metabolite_ids)} non-currency metabolites carry forward")
    print()

    if not metabolite_ids:
        print("(no non-currency metabolites — extend the seed or relax the blacklist)")
        return

    print(f"Step 2: which Alteromonas genes touch any of the {len(metabolite_ids)} metabolites?")
    print("  (split per-arm so both transport and metabolism get airtime;")
    print("   direct TCDB rows only — include_tcdb_family_substrates stays off;")
    print("   exclude_metabolite_ids=CURRENCY repeated as belt-and-braces guard)")
    alt_transport = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="Alteromonas macleodii HOT1A3",
        evidence_sources=["transport"],
        exclude_metabolite_ids=list(CURRENCY_METABOLITES_MIN8),
        limit=8,
    )
    alt_metab = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="Alteromonas macleodii HOT1A3",
        evidence_sources=["metabolism"],
        exclude_metabolite_ids=list(CURRENCY_METABOLITES_MIN8),
        limit=8,
    )
    print(f"  transport-arm: total_matching={alt_transport.get('total_matching')}")
    print(f"  metabolism-arm: total_matching={alt_metab.get('total_matching')}")
    print()
    print("  CAVEATS — Workflow B′ is 'compatible with cross-feeding', never confirmed:")
    print("    1. Currency cofactors blacklisted above (mitigated)")
    print("    2. Direct TCDB rows only (family-level reach left out)")
    print("    3. Transport polarity is node-level at best (tcdb_direction is")
    print("       TCDB's statement about the system, not the gene). The Track-B measurement")
    print("       layer can corroborate (extracellular elevation in coculture) but")
    print("       cannot confirm causality.")
    print()

    print(f"Top {alt_transport['returned']} ALT transporter candidates (direct rows, ranked by tcdb_identity):")
    for row in alt_transport["results"]:
        suffix = (
            "  [H+ → extend blacklist if PMF-coupling components are noise]"
            if row.get("metabolite_id") == "kegg.compound:C00080"
            else ""
        )
        print(
            f"  {row.get('locus_tag', '?'):<14} → "
            f"{str(row.get('metabolite_id', '?'))[:22]:<22} "
            f"{(row.get('product') or row.get('gene_name') or '')[:48]}  "
            f"identity={row.get('tcdb_identity')} direction={row.get('tcdb_direction')}{suffix}"
        )
    print()
    print(f"Top {alt_metab['returned']} ALT metabolism candidates (involved-in framing):")
    for row in alt_metab["results"]:
        print(
            f"  {row.get('locus_tag', '?'):<14} → "
            f"{str(row.get('metabolite_id', '?'))[:22]:<22} "
            f"{(row.get('product') or row.get('gene_name') or '')[:48]}"
        )


def scenario_n_source_de() -> None:
    """Use this when the user asks 'which MED4 N-substrate transporters respond to N stress?'

    Sources: chemistry layer (transport) → expression matrix.

    Three-tool cascade: list_metabolites → genes_by_metabolite → gene_response_profile.
    Demonstrates how the chemistry layer can scope a DE-style query without
    requiring a hand-curated gene pool.

    Important re: family rows — this scenario turns on
    include_tcdb_family_substrates=True (contrast with cross_feeding A4).
    Direct rows need the gene's own TCDB system call; family rows come from
    a family or subfamily call and carry the family's curated range. Both
    are annotations, neither is ground truth. For a broad-screen question
    like 'which N-source transporters respond?', family rows are
    appropriate — you want any candidate that could plausibly act on N
    substrates, including real N-uptake genes TCDB placed only at family
    level (PMM0628 gltS, glutamate:Na+ symporter family tcdb:2.A.27).

    The opposite call applies in cross_feeding (A4) — there direct rows
    are the more conservative cast for cross-organism inferences that are
    already fragile.

    Tolonen 2006 (10.1038/msb4100087) is the canonical MED4 N-source paper:
    3 microarray experiments (cyanate, urea, N-deprivation) provide the
    DE response context.
    """
    print("=== Scenario: n_source_de ===")
    print("Question class: 'which MED4 N-substrate transporters respond to N stress?'")
    print()

    print("Step 1: list_metabolites — N-bearing compounds with transport annotations in MED4")
    print("  (exclude_metabolite_ids=CURRENCY_METABOLITES_MIN8 — tool-side currency filter)")
    metabs = list_metabolites(
        elements=["N"],
        organism_names=["Prochlorococcus MED4"],
        evidence_sources=["transport"],   # filter at source, not post
        exclude_metabolite_ids=list(CURRENCY_METABOLITES_MIN8),
        limit=50,
    )
    # 'transport' in evidence_sources means TCDB lists the compound as a
    # substrate of some kept system, not that a gene reaches it: route on
    # transporter_gene_count > 0 (a KG-wide count) before drilling in.
    candidates = [r for r in metabs["results"]
                  if (r.get("transporter_gene_count") or 0) > 0][:10]
    metabolite_ids = [row["metabolite_id"] for row in candidates]
    print(f"  total_matching={metabs.get('total_matching')}  "
          f"top-10: {len(metabolite_ids)}")
    for row in candidates:
        print(
            f"    {row['metabolite_id']:<22} {(row.get('name') or '?'):<32} "
            f"transporter_gene_count={row.get('transporter_gene_count')}"
        )
    print()

    print(f"Step 2: genes_by_metabolite — MED4 transporter genes for these {len(metabolite_ids)} substrates")
    print("  (include_tcdb_family_substrates=True — see docstring; family rows are appropriate here)")
    g = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="MED4",
        evidence_sources=["transport"],
        include_tcdb_family_substrates=True,
        limit=300,
    )
    distinct_genes = sorted({row["locus_tag"] for row in g["results"] if row.get("locus_tag")})
    direct_genes = sorted({
        row["locus_tag"] for row in g["results"]
        if row.get("tcdb_route") == "direct" and row.get("locus_tag")
    })
    family_only = sorted(set(distinct_genes) - set(direct_genes))
    print(f"  total_matching={g['total_matching']}  distinct_genes={len(distinct_genes)}")
    print(f"  direct rows:             {len(direct_genes)} genes (own TCDB system call)")
    print(f"  family rows only:        {len(family_only)} genes (family-level call; candidates)")
    if g.get("tcdb_family_substrates_skipped"):
        print(f"  skipped by the breadth cap (superfamily call, substrate unknown): "
              f"{sorted({e.get('locus_tag') for e in g['tcdb_family_substrates_skipped']})}")
    print()

    print(f"Step 3: gene_response_profile — how do these {len(distinct_genes)} genes respond across N treatments?")
    tolonen_n_experiments = [
        # 10.1038/msb4100087 — Tolonen 2006: MED4 N-source microarray
        "10.1038/msb4100087_growth_medium_growth_on_cyanate_as_med4_microarray",
        "10.1038/msb4100087_growth_medium_growth_on_urea_as_med4_microarray",
        "10.1038/msb4100087_nitrogen_nitrogen_deprivation_med4_med4_microarray",
    ]
    profile = gene_response_profile(
        locus_tags=distinct_genes,
        experiment_ids=tolonen_n_experiments,
    )
    print(f"  scoped to {len(tolonen_n_experiments)} Tolonen 2006 N-source experiments  "
          f"(returned={profile['returned']})")
    print()

    # Sort: responders first, then non-responders. Within responders, by total magnitude (up + down).
    def _sort_key(row: dict) -> tuple:
        s = (row.get("response_summary") or {}).get("nitrogen") or {}
        responded = s.get("timepoints_up", 0) + s.get("timepoints_down", 0)
        return (-responded, row["locus_tag"])

    rows_sorted = sorted(profile["results"], key=_sort_key)
    print(f"{'gene':<12}{'name':<10}{'product':<48}"
          f"{'exps_up/down':<14}{'tps_up/down':<14}")
    print("-" * 100)
    for row in rows_sorted:
        s = (row.get("response_summary") or {}).get("nitrogen") or {}
        eu, ed = s.get("experiments_up", 0), s.get("experiments_down", 0)
        tu, td = s.get("timepoints_up", 0), s.get("timepoints_down", 0)
        prod = (row.get("product") or "")[:46]
        print(
            f"  {row['locus_tag']:<10}{(row.get('gene_name') or '-'):<10}{prod:<48}"
            f"{eu}/{ed:<12}{tu}/{td}"
        )
    print()
    print("  CAVEAT: transporter specificity is often unknown or context-dependent in nature.")
    print("  Family rows reflect family-level transport potential, not per-substrate")
    print("  confirmation. The DE column is the empirical anchor: genes that respond to")
    print("  N stress are functionally implicated whichever TCDB route reached them.")


def scenario_tcdb_chain() -> None:
    """Use this when the user asks 'which MED4 genes transport orthophosphate?'

    Sources: transport (TCDB).

    Demonstrates direct vs family TCDB rows and the family-anchored
    alternative, on the case that motivates the family walk: MED4's
    phosphonate transporter phnCDE has no TCDB system call, only a
    subfamily call on tcdb:3.A.1.9 (PhnT), so the default direct answer
    for orthophosphate is empty and the envelope says what the walk adds.

    Three-route comparison teaches:
      - Direct rows (default) need the gene's own call onto a TCDB system.
      - include_tcdb_family_substrates=True is a fallback for genes TCDB
        could not place in a system — a recall expansion, not a per-gene call.
      - Family-anchored genes_by_ontology answers 'which genes are in family
        Y?', a different question.
      - TCDB curation can be narrow: the Pst system (tcdb:3.A.1.7.6) is
        curated with triphosphate only, so pstS is absent from the
        orthophosphate answer although its system name says phosphate.
    """
    print("=== Scenario: tcdb_chain ===")
    print("Question class: 'which genes transport this substrate?' "
          "(direct vs family TCDB rows)")
    print()

    PHOSPHATE = "kegg.compound:C00009"   # orthophosphate
    print(f"Step 1: direct rows only (default) for {PHOSPHATE} in MED4")
    a = genes_by_metabolite(
        metabolite_ids=[PHOSPHATE],
        organism="MED4",
        evidence_sources=["transport"],
        limit=50,
    )
    a_genes = sorted({r["locus_tag"] for r in a["results"] if r.get("locus_tag")})
    print(f"  direct transport genes: {len(a_genes)} {a_genes}")
    print(f"  tcdb_family_substrates_not_shown: {a.get('tcdb_family_substrates_not_shown')}")
    for w in a.get("warnings") or []:
        print(f"  warning: {w}")
    print()

    print("Step 2: re-run with include_tcdb_family_substrates=True")
    b = genes_by_metabolite(
        metabolite_ids=[PHOSPHATE],
        organism="MED4",
        evidence_sources=["transport"],
        include_tcdb_family_substrates=True,
        limit=50,
    )
    print(f"  by_tcdb_route: {[(e.get('tcdb_route'), e.get('count')) for e in b.get('by_tcdb_route') or []]}")
    for r in b["results"]:
        print(
            f"  {r.get('locus_tag', '?'):<10} {(r.get('gene_name') or '-'):<6} "
            f"route={r.get('tcdb_route'):<7} attached={r.get('attached_tcdb_id')}  "
            f"systems_with_substrate={r.get('tcdb_substrate_system_count')}  "
            f"calls={r.get('tcdb_calls')}  direction={r.get('tcdb_direction')}"
        )
    print()

    print("Step 3: family-anchored — which MED4 genes sit in the PhnT subfamily?")
    c = genes_by_ontology(
        ontology="tcdb",
        term_ids=["tcdb:3.A.1.9"],
        organism="MED4",
        min_gene_set_size=1,
        limit=50,
    )
    c_genes = sorted({r["locus_tag"] for r in c["results"] if r.get("locus_tag")})
    print(f"  genes_by_ontology(ontology='tcdb', term_ids=['tcdb:3.A.1.9']): {c_genes}")
    print()

    print("Step 4: the Pst curation caveat — what does pstS (PMM0710) reach directly?")
    d = metabolites_by_gene(
        locus_tags=["PMM0710"],
        organism="MED4",
        evidence_sources=["transport"],
    )
    for r in d["results"]:
        print(
            f"  {r.get('metabolite_name')!s:<14} via {r.get('tcdb_family_id')}  "
            f"{str(r.get('tcdb_family_name'))[:60]}"
        )
    print()

    print("Reading the comparison:")
    print("  - Direct rows answer 'which genes have a TCDB system curated with X'.")
    print("    For orthophosphate in MED4 that is empty: phnCDE have only a subfamily call.")
    print("  - Family rows (Step 2) say the gene's family has some system moving X —")
    print("    candidates, not calls; report tcdb_substrate_system_count with them.")
    print("  - Family-anchored genes_by_ontology (Step 3) lists family members,")
    print("    whatever they transport.")
    print("  - TCDB curates Pst with triphosphate only, so pstABCS never reach")
    print("    orthophosphate here; read system names when an answer looks too narrow.")


def scenario_measurement() -> None:
    """Use this when the user asks 'what metabolites change under P stress in MIT9301?'

    Sources: metabolomics measurement (mass-spec layer; no gene anchor).
    Caveats surfaced: tested-absent vs unmeasured; compartment matters;
    targeted panel is not the full metabolome; replicate / normalisation
    conventions vary by paper.

    Demonstrates the four Track-B native tools end-to-end:
      list_metabolite_assays → metabolites_by_quantifies_assay (numeric arm)
                            → metabolites_by_flags_assay (boolean arm)
                            → assays_by_metabolite (reverse lookup)
    plus list_metabolites for chemistry-layer enrichment of the measured set.

    The Kujawinski et al. (10.1128/msystems.01261-22) phosphorus experiments
    on MIT9301 are the only P-stress metabolomics in the KG; the chitin paper
    (10.1073/pnas.2213271120) and vesicle paper (10.1111/1462-2920.15834)
    cover other treatments.
    """
    print("=== Scenario: measurement (Track B native) ===")
    print("Question class: 'what metabolites change under P stress in MIT9301?'")
    print()

    # --- Step 1 -------------------------------------------------------------
    # Discovery via list_metabolite_assays. Per-assay granularity is the right
    # level — compartment, value_kind, and metric_type are assay-level properties;
    # one experiment fans out to multiple assays (Kujawinski 2023 fans into
    # 4 P-stress assays — 2 numeric concentrations × 2 compartments + 2 boolean
    # presence flags).
    print("Step 1: list_metabolite_assays — discover P-stress assays")
    p_assays = list_metabolite_assays(treatment_type=["phosphorus"])
    print(
        f"  → {p_assays['returned']} P-stress assays "
        f"(of {p_assays['total_entries']} total in KG)"
    )
    print(f"  by_value_kind: {[(v.get('value_kind'), v.get('count')) for v in (p_assays.get('by_value_kind') or [])]}")
    print(f"  by_compartment: {[(c.get('compartment'), c.get('count')) for c in (p_assays.get('by_compartment') or [])]}")
    print(
        "  by_detection_status (numeric arm primary headline): "
        f"{[(d.get('detection_status'), d.get('count')) for d in (p_assays.get('by_detection_status') or [])]}"
    )
    print()
    for row in p_assays["results"]:
        print(
            f"    {row['assay_id'][:78]:<78} "
            f"kind={row['value_kind']:<8} compartment={row['compartment']}"
        )
    print()

    # --- Step 2 -------------------------------------------------------------
    # Numeric arm drill-down. Pass detection_status=['detected', 'sporadic']
    # to opt out of tested-absent rows for a 'present-only' slice. Default
    # (no filter) keeps tested-absent rows — that's the recommended invariant
    # because tested-absent is real biology (70.7% of numeric edges in this KG).
    numeric_ids = [r["assay_id"] for r in p_assays["results"] if r["value_kind"] == "numeric"]
    print(f"Step 2: metabolites_by_quantifies_assay — present-only slice, {len(numeric_ids)} numeric assays")
    mvals = metabolites_by_quantifies_assay(
        assay_ids=numeric_ids,
        detection_status=["detected", "sporadic"],
        limit=20,
    )
    print(f"  → returned={mvals['returned']}  total_matching={mvals['total_matching']}")
    print(f"  by_detection_status: {[(d.get('detection_status'), d.get('count')) for d in (mvals.get('by_detection_status') or [])]}")
    print(f"  by_compartment: {[(c.get('compartment'), c.get('count')) for c in (mvals.get('by_compartment') or [])]}")
    print()
    print(f"  {'metabolite':<32}{'compartment':<16}{'value':<14}{'detection':<14}")
    print(f"  {'-' * 30:<32}{'-' * 14:<16}{'-' * 12:<14}{'-' * 12:<14}")
    for row in mvals["results"][:10]:
        v = row.get("value")
        v_str = f"{v:.3g}" if isinstance(v, (int, float)) else "-"
        print(
            f"  {(row.get('name') or '?')[:30]:<32}"
            f"{(row.get('compartment') or '?'):<16}"
            f"{v_str:<14}"
            f"{(row.get('detection_status') or '?'):<14}"
        )
    print()

    # --- Step 3 -------------------------------------------------------------
    # Boolean arm drill-down. Default `flag_value=None` returns both presence
    # and absence; flag_value=False isolates the tested-absent slice (real
    # biology — 68.8% of boolean rows in the live KG, from the S2 paper-level
    # presence/absence tables).
    boolean_ids = [r["assay_id"] for r in p_assays["results"] if r["value_kind"] == "boolean"]
    if boolean_ids:
        print(f"Step 3: metabolites_by_flags_assay — boolean S2 flags, {len(boolean_ids)} assays")
        flags = metabolites_by_flags_assay(
            assay_ids=boolean_ids,
            limit=10,
        )
        print(f"  → returned={flags['returned']}  total_matching={flags['total_matching']}")
        print(f"  by_value: {[(b.get('flag_value'), b.get('count')) for b in (flags.get('by_value') or [])]}")
        print()

    # --- Step 4 -------------------------------------------------------------
    # Reverse lookup. assays_by_metabolite is polymorphic — both arms merged
    # via UNION ALL, cross-organism by default (D2 closure: metabolite IDs are
    # organism-agnostic). Use `metabolites_matched` (distinct metabolite count),
    # NOT total_matching (row count).
    print("Step 4: assays_by_metabolite — reverse lookup for PEP (kegg.compound:C00074)")
    pep = assays_by_metabolite(
        metabolite_ids=["kegg.compound:C00074"],
        limit=10,
    )
    print(
        f"  → returned={pep['returned']}  total_matching={pep['total_matching']}  "
        f"metabolites_matched={pep['metabolites_matched']}"
    )
    print(f"  by_evidence_kind: {[(e.get('evidence_kind'), e.get('count')) for e in (pep.get('by_evidence_kind') or [])]}")
    print(f"  by_detection_status: {[(d.get('detection_status'), d.get('count')) for d in (pep.get('by_detection_status') or [])]}")
    print(f"  by_flag_value: {[(b.get('flag_value'), b.get('count')) for b in (pep.get('by_flag_value') or [])]}")
    print()

    # --- Step 5 -------------------------------------------------------------
    # Chemistry annotation. list_metabolites covers the compound-side enrichment
    # of the measured set (formulas, pathway membership, transport reach,
    # measurement-rollup pass-through fields).
    print("Step 5: list_metabolites — chemistry annotation for the measured compounds")
    measured_ids = sorted({row["metabolite_id"] for row in mvals["results"][:10]})
    chem = list_metabolites(metabolite_ids=measured_ids)
    print(f"  → annotated {chem['returned']} of {len(measured_ids)} measured compounds")
    for row in chem["results"][:5]:
        print(
            f"    {row['metabolite_id']:<22} "
            f"formula={(row.get('formula') or '?'):<14} "
            f"pathways={row.get('pathway_count')} "
            f"transporter_genes={row.get('transporter_gene_count')} "
            f"measured_papers={row.get('measured_paper_count')}"
        )
    print()

    # --- Caveats ------------------------------------------------------------
    print("CAVEATS to surface alongside any answer:")
    print("  - No gene anchor — measurement says nothing about which gene produced/consumed it.")
    print("  - Quantifies (concentration) vs Flags (qualitative detection) — different drill-downs.")
    print("  - Compartment matters — whole_cell ≠ extracellular ≠ vesicle biology.")
    print("  - Tested-absent is not the same as unmeasured — value=0 /")
    print("    detection_status='not_detected' / flag_value=False rows are biology,")
    print("    kept by default; missing rows are unmeasured.")
    print("  - Targeted panel — absence in measurement is not absence in cell.")
    print("  - 149 of ~3.3k metabolites measured; 3 papers; 14 assays (12 numeric + 2 boolean).")


SCENARIOS: dict[str, Callable[[], None]] = {
    "discover": scenario_discover,
    "compound_to_genes": scenario_compound_to_genes,
    "gene_to_metabolites": scenario_gene_to_metabolites,
    "cross_feeding": scenario_cross_feeding,
    "n_source_de": scenario_n_source_de,
    "tcdb_chain": scenario_tcdb_chain,
    "measurement": scenario_measurement,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=sorted(SCENARIOS.keys()),
        help="Which scenario to run",
    )
    args = parser.parse_args()
    SCENARIOS[args.scenario]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
