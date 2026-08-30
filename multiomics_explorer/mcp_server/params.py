"""Shared parameter types for MCP tool wrappers (spec 2b.5 R2).

``OntologyKey`` is the single source of truth for the 17-way ontology enum
that recurs across `list_filter_values`, `search_ontology`,
`genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`,
`pathway_enrichment`, and `cluster_enrichment` — one Literal instead of the
same 17 strings retyped per tool. Order matches
`multiomics_explorer.kg.queries_lib.ONTOLOGY_CONFIG`.
"""
from __future__ import annotations

from typing import Literal

OntologyKey = Literal[
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
    "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
    "interpro", "ncbifam", "merops",
]
