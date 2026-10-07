# v0.2 implementation record

Historical context: these changes are implemented. For current work, read the
[roadmap](roadmap.md); for results, see [verification](verification.md).

The increment established three boundaries:

1. **Process lifetime:** Ctrl-C cancellation, exit 130 without completed partial
   artifacts, Unix process groups, and Windows Job Objects for descendant cleanup.
2. **Distribution and CI:** native archives with checksums and metadata, a composite
   action, exact-commit baseline artifacts, and trusted-base PR comparison.
3. **Comparison:** optional exact tool-argument/document gates and independent
   repeated observations with counts and descriptive intervals.

Run schema 2 introduced sample aggregation and migrated schema 1 in memory. Current
artifacts use schema 4; statistical gates and structured JSON checks arrived later.
The project is Apache-2.0 licensed and v0.5.0 is published.

These decisions remain relevant: evaluate in Rust, keep provider logic in adapters,
compare identical suites, preserve missing metrics, and distinguish observed changes
from configured regressions. See [architecture](architecture.md) for current contracts.
