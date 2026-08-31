"""Example: reading the annotation-trust surface (evidence / evidence_score /
tier / call_class / interpro_type) across the 17 supported ontologies.

See docs://analysis/annotation_evidence for the LLM-facing guide; this
script is its runnable companion. Each scenario names the trust axis it
exercises and the tool(s) that carry it.

Run with: uv run python examples/annotation_evidence.py --scenario <name>

Scenarios:
  1. merops_call_class    — peptidase-only clan census vs. unfiltered (call_class)
  2. tcdb_attachment_depth — most-specific vs superseded leaf rows (attachment_depth)
  3. interpro_enrichment  — interpro_type required on enrichment, then supplied
  4. trust_filtered_tcdb  — sources/evidence/min_evidence_score before enrichment
  5. organism_rollups     — per-organism protease / domain coverage (list_organisms)

Notes:
- Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`,
  `call_class`) default to `None` and never narrow a result unless set —
  every scenario below runs the unfiltered call first so the delta is visible.
- `min_evidence_score` is the only numeric cutoff anywhere in this surface.
  Native per-ontology scalars (evalue, bit_score, confidence_score, ...) are
  verbose-only and never filterable.
"""
# CONTENTS
#   1. scenario_merops_call_class      — peptidase clan census (call_class) (line ~52)
#   2. scenario_tcdb_attachment_depth  — most-specific vs superseded leaf rows (line ~90)
#   3. scenario_interpro_enrichment    — interpro_type required on enrichment (line ~132)
#   4. scenario_trust_filtered_tcdb    — evidence + min_evidence_score before enrichment (line ~169)
#   5. scenario_organism_rollups       — per-organism protease/domain coverage (line ~214)
from __future__ import annotations

import argparse
import sys
from typing import Callable

from multiomics_explorer import (
    gene_ontology_terms,
    genes_by_ontology,
    list_experiments,
    list_filter_values,
    list_organisms,
    pathway_enrichment,
)


def med4_experiment_id() -> str:
    """A real MED4 experiment_id, discovered live (not hardcoded — avoids
    drift across KG rebuilds). These scenarios only need a valid experiment
    to run pathway_enrichment against; the value tested is the trust-filter
    behavior, not this experiment's biology."""
    found = list_experiments(organism="MED4", limit=1)
    if not found["results"]:
        raise SystemExit("no MED4 experiments found in the KG")
    return found["results"][0]["experiment_id"]


def scenario_merops_call_class() -> None:
    """Use this when the user asks 'how many genes actually encode
    peptidases, by clan?' rather than 'how many genes resemble a peptidase
    family by sequence?'

    Trust axis: call_class (materially-important, MEROPS-only, compact always).
    """
    print("=== Scenario: merops_call_class ===")
    print("Question class: 'peptidase clan census, not sequence homology to one'")
    print()

    peptidase_only = genes_by_ontology(
        ontology="merops",
        organism="MIT1002",
        level=0,
        call_class=["peptidase"],
    )
    print("call_class=['peptidase']:")
    print(f"  total_terms={peptidase_only.get('total_terms')}  "
          f"total_genes={peptidase_only.get('total_genes')}  "
          f"warnings={peptidase_only.get('warnings')}")
    for row in (peptidase_only.get("top_terms") or [])[:7]:
        print(f"    {row.get('term_id'):<20} {row.get('term_name', '')[:30]:<30} count={row.get('count')}")
    print()

    unfiltered = genes_by_ontology(
        ontology="merops",
        organism="MIT1002",
        level=0,
    )
    print("no call_class filter (folds in nonpeptidase_homolog rows):")
    print(f"  total_terms={unfiltered.get('total_terms')}  "
          f"total_genes={unfiltered.get('total_genes')}  "
          f"warnings={unfiltered.get('warnings')}")
    by_call_class = unfiltered.get("by_call_class") or []
    print(f"  by_call_class: {[(c.get('call_class'), c.get('count')) for c in by_call_class]}")


def scenario_tcdb_attachment_depth() -> None:
    """Use this when the user asks 'what's this gene's actual TCDB call' —
    the deepest attachment, not every ancestor family it also technically
    belongs to.

    Trust axis: attachment_depth (native detail, TCDB-only) via mode='leaf'
    and include_superseded.
    """
    print("=== Scenario: tcdb_attachment_depth ===")
    print("Question class: 'most-specific TCDB call vs every ancestor attachment'")
    print()

    leaf_only = gene_ontology_terms(
        locus_tags=["PMM0392"],
        organism="MED4",
        ontology=["tcdb"],
        mode="leaf",
    )
    print("mode='leaf' (default — attachment_depth='most_specific' only):")
    print(f"  total_matching={leaf_only.get('total_matching')}")
    for row in leaf_only.get("results", [])[:5]:
        print(f"    {row.get('term_id'):<16} evidence={row.get('evidence')}")
    print()

    with_superseded = gene_ontology_terms(
        locus_tags=["PMM0392"],
        organism="MED4",
        ontology=["tcdb"],
        mode="leaf",
        include_superseded=True,
        # attachment_depth is TCDB native detail — verbose-only on the row.
        verbose=True,
    )
    print("include_superseded=True (adds back less-specific ancestor rows):")
    print(f"  total_matching={with_superseded.get('total_matching')}")
    for row in with_superseded.get("results", [])[:5]:
        print(f"    {row.get('term_id'):<16} attachment_depth={row.get('attachment_depth')}")
    print()
    print("'superseded' means less specific, not wrong — a real annotation,")
    print("just not the gene's deepest call for that lineage.")


def scenario_interpro_enrichment() -> None:
    """Use this when the user asks for InterPro enrichment — interpro_type
    is required because the 8 InterPro types size too differently to pool
    into one Fisher background.

    Trust axis: interpro_type (materially-important, term-side, InterPro-only).
    """
    print("=== Scenario: interpro_enrichment ===")
    print("Question class: 'InterPro enrichment requires picking a type first'")
    print()

    exp_id = med4_experiment_id()

    try:
        pathway_enrichment(
            organism="MED4",
            experiment_ids=[exp_id],
            ontology="interpro",
            level=0,
        )
        print("(unexpected: call succeeded without interpro_type)")
    except Exception as e:
        print(f"Without interpro_type — raises as expected: {e}")
    print()

    result = pathway_enrichment(
        organism="MED4",
        experiment_ids=[exp_id],
        ontology="interpro",
        interpro_type="HOMOLOGOUS_SUPERFAMILY",
        level=0,
    )
    print("With interpro_type='HOMOLOGOUS_SUPERFAMILY':")
    print(f"  kind={result.kind}  rows={len(result.results)}")
    print(result.results.head())


def scenario_trust_filtered_tcdb() -> None:
    """Use this when the user wants a TCDB-based gene set tightened to
    corroborated homology calls before feeding it into enrichment — the
    trust-surface analog of substrate_depth=['most_specific'] on the
    chemistry side (see docs://guide/conventions).

    Trust axes: evidence + min_evidence_score (comparable axes; the only
    numeric cutoff in the whole surface).
    """
    print("=== Scenario: trust_filtered_tcdb ===")
    print("Question class: 'restrict a hierarchical ontology gene set to corroborated calls'")
    print()

    axes = list_filter_values(filter_type="trust_axes", ontology="tcdb")
    print(f"tcdb trust axes: {[r.get('value') for r in axes.get('results', [])]}")
    print()

    unfiltered = genes_by_ontology(ontology="tcdb", organism="MED4", level=2)
    print(f"unfiltered: total_matching={unfiltered.get('total_matching')}")

    filtered = genes_by_ontology(
        ontology="tcdb",
        organism="MED4",
        level=2,
        evidence=["homology"],
        min_evidence_score=0.6,
    )
    print(f"evidence=['homology'] AND min_evidence_score=0.6: "
          f"total_matching={filtered.get('total_matching')}")
    print(f"evidence_score_signals: {filtered.get('evidence_score_signals')}")
    print()

    enrichment = pathway_enrichment(
        organism="MED4",
        experiment_ids=[med4_experiment_id()],
        ontology="tcdb",
        level=2,
        evidence=["homology"],
        min_evidence_score=0.6,
    )
    envelope = enrichment.to_envelope(limit=5)
    print(f"pathway_enrichment with the same filters: "
          f"background_filtered={envelope.get('background_filtered')}")


def scenario_organism_rollups() -> None:
    """Use this when the user asks 'which organisms carry the most
    protease genes?' or 'how well is this strain covered by InterPro /
    NCBIfam?' — organism-level coverage before any gene-level drill-down.

    Surface: list_organisms rows carry four zero-filled distinct-gene counts
    (peptidase_gene_count, nonpeptidase_homolog_gene_count,
    interpro_gene_count, ncbifam_gene_count); the envelope's
    top_annotation_capability ranks the top 10 of the matched set by
    peptidase_gene_count. There is no filter on these counts by design —
    48 organisms is small enough to read, so read the ranking.
    """
    print("=== Scenario: organism_rollups ===")
    print("Question class: 'which organisms are protease-rich / best covered by domain annotation?'")
    print()

    survey = list_organisms(summary=True)
    ranking = survey.get("top_annotation_capability") or []
    print(f"organisms matched: {survey.get('total_matching')}; "
          f"ranked (all-zero rows excluded, top 10): {len(ranking)}")
    print(f"  {'organism':<34} {'peptidase_gene_count':>20} "
          f"{'nonpeptidase_homolog_gene_count':>31} {'interpro_gene_count':>19} "
          f"{'ncbifam_gene_count':>18}")
    for row in ranking:
        print(f"  {row.get('preferred_name', '')[:34]:<34} "
              f"{row.get('peptidase_gene_count'):>20} "
              f"{row.get('nonpeptidase_homolog_gene_count'):>31} "
              f"{row.get('interpro_gene_count'):>19} "
              f"{row.get('ncbifam_gene_count'):>18}")
    if ranking:
        top = ranking[0]
        print()
        print(f"top organism by peptidase_gene_count: {top.get('preferred_name')} "
              f"({top.get('peptidase_gene_count')} peptidase genes)")
    print()
    print("Coverage counts scale with genome size — a 4,000-gene heterotroph")
    print("out-counts a 2,000-gene Prochlorococcus on every column. Compare")
    print("within a clade, then drill in with")
    print("genes_by_ontology(ontology='merops', organism=..., call_class=['peptidase']).")
    print()

    subset = list_organisms(organism_names=["Prochlorococcus MED4"])
    rows = subset.get("results", [])
    if rows:
        med4 = rows[0]
        print("Per-row counts for one organism (list_organisms(organism_names=['Prochlorococcus MED4'])):")
        for key in ("peptidase_gene_count", "nonpeptidase_homolog_gene_count",
                    "interpro_gene_count", "ncbifam_gene_count"):
            print(f"  {key}={med4.get(key)}")
    print(f"  top_annotation_capability over the subset: "
          f"{[r.get('preferred_name') for r in subset.get('top_annotation_capability') or []]}")


SCENARIOS: dict[str, Callable[[], None]] = {
    "merops_call_class": scenario_merops_call_class,
    "tcdb_attachment_depth": scenario_tcdb_attachment_depth,
    "interpro_enrichment": scenario_interpro_enrichment,
    "trust_filtered_tcdb": scenario_trust_filtered_tcdb,
    "organism_rollups": scenario_organism_rollups,
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
