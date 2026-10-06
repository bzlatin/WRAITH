# Wraith subprocess protocol v1

Request (one line followed by EOF):

```json
{"protocolVersion":1,"scenarioId":"find-pto-policy","input":{"text":"How many PTO days?"},"metadata":{}}
```

Response (one JSON value, recommended trailing newline, then exit 0):

```json
{
  "protocolVersion": 1,
  "scenarioId": "find-pto-policy",
  "output": {"text": "Employees receive 20 PTO days."},
  "toolCalls": [{"name": "search_documents", "arguments": {"query": "PTO policy"}, "success": true}],
  "retrievals": [{"source": "employee_handbook", "documentId": "employee-handbook", "score": 0.92}],
  "usage": {"inputTokens": 200, "outputTokens": 58},
  "estimatedCostUsd": 0.001,
  "metadata": {}
}
```

All field names are case-sensitive. Unknown response fields are rejected; use
`metadata` for extensions. `output` is any non-null JSON value. Text evaluators
inspect a string value or the string at `output.text`.

`toolCalls`, `retrievals`, and `metadata` may be omitted (empty defaults).
`usage` and `estimatedCostUsd` may be omitted or null (unavailable).
If present, usage requires nonnegative integer `inputTokens` and `outputTokens`,
whose sum must fit in a Rust `u64`. Cost must be finite and nonnegative.

Tool calls require a nonempty `name`; optional fields are `arguments`, `result`,
`durationMs` (nonnegative integer), and `success` (boolean). Failed tool calls still
count as calls. Retrievals may contain `source`, `documentId`, `chunkId`, `score`
(finite JSON number), and `metadata` (object). Unavailable optional fields may be
null. Durations and timestamps owned by Wraith are not accepted in the response.

Stdout is reserved for protocol output, limited to 1 MiB. Logs belong on stderr,
which is drained and bounded to 64 KiB of retained diagnostics. A nonzero exit,
empty stdout, wrong version/ID, malformed JSON, extra response, or timeout is a
Wraith execution failure (exit 2), not a behavioral test failure (exit 1).

The application owns how it instruments calls and aggregates usage. Wraith validates
the adapter's claims but cannot independently verify uninstrumented actions.
Both example adapters implement this contract without provider dependencies.
