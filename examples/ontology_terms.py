"""Example: the term side of the ontology surface — browsing terms without a
search string, fanning one search across several ontologies, and drilling
into a batch of term IDs (parents / children / bridge links).

See docs://ontologies/index for the per-ontology reference and
docs://analysis/annotation_evidence for the trust surface; this script is
their runnable companion.

Run with: uv run python examples/ontology_terms.py --scenario <name>

Scenarios:
  1. browse_merops      — search_ontology with no search_text (browse mode):
                          MEROPS families at level 1 ranked by gene_count
  2. multi_search       — one search_text across go_bp + tcdb with lockstep
                          paging (limit applies per ontology)
  3. term_details_batch — ontology_term_details on a mixed batch incl. an
                          unknown ID (not_found), showing hierarchy + links
  4. bridge_walk        — follow forward-only bridges: tcdb → pfam
                          (composition) → interpro (membership)

Notes:
- Browse mode sorts by `gene_count DESC, id` and leaves `score` null; the
  envelope says `mode: 'browse'` and carries `by_level`.
- Multi-ontology calls order rows by ontology (registry order) then score;
  `limit`/`offset` apply per ontology, so `returned <= limit * n`.
- Bridges are forward-only: `links_out` on the source term, no `links_in`.
  `router` links (InterPro → EC / CAZy) are recall-biased cross-references,
  never a gene-function call.
"""
# CONTENTS
#   1. scenario_browse_merops      — search_ontology browse mode (line ~53)
#   2. scenario_multi_search       — one search_text across two ontologies (line ~82)
#   3. scenario_term_details_batch — ontology_term_details on a mixed batch (line ~113)
#   4. scenario_bridge_walk        — forward-only bridge chain tcdb -> pfam -> interpro (line ~149)
from __future__ import annotations

import argparse
import sys
from typing import Callable

from multiomics_explorer import ontology_term_details, search_ontology


def _show_links(row: dict, max_rows: int = 5) -> None:
    links = row.get("links_out") or []
    for link in links[:max_rows]:
        print(f"      -> {link.get('target_ontology'):<9} {link.get('target_id'):<22} "
              f"[{link.get('link_kind')}] {str(link.get('target_name') or '')[:40]}")
    if len(links) > max_rows:
        print(f"      ... {len(links) - max_rows} more links")


def scenario_browse_merops() -> None:
    """Use this when the user asks 'what peptidase families are there and
    which are biggest?' — no keyword to search for, just a ranked listing.

    Browse mode = `search_text=None`. Sorted by gene_count, filtered by level.
    """
    print("=== Scenario: browse_merops ===")
    print("Question class: 'list an ontology's terms by size, no keyword'")
    print()

    result = search_ontology(
        search_text=None,
        ontology=["merops"],
        level=1,
        limit=10,
    )
    print(f"mode={result.get('mode')}  total_matching={result.get('total_matching')}  "
          f"returned={result.get('returned')}  truncated={result.get('truncated')}")
    print(f"by_level={result.get('by_level')}")
    print()
    print("MEROPS families at level 1, by gene_count (all organisms):")
    for row in result.get("results", []):
        print(f"    {row.get('id'):<22} {str(row.get('name') or '')[:34]:<34} "
              f"gene_count={row.get('gene_count')}  organism_count={row.get('organism_count')}")
    print()
    print("gene_count counts every homology hit, including non-peptidase homologs;")
    print("quote peptidase_gene_count (verbose / ontology_term_details) for protease counts.")


def scenario_multi_search() -> None:
    """Use this when a keyword could live in several ontologies — 'transport'
    is a GO process *and* a TCDB family name — and the user wants both views
    in one call.

    `ontology=[...]` fans out per ontology; `limit` applies to each.
    """
    print("=== Scenario: multi_search ===")
    print("Question class: 'one keyword, several ontologies, lockstep paging'")
    print()

    result = search_ontology(
        search_text="transport",
        ontology=["go_bp", "tcdb"],
        limit=5,
    )
    print(f"mode={result.get('mode')}  returned={result.get('returned')} "
          f"(<= limit x 2 ontologies)")
    for entry in result.get("by_ontology") or []:
        print(f"  by_ontology[{entry.get('ontology')}]: total_matching={entry.get('total_matching')} "
              f"returned={entry.get('returned')} truncated={entry.get('truncated')}")
    print()
    for row in result.get("results", []):
        print(f"    {row.get('ontology_type'):<6} {row.get('id'):<16} "
              f"score={row.get('score')}  level={row.get('level')}  "
              f"{str(row.get('name') or '')[:40]}")
    print()
    print("Rows are grouped by ontology (registry order) then score — Lucene scores")
    print("are per index, so never rank a go_bp row against a tcdb row by score.")


def scenario_term_details_batch() -> None:
    """Use this when you already hold term IDs (from search, enrichment or a
    paper) and need their context — parents, children, bridges, size — in
    one call, across ontologies.

    IDs are self-prefixed CURIEs; unknown IDs land in `not_found`.
    """
    print("=== Scenario: term_details_batch ===")
    print("Question class: 'what are these terms, where do they sit, what do they link to'")
    print()

    term_ids = [
        "tcdb:3.A.1",           # ABC superfamily — many children, many bridges
        "merops.family:S14",    # Clp protease family
        "interpro:IPR000362",   # router links to EC
        "ncbifam:NF000812",     # flat, no hierarchy, no links
        "go:0006979",           # response to oxidative stress
        "bogus:xyz",            # not a term
    ]
    result = ontology_term_details(term_ids=term_ids)
    print(f"total_matching={result.get('total_matching')}  not_found={result.get('not_found')}")
    print(f"by_ontology={result.get('by_ontology')}")
    print(f"links_out_total={result.get('links_out_total')}  by_link_kind={result.get('by_link_kind')}")
    print()
    for row in result.get("results", []):
        print(f"  {row.get('term_id'):<22} [{row.get('ontology')}] level={row.get('level')} "
              f"gene_count={row.get('gene_count')} organism_count={row.get('organism_count')}")
        print(f"      parents={[p.get('id') if isinstance(p, dict) else p for p in row.get('parents') or []]}  "
              f"children_total={row.get('children_total')} "
              f"(truncated={row.get('children_truncated')})  links_out={len(row.get('links_out') or [])}")
        _show_links(row, max_rows=3)
    print()
    print("Rows keep input order; a missing compact column (e.g. direct_gene_count on")
    print("a flat NCBIfam family) is absent, not null.")


def scenario_bridge_walk() -> None:
    """Use this when the user asks 'what is this transporter family built
    from, and what does the integrated signature database call those
    parts?' — a two-hop walk over forward-only bridges.

    tcdb → pfam is `composition`; pfam → interpro is `membership`.
    """
    print("=== Scenario: bridge_walk ===")
    print("Question class: 'tcdb family -> Pfam domains -> InterPro entries'")
    print()

    hop1 = ontology_term_details(term_ids=["tcdb:3.A.1"], link_kinds=["composition"])
    row = (hop1.get("results") or [{}])[0]
    pfam_ids = sorted({
        link["target_id"] for link in row.get("links_out") or []
        if link.get("target_ontology") == "pfam"
    })
    print(f"tcdb:3.A.1 -> {len(pfam_ids)} Pfam domains via composition links "
          f"(links_out_total={hop1.get('links_out_total')})")
    print(f"    first few: {pfam_ids[:5]}")
    print()

    hop2 = ontology_term_details(term_ids=pfam_ids[:10], link_kinds=["membership"])
    print("pfam -> interpro (membership):")
    interpro_ids: set[str] = set()
    for prow in hop2.get("results", []):
        targets = [
            link.get("target_id") for link in prow.get("links_out") or []
            if link.get("target_ontology") == "interpro"
        ]
        interpro_ids.update(t for t in targets if t)
        print(f"    {prow.get('term_id'):<16} {str(prow.get('name') or '')[:30]:<30} -> {targets}")
    print()
    print(f"Reached {len(interpro_ids)} interpro entries in two hops.")
    print("Each hop is read from the *source* term (no links_in). Bridges describe")
    print("what a family is built from — they never transfer function to a gene.")


SCENARIOS: dict[str, Callable[[], None]] = {
    "browse_merops": scenario_browse_merops,
    "multi_search": scenario_multi_search,
    "term_details_batch": scenario_term_details_batch,
    "bridge_walk": scenario_bridge_walk,
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
