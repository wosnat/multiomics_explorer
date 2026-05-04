"""CyVer validation of all query builder Cypher against the live KG.

Catches schema drift (renamed labels, removed properties, missing rel types)
after KG rebuilds. Each builder is called with representative args and
the generated Cypher is validated by SchemaValidator and PropertiesValidator.

SyntaxValidator false-negatives on $param syntax, so parameterized queries
are tested by substituting Cypher literals before validation (see
_substitute_params).

PropertiesValidator known limitations:
- Returns None for queries using fulltext indexes or CALL subqueries.
- False-positives on map projection keys (e.g. {org: g.organism_name}) —
  CyVer cannot distinguish map keys from property accesses.
  These false positives are filtered using _KNOWN_MAP_KEYS.
"""

import logging
import re

import pytest
from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_differential_expression_by_gene,
    build_gene_response_profile_envelope,
    build_gene_response_profile,
    build_differential_expression_by_gene_summary_by_experiment,
    build_differential_expression_by_gene_summary_diagnostics,
    build_differential_expression_by_gene_summary_global,
    build_differential_expression_by_ortholog_diagnostics,
    build_differential_expression_by_ortholog_group_check,
    build_differential_expression_by_ortholog_membership_counts,
    build_differential_expression_by_ortholog_results,
    build_differential_expression_by_ortholog_summary_global,
    build_differential_expression_by_ortholog_top_experiments,
    build_differential_expression_by_ortholog_top_groups,
    build_gene_details,
    build_gene_details_summary,
    build_gene_existence_check,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_gene_ontology_terms,
    build_gene_ontology_terms_summary,
    build_gene_overview,
    build_gene_overview_summary,
    build_gene_stub,
    build_genes_by_function,
    build_genes_by_function_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_diagnostics,
    build_genes_by_homolog_group_summary,
    build_genes_by_ontology_validate,
    build_genes_by_ontology_detail,
    build_genes_by_ontology_per_term,
    build_genes_by_ontology_per_gene,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_gene_categories,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_resolve_organism_for_experiments,
    build_resolve_organism_for_locus_tags,
    build_resolve_organism_for_organism,
    build_gene_clusters_by_gene,
    build_gene_clusters_by_gene_summary,
    build_genes_in_cluster,
    build_genes_in_cluster_summary,
    build_list_clustering_analyses,
    build_list_clustering_analyses_summary,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_search_ontology,
    build_search_ontology_summary,
    build_ontology_landscape,
    build_ontology_expcov,
    build_ontology_experiment_check,
    build_ontology_organism_gene_count,
)

# Suppress EXPLAIN notification noise from CyVer validators.
logging.getLogger("neo4j").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Param substitution for SyntaxValidator
# ---------------------------------------------------------------------------

def _cypher_literal(value) -> str:
    """Convert a Python value to a Cypher literal string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(_cypher_literal(v) for v in value) + "]"
    raise TypeError(f"Unsupported param type for CyVer substitution: {type(value)}")


def _substitute_params(cypher: str, params: dict) -> str:
    """Replace $param placeholders with Cypher literals.

    Longest keys first to avoid partial replacement (e.g. $organism before $org).
    """
    for key in sorted(params, key=len, reverse=True):
        cypher = re.sub(
            r"\$" + re.escape(key) + r"(?!\w)",
            _cypher_literal(params[key]),
            cypher,
        )
    return cypher

# Map projection keys used across query builders.  PropertiesValidator
# cannot distinguish {org: g.organism_name} from g.org, so it reports
# these as missing node properties.  We filter them out.
# Also includes sparse/future-proofed properties that exist in the schema
# but are not yet populated on all nodes (e.g. p_value on Gene_in_gene_cluster).
_KNOWN_MAP_KEYS = {
    "org", "cat", "lt", "cnt", "terms", "srcs", "gid",
    "org_input", "tt", "bfs", "ts", "gp", "eid", "status", "log2fc", "m",
    "tpo", "tph", "tp", "nf_raw", "ng_raw", "nm_raw",
    "cr_id", "cr_name", "cc_id", "cc_name", "og_ids", "src", "lvl",
    "cid", "cname",
    # Sparse cluster properties — valid in schema, not populated on all nodes
    "p_value",
    # ontology_landscape verbose example_terms map projection keys
    "term_id", "n_genes",
    # Sparse ontology property — present on GO nodes with best-effort levels,
    # absent on flat ontology nodes (CyanorakRole, TigrRole, etc.)
    "level_is_best_effort",
    # BRITE-only properties — present on BriteCategory nodes,
    # absent on all other ontology labels (returns null)
    "tree", "tree_code",
    # F1 informativeness flag — sparse on 7 ontology types
    # (KeggTerm, BiologicalProcess, MolecularFunction, CellularComponent,
    #  CogFunctionalCategory, CyanorakRole, TigrRole); coalesce-handled
    # for nodes without the property.
    "is_uninformative",
}

# Regex to extract property name from CyVer description:
# "...the missing property name is: foo"
_MISSING_PROP_RE = re.compile(r"missing property name is: (\w+)")


def _filter_false_positive_warnings(meta: list[dict]) -> list[dict]:
    """Remove PropertiesValidator warnings about known map-key aliases."""
    real = []
    for m in meta:
        match = _MISSING_PROP_RE.search(m.get("description", ""))
        if match and match.group(1) in _KNOWN_MAP_KEYS:
            continue
        # InvalidPropertyAccessByLabelWarning — check if ALL flagged props
        # are known map keys (e.g. "Gene does not have: org, cat.")
        if m.get("code") == "InvalidPropertyAccessByLabelWarning":
            desc = m.get("description", "")
            # Extract "properties:  org, cat." portion
            prop_match = re.search(r"properties:\s+(.+?)\.?$", desc)
            if prop_match:
                props = {p.strip() for p in prop_match.group(1).split(",")}
                if props <= _KNOWN_MAP_KEYS:
                    continue
        real.append(m)
    return real


def _assert_properties_valid(score, meta, label: str):
    """Assert PropertiesValidator result, filtering known false positives."""
    if score is None:
        # PropertiesValidator can't analyze fulltext/CALL queries — not actionable.
        return
    if score == 1.0:
        return
    real_warnings = _filter_false_positive_warnings(meta)
    if not real_warnings:
        return  # All warnings were false positives.
    descriptions = [m["description"] for m in real_warnings]
    raise AssertionError(
        f"Property score {score} for {label}: {descriptions}"
    )


# ---------------------------------------------------------------------------
# Dummy args for each builder.  Values don't matter — CyVer validates Cypher
# structure (labels, rels, properties) not data.
# ---------------------------------------------------------------------------

_LOCUS = ["PMM0001"]
_ORGANISM = "MED4"
_GROUPS = ["OG_1"]
_EIDS = ["EXP_1"]
_TERM_IDS = ["GO:0008150"]

# (test_id, builder_callable, kwargs)
# Ontology-dependent builders are expanded below via ONTOLOGY_CONFIG.
_BUILDERS: list[tuple[str, ...]] = [
    # --- resolve / overview ---
    ("resolve_gene", build_resolve_gene, {"identifier": "PMM0001"}),
    ("genes_by_function_summary", build_genes_by_function_summary, {"search_text": "photosystem"}),
    ("genes_by_function", build_genes_by_function, {"search_text": "photosystem"}),
    ("gene_overview_summary", build_gene_overview_summary, {"locus_tags": _LOCUS}),
    ("gene_overview", build_gene_overview, {"locus_tags": _LOCUS}),
    ("gene_details", build_gene_details, {"locus_tags": _LOCUS}),
    ("gene_details_summary", build_gene_details_summary, {"locus_tags": _LOCUS}),
    ("gene_stub", build_gene_stub, {"gene_id": "PMM0001"}),
    ("gene_existence_check", build_gene_existence_check, {"locus_tags": _LOCUS}),
    # --- homologs ---
    ("gene_homologs_summary", build_gene_homologs_summary, {"locus_tags": _LOCUS}),
    ("gene_homologs", build_gene_homologs, {"locus_tags": _LOCUS}),
    # --- publications ---
    ("list_publications", build_list_publications, {}),
    ("list_publications_search", build_list_publications, {"search_text": "light"}),
    ("list_publications_dois", build_list_publications, {"publication_dois": ["10.1038/ismej.2016.70"]}),
    ("list_publications_summary", build_list_publications_summary, {}),
    ("list_publications_summary_search", build_list_publications_summary, {"search_text": "light"}),
    # --- organisms ---
    ("list_gene_categories", build_list_gene_categories, {}),
    ("list_organisms", build_list_organisms, {}),
    ("list_organisms_verbose", build_list_organisms, {"verbose": True}),
    # --- experiments ---
    ("list_experiments", build_list_experiments, {}),
    ("list_experiments_search", build_list_experiments, {"search_text": "light"}),
    ("list_experiments_summary", build_list_experiments_summary, {}),
    ("list_experiments_summary_search", build_list_experiments_summary, {"search_text": "light"}),
    # --- homolog group search ---
    ("search_homolog_groups_summary", build_search_homolog_groups_summary, {"search_text": "photosystem"}),
    ("search_homolog_groups", build_search_homolog_groups, {"search_text": "photosystem"}),
    # --- homologs with ontology filters ---
    ("gene_homologs_summary_ont", build_gene_homologs_summary,
     {"locus_tags": _LOCUS, "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("gene_homologs_ont", build_gene_homologs,
     {"locus_tags": _LOCUS, "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("gene_homologs_verbose", build_gene_homologs,
     {"locus_tags": _LOCUS, "verbose": True}),
    ("search_homolog_groups_summary_ont", build_search_homolog_groups_summary,
     {"search_text": "photosystem", "cog_categories": ["cog.category:C"]}),
    ("search_homolog_groups_ont", build_search_homolog_groups,
     {"search_text": "photosystem", "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("search_homolog_groups_verbose", build_search_homolog_groups,
     {"search_text": "photosystem", "verbose": True}),
    # --- genes by homolog group ---
    ("genes_by_homolog_group_summary", build_genes_by_homolog_group_summary, {"group_ids": _GROUPS}),
    ("genes_by_homolog_group_diagnostics", build_genes_by_homolog_group_diagnostics, {"group_ids": _GROUPS}),
    ("genes_by_homolog_group", build_genes_by_homolog_group, {"group_ids": _GROUPS}),
    # --- differential expression by gene ---
    ("de_by_gene_summary_global", build_differential_expression_by_gene_summary_global, {}),
    ("de_by_gene_summary_by_experiment", build_differential_expression_by_gene_summary_by_experiment, {}),
    ("de_by_gene_summary_diagnostics", build_differential_expression_by_gene_summary_diagnostics, {}),
    ("de_by_gene_summary_diagnostics_batch", build_differential_expression_by_gene_summary_diagnostics, {"locus_tags": _LOCUS}),
    ("de_by_gene", build_differential_expression_by_gene, {}),
    # --- organism pre-validation ---
    ("resolve_organism_for_organism", build_resolve_organism_for_organism, {"organism": "Prochlorococcus"}),
    ("resolve_organism_for_locus_tags", build_resolve_organism_for_locus_tags, {"locus_tags": _LOCUS}),
    ("resolve_organism_for_experiments", build_resolve_organism_for_experiments, {"experiment_ids": _EIDS}),
    # --- differential expression by ortholog ---
    ("de_by_ortholog_group_check", build_differential_expression_by_ortholog_group_check, {"group_ids": _GROUPS}),
    ("de_by_ortholog_summary_global", build_differential_expression_by_ortholog_summary_global, {"group_ids": _GROUPS}),
    ("de_by_ortholog_top_groups", build_differential_expression_by_ortholog_top_groups, {"group_ids": _GROUPS}),
    ("de_by_ortholog_top_experiments", build_differential_expression_by_ortholog_top_experiments, {"group_ids": _GROUPS}),
    ("de_by_ortholog_results", build_differential_expression_by_ortholog_results, {"group_ids": _GROUPS}),
    ("de_by_ortholog_membership_counts", build_differential_expression_by_ortholog_membership_counts, {"group_ids": _GROUPS}),
    # --- gene_response_profile ---
    ("gene_response_profile_envelope", build_gene_response_profile_envelope,
     {"locus_tags": _LOCUS, "organism_name": _ORGANISM}),
    ("gene_response_profile", build_gene_response_profile,
     {"locus_tags": _LOCUS, "organism_name": _ORGANISM}),
    ("gene_response_profile_by_experiment", build_gene_response_profile,
     {"locus_tags": _LOCUS, "organism_name": _ORGANISM, "group_by": "experiment"}),
    # --- clustering analyses ---
    ("list_clustering_analyses_summary", build_list_clustering_analyses_summary, {}),
    ("list_clustering_analyses", build_list_clustering_analyses, {}),
    ("list_clustering_analyses_verbose", build_list_clustering_analyses, {"verbose": True}),
    ("list_clustering_analyses_search", build_list_clustering_analyses_summary, {"search_text": "nitrogen"}),
    # --- gene_clusters_by_gene ---
    ("gene_clusters_by_gene_summary", build_gene_clusters_by_gene_summary, {"locus_tags": _LOCUS}),
    ("gene_clusters_by_gene", build_gene_clusters_by_gene, {"locus_tags": _LOCUS}),
    ("gene_clusters_by_gene_verbose", build_gene_clusters_by_gene, {"locus_tags": _LOCUS, "verbose": True}),
    # --- genes_in_cluster ---
    ("genes_in_cluster_summary", build_genes_in_cluster_summary, {"cluster_ids": ["cluster:test"]}),
    ("genes_in_cluster", build_genes_in_cluster, {"cluster_ids": ["cluster:test"]}),
    ("genes_in_cluster_verbose", build_genes_in_cluster, {"cluster_ids": ["cluster:test"], "verbose": True}),
    ("genes_in_cluster_by_analysis", build_genes_in_cluster, {"analysis_id": "clustering_analysis:test"}),
    # --- ontology landscape non-ontology builders ---
    ("ontology_experiment_check", build_ontology_experiment_check, {"experiment_ids": _EIDS}),
    ("ontology_organism_gene_count", build_ontology_organism_gene_count, {"organism_name": "Prochlorococcus MED4"}),
]

# Ontology-dependent builders: expand for each ontology key.
for _ont_key in ONTOLOGY_CONFIG:
    _BUILDERS.extend([
        (
            f"search_ontology_summary_{_ont_key}",
            build_search_ontology_summary,
            {"ontology": _ont_key, "search_text": "test"},
        ),
        (
            f"search_ontology_{_ont_key}",
            build_search_ontology,
            {"ontology": _ont_key, "search_text": "test"},
        ),
        (
            f"genes_by_ontology_validate_{_ont_key}",
            build_genes_by_ontology_validate,
            {"ontology": _ont_key, "term_ids": _TERM_IDS, "level": None},
        ),
        (
            f"genes_by_ontology_detail_{_ont_key}",
            build_genes_by_ontology_detail,
            {
                "ontology": _ont_key,
                "organism": "Prochlorococcus MED4",
                "level": 1,
                "min_gene_set_size": 5,
                "max_gene_set_size": 500,
            },
        ),
        (
            f"genes_by_ontology_detail_verbose_{_ont_key}",
            build_genes_by_ontology_detail,
            {
                "ontology": _ont_key,
                "organism": "Prochlorococcus MED4",
                "level": 1,
                "min_gene_set_size": 5,
                "max_gene_set_size": 500,
                "verbose": True,
            },
        ),
        (
            f"genes_by_ontology_per_term_{_ont_key}",
            build_genes_by_ontology_per_term,
            {
                "ontology": _ont_key,
                "organism": "Prochlorococcus MED4",
                "level": 1,
                "term_ids": None,
                "min_gene_set_size": 5,
                "max_gene_set_size": 500,
            },
        ),
        (
            f"genes_by_ontology_per_gene_{_ont_key}",
            build_genes_by_ontology_per_gene,
            {
                "ontology": _ont_key,
                "organism": "Prochlorococcus MED4",
                "level": 1,
                "term_ids": None,
                "min_gene_set_size": 5,
                "max_gene_set_size": 500,
            },
        ),
        (
            f"gene_ontology_terms_summary_{_ont_key}",
            build_gene_ontology_terms_summary,
            {"ontology": _ont_key, "locus_tags": _LOCUS,
             "organism_name": "Prochlorococcus MED4"},
        ),
        (
            f"gene_ontology_terms_{_ont_key}",
            build_gene_ontology_terms,
            {"ontology": _ont_key, "locus_tags": _LOCUS,
             "organism_name": "Prochlorococcus MED4"},
        ),
        (
            f"ontology_landscape_{_ont_key}",
            build_ontology_landscape,
            {"ontology": _ont_key, "organism_name": "Prochlorococcus MED4"},
        ),
        (
            f"ontology_landscape_verbose_{_ont_key}",
            build_ontology_landscape,
            {"ontology": _ont_key, "organism_name": "Prochlorococcus MED4", "verbose": True},
        ),
        (
            f"ontology_expcov_{_ont_key}",
            build_ontology_expcov,
            {"ontology": _ont_key, "organism_name": "Prochlorococcus MED4", "experiment_ids": _EIDS},
        ),
    ])

# Differential-expression-by-ortholog diagnostics returns a *list* of
# (cypher, params) tuples — handled separately.
_DE_ORTHO_DIAG_CASES = [
    (
        "de_by_ortholog_diagnostics_organisms",
        {"group_ids": _GROUPS, "organisms": ["Prochlorococcus"]},
    ),
    (
        "de_by_ortholog_diagnostics_experiments",
        {"group_ids": _GROUPS, "experiment_ids": _EIDS},
    ),
    (
        "de_by_ortholog_diagnostics_both",
        {"group_ids": _GROUPS, "organisms": ["Prochlorococcus"], "experiment_ids": _EIDS},
    ),
]


def _builder_ids():
    return [b[0] for b in _BUILDERS]


def _builder_args():
    return [(b[1], b[2]) for b in _BUILDERS]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.kg
class TestBuilderSchemaValidation:
    """Validate all query builder Cypher against the live KG schema."""

    @pytest.fixture(scope="class")
    def schema_validator(self, neo4j_driver):
        return SchemaValidator(neo4j_driver)

    @pytest.mark.parametrize(
        "builder_fn, kwargs", _builder_args(), ids=_builder_ids(),
    )
    def test_schema_valid(self, schema_validator, builder_fn, kwargs):
        cypher, _params = builder_fn(**kwargs)
        score, meta = schema_validator.validate(cypher)
        descriptions = [m["description"] for m in meta]
        assert score == 1.0, (
            f"Schema score {score} for {builder_fn.__name__}: {descriptions}"
        )

    @pytest.mark.parametrize(
        "test_id, kwargs", _DE_ORTHO_DIAG_CASES, ids=[c[0] for c in _DE_ORTHO_DIAG_CASES],
    )
    def test_schema_valid_de_ortholog_diagnostics(
        self, schema_validator, test_id, kwargs,
    ):
        queries = build_differential_expression_by_ortholog_diagnostics(**kwargs)
        assert queries is not None, f"{test_id}: expected diagnostic queries"
        for i, (cypher, _params) in enumerate(queries):
            score, meta = schema_validator.validate(cypher)
            descriptions = [m["description"] for m in meta]
            assert score == 1.0, (
                f"Schema score {score} for {test_id}[{i}]: {descriptions}"
            )


@pytest.mark.kg
class TestBuilderPropertyValidation:
    """Validate all query builder Cypher properties against the live KG."""

    @pytest.fixture(scope="class")
    def property_validator(self, neo4j_driver):
        return PropertiesValidator(neo4j_driver)

    @pytest.mark.parametrize(
        "builder_fn, kwargs", _builder_args(), ids=_builder_ids(),
    )
    def test_properties_valid(self, property_validator, builder_fn, kwargs):
        cypher, _params = builder_fn(**kwargs)
        score, meta = property_validator.validate(cypher)
        _assert_properties_valid(score, meta, builder_fn.__name__)

    @pytest.mark.parametrize(
        "test_id, kwargs", _DE_ORTHO_DIAG_CASES, ids=[c[0] for c in _DE_ORTHO_DIAG_CASES],
    )
    def test_properties_valid_de_ortholog_diagnostics(
        self, property_validator, test_id, kwargs,
    ):
        queries = build_differential_expression_by_ortholog_diagnostics(**kwargs)
        assert queries is not None, f"{test_id}: expected diagnostic queries"
        for i, (cypher, _params) in enumerate(queries):
            score, meta = property_validator.validate(cypher)
            _assert_properties_valid(score, meta, f"{test_id}[{i}]")


@pytest.mark.kg
class TestBuilderSyntaxValidation:
    """SyntaxValidator with param substitution for all builders."""

    @pytest.fixture(scope="class")
    def syntax_validator(self, neo4j_driver):
        return SyntaxValidator(neo4j_driver)

    @pytest.mark.parametrize(
        "builder_fn, kwargs", _builder_args(), ids=_builder_ids(),
    )
    def test_syntax_valid(self, syntax_validator, builder_fn, kwargs):
        cypher, params = builder_fn(**kwargs)
        query = _substitute_params(cypher, params) if params else cypher
        valid, meta = syntax_validator.validate(query)
        descriptions = [m["description"] for m in meta]
        assert valid, (
            f"Syntax error for {builder_fn.__name__}: {descriptions}"
        )

    @pytest.mark.parametrize(
        "test_id, kwargs", _DE_ORTHO_DIAG_CASES, ids=[c[0] for c in _DE_ORTHO_DIAG_CASES],
    )
    def test_syntax_valid_de_ortholog_diagnostics(
        self, syntax_validator, test_id, kwargs,
    ):
        queries = build_differential_expression_by_ortholog_diagnostics(**kwargs)
        assert queries is not None, f"{test_id}: expected diagnostic queries"
        for i, (cypher, params) in enumerate(queries):
            query = _substitute_params(cypher, params) if params else cypher
            valid, meta = syntax_validator.validate(query)
            descriptions = [m["description"] for m in meta]
            assert valid, (
                f"Syntax error for {test_id}[{i}]: {descriptions}"
            )
