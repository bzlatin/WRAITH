# CI and release packaging

The CI action wraps a prebuilt executable; evaluation stays in Rust. Python 3 is
required for workflow/packaging scripts, while the released executable needs no
Python/Node runtime. Official GitHub Actions are pinned to resolved commit IDs.

## Local equivalent

```sh
cargo build --release --locked
python3 scripts/ci-check.py --binary ./target/release/wraith --mode run --save baseline --samples 5
# Change the agent, keeping scenario definitions fixed.
python3 scripts/ci-check.py --binary ./target/release/wraith --mode run --save candidate --samples 5
python3 scripts/ci-check.py --binary ./target/release/wraith --mode compare \
  --baseline baseline --candidate candidate --policy wraith.yaml --report reports/comparison.json
```

The script propagates 0/1/2/3/130 and appends `exit-code` to `GITHUB_OUTPUT` when set.
The composite action exposes that output and fails for nonzero exits. Use
`continue-on-error` on the candidate run so comparison can explain expected failures;
preserve execution errors as final failures. Store candidate/report evidence with
an `always()` artifact step.

## Baseline and PR workflows

`baseline.yml` runs five samples on pushes to `main` and uploads
`wraith-baseline-<commit SHA>`. `regression.yml` runs for ordinary `pull_request`
events, checks out the candidate and a separate harness from the trusted base SHA,
builds that harness, and downloads a successful push baseline for **that exact SHA**.
It rejects absent/expired baselines rather than picking the most recent unrelated
run. Lookup filters full SHA, branch, push event, and successful conclusion through
the [workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow).
Artifact names, run IDs, and retention follow [GitHub artifact support](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts).

Comparison uses `--policy` with the trusted base configuration, enforcing its
complete suite, thresholds, and comparison options. Candidate-config relaxation
does not relax this gate. Intentional scenario-suite changes require a coordinated
baseline refresh; they produce an incompatibility error first. These workflows
evaluate the repository's offline RAG fixture at `examples/rag-agent/wraith.yaml`.
Statistical comparisons returning 3 also block the action.

Bootstrap by merging the harness/workflow files onto `main`, then allow its push
baseline to succeed before enabling required PR checks. The first PR introducing
these files cannot build them from an older base that lacks the harness. Adapt the
branch filters if your default branch differs. Baselines retain 30 days; PR evidence
retains 14. An expired exact-commit baseline requires a new trusted baseline; a manual
baseline can produce an artifact for inspection, but automated lookup deliberately
accepts push runs only. Rerun the original trusted push workflow to regenerate
that exact baseline; its upload overwrites the old artifact. Extending the lookup
rule to accept manually generated baselines requires a separate trust decision.

PR jobs have read-only contents/actions permissions, no provider keys, and checkout
does not retain Git credentials. They use no `pull_request_target` or privileged
`workflow_run` execution. The token is present only for artifact lookup/download,
before agent execution. See [GitHub's trusted-event guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target).
An agent can still modify its host workspace or report dishonest traces: process
containment is not an adversarial sandbox or an attestation system. Treat agent and
test changes as code requiring review. Do not run fork code on privileged/self-hosted
runners or add secrets without redesigning that boundary.

## Native releases

`release.yml` runs tests and creates native Linux x86_64, macOS arm64/x86_64, and
Windows x86_64 MSVC binaries. Linux builds use Ubuntu 24.04/glibc; they are not musl
static binaries and do not promise compatibility with older glibc installations.
Runner labels follow the [hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

```sh
cargo build --release --locked
python3 scripts/package-release.py --binary target/release/wraith --target aarch64-apple-darwin
```

Packages contain the executable, README, protocol, `RELEASE.json` with target/version
and executable SHA-256, and a license or an explicit unlicensed private-build notice.
Archives use reproducible member metadata. Adjacent `.sha256` files checksum the
complete archive. The packaging script executes the native binary to verify its
version; cross-built files should be packaged on a compatible host. Use the actual
build target when invoking the script.

Manual workflow dispatch produces downloadable Actions artifacts. A pushed `v*`
tag checks binary/tag version equality and requires a nonempty owner-selected
`LICENSE`, then creates a **draft** GitHub release for review. The owner selected Apache-2.0;
`LICENSE`, `NOTICE`, and generated `THIRD_PARTY_LICENSES.txt` are included in packages.
Manual dispatch validates native archives without creating a release or tag. Checksums provide integrity, not signer authenticity.
Package reproducibility assumes identical input binaries; reproducible Rust compilation
and signed build provenance are not claimed.
