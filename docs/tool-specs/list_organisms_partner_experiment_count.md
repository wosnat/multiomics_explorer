# list_organisms — surface `partner_experiment_count`

Mode A (one tool, small additive change). Follow-up from the 2026-10-28 Ford-strains absorb
(`docs/kg-specs/2026-10-28-ford-strains-absorb-asks.md`, A1 explorer reply).

## Purpose

KG A1 narrowed `OrganismTaxon.experiment_count` to the organism's own experiments
(`Experiment.organism_name`) and added `OrganismTaxon.partner_experiment_count`: experiments with
a `Tests_coculture_with` edge to the organism, either role. Without it, partner-only taxa (Phage,
E. coli, Vibrio parahaemolyticus, Meiothermus ruber) read `experiment_count=0` and look
data-less, though `list_experiments(coculture_partner=...)` returns their experiments.

## Change

One new compact per-row field on `list_organisms`:

| Field | Type | Semantics |
|---|---|---|
| `partner_experiment_count` | `int`, default 0 | Experiments in which this organism is the coculture partner (either `coculture_role`), not the profiled organism. Disjoint from `experiment_count`'s basis; drill in with `list_experiments(coculture_partner=<organism_name>)`. |

- Placed right after `experiment_count` in the builder RETURN, API docstring, and Pydantic model.
- Compact (not verbose-gated); never sparse-stripped.
- Reword `experiment_count`'s Field description to point at the new field instead of only at
  `list_experiments(coculture_partner=...)`.
- No new parameter, no filter, no sort change, no envelope change.
- Capability projection (`build_list_organisms_capability`) and summary builder untouched.

## Verified Cypher (live KG, build 2026-10-28T18:39:47Z)

Detail builder gains one column:

```cypher
       o.experiment_count AS experiment_count,
       coalesce(o.partner_experiment_count, 0) AS partner_experiment_count,
```

Checks run:
- Populated on 121/121 organisms; 23 non-zero; total 182; 4 partner-only (`experiment_count=0`).
- Precompute equals the live `count(DISTINCT e)` over `(e:Experiment)-[:Tests_coculture_with]->(o)`
  on every organism (0 mismatches).
- Spot values: MED4 45 own / 11 partner; WH7803 11 / 12; Phage 0 / 7; E. coli 0 / 2;
  Alteromonas (MarRef v6) 20 / 40; MIT9515 0 partner.
- Chain: `list_experiments(coculture_partner=p, summary=True).total_matching` equals
  `partner_experiment_count` for Phage (7), E. coli (2), MED4 (11), Alteromonas (MarRef v6) (40).

## Docs

- `inputs/tools/list_organisms.yaml`: one `mistakes` line — `experiment_count` is own experiments
  only; partner experiments are `partner_experiment_count`, listed via
  `list_experiments(coculture_partner=...)`. A `chaining` line for the same hop if not already there.
- Example responses: refresh via `scripts/refresh_examples.py --write --tool list_organisms`.
- CLAUDE.md row: add `partner_experiment_count` only if the row stays within the length lint.

## Tests

- Unit: builder emits `partner_experiment_count` with `coalesce(..., 0)`; api passes it through
  on compact rows; wrapper model accepts it with default 0.
- Regression: `--force-regen` the `list_organisms*` goldens that carry detail rows (new column).
- Edge cases: existing `list_organisms` scenarios cover it (no new input axis); no new scenario.
