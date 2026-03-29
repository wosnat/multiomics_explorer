# CyVer — dev/testing scoping

CyVer (`pip install cyver`, already in `pyproject.toml`) validates Cypher queries
against a live Neo4j instance. Three validators:

| Validator | Method | Returns | Hard block? |
|---|---|---|---|
| `SyntaxValidator` | `EXPLAIN` | `(bool, list[dict])` | Yes — syntax errors |
| `SchemaValidator` | `EXPLAIN` + path checks | `(float 0–1, list[dict])` | No — score + warnings |
| `PropertiesValidator` | `EXPLAIN` + prop checks | `(float 0–1, list[dict])` | No — score + warnings |

All validators take a `neo4j.Driver` (available as `conn.driver`).

---

## Known behaviour / gotchas

### Parameterized queries fail SyntaxValidator

Queries using `$param` syntax (all our query builders) return `False` from
`SyntaxValidator.validate()` with code
`Neo.ClientNotification.Statement.ParameterNotProvided`.
This is a false negative — the query is syntactically valid, the driver just
can't cache the plan without parameter values.

**Confirmed:** SchemaValidator and PropertiesValidator work correctly on
parameterized queries — they return valid scores and detect bad labels/properties.

**Resolution:** SyntaxValidator is skipped for parameterized queries (detect
`$` in query string). Schema + Properties validators run on all builders.
SyntaxValidator runs only on non-parameterized queries (e.g. `list_gene_categories`,
`list_organisms`).

**Implication for `run_cypher` tool:** Not a problem — tool users write raw
Cypher without `$params`.

### PropertiesValidator false positives on map projection keys

PropertiesValidator cannot distinguish map projection keys (e.g.
`{org: g.organism_name}`) from property accesses (e.g. `g.org`). It reports
map keys like `org`, `cat`, `lt`, `cnt`, `terms` as missing node properties.

PropertiesValidator also returns `None` (instead of a float score) for queries
using fulltext indexes (`CALL db.index.fulltext.queryNodes`) or CALL subqueries.

**Resolution:** `test_cyver_queries.py` filters known false-positive map keys
via `_KNOWN_MAP_KEYS` set and accepts `None` scores as passing.

### Driver notification noise

CyVer uses `EXPLAIN` internally. The neo4j Python driver logs EXPLAIN
notifications via its own logger (`neo4j` logger). These appear as:
```
Received notification from DBMS server: <GqlStatusObject ...>
```
In tests these pollute stdout/stderr. Suppress via:
```python
import logging
logging.getLogger("neo4j").setLevel(logging.ERROR)
```
or add to `pytest.ini` / `conftest.py`.

### APOC queries

APOC calls (e.g. `apoc.coll.frequencies()`) pass SyntaxValidator — CyVer
does not check procedure availability, only Cypher syntax.

---

## Proposed dev/testing uses

### 1. Post-rebuild query validation test (`@pytest.mark.kg`) ✅

Implemented in `tests/integration/test_cyver_queries.py`.

**Resolved scope decisions:**
- **Validators:** SchemaValidator (strict, score == 1.0) + PropertiesValidator
  (with false-positive filtering) on all builders. SyntaxValidator only on
  non-parameterized queries.
- **Test file:** `tests/integration/test_cyver_queries.py` (separate file).
- **Threshold:** SchemaValidator: fail on score < 1.0. PropertiesValidator:
  fail on score < 1.0 after filtering known false positives (map keys, None scores).
- **Builder invocation:** Each builder called with representative dummy args via
  `@pytest.mark.parametrize` for per-builder test reporting.
- **Coverage:** ~105 builder variants (all builders × ontologies × verbose modes).

### 2. Add-or-update-tool skill step

Add a KG verification step to the add-or-update-tool skill: after writing
a new query builder, run CyVer Schema + Properties validators against it
before writing tests. This catches label/property typos earlier.

**Scope questions:**
- Add as optional step 2b in the skill, or as a gate before "Ready for build"?
- Document in the skill that `$param` queries need schema+props only (not syntax)?

### 3. CI integration

If validation tests are fast enough, run `@pytest.mark.kg` CyVer tests in CI
against the deployed KG. Blocks merge if KG/query drift detected.

**Scope questions:**
- Is the KG available in CI? (Docker in CI vs external)?
- How slow is CyVer per query? (Each call = 2–3 EXPLAIN round trips.)

---

## Status

- [x] Decide which validators to use for parameterized queries
  → Schema + Properties on all; Syntax only on non-parameterized.
- [x] Test SchemaValidator + PropertiesValidator against parameterized queries
  → Both work. Properties has false positives on map keys (filtered).
- [x] Decide test file structure for dev validation tests
  → `tests/integration/test_cyver_queries.py` with parametrize.
- [ ] Decide whether to add CyVer step to add-or-update-tool skill
- [ ] Decide CI integration approach (or defer)
