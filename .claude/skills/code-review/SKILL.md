---
name: code-review
description: Review code changes against architecture conventions. Use after implementing or modifying tools to validate correctness across all 4 layers.
argument-hint: "[file path, tool name, or 'all' for full audit]"
---

# Code review

See [review checklist](references/review-checklist.md) for the full
checklist.

## Process

1. **Identify scope** — which layers were changed? Use `git diff` to
   see all modified files.

2. **Run checklist per layer** — for each changed layer, run through
   the relevant section of the review checklist.

3. **Check cross-layer consistency** — do signatures match across
   layers? Do return field names match between Cypher RETURN, API
   docstring, and about content (MCP resource)?

4. **Verify test coverage** — does every changed layer have
   corresponding test updates?

5. **Run tests** — verify everything passes:
   ```bash
   pytest tests/unit/ -v                        # unit tests (no Neo4j)
   pytest tests/integration/ -v                  # contract, about-examples, KG tests
   pytest tests/regression/ -m kg                # regression golden files
   ```

## Quick checks

Before diving into the full checklist, verify these common issues:

- [ ] New API function added to both `__init__.py` files?
- [ ] New tool added to `EXPECTED_TOOLS`?
- [ ] New builder added to `TOOL_BUILDERS`?
- [ ] No f-string interpolation of user input in Cypher?
- [ ] `ORDER BY` in every query for deterministic results?
- [ ] About content (MCP resource) updated if tool behavior changed?
