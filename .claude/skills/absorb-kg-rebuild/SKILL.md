---
name: absorb-kg-rebuild
description: Use when a new KG build has landed at localhost:7687 (rebuild, re-index, paper batch, vocab change, official release) and the explorer's tests, goldens, pins, docs snapshots and example responses must be brought in line — "absorb the rebuild", "make it green after the rebuild", "kg_release_info says warn".
---

# Absorb a KG rebuild

## Overview

A rebuild moves data, not code. The job is to (1) prove every diff is a
data move the KG note announced, (2) regenerate what is derived, and
(3) record what moved. **Never loosen an assertion to make it pass.** A
diff the note can't explain is a regression or a wrong database; both
stop the release, and the deadline is not a reason to regenerate it.

A rebuild never needs edits under `kg/`, `api/`, `mcp_server/`. If it
does, it is not an absorption — write `docs/kg-specs/YYYY-MM-DD-*-asks.md`.

Only the scripts and tests below exist. Do not invent others.

## Order of work

Paths are repo-relative. `LINT = multiomics_explorer/inputs/lint`.

| # | Step | Command / file |
|---|---|---|
| 1 | Identify the build | The verdict is cached at MCP lifespan start — restart (`/mcp`) or read live: `uv run python -c "from multiomics_explorer.kg.connection import GraphConnection as G; print(G().execute_query('MATCH (s:Schema_info) RETURN s.version, s.built_at, s.gene_count, s.controlled_vocabularies_hash'))"`. Note all four. `built_at` equal to the one in the `constants.py` hash comment ⇒ already absorbed, stop. `deployment_role` / `version` say whether this is a dev build — a release must not be cut against one. |
| 2 | Hash rule | Any change to a `ControlledVocabulary` value set moves the hash. Note says vocab changed and hash moved ⇒ re-pin `EXPECTED_CONTROLLED_VOCABULARIES_HASH` in `multiomics_explorer/kg/constants.py` (+ its comment: what changed, `built_at`). Note says hash-neutral but a value changed, or hash moved with no vocab note ⇒ **stop, ask the KG side** (steps 3–7 are read-only and may run while waiting; no edits). Re-pin only after step 3's diff shows exactly the announced values. |
| 3 | Vocab snapshot | `uv run python scripts/snapshot_vocab.py` → `git diff $LINT/vocab_snapshot.yaml`: only announced values may appear/disappear. |
| 4 | Offline gate | `pytest tests/unit -q` — never touches the KG. Failures are code, or a doc quoting a retired vocab value (`tests/unit/test_docs_lint.py`; fix the prose). |
| 5 | Start the long poles (background, independent) | `pytest tests/regression -m kg -q` and `pytest tests/integration -m kg -q -p no:cacheprovider`. Classify while they run. |
| 6 | Constants + fixture guards (fast) | `pytest tests/integration/test_kg_constants_drift.py tests/integration/edge_cases/test_fixture_guards.py -m kg -q`. A `VALID_*` constant moving is an unannounced layer change ⇒ stop. A guard failure = a degenerate fixture is no longer degenerate → re-pin it in `tests/integration/edge_cases/fixtures.py` with the discovery Cypher in its own comment. |
| 7 | Goldens | Classify every failing golden (rule below). Count the allowed set = n. `pytest tests/regression --force-regen -m kg -q`; `git diff --stat tests/regression/` must list exactly n files; `git checkout --` the rest and investigate. |
| 8 | Live-suite triage | Literal pin moved by the announced amount → update the number (prefer the live `kg_count` fixture over a new literal). Vanished exemplar locus_tag → `resolve_gene`; gone ⇒ a same-organism neighbour with the same annotation profile; add the old tag to `$LINT/stale_identifiers.yaml` if docs quoted it. Invariant tests (`test_two_state_invariants`, `test_trust_*`) failing ⇒ stop. |
| 9 | Example responses | `uv run python scripts/refresh_examples.py --check` → `--write <tool …>` for the drifted tools. `error`/`empty` = an example input the rebuild removed → fix the `call:`, never the response. |
| 10 | Regenerate docs | `uv run python scripts/build_about_content.py` (add `--live-vocab` when a vocabulary changed) then `--lint`; `pytest tests/unit -q` again. |
| 11 | KG numbers in docs (after 10) | `pytest tests/integration/test_docs_kg_claims.py -m kg -q` — a failing claim names its `used_in` files: fix the prose, then `$LINT/kg_claims.yaml`. |
| 12 | Record + verify | CHANGELOG `[Unreleased]`: `built_at`, gene_count before→after, goldens n, pins n, hash old→new, `-m kg` pass count. Close matching `docs/backlog.md` / `docs/kg-specs/*-asks.md` items. Restart `/mcp`; `kg_release_info` must read `ok` with every assert passed. One commit `chore(kg): absorb <built_at> rebuild (<what>)`. |

**Commit allowlist:** `kg/constants.py` (hash only), `$LINT/*.yaml`,
`tests/regression/**`, `tests/integration/**` (pins, exemplars, fixtures),
`inputs/tools/*.yaml`, regenerated `skills/**`, CHANGELOG, backlog. `git diff
--stat` showing anything else means the no-code-edits rule above was broken.

## Classifying a diff

Allowed = attributable to exactly one announced delta:
- gene-id mapping → Gene-anchored ids/counts move (`gene_overview`,
  `genes_by_*`, `gene_homologs`, organism `gene_count`, DE rows, and the
  gene-side chemistry counts `transporter_gene_count` / `catalyst_gene_count`);
  metabolite / reaction / assay / DM counts stay flat.
- index rebuild → tied-score reordering in `search_ontology` /
  `genes_by_function` (Lucene ties are non-deterministic).
- vocab change → the value appears in `list_filter_values` and `by_*` rollups.

Regression = anything else: an envelope key appears or vanishes, a type
changes, `truncated` flips, a count moves in a layer the note did not
name, a `not_found` for a gene the mapping note doesn't cover.

## Common mistakes

- Trusting a `kg_release_info` served by a process started before the rebuild.
- `--force-regen` before classifying — regenerating a regression into the golden.
- Skipping steps 3, 6, 9, 11: they fail late and look like unrelated flakes.
- Fixing an example by editing its `response:` — responses are generated; only `call:` is yours.
