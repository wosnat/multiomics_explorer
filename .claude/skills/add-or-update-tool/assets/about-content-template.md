# {tool_name}

## What it does

One paragraph expanding on the tool's docstring. What data it returns,
what questions it answers, when to use it vs alternatives.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| — | — | — | — |

**Discovery:** use `list_organisms` for valid organism names,
`list_filter_values` for valid categories, etc.

## Response format

<!-- Choose the section that matches the tool. Delete the other. -->

### Option A: Small result set (no modes)

Returns all matching rows directly. No modes.

```example-call
{tool_name}(param="value")
```

```expected-keys
field1, field2, field3, ...
```

#### Verbose

Set `verbose=True` to include heavy text fields:

```example-call
{tool_name}(param="value", verbose=True)
```

```expected-keys
field1, field2, field3, abstract, description, ...
```

### Option B: Summary/detail/about modes

#### Summary mode (default)

Returns aggregated statistics without fetching individual rows.

```example-call
{tool_name}(param="value", mode="summary")
```

```expected-keys
total, breakdown_field, ...
```

#### Detail mode

Returns individual rows ordered by {sort_key}, limited.

```example-call
{tool_name}(param="value", mode="detail", limit=25)
```

```expected-keys
field1, field2, field3, ...
```

**Sort key:** {sort_key} ({direction})
**Default limit:** {N}, **Max:** {M}

When `truncated: true`, use `total` from the response — not `len(rows)`.

## Few-shot examples

### Example 1: {simple use case description}

```example-call
{tool_name}(param="value")
```

```example-response
[
  {"field1": "value1", "field2": 42},
  {"field1": "value2", "field2": 17}
]
```

### Example 2: {chained use case description}

Show a realistic multi-step sequence — what tool comes before,
how its output feeds into this tool, and what to do next:

```
Step 1: {previous_tool}(identifier="gene_x")
        → get value from result

Step 2: {tool_name}(param=value)
        → inspect results

Step 3: {next_tool}(param=value_from_step_2)
```

## Chaining patterns

What tool to call before this one, and what to do with the results:

```
{previous_tool} → {tool_name} → {next_tool}
```

## Package import equivalent

```python
from multiomics_explorer import {tool_name}

results = {tool_name}(param="value")
# returns list[dict] with all rows (no limit)
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
