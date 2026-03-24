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

`SchemaValidator` and `PropertiesValidator` need to be tested to confirm
whether they also false-negative on parameterized queries.

**Implication for dev testing:** SyntaxValidator cannot be used as-is against
query builder output. Options:
1. Skip SyntaxValidator for parameterized queries (detect `$` in query string).
2. Substitute dummy values before validating (fragile for complex types).
3. Only run Schema + Properties validators against builders.
4. Run SyntaxValidator only on queries without `$params`.

**Implication for `run_cypher` tool:** Not a problem — tool users write raw
Cypher without `$params`.

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

### 1. Post-rebuild query validation test (`@pytest.mark.kg`)

After each KG rebuild, run CyVer against all queries in `kg/queries_lib.py`
to catch schema drift (renamed labels, removed properties, missing rel types).

**Scope questions to resolve:**
- Which validators to use for parameterized queries? (see gotcha above)
- Run Schema + Properties only? Or filter out `$param` queries first?
- Test file: `tests/integration/test_cyver_queries.py` (new) or add to
  `test_tool_correctness_kg.py`?
- Threshold: fail on score < 1.0, or warn below a threshold?
- How to extract query strings from builders (call each builder with
  representative args vs. parse source)?

**Sketch:**
```python
@pytest.mark.kg
def test_all_builders_schema_valid(conn):
    from CyVer import SchemaValidator
    schv = SchemaValidator(conn.driver)
    failures = []
    for name, builder_fn in QUERY_BUILDERS.items():
        cypher, _ = builder_fn()          # call with no-filter defaults
        score, meta = schv.validate(cypher)
        if score < 1.0:
            failures.append((name, score, meta))
    assert not failures, f"Schema issues: {failures}"
```

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

- [ ] Decide which validators to use for parameterized queries
- [ ] Test SchemaValidator + PropertiesValidator against parameterized queries
- [ ] Decide test file structure for dev validation tests
- [ ] Decide whether to add CyVer step to add-or-update-tool skill
- [ ] Decide CI integration approach (or defer)
