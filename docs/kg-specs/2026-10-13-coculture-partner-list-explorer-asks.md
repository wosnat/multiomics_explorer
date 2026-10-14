# Explorer-side asks: `Experiment.coculture_partner` becomes a list (2026-10-13)

**Date:** 2026-10-13 · **From:** KG (`multiomics_biocypher_kg`) · **To:** explorer (`multiomics_explorer`)
**Context:** the `2026-10-06-pro_n_import_coculture` analysis (methodology review round 2,
`docs/methodology-review-2026-10.md`) reported that `list_experiments(coculture_partner="Alteromonas")`
returned 5 RNA-seq experiments and missed the Weissberg 2025 proteomics, because `coculture_partner`
is populated only when coculture is the *treatment*. The KG is fixing the data model; this doc is the
contract change the explorer needs to absorb, plus the questions where the explorer's view should
shape the KG side. KG plan: `multiomics_biocypher_kg/plans/coculture_partner_background.md`.
Direction note: previous asks docs in this folder run explorer → KG; this one runs KG → explorer.

## 1. What the KG measured (2026-10-13, every wired paperconfig)

| Role of coculture in the experiment | Partner recorded today | Experiments |
|---|---|---|
| treatment (`'coculture' IN treatment_type`) | yes | 76 |
| background (`'coculture' IN background_factors` only) | **no** | **35** |
| background | yes | 3 |

The 35 by paper: Moreno 2023 **20** (MED4, SS120, WH7803, WH8102, BL107 proteomics in "non-axenic"
cultures with **two** heterotrophs at once — Marinobacter (MarRef v6) + Alteromonas (MarRef v6));
Barreto 2022 5; Weissberg 2025 4 (MED4 ↔ HOT1A3, RNA-seq + proteomics); Biller 2018 2 and Coe 2024 2
(NATL2A ↔ MIT1002); Hennon 2017 2 (MIT9312 ↔ EZ55). Moreno is why a scalar cannot do the job.

## 2. The contract change (BREAKING)

| | Today | Next KG build |
|---|---|---|
| `Experiment.coculture_partner` | `str`, **sparse** (absent unless coculture is the treatment) | **`str[]`, dense** — sorted partner names, `[]` on axenic experiments (post-import re-materialises `[]`, like `treatment_type`); treatment AND background partners in one list |
| `Tests_coculture_with` (Experiment → OrganismTaxon) | one edge, treatment partner only, no properties | one edge **per partner**; new property **`partner_role ∈ {treatment, background}`** |
| `Publication.organisms` | rolls up the scalar | rolls up the list (6 publications gain organisms) |
| paperconfig | `treatment_organism` / `treatment_taxid` | + optional `background_organisms: [{organism, taxid}]`; validator errors when `coculture` is in `background_factors` and no partner is given |

Same name kept on purpose: `treatment_type` is already a singular-named list on Experiment, and a rename
would break the same consumers for nothing. Role is **not** a node property — it is derivable:
`'coculture' IN e.treatment_type` ⇒ the partner is the treatment; otherwise background. The edge
property exists for the mixed case (a treatment partner plus a different background partner).

Release gating: this ships with a `### Breaking` CHANGELOG bullet and an `mcp_min_version` bump, so an
explorer older than the fix refuses the graph at `kg_release_info` instead of erroring mid-query.

## 3. What breaks in the explorer (measured against `main` on 2026-10-13)

`CONTAINS` on a list is a Cypher type error, so the two filter sites fail outright; the return sites keep
working but hand back a list.

| Site | Today | Needed |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py:2890` (`list_experiments` filter) | `toLower(e.coculture_partner) CONTAINS toLower($partner)` | `ANY(p IN e.coculture_partner WHERE toLower(p) CONTAINS toLower($partner))` |
| `multiomics_explorer/kg/queries.py:97` (`GENES_UPREGULATED_BY_COCULTURE`) | `e.coculture_partner CONTAINS $coculture_genus` | same `ANY(...)` form |
| `queries_lib.py` return sites ~3007, 5272, 5512, 6142 and `queries.py:101` | return the scalar | return the list (type change in the tool envelope) |
| docstrings / `docs://tools/list_experiments`, `docs://guide/conventions` | "coculture_partner containing the partner organism name" | say it is a list covering treatment **and** background cocultures, and that role comes from `treatment_type` |
| example queries in `queries.py:166/204` | scalar `CONTAINS` | `ANY(...)` |

## 4. Asks — where the explorer view should shape the KG

| ID | Ask | Pri |
|---|---|---|
| **CCP-001** | **Confirm the list-in-place shape** (one dense `str[]` under the existing name) over the alternative the KG considered — scalar kept treatment-only plus a new `coculture_partners` list. The KG prefers one field; say so if the envelope type change is worse for you than a second property. | P1 |
| **CCP-002** | **Does `list_experiments` want a role filter?** e.g. `coculture_role: treatment \| background \| any` (default `any`). Cheap on the KG side either way; the KG will not add a node property for it unless the explorer wants to filter on it without touching `treatment_type`. | P1 |
| CCP-003 | **Multi-partner display.** For Moreno the list has two MarRef organisms. Is a list in the envelope fine, or does the explorer want a precomputed `coculture_partner_label` ("Marinobacter (MarRef v6); Alteromonas (MarRef v6)") for one-line rows? KG default: no label, the list is the truth. | P2 |
| CCP-004 | **Partner identity.** Partners resolve to the three existing OrganismTaxon kinds (`insdc.gcf:` genome strains, `ncbitaxon:` treatment organisms, reference-proteome-match organisms). The list holds `preferred_name`s. Does the explorer want the node ids alongside (`coculture_partner_ids: str[]`, index-aligned) to join without a name match? | P2 |
| CCP-005 | **Docs wording for the role rule** — the explorer's `conventions` page is the right home for "`'coculture' IN treatment_type` ⇒ partner is the treatment; a partner listed on an experiment whose `treatment_type` lacks `coculture` is the culture background". Confirm, or ask the KG to publish it as a `ControlledVocabulary` description instead. | P3 |

## 5. Timeline

- KG: data fill on the 35 experiments (Barreto per-entry check first), adapter + validator + post-import,
  dev rebuild on 7687. Target: this week.
- Explorer: the two filter sites + docs, released with the `mcp_min_version` bump.
- Dialog: answer CCP-001/002 here (append a "Responses" section) before the KG freezes the adapter;
  CCP-003/004/005 can land after.

---

## Responses (explorer, 2026-10-13)

Checked against explorer `main` @ `81f2d3e` and the live KG on 7687 (the 2026-10-13T06:28Z build).
Your §1 counts reproduce exactly (76 treatment / 35 background-only without a partner / 3 background
with a partner). Two things in the live data change the answers below, so they come first.

### R0. Findings that affect the contract

**R0.1 — The 8 phage experiments break the role rule in §2.** `coculture_partner` is also the
"interacting organism" slot for phage. 8 experiments have `treatment_type = ['viral']`, no `coculture` in
either field, `coculture_partner = 'Phage'` and a `Tests_coculture_with` edge to `ncbitaxon:10239`
(`10.1038/nature06130`, `10.1111/1462-2920.14513`, `10.1371/journal.pone.0165375` ×2,
`10.1002/mbo3.1150`, `10.1038/ismej.2015.210` ×3). The explorer's
`ExperimentResult.coculture_partner` description already says "coculture partner or phage". Under the
rule "`'coculture' IN treatment_type` ⇒ treatment, otherwise background", all 8 phage experiments come
out as *background*, which is wrong. Please (a) confirm they stay in the dense list as `['Phage']`,
(b) give their edges `partner_role = 'treatment'`, and (c) drop the node-level derivation rule from the
contract, or restate it as "`treatment_type` ∩ {`coculture`, `viral`} ≠ ∅".

**R0.2 — The mixed case is real, not just possible: Moreno 2023 has 20 of them.** These are the
heterotroph-side Moreno experiments (`10.1128/spectrum.03275-22`, profiled organism
`Marinobacter (MarRef v6)`, partner = one of the 5 cyanobacteria). They have `coculture` in **both**
`treatment_type` (`['carbon','coculture']`) and `background_factors`. After your fill, each would list
`[<cyanobacterium>, 'Alteromonas (MarRef v6)']` while `treatment_type` contains `coculture`. The
node-level rule then marks both partners as treatment, but only one is. So for 20 + 8 = 28 experiments
the role can only come from the edge.
Related curation question for the paperconfig: the 20 cyanobacteria-side Moreno experiments have
`treatment_type = ['carbon']` and treat coculture as background only. The heterotroph side marks the
same culture setup as a treatment. If that asymmetry is a curation slip (the treatment is glucose ±
light on both sides), removing `coculture` from the heterotroph-side `treatment_type` gets rid of the
mixed case completely. Please check this while you do the Barreto per-entry check.

**R0.3 — §3 understates what breaks.** The return sites do **not** keep working. The explorer
validates rows against Pydantic models typed `coculture_partner: str | None`, so a list value raises a
`ValidationError` in 4 response models:
`ExperimentResult` (`list_experiments`), `ExpressionByExperiment` and `ExpressionRow`
(`differential_expression_by_gene` verbose `experiments[]` and verbose rows), and
`DifferentialExpressionByOrthologResult` (`differential_expression_by_ortholog`, a **compact** field).
So until the explorer change lands, 3 tools fail outright on the new build, not just the
`coculture_partner=` filter. The full explorer change list is: the 2 filter sites + 3 example queries
(as you listed), the 4 Pydantic models, `config/schema_baseline.yaml` (2 node entries `string → list`,
plus `partner_role` on `Tests_coculture_with`), docstrings and tool YAML, `conventions.md` /
`concepts.md`, and the regression goldens (`list_experiments_coculture_partner` will gain the
background experiments; the `list_experiments_*` / DE goldens change type).
One more small correction: a KG `mcp_min_version` above the explorer version does not make the
explorer *refuse* the graph. `kg_release_info` reports a failed `version_compat` check (verdict
`warn`), and calls still run. The bump is still the right signal; just don't count on it as a hard stop.

### CCP-001 — Confirmed: one dense list under the existing name

Agreed. The explorer has to change the 4 models whichever shape you pick, and a second
`coculture_partners` field would leave every caller asking which one to filter on. That question is
exactly what caused the Weissberg miss. Conditions:

1. Phage stays in the list (R0.1).
2. **Invariant:** `e.coculture_partner == sorted(collect(o.preferred_name))` over the experiment's
   `Tests_coculture_with` edges. It holds today (87/87 edges name-match), and the explorer will rely on
   it so the node-list filter and the edge-based role filter (CCP-002) always return the same set.
   Please add it to the post-import checks.
3. Lockstep: land it on a dev build first. The explorer will absorb it (`absorb-kg-rebuild`) and ship
   the fix as `0.1.0-alpha.6` before the official KG release. Set `mcp_min_version = 0.1.0a6`
   (PEP 440) in that release.

### CCP-002 — Yes to a role filter, taken from the edge; no node property needed

The explorer will add `coculture_role: 'treatment' | 'background' | None` (default `None` = any) to
`list_experiments`. Because of R0.1 and R0.2 it can't be derived from `treatment_type`, and a
node-level role list (index-aligned or not) can't tie a *name* to a *role* in a single predicate.
The explorer will query the edge instead:
`EXISTS { (e)-[r:Tests_coculture_with]->(o) WHERE ($role IS NULL OR r.partner_role = $role) AND toLower(o.preferred_name) CONTAINS toLower($partner) }`.
**The KG ask is therefore just:** `partner_role` is set on **every** `Tests_coculture_with` edge
(phage included), with values limited to `{treatment, background}`. Please don't add a node property.

### CCP-003 — No label

A list in the envelope is fine, and the list is the truth. The explorer will join it for display if a
row ever needs one line.

### CCP-004 — No index-aligned id list

The edge already holds the identity. For `list_experiments` verbose the explorer will build
`coculture_partners: [{name, role, organism_id}]` from the edges, which covers both the id and the role
without a name match. The only KG ask here is the invariant in CCP-001.2.

### CCP-005 — `conventions` page, plus a small vocab ask

The explorer's `conventions` page ("Organism naming") is the right home for the explanation. It will
say: the list covers treatment, background and phage partners; role is on the edge and exposed as
`coculture_role=`; `coculture_partner=` alone matches any role. Two small KG asks so the vocabulary
side stays live and consistent with the other closed vocabularies:
(a) a `ControlledVocabulary` for `partner_role` (2 values, with descriptions), which
`list_filter_values` will serve; (b) mention the partner field in the `coculture` value descriptions in
`treatment_type` and `background_factors`. P3, can follow the dev build.

### Explorer-side timeline

As soon as the dev build lands on 7687: filter sites + 4 models + `coculture_role=` + docs + goldens in
one absorb, then `0.1.0-alpha.6`. The motivating query becomes
`list_experiments(coculture_partner="Alteromonas")`, which matches treatment and background
Alteromonas, including Weissberg 2025 proteomics and Moreno's `Alteromonas (MarRef v6)`. The current
tool example `list_experiments(treatment_type=["coculture"], coculture_partner="Alteromonas")` will be
rewritten, because the `treatment_type` filter there silently drops the background cocultures.

---

## KG reply (2026-10-13)

All three R0 findings verified against the paperconfigs and the 7687 build. Decisions below; they
supersede §2's derived-role sentence and §3's "return sites keep working" / `mcp_min_version` lines.

### R0.1 phage — accepted

Verified: 8 experiments, `treatment_type = ['viral']`, partner `Phage` (`ncbitaxon:10239`), 8/8
name-match. `Phage` stays in the list; its edges get `partner_role = 'treatment'`. The node-level
derivation rule is **dropped from the contract**: role lives on the edge only (your CCP-002 shape).
Adapter rule, stated here so curators can predict it: a `treatment_organism` is `treatment` iff
`treatment_type ∩ {coculture, viral} ≠ ∅`, else `background`; every `background_organisms` entry is
`background`. The validator will warn when `treatment_organism` is set but read as background, so
the three such entries today (Biller 2016 ×2 growth-phase in NATL2A coculture, Bernstein 2017
light/oxygen in BP-1 + *M. ruber*) become explicit `background_organisms`.

### R0.2 Moreno — it is a curation slip; the mixed case goes away

Checked all three sides of one Moreno condition (`light_low_glucose_*`): cyanobacterium side,
Marinobacter side and Alteromonas side all compare **"Light + 100 nM glucose" vs "Light (no
glucose)"**. The treatment is glucose ± light on every side; the coculture is the culture state. So
the 40 heterotroph-side experiments will be corrected: `coculture` removed from `treatment_type`
(→ `['carbon']`), added to `background_factors` where missing (the 20 Alteromonas-side entries),
and `treatment_organism` moved to `background_organisms`. Each of the 60 Moreno experiments then
lists the other two members of its culture (cyanobacterium-side: Marinobacter + Alteromonas;
Marinobacter-side: cyanobacterium + Alteromonas; Alteromonas-side: cyanobacterium + Marinobacter),
all `background`. After this there is **no mixed-role experiment in the corpus**; the edge role
still covers one if it ever appears. This is a data correction with visible consequences —
`list_experiments(treatment_type=['coculture'])` loses 40 Moreno heterotroph experiments that were
never coculture-vs-axenic comparisons, and the Publication / OrganismTaxon `treatment_types`
rollups shrink accordingly — so it gets its own `### Data` CHANGELOG bullet. Pending the
curator's (Osnat's) confirmation, which is being asked for alongside this reply.

### R0.3 — accepted, with the wording corrected on the KG side

Pydantic break noted; the KG plan now says "3 tools fail on the new build until the explorer
absorbs it". `mcp_min_version` is understood as a `warn` verdict, not a hard stop; the bump stays.

### CCP-001 — confirmed, and the invariant becomes structural

The adapter emits the edges (with `partner_role`) and a best-effort list; **post-import then
overwrites** `e.coculture_partner = apoc.coll.sort(collect(o.preferred_name))` over the
experiment's `Tests_coculture_with` edges, `[]` when it has none. So the invariant holds by
construction, not by name discipline in paperconfigs, and the dense `[]` falls out of the same
statement. A KG validity test asserts list == sorted edge names on every Experiment (sibling of
the existing `Publication.organisms ↔ preferred_name` alignment test). Lockstep as you propose:
dev build on 7687 first; `mcp_min_version = 0.1.0a6` in the release.

### CCP-002 — accepted exactly

`partner_role ∈ {treatment, background}` on **every** `Tests_coculture_with` edge, phage included;
no node property.

### CCP-003 / CCP-004 — accepted (no label, no id list)

### CCP-005 — accepted

`Tests_coculture_with.partner_role` gets a `ControlledVocabulary` entry with `value_descriptions`;
the `coculture` value descriptions on `Experiment.treatment_type` and `Experiment.background_factors`
will name the partner field and the edge role. Lands with the dev build, not after.

### Open on the KG side

1. Curator confirmation of the Moreno correction (R0.2).
2. Barreto 2022's 5 background entries: per-entry check whether "coculture in background"
   describes the culture or the GLM design (interaction terms). Partners will only be filled where
   the measured sample was actually a coculture.

---

## Explorer follow-up (2026-10-13)

Read the KG reply and checked it against the 7687 build. The R0.1 counts, the 40 Moreno
heterotroph-side experiments (20 Marinobacter with `coculture` in both fields, 20 Alteromonas with
`coculture` in `treatment_type` only) and the 3 treatment-organism-read-as-background entries
(Biller 2016 ×2, Bernstein 2017) all reproduce. The structural invariant (post-import overwrite) is
better than what we asked for. Thanks.

### R0.2 — curator confirmed

Osnat confirms the Moreno correction as described: on all 40 heterotroph-side experiments,
`coculture` is the culture state, not the treatment. Go ahead, with the `### Data` CHANGELOG bullet.
The explorer absorb will regenerate the goldens that count `treatment_type=['coculture']` rows and the
`treatment_type` / `background_factors` vocab snapshot.

### Open item 2 (Barreto) — explorer view: fill the partners, don't drop them

The 5 Barreto 2022 entries (`10.1038/s43705-022-00197-2`) are 4 pooled main effects
("Elevated pCO2 vs Ambient", `background_factors = ['axenic','coculture']`) plus 1 interaction term
(`EZ55 pCO2 x Coculture Interaction Effect`, same factors). The samples behind them include real
cocultures, pooled with axenic ones. The explorer view: fill the partners as `background` (EZ55 for
the 3 cyanobacteria; CC9311 + WH8102 + MIT9312 for EZ55). Two reasons:

- `list_experiments(coculture_partner="EZ55")` should find them; discoverability is the reason for
  this whole change.
- The `['axenic','coculture']` pair already marks the design as pooled, and the explorer will say so
  in `conventions`.

If you decide instead that "coculture" there is only a GLM term, then remove `coculture` from those
entries' `background_factors` rather than leaving it with an empty partner list. The §2 validator
(error when `coculture` is in `background_factors` with no partner) should hold with no exceptions,
because an empty list next to `coculture` is the silent-drop shape we are trying to remove.

### New, P3 — Meiothermus ruber edge target

Bernstein 2017's `Tests_coculture_with` edge points at `ncbitaxon:277`, but a genome node
`insdc.gcf:GCF_000836395.1` has the same `preferred_name = 'Meiothermus ruber'`. This is the only
partner with a genome twin; all 16 other genome-strain partners already point at their `insdc.gcf:`
node. If the culture strain matches that assembly, please retarget the edge to the genome node, so
the `organism_id` the explorer exposes (CCP-004) routes into the gene tools. If the strains differ,
leave it as is; the name list is unaffected either way.

### Explorer side

Nothing else blocks us. We start the absorb when the dev build is on 7687 (filter sites, 4 Pydantic
models, `coculture_role=`, verbose `coculture_partners[]`, docs, goldens), then release
`0.1.0-alpha.6`.

---

## KG status (2026-10-13, later)

**Landed on the dev graph at 127.0.0.1:7687** (`0.0.0-dev`, chain build → import → post-process
exit 0, empty `import.report`). Everything in the KG reply is in: dense `coculture_partner` list
written post-import from the edges, `partner_role` on every `Tests_coculture_with` edge,
`background_organisms` in 8 paperconfigs (78 experiment blocks), the Moreno correction
(curator-confirmed), Barreto filled as background per your view, and the P3 Bernstein retarget —
the edge now points at `insdc.gcf:GCF_000836395.1` and the duplicate-named `ncbitaxon:277` node is
retired (`OrganismTaxon` 48 → 47; `organism_type = treatment` 5 → 4). CHANGELOG carries a
`### Breaking` bullet for both. Ready for the absorb; the KG release will set
`mcp_min_version = 0.1.0a6` once alpha.6 is out. KG-side write-up:
`multiomics_biocypher_kg/docs/kg-changes/coculture-partner-list.md`.

---

## Explorer verification of the dev build (2026-10-13)

Checked directly on 7687 (`Schema_info.built_at = 2026-10-13T13:51:35Z`, CV hash `sha256:6f01dce4…`).
Everything claimed in "KG status" is there:

| Check | Result |
|---|---|
| `coculture_partner` type | `LIST<STRING>` on all 209 experiments; `[]` on the 87 with no edges |
| Invariant: list == sorted edge `preferred_name`s | 209 / 209 |
| `partner_role` on every edge | 186 / 186 (44 `treatment`, 142 `background`), no nulls |
| Role agrees with the adapter rule (`treatment_type` ∩ {coculture, viral}) | 44 / 44 treatment, 142 / 142 background |
| Mixed-role experiments | 0 |
| Partition (axenic / bg / treatment / phage) | 87 / 78 / 36 / 8 = 209. Treatment 76 → 36 (−40 Moreno), bg 35 + 3 + 40 = 78 |
| `coculture` in `background_factors` with an empty list | 0, so the validator rule holds with no exceptions |
| Moreno | all 60 sides list the other 2 culture members, all `background`; heterotroph `treatment_type = ['carbon']` |
| Barreto | 4 pooled main effects + interaction carry partners (`EZ55`; or `CC9311 + MIT9312 + WH8102` for EZ55) |
| Weissberg 2025 | HOT1A3 / MED4 nitrogen RNA-seq + proteomics, cocultured side, now list the partner: the original miss is fixed |
| Bernstein | edge → `insdc.gcf:GCF_000836395.1` (`background`); `ncbitaxon:277` gone; `OrganismTaxon` = 47 |
| `Tests_coculture_with.partner_role` CV | present, closed, 2 values with descriptions |

### One wording fix, P3: the `background` description doesn't fit Barreto

The CV says *background = "this partner shared the culture in **every arm**"*. That isn't true for
the 5 Barreto entries you filled as `background` on our advice: their
`background_factors = ['axenic','coculture']` because the comparison pools axenic and coculture
samples, so the partner is in some arms, not all. Suggested wording for both the value description and
the CV `description`: *"background: the partner was in the culture, but its presence is not the
variable under test (in every arm, or, when `background_factors` also lists `axenic`, in a design
that pools axenic and coculture samples)."* The explorer `conventions` page will say the same.
Separately, a question: the CV is `closed: true` with 2 values but `exhaustive: false`. If
`exhaustive` means "every value is listed", it should be `true`.

### Explorer-side consequences noted for the absorb (no KG action)

- Retiring `ncbitaxon:277` makes the explorer's "two OrganismTaxon nodes share `Meiothermus ruber`"
  caveat obsolete. It appears in 4 tool YAMLs (`list_organisms`, `resolve_gene`,
  `differential_expression_by_gene`, `run_cypher`), the `kg_claims` lint (48 → 47) and `CLAUDE.md`.
  Those go in the absorb.
- The explorer MCP server was still serving the cached 06:28Z identity from `kg_release_info`, so
  it needs a restart before the absorb (our side, not yours).

Ready to absorb. Nothing else is needed from the KG apart from the P3 wording fix.
