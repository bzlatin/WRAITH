# Where REA can help Wraith

Reviewed October 15, 2026. This is a fit assessment based on REA's documentation;
REA was not installed or executed, and no integration is claimed as verified.

[REA](https://github.com/morluto/rea) exposes local software analysis through a CLI
and MCP. It is potentially useful after an index check finds a discrepancy and the
connector's implementation or behavior is hard to inspect.

| Use case | Proposed investigation | Value to Wraith |
| --- | --- | --- |
| A packaged JavaScript/Electron importer writes unexpected IDs | Inspect its modules and trace the import path | Help locate identity mapping or pagination behavior |
| A connector update changes local behavior | Capture old/new runs in an isolated test directory and compare their outputs/files | Supply diagnostic evidence for a reported discrepancy |
| A supplied API capture contains a partial batch | Inspect that saved capture for pagination and response handling | Explain why a job's success message disagrees with the index |

These are proposed applications of documented capabilities, not tests we ran.
[JavaScript inspection](https://github.com/morluto/rea#what-you-can-analyze),
[process capture](https://github.com/morluto/rea/blob/main/docs/process-capture.md),
[saved network captures](https://github.com/morluto/rea/blob/main/docs/web-network-captures.md).

## Recommended first use

Use REA only when an actual ingestion failure cannot be explained from source and
ordinary logs. Select an application we own or are authorized to inspect. Retain the
Wraith manifest, observed inventory and failed job ID. Investigate only the relevant
connector, form a hypothesis, fix it in a test environment, then run the same index
contract again.

REA documents `capture-process` and `compare-process-captures` for direct runs with
terminal and selected filesystem evidence. It does not replay external dependencies.
Native capture currently requires Linux/macOS; comparisons of saved evidence can
run on Windows. Runtime capture executes with the current user's permissions and
is not a sandbox. Use an isolated fixture and explicit filesystem scope.
[Process contract](https://github.com/morluto/rea/blob/main/docs/process-capture.md).

Treat REA's operation completion separately from a Wraith pass: its CLI exit 0 can
include incomplete or unresolved evidence. Preserve unknowns and source locations
when reviewing a result. REA can explain what it observed; it cannot infer the
intended complete chunk inventory or prove that a database snapshot is consistent.
[CLI evidence and exits](https://github.com/morluto/rea/blob/main/docs/cli.md).

Do not add REA to every ingestion job or make it a required dependency. This source
checkout already exposes Wraith's implementation, so source inspection and tests
are the cheaper first step. A future optional diagnostic adapter should be driven
by a real case that needs REA, then pinned and validated against that case. Adding
reverse-engineering capability does not itself establish a new Wraith market.
