"""Example: working with metabolites in the KG.

Demonstrates the three Metabolite-source pipelines (transport / gene reaction /
metabolomics) and the workflow patterns for each. See
docs://analysis/metabolites for the LLM-facing guide; this script is its
runnable companion.

Each scenario function names the source(s) it touches and the metabolite-source
caveat it surfaces. Print intermediate envelope state to teach the LLM how to
read responses, not just consume detail rows.

Run with: uv run python examples/metabolites.py --scenario <name>

Scenarios:
  1. discover            — element + organism filter (sources: reaction + transport)
  2. compound_to_genes   — evidence_source split on glutamine (reaction + transport)
  3. gene_to_metabolites — element signature + top_pathways (reaction + transport)
  4. cross_feeding       — bridge MED4 → ALT (reaction + transport)
  5. n_source_de         — N-source primitive → DE (reaction + transport → expression)
  6. tcdb_chain          — TCDB ontology → metabolite (transport)
  7. precision_tier      — family_inferred warning interpretation (transport)
  8. measurement         — metabolomics via run_cypher (measurement; native tools pending)

Build-derived notes (audit Part 2/3a P0 confirmed):
- list_metabolites does NOT pass through `measured_assay_count` per row, even
  though Metabolite nodes carry it (see audit Part 3a row for list_metabolites).
- Metabolite IDs use prefixed form `kegg.compound:C00064`, not bare `C00064`.
- evidence_sources filter is needed to narrow at-scale; per-row schema is union
  (metabolism rows have reaction_id/ec_numbers; transport rows have
  transport_confidence/tcdb_family_id).
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from multiomics_explorer import (
    differential_expression_by_gene,
    genes_by_metabolite,
    genes_by_ontology,
    list_experiments,
    list_metabolites,
    metabolites_by_gene,
    run_cypher,
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

    top_paths = result.get("top_pathways") or []
    print(f"top_pathways: {[p.get('pathway_name') for p in top_paths][:5]}")

    by_es = result.get("by_evidence_source") or []
    print(f"by_evidence_source: {[(e.get('evidence_source'), e.get('count')) for e in by_es]}")

    top_orgs = result.get("top_organisms") or []
    print(f"top_organisms: {[(o.get('organism_name'), o.get('count')) for o in top_orgs][:5]}")
    print(f"xref_coverage: {result.get('xref_coverage')}")
    print()
    print("First metabolites (id | name | gene_count | transporter_count | evidence_sources):")
    for row in result["results"][:5]:
        print(
            f"  {str(row.get('metabolite_id', '?'))[:18]:<18} "
            f"{str(row.get('name', '?'))[:30]:<30} "
            f"gene_count={row.get('gene_count')}  "
            f"transporter_count={row.get('transporter_count')}  "
            f"evidence={row.get('evidence_sources')}"
        )
    print()
    print("Build-derived note: list_metabolites does NOT surface `measured_assay_count` per row")
    print("even though Metabolite nodes carry it. Audit Part 3a P0.")


def scenario_compound_to_genes() -> None:
    """Use this when the user asks 'which MED4 genes act on glutamine?'

    Sources: reaction + transport (response is split by evidence_source).
    Caveat surfaced: metabolism vs transport semantics differ; row counts
    are not comparable (transport rows often family_inferred). Per-row
    schema is union — metabolism rows carry reaction_id/ec_numbers;
    transport rows carry transport_confidence/tcdb_family_id.

    Two-step chain: name → metabolite_id (via list_metabolites search)
    → genes (via genes_by_metabolite). Most user-facing questions arrive
    by metabolite NAME, not by KEGG ID, so the search step is the
    realistic entry point.
    """
    print("=== Scenario: compound_to_genes ===")
    print("Question class: 'which genes catalyse / transport this compound?'")
    print()

    # Step 1: name → KEGG ID via free-text search.
    print("Step 1: resolve name → KEGG ID via list_metabolites(search='glutamine')")
    name_lookup = list_metabolites(search="glutamine", limit=5)
    print(f"  returned={name_lookup['returned']}  total_matching={name_lookup['total_matching']}")
    for row in name_lookup["results"][:5]:
        print(f"  {row['metabolite_id']:<25} {row['name']}")
    # Pick the canonical L-Glutamine match (KEGG C00064) — N-bearing, has
    # BOTH metabolism and transport arms in MED4.
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
    by_tc = result.get("by_transport_confidence") or []
    print(f"by_transport_confidence: {[(e.get('transport_confidence'), e.get('count')) for e in by_tc]}")
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
                f"transport_conf={str(row.get('transport_confidence', '?')):<22} "
                f"family={str(row.get('tcdb_family_id', '?'))}"
            )
        else:
            print(f"  {row.get('locus_tag', '?'):<12} {es}")
    print()
    print("LESSON: rows have UNION shape — different fields per evidence_source.")
    print("        Counts NOT comparable across arms (transport often family_inferred).")


def scenario_gene_to_metabolites() -> None:
    """Use this when the user asks 'what metabolites does PMM0001 act on?'

    Sources: reaction + transport.
    Caveat surfaced: chemistry-side `top_pathways` (Reaction-anchored) is
    NOT the same surface as gene-KO pathways from `genes_by_ontology(ontology='kegg')`.
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
    chem_pathways = result.get("top_pathways") or []
    print("top_pathways (chemistry-side, via Reaction → KeggTerm):")
    for p in chem_pathways[:5]:
        print(
            f"  {str(p.get('pathway_id', '?'))[:24]:<24} "
            f"{str(p.get('pathway_name', '?'))[:40]:<40} "
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
                f"transport   conf={row.get('transport_confidence', '?')}"
            )


def scenario_cross_feeding() -> None:
    """Use this when the user asks 'what could MED4 produce that ALT might consume?'

    Sources: reaction + transport (annotation-only).

    Workflow B′ has THREE structural confounders that compound; each requires
    a workflow-side mitigation:

    1. Currency-cofactor flooding (metabolism arm) — top_metabolites is sorted
       by gene_count, which is exactly the wrong sort for cross-feeding because
       the highest-reach metabolites are universal cofactors (H2O, ATP, ADP,
       Pi, PPi, NAD(P)(H)). Mitigation: post-filter via CURRENCY_METABOLITES_MIN8.
       Extend the blacklist if H+, glutamate/glutamine, or coenzyme A dominate
       results in your seed. The printed output deliberately keeps H+ outside
       the minimal-8 blacklist — proton channels (MotA/TolQ/ExbB family)
       surface in the transport arm and demonstrate when extension is warranted.
    2. Family-inferred plateau (transport arm) — broad-substrate ABC superfamily
       annotations propagate ~554 metabolites per MED4 gene at low confidence.
       Mitigation: transport_confidence='substrate_confirmed' on Step 2.
    3. Transport polarity not encoded — TCDB annotation says 'transports X'
       without import/export direction (KG-MET-011 open). Even with clean
       filters, the result is 'compatible with cross-feeding', never confirmed.

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
    med4 = metabolites_by_gene(
        locus_tags=seed_locus_tags,
        organism="MED4",
        summary=True,
    )
    by_es_med4 = med4.get("by_evidence_source") or []
    print(f"  total_matching={med4.get('total_matching')}  "
          f"by_evidence_source={[(e['evidence_source'], e['count']) for e in by_es_med4]}")
    top_metabs = med4.get("top_metabolites") or []

    print("  top_metabolites (raw, pre-blacklist):")
    for r in top_metabs:
        flag = " [CURRENCY → blacklisted]" if r["metabolite_id"] in CURRENCY_METABOLITES_MIN8 else ""
        print(
            f"    {r['metabolite_id']:<22} {(r.get('name') or '?'):<32} "
            f"metab={r.get('metabolism_rows')} "
            f"trans_conf={r.get('transport_substrate_confirmed_rows')} "
            f"trans_inf={r.get('transport_family_inferred_rows')}{flag}"
        )

    metabolite_ids = [
        m["metabolite_id"]
        for m in top_metabs
        if m.get("metabolite_id") and m["metabolite_id"] not in CURRENCY_METABOLITES_MIN8
    ]
    dropped = [m["metabolite_id"] for m in top_metabs if m.get("metabolite_id") in CURRENCY_METABOLITES_MIN8]
    print(f"  after minimal-8 currency blacklist: {len(metabolite_ids)} kept, {len(dropped)} dropped")
    print()

    if not metabolite_ids:
        print("(no non-currency metabolites — extend the seed or relax the blacklist)")
        return

    print(f"Step 2: which Alteromonas genes touch any of the {len(metabolite_ids)} metabolites?")
    print("  (split per-arm so both transport and metabolism get airtime;")
    print("   transport_confidence='substrate_confirmed' kills the ABC family-inferred plateau)")
    alt_transport = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="Alteromonas macleodii HOT1A3",
        evidence_sources=["transport"],
        transport_confidence="substrate_confirmed",
        limit=8,
    )
    alt_metab = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="Alteromonas macleodii HOT1A3",
        evidence_sources=["metabolism"],
        limit=8,
    )
    print(f"  transport-arm: total_matching={alt_transport.get('total_matching')}")
    print(f"  metabolism-arm: total_matching={alt_metab.get('total_matching')}")
    print()
    print("  CAVEATS — Workflow B′ is 'compatible with cross-feeding', never confirmed:")
    print("    1. Currency cofactors blacklisted above (mitigated)")
    print("    2. transport_confidence filter applied (mitigated for ABC plateau)")
    print("    3. Transport polarity not encoded — KG-MET-011 open. The Track-B")
    print("       measurement layer can corroborate (extracellular elevation in coculture)")
    print("       but cannot confirm causality.")
    print()

    print(f"Top {alt_transport['returned']} ALT transporter candidates (substrate_confirmed):")
    for row in alt_transport["results"]:
        suffix = (
            "  [H+ → extend blacklist if PMF-coupling components are noise]"
            if row.get("metabolite_id") == "kegg.compound:C00080"
            else ""
        )
        print(
            f"  {row.get('locus_tag', '?'):<14} → "
            f"{str(row.get('metabolite_id', '?'))[:22]:<22} "
            f"{(row.get('product') or row.get('gene_name') or '')[:48]}{suffix}"
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
    """Use this when the user asks 'which N-acting genes respond to N starvation?'

    Sources: reaction + transport → expression (chemistry filters DE input).
    Caveat surfaced: promiscuous enzymes / family_inferred transport can
    inflate the gene set fed to DE — tighten with evidence_sources or
    transport_confidence if results are noisy.
    """
    print("=== Scenario: n_source_de ===")
    print("Question class: 'which N-acting genes respond to N starvation?'")
    print()

    pool = [
        "PMM0001", "PMM0002", "PMM0003", "PMM0004", "PMM0005",
        "PMM1428", "PMM0532", "PMM0374", "PMM0533", "PMM0534",
    ]

    print(f"Step 1: filter pool ({len(pool)} genes) to N-bearing chemistry")
    chem = metabolites_by_gene(
        locus_tags=pool,
        organism="MED4",
        metabolite_elements=["N"],
        limit=200,
    )
    n_genes = sorted({row.get("locus_tag") for row in chem["results"] if row.get("locus_tag")})
    print(f"  → {len(n_genes)} N-acting genes (from {chem['returned']} (gene, metabolite) rows): "
          f"{n_genes[:5]}{'...' if len(n_genes) > 5 else ''}")
    print("  CAVEAT: pool may include promiscuous-enzyme / family_inferred-transport hits.")
    print("  To tighten: add evidence_sources=['metabolism'] or "
          "transport_confidence='substrate_confirmed'.")
    print()

    if not n_genes:
        print("(no N-acting genes in pool — try a larger or differently-curated pool)")
        return

    print(f"Step 2: DE for {len(n_genes)} N-acting genes (significant_only=True)")
    # Note: direction valid values are {'up', 'down'} — NOT 'both'. Omit to get
    # both directions (default).
    de = differential_expression_by_gene(
        organism="MED4",
        locus_tags=n_genes,
        significant_only=True,
        limit=10,
    )
    print(f"  → returned={de['returned']}  total_matching={de.get('total_matching')}")
    print(f"  rows_by_treatment_type: {de.get('rows_by_treatment_type')}")
    print()
    print("First 10 DE rows:")
    for row in de["results"][:10]:
        log2fc = row.get("log2fc")
        padj = row.get("padj")
        log2fc_str = f"{log2fc:.3f}" if isinstance(log2fc, (int, float)) else str(log2fc)
        padj_str = f"{padj:.3g}" if isinstance(padj, (int, float)) else str(padj)
        print(
            f"  {row.get('locus_tag', '?'):<10} "
            f"treatment={str(row.get('treatment_type', '-')):<22} "
            f"tp={str(row.get('timepoint', '-')):<6} "
            f"log2fc={log2fc_str:<8} adj_p={padj_str:<10} "
            f"{row.get('expression_status', '-')}"
        )


def scenario_tcdb_chain() -> None:
    """Use this when the user asks 'which MED4 genes transport glycine betaine?'

    Sources: transport (TCDB ontology bridge to metabolite-anchored route).
    Caveat surfaced: substrate-anchored route (`genes_by_metabolite`) is
    preferred over family-anchored route (`genes_by_ontology(ontology='tcdb')`)
    for cross-family substrate hits.
    """
    print("=== Scenario: tcdb_chain ===")
    print("Question class: 'which genes transport this substrate?' "
          "(substrate-anchored, not family-anchored)")
    print()

    print("Step 1 (illustrative): locate substrate via search_ontology(tcdb)")
    # search_ontology requires positional `search_text` and `ontology` kwargs.
    found = search_ontology(search_text="betaine", ontology="tcdb", limit=5)
    print(f"  search returned {found.get('returned')} ontology terms.")
    print()

    print("Step 2: substrate-anchored — genes_by_metabolite(['kegg.compound:C00719'], "
          "evidence_sources=['transport'])")
    result = genes_by_metabolite(
        metabolite_ids=["kegg.compound:C00719"],            # glycine betaine
        organism="MED4",
        evidence_sources=["transport"],
        limit=10,
    )
    print(f"  returned={result['returned']}  total_matching={result.get('total_matching')}")
    print(f"  warnings: {result.get('warnings', [])}")
    by_tc = result.get("by_transport_confidence") or []
    print(f"  by_transport_confidence: "
          f"{[(e.get('transport_confidence'), e.get('count')) for e in by_tc]}")
    print()
    print("First 10 transporter candidates:")
    for row in result["results"][:10]:
        tc = row.get("transport_confidence", "-")
        print(
            f"  {row.get('locus_tag', '?'):<12} "
            f"conf={tc:<22} "
            f"family={str(row.get('tcdb_family_id', '-'))[:14]:<14} "
            f"({str(row.get('tcdb_family_name', '?'))[:35]})"
        )
    print()
    print("NOTE: prefer this substrate-anchored route over genes_by_ontology(ontology='tcdb').")
    print("      The latter is family-anchored — misses substrates curated by other families.")


def scenario_precision_tier() -> None:
    """Use this when interpreting a `genes_by_metabolite` result with the
    family_inferred-dominance auto-warning.

    Sources: transport (warning is transport-arm specific).
    Caveat surfaced: ABC superfamily inflates family_inferred row counts;
    tighten via transport_confidence='substrate_confirmed' for high-confidence
    rows only.
    """
    print("=== Scenario: precision_tier ===")
    print("Question class: 'how do I interpret family_inferred-dominance warning?'")
    print()

    # Glycine betaine triggers the warning (ABC superfamily curates it).
    print("Step 1: query a substrate likely to trigger the family_inferred warning")
    broad = genes_by_metabolite(
        metabolite_ids=["kegg.compound:C00719"],            # glycine betaine
        organism="MED4",
        evidence_sources=["transport"],
        limit=5,
    )
    print(f"  returned={broad['returned']}  total_matching={broad.get('total_matching')}")
    print(f"  warnings: {broad.get('warnings', [])}")
    by_tc = broad.get("by_transport_confidence") or []
    print(f"  by_transport_confidence: "
          f"{[(e.get('transport_confidence'), e.get('count')) for e in by_tc]}")
    print()

    print("Step 2: tighten to transport_confidence='substrate_confirmed'")
    tight = genes_by_metabolite(
        metabolite_ids=["kegg.compound:C00719"],
        organism="MED4",
        evidence_sources=["transport"],
        transport_confidence="substrate_confirmed",
        limit=5,
    )
    print(f"  returned={tight['returned']}  total_matching={tight.get('total_matching')}")
    print(f"  warnings: {tight.get('warnings', [])}")
    print()
    print("LESSON: when the warning fires, decide between:")
    print("  (a) keep all rows but explicitly call out family_inferred-vs-substrate_confirmed,")
    print("  (b) tighten to substrate_confirmed only (high precision, lower recall),")
    print("  (c) exclude promiscuous families via tcdb_family_ids (rarely needed).")


def scenario_measurement() -> None:
    """Use this when the user asks 'what metabolites were measured under N starvation?'

    Sources: metabolomics measurement (no gene anchor).
    Caveat surfaced: native tools pending — uses `run_cypher`. Read the
    `Assay_quantifies` vs `Assay_flags` discriminator; compartment matters;
    targeted panel ≠ full metabolome.
    """
    print("=== Scenario: measurement ===")
    print("Question class: 'what metabolites were measured under condition X?'")
    print()
    print(">>> BANNER: native tools pending — using run_cypher.")
    print(">>> See docs://analysis/metabolites Track B and the audit doc for the planned surface.")
    print()

    print("Step 1: list_experiments(omics_type=['METABOLOMICS'])")
    exps = list_experiments(omics_type=["METABOLOMICS"], summary=False, limit=5)
    print(f"  returned={exps['returned']}  total_matching={exps.get('total_matching')}")
    for e in exps["results"][:5]:
        print(
            f"  {str(e.get('id', '?'))[:55]:<55} "
            f"treatment={e.get('treatment_type')}  bg={e.get('background_factors')}"
        )
    print()

    print("Step 2: assay → metabolite walk via run_cypher (Quantifies arm)")
    cy = run_cypher(
        query="""
        MATCH (e:Experiment)-[:ExperimentHasMetaboliteAssay]->(a:MetaboliteAssay)
              -[r:Assay_quantifies_metabolite]->(m:Metabolite)
        RETURN m.preferred_id AS metabolite_id,
               m.name AS metabolite,
               a.compartment AS compartment,
               r.value AS value,
               r.value_sd AS value_sd,
               r.n_replicates AS n_replicates,
               r.metric_type AS metric_type,
               coalesce(r.condition_label, '') AS condition,
               e.id AS experiment
        ORDER BY metabolite_id
        """,
        limit=15,
    )
    print(f"  returned={cy['returned']}  truncated={cy['truncated']}")
    print(f"  warnings: {cy.get('warnings', [])}")
    print()
    print("First quantified rows (metabolite | compartment | value±sd | metric | experiment):")
    for row in cy["results"][:15]:
        v = row.get("value")
        v_sd = row.get("value_sd")
        v_str = (
            f"{v:.3g}±{v_sd:.3g}"
            if isinstance(v, (int, float)) and isinstance(v_sd, (int, float))
            else str(v)
        )
        print(
            f"  {str(row.get('metabolite', '?'))[:30]:<30} "
            f"{str(row.get('compartment', '?')):<14} "
            f"{v_str:<18} "
            f"{str(row.get('metric_type', '?'))[:24]:<24} "
            f"{str(row.get('experiment', '?'))[:30]}"
        )
    print()
    print("CAVEATS to surface alongside any answer:")
    print("  - No gene anchor: cannot attribute these to specific genes.")
    print("  - Quantifies (concentration) vs Flags (qualitative detection).")
    print("  - Compartment matters — extracellular ≠ whole_cell biology.")
    print("  - Targeted panel — absence in measurement ≠ absence in cell.")
    print("  - 107 of 3218 metabolites measured; 2 papers; 10 assays (KG release 2026-05-05).")


SCENARIOS: dict[str, Callable[[], None]] = {
    "discover": scenario_discover,
    "compound_to_genes": scenario_compound_to_genes,
    "gene_to_metabolites": scenario_gene_to_metabolites,
    "cross_feeding": scenario_cross_feeding,
    "n_source_de": scenario_n_source_de,
    "tcdb_chain": scenario_tcdb_chain,
    "precision_tier": scenario_precision_tier,
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
