"""Shared parameter types for MCP tool wrappers (spec 2b.5 R2 + D3).

``OntologyKey`` is the single source of truth for the 17-way ontology enum
that recurs across `list_filter_values`, `search_ontology`,
`genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`,
`pathway_enrichment`, and `cluster_enrichment` — one Literal instead of the
same 17 strings retyped per tool. Order matches
`multiomics_explorer.kg.queries_lib.ONTOLOGY_CONFIG`.

The `*Param` names below (D3) are each a full
``Annotated[<type>, Field(description=...)]`` — used directly as a tool's
parameter annotation (`name: OrganismParam = None`), one description per
shared parameter instead of one retyped per tool. Where a single tool needs
a tighter constraint on top of the shared type (an extra `min_length`, a
different `ge`), stack another `Field(...)` on top:
`Annotated[OrganismParam, Field(min_length=1)]` — pydantic merges the two
`FieldInfo` layers, with the outer one winning on overlap.

A handful of tools had a required (non-`Optional`) `str` / `list[str]`
param at spec baseline commit 8b8f16d — `organism`, `metabolite_ids`,
`publication_dois`. Sharing a description must never widen that JSON-schema
type to nullable, so each of those three gets a `*RequiredParam` sibling
(`OrganismRequiredParam`, `MetaboliteIdsRequiredParam`,
`PublicationDoisRequiredParam`) carrying the identical description text as
its `Optional` counterpart but a non-`Optional` type — used only on the
tools that were already required at baseline. Same story for `limit`: most
tools had a plain `int`; a few (`gene_overview`, `gene_details`,
`gene_homologs`, `ontology_landscape`, `gene_aa_sequence`,
`gene_neighbors`) had `int | None` (an "unbounded — pass a number to page"
default) — `LimitParam` stays non-`Optional` `int` (baseline majority) and
`LimitOptionalParam` covers the `int | None` minority.
`tests/unit/test_params.py::test_param_types_match_baseline` snapshots
every tool's per-param JSON-schema `type`/`anyOf`/`items`/`enum` +
`required` at 8b8f16d and asserts it is unchanged today — run before adding
a new shared type to catch this class of accidental widening.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

OntologyKey = Literal[
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
    "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
    "interpro", "ncbifam", "merops",
]

# ---------------------------------------------------------------------------
# Cross-cutting filters / paging / mode switches.
# ---------------------------------------------------------------------------

_ORGANISM_DESC = "Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms."

OrganismParam = Annotated[str | None, Field(description=_ORGANISM_DESC)]

OrganismRequiredParam = Annotated[str, Field(description=_ORGANISM_DESC)]

OrganismsParam = Annotated[list[str] | None, Field(
    description="Organisms, each word-matched as `organism`. Omit for all.",
)]

_LIMIT_DESC = "Max rows returned (paging)."

LimitParam = Annotated[int, Field(
    description=_LIMIT_DESC,
    ge=1,
)]

LimitOptionalParam = Annotated[int | None, Field(
    description=_LIMIT_DESC,
    ge=1,
)]

OffsetParam = Annotated[int, Field(
    description="Rows to skip (paging).",
    ge=0,
)]

SummaryParam = Annotated[bool, Field(
    description="True = envelope breakdowns only, no rows — the cheap first call.",
)]

VerboseParam = Annotated[bool, Field(
    description="True adds the fields listed under verbose_fields in docs://tools/{name}.",
)]

TreatmentTypeParam = Annotated[list[str] | None, Field(
    description="Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type').",
)]

BackgroundFactorsParam = Annotated[list[str] | None, Field(
    description="Keep experiments with any of these background_factors. Values: list_filter_values('background_factors').",
)]

GrowthPhasesParam = Annotated[list[str] | None, Field(
    description="Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase').",
)]

OmicsTypeParam = Annotated[list[str] | None, Field(
    description="Keep experiments whose omics_type is in this list. Values: list_filter_values('omics_type').",
)]

CompartmentParam = Annotated[str | None, Field(
    description="Keep rows in this compartment. Values: list_filter_values('compartment').",
)]

_PUBLICATION_DOIS_DESC = "Restrict to these publication DOIs."

PublicationDoisParam = Annotated[list[str] | None, Field(description=_PUBLICATION_DOIS_DESC)]

PublicationDoisRequiredParam = Annotated[list[str], Field(description=_PUBLICATION_DOIS_DESC)]

_METABOLITE_IDS_DESC = "Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites)."

MetaboliteIdsParam = Annotated[list[str] | None, Field(description=_METABOLITE_IDS_DESC)]

MetaboliteIdsRequiredParam = Annotated[list[str], Field(description=_METABOLITE_IDS_DESC)]

ExcludeMetaboliteIdsParam = Annotated[list[str] | None, Field(
    description="Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap.",
)]

InformativeOnlyParam = Annotated[bool, Field(
    description="True drops terms the KG flags uninformative (roots, catch-alls).",
)]

# ---------------------------------------------------------------------------
# Annotation-trust surface (PR 3a, moved from the former register_tools
# `_TRUST_*_DESC` module constants). See docs://analysis/annotation_evidence
# for the full trust model.
# ---------------------------------------------------------------------------

CallClass = Literal["peptidase", "inhibitor", "nonpeptidase_homolog"]

SourcesParam = Annotated[list[str] | None, Field(
    description="Keep rows whose edge sources[] contains any of these values. Valid on the 14 functional-edge ontologies (not PSORTb/SignalP). See list_filter_values('sources').",
)]

EvidenceParam = Annotated[list[str] | None, Field(
    description="Keep rows whose compact evidence-ladder value is in this list. Valid on the 14 functional-edge ontologies. See docs://analysis/annotation_evidence.",
)]

MaxTierParam = Annotated[int | None, Field(
    description="Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; null tier always kept). Valid on tcdb, merops only.",
    ge=1, le=3,
)]

MinEvidenceScoreParam = Annotated[float | None, Field(
    description="Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops.",
    ge=0, le=1,
)]

CallClassParam = Annotated[list[CallClass] | None, Field(
    description="MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows.",
)]
