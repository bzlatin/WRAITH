# Next implementation increment

Implemented as v0.2.0. Local acceptance checks and remaining remote-platform
verification are recorded in [verification.md](verification.md). GitHub workflow
execution requires bootstrapping the files onto the default branch; this session
prepared and validated that code without publishing it.

## 1. Process lifetime

Add a reusable cancellation token and a CLI Ctrl-C listener. Cancel the active
invocation, kill its contained process tree, wait for cleanup, stop launching new
scenarios, and exit 130 without publishing an incomplete snapshot. Preserve the
drop guard for async task cancellation. Use Windows Job Objects via `process-wrap`
so the process is assigned while suspended, before it can spawn descendants.
Add descendant, parent-exit/pipe, and cancellation tests and a three-OS CI matrix.

## 2. Releases and CI

Build native release binaries on Linux, macOS, and Windows. Package them with docs,
version/target metadata, and SHA-256 checksums using a portable, tested script.
Prepare downloadable workflow artifacts and an explicit tag-driven release job.
Do not publish from this session. Licensing remains unselected; publication must
require a real LICENSE file while private packaging remains usable.

Create a composite action wrapping the local binary, with explicit run/compare
modes and exit-code propagation. Provide a baseline workflow tied to the exact
default-branch commit and a PR workflow that retrieves only a successful baseline
for the PR base SHA. Pin the evaluation harness to trusted base code, keep tokens
read-only, and retain candidate/report artifacts even on failure. Validate locally
the scripts and offline workflow-equivalent sequence; remote workflows require CI.

## 3. Richer comparisons and sampling

Add opt-in exact comparisons for tool arguments and retrieval document identities.
Canonicalize JSON objects, ignore ordering, preserve multiplicity, and identify
missing instrumentation. Add `run --samples N` with fresh process isolation for
each observation. Aggregate pass/failure counts per scenario and evaluator rather
than pairing sample indices across independently sampled versions. Show sample
rates and descriptive confidence intervals; never claim statistical significance.

Use run schema 2 and migrate schema 1 into one-sample runs. Validate complete sample
sets and compatible sample counts. Candidate snapshots store comparison policy;
CI can apply a separately supplied trusted config to prevent PR threshold relaxation.
Keep one-sample behavior compatible. Add migration, ordering, instrumentation,
sample aggregation, and CLI tests; exercise a changing deterministic fixture.

## Completion checks

Format, Clippy, unit/integration tests, debug/release builds, TypeScript compilation,
sampled and ordinary demos, package/checksum verification, CI YAML/action lint,
MSRV build, and a Windows target check where the local toolchain supports it.
Document remote-platform tests as pending until those workflows actually run.
