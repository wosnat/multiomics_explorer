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

## Response modes

### Summary mode (default)

Returns aggregated statistics without fetching individual rows.

```example-call
{tool_name}(param="value", mode="summary")
```

```expected-keys
total, breakdown_field, ...
```

### Detail mode

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
{tool_name}(param="value", mode="summary")
```

```example-response
{
  "total": 42,
  "breakdown_field": {"category_a": 25, "category_b": 17}
}
```

### Example 2: {filtered use case description}

```example-call
{tool_name}(param="value", other_filter="filter_value", mode="detail", limit=10)
```

```example-response
[
  {"field1": "value1", "field2": 3.2, "field3": "annotation"},
  {"field1": "value2", "field2": 2.8, "field3": "annotation"}
]
```

### Example 3: {chained use case description}

Show a realistic multi-step sequence — what tool comes before,
how its output feeds into this tool, and what to do next:

```
Step 1: {previous_tool}(identifier="gene_x")
        → get locus_tag from result

Step 2: {tool_name}(param=locus_tag, mode="summary")
        → check total, decide on limit

Step 3: {tool_name}(param=locus_tag, mode="detail", limit=50)
        → inspect individual rows

Step 4: {next_tool}(param=value_from_step_3)
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

## Common mistakes

```mistake
# WRONG: counting rows from truncated detail
len(rows)  # gives {limit}, not the real total
```

```correction
# RIGHT: use total from summary or truncation metadata
response["total"]  # gives the real count
```
