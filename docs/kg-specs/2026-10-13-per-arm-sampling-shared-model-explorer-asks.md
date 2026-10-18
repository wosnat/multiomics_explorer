# Explorer-side asks: per-arm sampling time + shared-model identifier on contrasts (2026-10-13)

**Date:** 2026-10-13 · **From:** KG (`multiomics_biocypher_kg`) · **To:** explorer (`multiomics_explorer`)
**Context:** the `2026-10-06-pro_n_import_coculture` analysis found (E7) that Weissberg 2025's four MED4
RNA contrasts are one fitted DESeq2 model — [coculture d18 − axenic d14] equals [direct d18 − direct d11]
for all 1,849 genes to 1e-15 — and that the "day 18" coculture-vs-axenic contrast pairs a day-18 coculture
with a day-14 axenic culture that was in full decline, while the KG shows one label, "day 18". Nothing in
the graph lets a consumer see either fact. The KG proposes an **additive** contract change; this doc
asks the explorer to confirm the shape before the adapter is written. KG scope:
`multiomics_biocypher_kg/plans/per_arm_sampling_and_shared_model.md`.
Direction note: KG → explorer, like `2026-10-13-coculture-partner-list-explorer-asks.md`.

> **Status 2026-10-15:** the contract in §2 and the KG reply below is **superseded** by
> [§ KG revision (2026-10-15) — simplified contract](#kg-revision-2026-10-15--simplified-contract)
> at the end of this file. Explorer review requested there; explorer responded 2026-10-15
> (SIM-001 accepted, contract gaps T1–T5).

## 1. What the KG measured (2026-10-13, every wired paperconfig)

- 335 `statistical_analyses`; **all** carry `timepoint`, `timepoint_hours`, `growth_phase` — one value
  each, describing the **treatment arm** by an unstated convention. Live `growth_phase` values:
  exponential 52, acclimated_steady_state 49, infected 47, acute_stress 46, nutrient_limited 45,
  darkness 38, stationary 32, diel 18, recovery 6, death 2.
- **Baseline-control designs** (control sampled at a different time than the treatment):
  Weissberg 2025 — 8 experiments / 32 analyses ("vs exponential day 7 / day 11"); Kaur 2018 — 4
  ("Timepoint 1 (day 1) baseline"); Bagby & Chisholm 2015 — 1 ("Time 0 pre-shock"). Every other
  time course compares arms sampled at the same time, where `timepoint` already describes both.
- **Shared fitted models**: Weissberg 2025 (one DESeq2 model per organism × omics layer; the MED4 RNA
  model alone yields 4 experiments / 11 contrasts); Barreto 2022 (**11 edgeR experiments from one GLM**,
  stated in `experimental_context`: `~0+cyano+treatment+cyano:treatment`); Hennon 2017 (3 edgeR
  experiments, probably one GLM — curator check). Other multi-experiment papers are probably separate
  fits; curator call per paper.
- Explorer today: 192 references to `time_point*` / `growth_phase*` in `kg/queries_lib.py`, all reading
  existing names. Nothing below renames or retypes anything.

## 2. Proposed contract (ADDITIVE — no breaking change)

### 2a. Per-arm sampling — on `Changes_expression_of` edges (sparse)

| New edge property | Type | Meaning | Absent means |
|---|---|---|---|
| `control_time_point` | str | control arm's sampling-time label ("day 14") | control sampled at the same time as the treatment |
| `control_time_point_hours` | float | parsed like `time_point_hours` | same |
| `control_growth_phase` | str (same open vocab as `growth_phase`) | control arm's state | same as implied by the experiment's `control_condition` |

Existing `time_point` / `time_point_hours` / `growth_phase` keep names, types and values; their docs
will say **treatment arm**. Never `""` — sparse.

### 2b. Experiment-level rollups (post-import)

| New Experiment property | Type | Meaning |
|---|---|---|
| `control_timing` | str, **dense, closed** `{time_matched, baseline, mixed}` | `time_matched` = no analysis carries a `control_time_point`; `baseline` = every curated analysis has `control_time_point_hours ≠ time_point_hours`; `mixed` otherwise |
| `control_growth_phases` | str[], dense, `[]` when none | parallel to the existing `growth_phases` (treatment arm) |
| `statistical_model_id` | str, **sparse**, `"{doi}:{model key}"` | the fitted model this experiment's contrasts come from; declared per experiment in the paperconfig |
| `linked_experiment_ids` | str[], dense, `[]` when none | the other experiments sharing the model (symmetric, never self-including) |
| `linked_experiment_count` | int, dense | `size(linked_experiment_ids)` |

`ControlledVocabulary` entries: `Experiment.control_timing` (closed, 3 values, descriptions);
`Changes_expression_of.control_growth_phase` registered as open like `growth_phase`.

### 2c. Data that will carry the new fields (curated only — absent elsewhere)

Weissberg 2025 (all 32 analyses + 4 model ids over 10 experiments), Barreto 2022 (one model id over
11), Hennon 2017 (one id over 3, if confirmed), Kaur 2018 and Bagby & Chisholm 2015 (control days).
Every other paper: `control_timing = 'time_matched'`, `linked_experiment_ids = []`, no edge props.

## 3. What the explorer could do with it (nothing required)

- `list_experiments` envelope: `control_timing`, `linked_experiment_count` — the two one-field reads
  that would have flagged both E7 findings at Plan time.
- `differential_expression_by_gene` verbose rows: `control_time_point`, `control_growth_phase` next to
  the existing `time_point` / `growth_phase`.
- `docs://guide/conventions`: "`time_point` and `growth_phase` describe the treatment arm; a
  `control_*` value means the control was sampled at another time; `linked_experiment_ids` means the
  contrasts are algebraically dependent, not replications."

## 4. Asks

| ID | Ask | Pri |
|---|---|---|
| **ARM-001** | **Confirm the per-arm shape**: three sparse `control_*` edge properties next to the existing treatment-arm triple, rather than (a) renaming the existing triple to `treatment_*` (breaking, 192 explorer references) or (b) a Sample/Arm node (a join for two facts most experiments do not have). | P1 |
| **ARM-002** | **Confirm `control_timing` as a dense three-state node property** (`time_matched` / `baseline` / `mixed`) — is `mixed` useful to you, or would you rather have `baseline` whenever any analysis is curated and read the edges for detail? | P1 |
| **ARM-003** | **Model id on the Experiment, not the analysis** (`statistical_model_id` + `linked_experiment_ids`). Every known case (Weissberg, Barreto) is one model → several whole experiments. Say so if you have a case where a model spans part of an experiment. | P1 |
| ARM-004 | **Envelope placement**: do you want `control_timing` and `linked_experiment_count` in the compact `list_experiments` row (two scalars) or verbose-only? KG has no preference; it affects only your goldens. | P2 |
| ARM-005 | **`growth_phases` rollup**: keep it treatment-arm-only (proposed, no meaning change) and add `control_growth_phases` beside it, or fold both arms into `growth_phases` (meaning change, `### Breaking`)? KG recommends the former. | P2 |
| ARM-006 | **Naming**: `linked_experiment_ids` vs `same_model_experiment_ids`. KG leans `linked_` for brevity; the vocab description will say "same fitted statistical model". | P3 |

## 5. Timeline

- KG: adapter + validator + post-import + vocab after ARM-001..003 are answered; Weissberg values
  are being confirmed with the curator in parallel; dev rebuild on 7687.
- Explorer: nothing blocks; absorb when the dev build lands if you want the envelope fields.
- Dialog: append a "Responses" section here, as before.

## Responses (explorer, 2026-10-14)

Checked against explorer `main` @ `de44d71` and the live KG on 7687 (the 2026-10-13T13:51Z build).
Short version: ARM-001/002/003 are all yes, with conditions. Four things in the live data change the
details, so they come first.

### R0. Findings that affect the contract

**R0.1 — The motivating E7 contrast is not in your §1 / §2c list of baseline designs.** The
"coculture d18 vs axenic d14" contrast lives in
`10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq` (control `"Axenic"`, timepoints
`day 11` / `day 18`). The 8 Weissberg baseline experiments in §1 ("vs exponential day 7 / day 11") look
like the 8 `growth_state_*` ones. Please confirm the two `coculture_*` Weissberg experiments are
curated too. If axenic was sampled on day 11 for the day-11 contrast, the MED4 one comes out
**`mixed`** (d11 matched, d18 vs d14), which is the case that started all this. If it is left
uncurated it gets `time_matched`, and the field would state the opposite of E7.

**R0.2 — The counts don't reproduce from the graph.** Live KG, Weissberg 2025: 10 experiments, 35
timepoints. The 8 `growth_state_*` experiments hold 30 timepoints, not 32. MED4 RNA is **3**
experiments / **9** timepoints (axenic 2, coculture 5, `coculture_alteromonas_*` 2), not 4 / 11. Bagby
2015 has 4 experiments in the KG, not 1. These may be paperconfig analyses that collapse or drop at
import, which is fine. But the validator and the post-import check should count **what lands in the
graph**, and the doc should say which count it is quoting.

**R0.3 — Barreto and Hennon each span several organisms; one model can't.** Barreto 2022's 11
experiments are EZ55 × 8, MIT9312 × 1, CC9311 × 1, WH8102 × 1. Hennon 2017's 3 are EZ55 × 2 +
MIT9312 × 1. One edgeR GLM is fitted on one count matrix, which means one organism's genes. So
`~0+cyano+treatment+cyano:treatment` most likely covers the **8 EZ55 experiments only**, and the 3
cyanobacteria-side experiments are separate fits (or not linked at all). Hennon would share at most 2.
**Ask:** add a post-import invariant that all experiments sharing a `statistical_model_id` have the
same `organism_name` and `omics_type`. This would catch a curation slip like "one id over 11" before
it ships.

**R0.4 — `time_point_hours` already uses a `-1` sentinel, and §2b's rule compares hours.**
`days 60+89` has `time_point_hours = -1` on the Experiment array (and no `time_point_hours` on 60k
edges). The `baseline` rule "`control_time_point_hours ≠ time_point_hours`" puts any pooled or
unparseable label in the wrong bucket. Please (a) compare **labels** when either side's hours is
missing / `-1`; (b) make the validator **reject** a `control_time_point` equal to the treatment
`time_point`. "Present ⇔ differs" then holds by construction, and the three-state rollup becomes a
count: `time_matched` = 0 timepoints carry it, `baseline` = all of them do, `mixed` = some do.

### ARM-001 — Confirmed: three sparse `control_*` edge properties. Please also add Experiment arrays.

Agreed on the shape. A rename would be breaking for no gain, and an Arm node would be a join for two
facts. **One addition the explorer needs:** `list_experiments` builds its per-timepoint `timepoints[]`
sub-rows (label / hours / growth_phase) from the **Experiment parallel arrays** (`time_point_labels`,
`time_point_hours`, `time_point_growth_phases`). It does not scan edges, because that would mean 327k
edges. To show the control arm per timepoint there, the explorer needs the same data rolled up onto
the Experiment, aligned with the existing arrays:

| New Experiment property | Type | Sentinel when time-matched |
|---|---|---|
| `time_point_control_labels` | str[] | `''` |
| `time_point_control_hours` | float[] | `-1` |
| `time_point_control_growth_phases` | str[] | `''` |

These are dense arrays of length `time_point_count`. Neo4j arrays can't hold null, so the explorer
coerces the sentinels to null, as it already does for `time_point_hours`. The edge properties stay the
source of truth for row-level DE. **Invariant:** the array value at `time_point_order − 1` equals the
edge value for every edge at that order. Please add it as a post-import check.

### ARM-002 — Keep `mixed`

Yes to the dense, closed, three-state field, and keep `mixed`. A collapsed `baseline` would say "the
control is a different timepoint" for every row of an experiment where some rows are time-matched. A
consumer reading one field would then mistrust correct contrasts. R0.1 (Weissberg coculture) and
probably Kaur (if `Timepoint 1` is itself one of the 14 reported timepoints) are real `mixed` cases.
The explorer will add `control_timing` as a `list_experiments` filter and as a `by_control_timing`
summary breakdown. Please register it in `ControlledVocabulary` with descriptions as proposed, so
`list_filter_values('control_timing')` works without new code.

### ARM-003 — Model id on the Experiment: confirmed

The explorer has no case where a model covers only part of an experiment. With the R0.3 invariant,
Experiment-level is correct. `linked_experiment_ids` symmetric, without self, `[]` when none: fine.
Please also guarantee `statistical_model_id` is present **iff** `linked_experiment_count > 0`. A model
id on a single experiment carries no information, and having it would leave two ways to ask "is this
linked?".

### ARM-004 — Compact, in both places

- `list_experiments`: `control_timing` and `linked_experiment_count` go in the **compact** row (two
  scalars). They are the fields that would have flagged E7, and verbose-only fields don't get read at
  Plan time. `linked_experiment_ids` and `statistical_model_id` are verbose. The per-timepoint
  `control_*` (from the ARM-001 arrays) go into the existing `timepoints[]` sub-rows.
- `differential_expression_by_gene`: `control_time_point` / `control_growth_phase` go in the
  **compact** rows, not verbose as §3 proposes. DE rows are `SparseRow`s, so the fields appear only
  on the curated rows and cost nothing elsewhere. Hiding them in verbose brings back the exact
  "day 18" misread. They also go into the per-experiment `timepoints[]` in the envelope.
- `differential_expression_by_ortholog`: the same two fields on its group × experiment × timepoint
  rows (sparse).

### ARM-005 — Keep `growth_phases` treatment-arm-only, add `control_growth_phases`

Agreed with the KG recommendation. Folding the two arms together would change the meaning of the
`growth_phases` filter on 4 tools (`list_experiments`, `list_publications`,
`list_clustering_analyses`, the DE tools via the edge `growth_phase`). A query for `death` would then
match experiments where only the control was dying. The explorer will **not** add a
`control_growth_phases` filter for now; it will appear as a field and in docs only.

### ARM-006 — `linked_experiment_ids` is fine

The name works if the vocab description says "same fitted statistical model". One wording correction
for §3's proposed conventions text: "algebraically dependent, not replications" overstates the
general case. Contrasts from one fitted model share samples and dispersion estimates, so they are
**not independent evidence**. Only some are exact linear combinations of each other, as with E7's
identity. The explorer's `conventions.md` will say: "experiments sharing `statistical_model_id` come
from one fitted model; their contrasts share samples and dispersion and must not be counted as
independent replications; some may be exact linear combinations of others."

### Explorer plan

Nothing here is breaking, so there is no `mcp_min_version` bump. When the dev build lands on 7687,
`absorb-kg-rebuild` handles the schema baseline (`config/schema_baseline.yaml`: 3 edge properties,
5 Experiment properties + 3 arrays), goldens and vocab snapshot. The surface changes above then ship
as one explorer commit: `ExperimentResult`, `TimePoint`, `ExpressionRow`, `ExpressionTimepoint`,
ortholog rows, the `control_timing` filter and breakdown, the `conventions.md` paragraph, and tool
YAML. Until that commit lands, the new properties are visible only through `run_cypher`, and nothing
breaks.

---

## KG reply (2026-10-14)

All four R0 findings verified against the paperconfigs; every ask is accepted. Corrections to §1 /
§2 are below and are folded into `plans/per_arm_sampling_and_shared_model.md`.

### R0.1 — accepted: the two Weissberg `coculture_*` experiments are curated, and MED4's is `mixed`

They were missing from §1 because the scan keyed on `control_condition` text ("Axenic" has no time
token). Curation: `coculture_alteromonas_hot1a3_med4_rnaseq` — day 11 vs axenic day 11
(time-matched), day 18 vs axenic **day 14** (`death`) ⇒ `control_timing = mixed`, the E7 case.
`coculture_prochlorococcus_med4_hot1a3_rnaseq` (day 11 / 18 / 31 vs axenic HOT1A3): control days
being confirmed with the curator; expected `mixed` as well. Kaur 2018 is **not** mixed — day 1 is
not among its 7 reported timepoints, so all four experiments are pure `baseline`. Bagby & Chisholm
2015: 1 of its 4 experiments is baseline ("max across 3–24 h" vs time-0 pre-shock); the other 3
compare against air at the same time and stay `time_matched`.

### R0.2 — accepted: counts are graph counts from now on

§1 quoted paperconfig analyses matched by a label regex (and the "4 / 11" was wrong even there).
Graph counts: Weissberg 2025 = 10 experiments / 35 timepoints; the 8 `growth_state_*` = 30; MED4 RNA
model = **3 experiments / 9 timepoints** (axenic 2, coculture 5, direct 2). The validator counts
analyses; the post-import invariants count edges / timepoints; the plan says which.

### R0.3 — accepted, with the invariant

One count matrix ⇒ one organism ⇒ one model. Barreto 2022: one id over the **8 EZ55** experiments
(6 coculture contrasts + pCO₂ main effect + interaction all come from `~0+cyano+treatment+cyano:treatment`);
the 3 cyanobacteria-side experiments are separate fits and get no id. Hennon 2017: at most the 2 EZ55
experiments (axenic + coculture pCO₂), curator check. Post-import invariant added: every experiment
sharing a `statistical_model_id` has the same `organism_name` and `omics_type`; it is a KG validity
test, and the validator enforces the same within a paperconfig.

### R0.4 — accepted: labels decide, hours are advisory; the validator rejects equality

`control_time_point` is **required** whenever `control_time_point_hours` or `control_growth_phase`
is set, and must differ from the treatment `time_point` (validator error). "Present ⇔ differs" then
holds by construction; `control_timing` is a count over the experiment's timepoints: 0 carry it →
`time_matched`, all → `baseline`, some → `mixed`. No hours comparison anywhere, so `-1` / pooled
labels (`days 60+89`) cannot misroute.

### ARM-001 — accepted, including the three Experiment arrays

`time_point_control_labels` (str[], `''`), `time_point_control_hours` (float[], `-1`),
`time_point_control_growth_phases` (str[], `''`), dense, length `time_point_count`, built in the same
per-(experiment, `time_point_order`) aggregation that fills `time_point_labels` / `_hours` /
`_growth_phases` today, so alignment is by construction. Invariant (KG validity test): for every edge,
the array value at `time_point_order − 1` equals the edge value (sentinel ↔ absent).

### ARM-002 — `mixed` kept; `Experiment.control_timing` registered with value descriptions

### ARM-003 — accepted: `statistical_model_id` present iff `linked_experiment_count > 0`

Guaranteed twice: the validator rejects a model id shared by fewer than 2 experiments of the paper,
and post-import clears any id that would end up alone after import (and the KG validity test asserts
the iff).

### ARM-004 / 005 / 006 — accepted as you state them

Compact placement is yours. `growth_phases` stays treatment-arm; `control_growth_phases` is added as a
field, no filter. `linked_experiment_ids` keeps its name; the vocab description reads: "experiments
sharing `statistical_model_id` come from one fitted model; their contrasts share samples and
dispersion and must not be counted as independent replications; some may be exact linear
combinations of others." Your §3 wording correction is adopted verbatim.

### Open on the KG side

1. Curator values for Weissberg's HOT1A3-side control days and the proteomics model split.
2. Hennon 2017: one EZ55 GLM or two fits.
Implementation starts once (1) is in; the dev build will land on 7687 and this file gets a status
note, as before.

---

## KG revision (2026-10-15) — simplified contract

**Supersedes** §2 and the 2026-10-14 KG reply. The accepted contract had grown to 11 new properties
(3 edge, 8 Experiment), 4 paperconfig fields and 3 post-import mechanisms to record two facts about
roughly 15 experiments. The KG is withdrawing most of it. The two facts move into **one curated
categorical, one model id, and one free-text note**, all on the Experiment, all emitted as curated,
with nothing computed post-import. The graph's primary readers are LLM agents, and they read a
sentence about a dozen experiments better than they read three sentinel-padded arrays.
Everything is still **additive**: no renames or retypes, and no `mcp_min_version` bump.

### S1. Contract

Three **experiment-level** paperconfig fields, emitted unchanged onto the `Experiment` node:

| Experiment property | Type | Meaning |
|---|---|---|
| `control_timing` | str, **dense, closed** `{time_matched, baseline, mixed}` | `time_matched`: every control arm was sampled at the same time as its treatment arm. `baseline`: every timepoint is compared with a control sampled at another time (e.g. "vs exponential day 7"). `mixed`: some timepoints are time-matched and some are not. Curated directly; the adapter writes `time_matched` when the field is absent. Registered as a `ControlledVocabulary` with value descriptions. |
| `statistical_model_id` | str, **sparse**, `"{doi}:{model key}"` | Present only on experiments whose contrasts come from one fitted model shared with ≥1 other experiment. Vocab description (your ARM-006 wording): "experiments sharing `statistical_model_id` come from one fitted model; their contrasts share samples and dispersion and must not be counted as independent replications; some may be exact linear combinations of others." |
| `design_notes` | str, **sparse**, free text | Plain sentences saying what the structured fields can't: which timepoint's control was sampled when and in what state, and how the experiment relates to the others in its model. Added to `experimentFullText`. |

Validator (`scripts/validate_paperconfig.py`), the only enforcement:
1. `control_timing` ∈ the three values.
2. `control_timing ∈ {baseline, mixed}` ⇒ `design_notes` is required (otherwise nobody can tell what
   differs).
3. A `statistical_model_id` value is shared by ≥ 2 experiments of the paper, all with the same
   `organism` and `omics_type` (R0.3).
4. `design_notes` contains no `|` or `'` (house string rule).

The R0.3 invariant (same `organism_name` + `omics_type` within a model id) also becomes a KG validity
test.

Example (Weissberg 2025, the E7 experiment):

```yaml
coculture_alteromonas_hot1a3_med4_rnaseq:
  control_timing: mixed
  statistical_model_id: med4_rnaseq_deseq2
  design_notes: >-
    Day 11: coculture vs axenic, both sampled on day 11. Day 18: coculture sampled on day 18 vs
    axenic sampled on day 14, when the axenic culture was already in death phase - not a
    time-matched comparison. Fitted in one DESeq2 model with the axenic and direct MED4 RNA
    experiments; the day-18 contrast equals [direct d18 - direct d11] exactly.
```

### S2. Withdrawn

| Was | Status | What replaces it |
|---|---|---|
| `Changes_expression_of.control_time_point` / `_hours` / `control_growth_phase` | withdrawn | `design_notes` |
| `time_point_control_labels` / `_hours` / `_growth_phases` (ARM-001 arrays) | withdrawn | `design_notes` |
| `control_timing` as a post-import rollup over edges | now **curated** directly | the same property, same values |
| `control_growth_phases` (ARM-005) | withdrawn | `design_notes` |
| `linked_experiment_ids`, `linked_experiment_count` (ARM-003/006) | withdrawn | match on equal `statistical_model_id` (below) |
| post-import clearing of singleton model ids | withdrawn | validator check 3 makes a singleton impossible |
| GLM / `interaction` / `design ~` heuristic warning | withdrawn | none |
| `growth_phase` / `time_point` "treatment arm" semantics | **kept** as documentation | (unchanged) |

Linked experiments, when needed:

```cypher
MATCH (e:Experiment {id: $id}) WHERE e.statistical_model_id IS NOT NULL
MATCH (o:Experiment {statistical_model_id: e.statistical_model_id}) WHERE o <> e
RETURN o.id
```

There are ~170 Experiment nodes, so no index is needed. The KG will add
`experiment_statistical_model_id_idx` anyway if you want it.

### S3. What you lose, honestly

- **Per-timepoint structure.** In a `mixed` experiment, no field says *which* timepoint has the
  offset control; only the note does. `list_experiments`' `timepoints[]` sub-rows can't show a
  control column.
- **DE rows carry no control information** (your ARM-004 point: "day 18" in a DE row is the original
  misread). Suggested mitigation, explorer-side: copy the experiment's `control_timing` onto DE rows
  as a sparse field when it isn't `time_matched` (one scalar per experiment, cheap on `SparseRow`s),
  so a consumer reading `day 18` also sees `mixed` and knows to read `design_notes`.
- **No filter on the control arm's growth phase.** (You had already declined one under ARM-005.)

If any of these starts causing wrong answers, the structured per-timepoint fields can come back
later as an additive change; this contract doesn't block them.

### S4. Data (curated only)

| Paper | `control_timing` | `statistical_model_id` |
|---|---|---|
| Weissberg 2025 | 8 `growth_state_*` → `baseline`; `coculture_alteromonas_hot1a3_med4_rnaseq` → `mixed`; `coculture_prochlorococcus_med4_hot1a3_rnaseq` → pending curator (expected `mixed`) | one per organism × omics layer (MED4 RNA = 3 experiments; HOT1A3 RNA = 3; proteomics pending curator) |
| Barreto 2022 | — | one id over the 8 EZ55 experiments |
| Hennon 2017 | — | the 2 EZ55 experiments, if the curator confirms one GLM |
| Kaur 2018 | 4 → `baseline` (vs day 1, which is not reported) | — |
| Bagby & Chisholm 2015 | `carbon_air_0036_co2_21_med4_microarray` → `baseline`; other 3 stay `time_matched` | — |
| every other paper | `time_matched` (default) | absent |

Counts are graph counts (R0.2).

### S5. Asks

| ID | Ask | Pri |
|---|---|---|
| **SIM-001** | **Accept the simplified shape** (S1) and the withdrawals (S2), in particular the ARM-001 arrays and the three DE edge properties you planned to surface in compact rows. If one of them is load-bearing for a tool you have already designed, say which, and the KG will weigh restoring that one field rather than the whole set. | P1 |
| SIM-002 | **Linked experiments**: is the equal-`statistical_model_id` match (S2) acceptable for `list_experiments`, or do you need a materialized `linked_experiment_count` for the compact row? KG prefers not to store it (R3: it's derivable from a property already on the node). | P2 |
| SIM-003 | **`design_notes` placement**: compact in `list_experiments` only when `control_timing ≠ time_matched` or a model id is present (sparse, so it costs nothing elsewhere), or verbose-only? KG suggests sparse-compact, for the same reason as ARM-004. | P2 |
| SIM-004 | **Naming**: `design_notes` (general; future design caveats go there too) vs. a narrower `control_timing_note`. KG prefers `design_notes`. | P3 |

### S6. Timeline

KG: paperconfig fields + adapter + validator + vocab + `experimentFullText` after SIM-001 is
answered; Weissberg curator values in parallel; dev rebuild on 7687, then a status note here.
Explorer: append responses below, as before.

## Responses (explorer, 2026-10-15)

Checked against explorer `main` @ `5b24b26` and the live KG on 7687. Short version: SIM-001 is
accepted. Two contract gaps (T1, T2) should be fixed before the adapter is written.

### T0. Findings on the revised contract

**T1 — A default of `time_matched` turns "nobody checked" into a stated fact.** This is R0.1 again.
The §1 scan missed the Weissberg `coculture_*` experiments because `"Axenic"` has no time token.
Under S1, any baseline design that curation misses is written as `time_matched`. That claims the
control was sampled at the same time, which is the opposite of the truth. Preferred fix: make
`control_timing` **required** in paperconfigs, with a paper-level default that each experiment can
override. Every value is then a curated claim. Fallback: keep the default, but have the
`time_matched` vocab description say "not flagged by curation" instead of "every control arm was
sampled at the same time".

**T2 — Validator check 3 only covers the paperconfig, not the graph.** R0.2 showed that analyses
can collapse or drop at import. A model id can therefore end up on a single experiment in the
graph, and the post-import clearing step that guarded against this is withdrawn. Please add a KG
validity test (a test, not a mechanism): every `statistical_model_id` in the graph is shared by at
least 2 experiments, with the same `organism_name` and `omics_type`.

**T3 — The `statistical_model_id` format doesn't match its example.** S1 gives the format as
`"{doi}:{model key}"`, but the S1 YAML uses the bare `med4_rnaseq_deseq2`. Please say whether the
adapter adds the DOI prefix. Ids are only unique across papers if it does.

**T4 — `design_notes` is now the only per-timepoint information, so it needs writing rules.**
(a) Refer to timepoints by their exact `time_point` labels ("day 18"), so an agent can match a DE
row's label to the note. (b) Refer to linked experiments by experiment id, not by curator shorthand.
The example's "[direct d18 − direct d11]" can't be resolved from the graph; it appears to mean
`..._growth_state_pro99lown_nutrient_starvation_med4_rnaseq_coculture`. A validator warning for
(a) would be enough.

**T5 — Small items.** Add a validator check that `control_timing = mixed` ⇒ the experiment has at
least 2 timepoints. S2's "~170 Experiment nodes" is **209** in the live graph. This doesn't change
the index decision, but the doc should use graph counts per R0.2.

### SIM-001 — Accepted

None of the withdrawn fields is load-bearing for a tool we have built. The explorer plan in the
2026-10-14 responses is **superseded** by the following:

- `list_experiments`: `control_timing` in the compact row (dense), `statistical_model_id` and
  `design_notes` compact but sparse, a `control_timing` filter, and a `by_control_timing` summary
  breakdown.
- `differential_expression_by_gene` / `differential_expression_by_ortholog`: `control_timing` on
  rows as a sparse field when it isn't `time_matched`, as S3 suggests. `design_notes` goes in the
  per-experiment envelope block (`ExpressionByExperiment`), not on every row. In a `mixed`
  experiment the time-matched rows are flagged too. With about 3 such experiments, that's
  acceptable.
- `conventions.md`: the treatment-arm reading of `time_point` / `growth_phase`, and the ARM-006
  model wording.

### SIM-002 — No stored count needed

Validator check 3 (plus the T2 test) guarantees an id is never alone, so `statistical_model_id`
being present already means the experiment is linked. The explorer will show the id and compute
`linked_experiment_ids` in verbose with a `COUNT {}` / `collect` subquery, which is cheap at 209
nodes. No index needed.

### SIM-003 — Sparse-compact is fine

`experimental_context` is verbose-only today, but `design_notes` will be on about 15 experiments
and is exactly what has to be read at Plan time.

### SIM-004 — `design_notes` is fine

If other caveats go there later, a note on an experiment no longer means its control timing is
unusual. Agents will be told to read `control_timing` for that, not the presence of a note.

### Explorer plan

Still additive, with no `mcp_min_version` bump. When the dev build lands, `absorb-kg-rebuild`
handles the schema baseline (3 Experiment properties), goldens, and vocab snapshot. Adding
`design_notes` to `experimentFullText` will shift Lucene scores, so expect some `list_experiments`
`search_text` goldens to move. The surface changes above then ship as one explorer commit.

---

## KG reply (2026-10-15)

All of T1–T5 adopted; SIM-001..004 answers accepted as you state them. KG plan updated:
`multiomics_biocypher_kg/plans/per_arm_sampling_and_shared_model.md`.

### T1 — adopted: `control_timing` is required, no adapter default

`publication.control_timing` is a paper-level default and each experiment can override it. The
validator **errors** when an experiment with ≥ 1 `statistical_analyses` entry resolves no value. The
adapter never fills one in, so every value in the graph is a curator's claim. The field is
**absent** on experiments with no DE contrast (metabolomics / derived-metric-only), the same as
`table_scope`. So it is dense over DE experiments, not over all 209. The KG validity test asserts
it is present on every Experiment with `Changes_expression_of` edges. To make "required" mean
something, the KG adds a **curation pass** over all 49 papers / 174 DE experiments. For each paper,
a curator reads the methods (sampling schedule and model design) and records the value with a
one-line evidence quote in `plans/control_timing_curation.md`. The validator rule lands in the same
commit as the curation.

`Experiment.control_timing` will be registered in `config/controlled_vocabularies.yaml` (closed,
sparse, value descriptions; text drafted in the KG plan), so `list_filter_values('control_timing')`
will work once the build lands. `time_matched` reads "every contrast compares treatment and control arms sampled at the same
time". That is a stated fact now, not "not flagged".

### T2 — adopted

KG validity test: every `statistical_model_id` in the graph is on ≥ 2 Experiment nodes with the
same `organism_name` + `omics_type`.

### T3 — the adapter adds the DOI prefix

The paperconfig holds the bare key (`med4_rnaseq_deseq2`) and the graph holds `"{doi}:{key}"`. S1's
table describes the graph and its YAML describes the paperconfig; both are correct.

### T4 — adopted as writing rules in the `/paperconfig` skill

Exact `timepoint` labels; other experiments by paperconfig key verbatim (the graph id is
`{doi}_{key}`); control sampling time + growth phase in the `growth_phase` vocabulary; for a shared
model, what the model is and any exact linear relation; no `|` / `'`. No validator warning for
label matching: free-text matching would be noisy, and the curation log is the review surface. The
S1 example's "[direct d18 − direct d11]" is replaced by the experiment keys.

### T5 — adopted

Validator: `mixed` ⇒ the experiment's analyses span ≥ 2 distinct `timepoint` labels. KG validity:
`mixed` ⇒ `time_point_count ≥ 2`. Counts in this file are graph counts: 209 Experiment nodes.

### Next

Curation pass → validator + adapter + `experimentFullText` in one change → dev rebuild on 7687 →
status note here. Open with the curator: Weissberg's HOT1A3-side control days and proteomics model
split; Hennon 2017 one GLM or two.

## KG update — 2026-10-18: contract changes after the curator review

Implemented and pushed to KG `main` (merge 6a948295; rebuild pending). Two changes to the contract
accepted above:

1. **`statistical_model_id` is dropped** — not in the graph, the paperconfig or the validator.
   Most papers do not report how DE was fitted, so the id was mostly a guess. SIM-002 (no stored
   list/count) and T2/T3 are moot; drop any explorer code or goldens that read it. `design_notes`
   no longer describes fitted models either.
2. **`time_matched` is renamed `matched`.** `Experiment.control_timing ∈ {matched, baseline,
   mixed}`. `matched` = the control was sampled at the same time **or** in the same growth state
   (parallel acclimated cultures, successive chemostat steady states, a control run repeated to
   match growth dynamics); `design_notes` says which when it is not the same time. The
   `ControlledVocabulary` value descriptions carry this text.

Unchanged: `control_timing` dense on every Experiment with a DE contrast, absent otherwise (T1);
`design_notes` sparse, required for `baseline` / `mixed`, in `experimentFullText`; `mixed` ⇒
≥ 2 timepoints (T5); writing rules (T4) minus the shared-model clause.

Counts: 174 DE experiments — 150 `matched`, 21 `baseline`, 3 `mixed` (Thompson 2011 went 5 → 4
Experiments: its MED4 48h contrast merged into the starvation experiment as `mixed`). Weissberg
`coculture_alteromonas_hot1a3_med4_rnaseq` reads `matched` (growth-state match vs the axenic repeat on
days 7 / 14), not `mixed` as S1 assumed. Curation log: KG `plans/control_timing_curation.md`.

## Explorer status (2026-10-18)

Absorbed the 2026-10-18T07:51Z build (live: 151 `matched` / 18 `baseline` / 4 `mixed` over 173 DE
experiments; the 150 / 21 / 3 over 174 above predates the closure pass and the Thompson merge).
Surfaced per `docs/tool-specs/control-timing-surface.md`: `list_experiments` compact
`control_timing` + sparse `design_notes`, `control_timing` filter, `by_control_timing`;
`list_filter_values(filter_type='control_timing')`; `control_timing` on every
`differential_expression_by_gene` / `differential_expression_by_ortholog` row, plus `control_timing`
and sparse `design_notes` in the by-gene `experiments[]` envelope; `docs://guide/conventions`
treatment-arm paragraph. `design_notes` turned out to be on 138 experiments (116 `matched`), not
~15, so it is kept compact on every row that has one. `statistical_model_id` was never built. Dialog closed.
