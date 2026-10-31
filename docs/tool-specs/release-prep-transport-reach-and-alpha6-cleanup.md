# Release prep: organism-scoped transport reach, TCDB role-only genes, alpha.6 API cleanup (Mode B)

**Status:** FROZEN 2026-10-31 (user-approved; compartment-as-list deferred) · **KG:** dev build `2026-10-31T14:01:03Z` ·
**Backlog:** 2c.5, 2c.19, 2.15 · No KG ask; no `mcp_min_version` bump of its own (rides the
next release, which is already breaking).

## 1. Purpose

Three items to close before the next explorer release:

- **2c.5** — `list_metabolites(organism_names=[X], evidence_sources=[S])` combines two unrelated
  conditions: "X reaches the metabolite by *any* route" and "*some* organism or TCDB system gives
  it evidence S". Under `transport` the answer looks the same for every organism (MED4 + transport
  + N: 147 metabolites; `top_organisms` 145–147 for every Pro / Syn strain). MED4's transport
  reach is actually 20 of those.
- **2c.19** — genes whose only TCDB route is a direct system with chemical-role substrates (e.g.
  SMR / BmrA efflux pumps → "drug") get no `transport` tag in `gene_overview.evidence_sources` and
  don't count toward `has_chemistry`, though `metabolites_by_gene` returns role rows for them and
  the GO route already counts role targets.
- **2.15** — the alpha.6 breaking-cleanup queue promised in the alpha.5 deprecation warnings.

## 2. Out of scope

2c.9 (genome-plausibility of substrates); per-row route-scoped `organism_names` / `organism_count`
on `list_metabolites` rows (stay any-route); `Gene.transported_metabolite_count` (KG precompute,
metabolites only by definition — unchanged); 2b.6 tool merges; compartment-as-list (see §6, open
decision).

## 3. KG facts (verified live, build 2026-10-31T14:01:03Z)

| Fact | Live value |
|---|---|
| `Organism_has_metabolite.evidence_sources` values | `metabolism` 132,665 edges · `transport` 8,738 · `measured` 408 (118 / 118 / 5 organisms) |
| Edge organism set = `Metabolite.organism_names` | equal on 2,590 / 2,590 metabolites with edges |
| `measured` edge ↔ metabolite-level `metabolomics` | 135 = 135 metabolites, same set |
| `transport` metabolite-level vs edge-level | 1,311 metabolites are TCDB substrates of some system; 458 are reached by some organism's gene (direct gate) |
| MED4 + `transport` + `N`: current vs edge-scoped | 147 → **20** |
| No organism filter, `transport` + `N`, `top_organisms` | current (any route): KT2440 275, W3-18-1 236, DSS-3 226 · edge-scoped: KT2440 147, W3-18-1 103, Marinobacter 87; MED4 20 |
| 2c.19 genes: direct TCDB system with role substrates, no metabolite substrate | **108** (was 29 when logged); 35 have a GO transport route, 73 have no other chemistry → `has_chemistry` false today |

## 4. Changes

### 4.1 `list_metabolites` (2c.5)

Route map: `metabolism` → edge `metabolism`; `transport` → edge `transport`; `metabolomics` →
edge `measured`; `go_transport` → `m.go_transport_organism_names` (unchanged source).

- **Filter.** When `organism_names` AND `evidence_sources` are both set, a metabolite matches only
  if a listed organism reaches it by one of the listed routes:
  ```cypher
  ( EXISTS { MATCH (o:OrganismTaxon)-[r:Organism_has_metabolite]->(m)
             WHERE toLower(o.preferred_name) IN $organism_names_lc
               AND ANY(s IN coalesce(r.evidence_sources, []) WHERE s IN $edge_sources) }
    OR ($want_go AND ANY(o IN coalesce(m.go_transport_organism_names, [])
                         WHERE toLower(o) IN $organism_names_lc)) )
  ```
  (verified: MED4 / transport / N = 20). Either filter alone is unchanged: `organism_names` alone
  = any route; `evidence_sources` alone = metabolite-level (catalogue sense: `transport` = some
  TCDB system lists it).
- **`top_organisms`.** When `evidence_sources` is set, count an organism only by the listed routes
  (per-metabolite `CALL { … collect(o.preferred_name) }` over matching edges, plus GO names when
  `go_transport` is listed). Without `evidence_sources`, unchanged.
- **No-formula count** shares `_list_metabolites_where` → picks the change up automatically.
- **Docs.** `organism_names` / `evidence_sources` Field descriptions + yaml mistake entry ("with
  both filters, the organism must reach the metabolite by that route"); envelope `top_organisms`
  description. CHANGELOG `Changed` (row counts drop).

### 4.2 `gene_overview` (2c.19)

`queries_lib.py` `chemistry_with` `transport` EXISTS and the `has_chemistry` summary EXISTS:
`Tcdb_family_transports_metabolite]->(:Metabolite)` → `{_TCDB_SUBSTRATE_RELS}]->(:Metabolite|ChemicalRole)`.
The `metabolomics` EXISTS stays metabolite-only (roles have no assays). Field descriptions for
`evidence_sources` / `has_chemistry` say transport includes chemical-role substrates;
`transported_metabolite_count` stays metabolites-only (say so: a gene can be tagged `transport`
with count 0). CHANGELOG `Fixed`.

### 4.3 alpha.6 API cleanup (2.15) — breaking, Python API + one MCP envelope rename

1. **Remove `api/_compat.py`** and all 27 `deprecated_alias` call sites: the 22 renamed keywords
   (`publication_doi`→`publication_dois` ×11, `mass_min/max`, `value_min/max`, `bucket`, `flag`,
   `category`, `treatment_types`, `metric_percentile_min/max`, `rank_by_metric_max`) and the 5
   `listify=True` shims (same-name params; `listify_bare_str` already covers bare strings —
   confirm each of the 5 params is in its scope, else add it). Delete `tests/unit/test_api_compat.py`
   and the `test_deprecated_alias_*` tests; add one test per tool family that the old keyword now
   raises `TypeError`. Checked: no old keyword in use in `multiomics_analysis` / `multiomics_research`.
2. **Rename `not_found.publication_doi` → `publication_dois`** on `list_metabolite_assays`,
   `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay` (Pydantic `LmaNotFound` /
   `MqaNotFound` / `MfaNotFound` + api dict keys + yaml examples). MCP-visible → CHANGELOG `Breaking`.
3. **`kg_release_info(*, conn: GraphConnection | None = None)`** like every other function;
   update `server.py:45` and the 7 test call sites; drop the exception note from `python_api.md`.

## 5. Tests / gates

Unit RED first per layer (builder Cypher contains the edge-scoped EXISTS only when both filters
are set; role rel in both gene_overview EXISTS; removed keywords raise; renamed not_found key).
`-m kg`: MED4/transport/N = 20; a role-only gene (e.g. `SynWH7803_0604`) tagged `transport` and
counted by `has_chemistry`. Regression `--force-regen` with a classified diff; `refresh_examples
--check`; `build_about_content.py --live-vocab` then `--lint`; code review (hard gate).

## 6. Decided: deferred

**Compartment as `list[str]`** (the "consider" in 2.15): 12 functions take `compartment: str`.
Recommendation: **defer** — it's a schema change on 12 MCP tools with no user request behind it,
and it can be added non-breakingly later (`str | list[str]`).
