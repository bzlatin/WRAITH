# Verification

This record separates engineering checks from evidence of product usefulness.
Controlled fixtures show that Wraith detects specified defects; they do not measure
production accuracy or prove that developers find it useful repeatedly.

## v0.5.0 release

[v0.5.0](https://github.com/bzlatin/WRAITH/releases/tag/v0.5.0) is publicly available.
The [tagged native matrix](https://github.com/bzlatin/WRAITH/actions/runs/37558689791)
ran tests, built archives, verified checksums, and executed extracted binaries on:

| Platform | Native execution |
| --- | --- |
| Linux x86_64 GNU | Passed |
| macOS Apple Silicon | Passed |
| macOS Intel | Passed |
| Windows x86_64 MSVC | Passed |

The [general matrix](https://github.com/bzlatin/WRAITH/actions/runs/37558689781)
also passed, including formatting, Clippy, tooling tests, Rust 1.87 checks, adapter
demos, dependency notices, and workflow linting. Local macOS arm64 validation ran
42 Rust tests and seven Python tooling tests; the Windows Rust suite omits the
Unix-specific SIGINT test.

Anonymous installer download, checksum verification, and installation passed on
macOS arm64. The installed binary passed `init`, `doctor`, `baseline`, a deliberately
failing `check`, and a passing `check`, without model calls.

## Regression fixtures

- **RAG:** 21 comparisons produced 0/213 false alarms and 0/39 missed controlled
  regressions. Reproduce with `python3 scripts/pilot.py --repeats 3`.
- **Upstream orchestration:** three PydanticAI and three LangGraph cases passed;
  all six injected tool-skipping regressions were detected using offline models.
  See [the external pilot](../examples/external-agents/README.md).
- **Statistics:** the deterministic fixture produced an inconclusive result with
  20 samples, a passing harmless comparison with 200, and a failing stale-policy
  comparison with 200. These exercise policy mechanics, not model randomness.
- **Process and artifacts:** fault tests cover bounded pipes, timeouts, descendants,
  cancellation, protocol errors, schema migration, incompatible suites, fixed
  baselines, immutable history, and live-budget exhaustion/failure preservation.
- **HTML:** passing/failing reports were reviewed at desktop and mobile widths,
  including output disclosures, escaped hostile strings, and failure ordering.

## Published-binary PR checks

The generated workflow was tested against exact base/candidate commits:

- [Harmless wording PR](https://github.com/bzlatin/WRAITH/pull/1):
  [check passed](https://github.com/bzlatin/WRAITH/actions/runs/37559442806);
  changed output remained informational.
- [Injected refund regression PR](https://github.com/bzlatin/WRAITH/pull/2):
  [check failed](https://github.com/bzlatin/WRAITH/actions/runs/37559459123)
  with `OUTPUT_REGRESSION` and `PASS_TO_FAIL`, without execution errors.

Both PRs were closed without merging their fixture changes. JSON and HTML evidence
were retained by CI. Main requires the GitHub Actions `check` status and up-to-date
branches, including for administrators.

## Public documentation audit

The documentation refresh removes contributor-specific paths and private application
references. Gitleaks 8.30.1 found no credentials in the tracked files, existing Git
history, or extracted release-package contents. Pattern checks also reviewed local
paths and email addresses; upstream license credits and synthetic example addresses
remain. Automated scans do not guarantee that every form of sensitive data is detected.

The refreshed native archives contain updated documentation; the v0.5.0 executables
and binary metadata remain byte-for-byte unchanged. Archive checksums change with
the documentation. This does not change the source release tag or erase older commits.

## Reproduce locally

See [contributing](../CONTRIBUTING.md) for build/test commands,
[manual testing](dogfooding.md) for passing and failing workflows, and
[CI and packaging](ci.md) for native archives.

Natural regression discovery and repeat use on independent projects remain the
next product validation goals. Release checks used no live model requests. No
signing, automatic data redaction, or adversarial execution sandbox is provided.
