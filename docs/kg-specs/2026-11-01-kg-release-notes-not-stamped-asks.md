# KG ask: release notes never reach `Schema_info` (2026-11-01)

Origin: explorer absorb of `kg-0.1.0-alpha.8` (alpha-deploy, `bolt://127.0.0.1:17687`,
built 2026-11-01T09:15:07Z, git `91c5a952`, `deployment_role: production`).
The staging deploy (27687, built 09:01Z) shows the same.

## R1 — `release_highlights` / `release_breaking` are null on the release (P1)

Live on alpha.8: `size(s.release_highlights) = 0`, `size(s.release_breaking) = 0`, although
the tagged `CHANGELOG.md` has `## [0.1.0-alpha.8]` with `### Highlights` (5 bullets) and
`### Breaking` (9 bullets). alpha.7 shipped the same way. The explorer's `kg_release_info`
therefore shows no highlights and no breaking changes, so connecting users are not told
that `coculture_partner` is now a list, TCDB edges changed, and so on.

**Cause.** `release_kg.py` puts `KG_RELEASE_HIGHLIGHTS` / `KG_RELEASE_BREAKING` into the
environment of `docker compose up`, and `scripts/post-import.sh` stamps them, but no compose
file forwards them into the `post-process` container. `docker-compose.yml`,
`docker-compose.staging.yml` and `docker-compose.alpha.yml` list `KG_RELEASE_VERSION`,
`KG_GIT_SHA*`, `KG_MCP_MIN_VERSION` and `KG_DEPLOYMENT_ROLE` under `post-process.environment`,
but not these two. Inside the container both are unset, `post-import.sh` reads `''`, and the
`CASE WHEN … = '' THEN null` stamps null.

The same applies to `KG_RELEASE_NOTES_URL` (`post-import.sh:2134`): no compose file forwards it
and `release_kg.py` does not set it, so `release_notes_url` is always `''`.

**Fix.**
1. Add to `post-process.environment` in all three compose files:
   ```yaml
   KG_RELEASE_HIGHLIGHTS: ${KG_RELEASE_HIGHLIGHTS:-}
   KG_RELEASE_BREAKING:   ${KG_RELEASE_BREAKING:-}
   KG_RELEASE_NOTES_URL:  ${KG_RELEASE_NOTES_URL:-}
   ```
   and have `release_kg.py` set `KG_RELEASE_NOTES_URL` to the GitHub Release URL of the tag.
2. Make `/release-kg` fail, not just log, when the tagged CHANGELOG section has a non-empty
   `### Highlights` / `### Breaking` but the staging `Schema_info` reads `highlights_chars = 0` /
   `breaking_chars = 0`. It already queries both sizes; it only prints them.
3. Check that a multi-line markdown value survives the `-P "release_highlights => '…'"`
   parameter in `post-import.sh` (newlines inside a single-quoted cypher-shell parameter).
   The explorer expects the bullets verbatim.

**For alpha.8 now.** A rebuild is not needed. Stamp the two properties (and the release
notes URL) on the alpha-deploy `Schema_info` node from the tagged CHANGELOG section, then
re-check from the explorer side: `kg_release_info()` should show `kg.release_highlights` and
`kg.breaking_changes`. (The explorer reads `release_breaking`; fixed explorer-side 2026-11-01.)

## Status

Open (KG side).
