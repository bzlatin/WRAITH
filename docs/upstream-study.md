# Frozen checks against upstream pull requests

Wraith can run a repeatable CI gate. This study does **not** establish that the
current suite prevents valuable regressions beyond application tests: four PR
comparisons passed, six selected PRs were blocked, and no useful catch was found.

## What ran

Sixteen existing smolagents scenarios and a chronological selection rule were
frozen before inspecting the selected PR changes. The first queue looked for
mainline changes after the pinned source revision; there were none. Two separately
frozen batches then selected the first five and next five oldest open PRs targeting
`main` that touched `src/smolagents/agents.py`. Blocked PRs were not replaced.

Only exact test merges with the pinned base and recorded PR head were accepted.
Each executable revision retained three previously reviewed local fixes from the
[green baseline](workflow-value.md). These are proposed upstream changes with local
prerequisites, not pristine upstream, maintainer adoption, or prospective discovery.

| Selected PR | Result |
| --- | --- |
| [#301](https://github.com/huggingface/smolagents/pull/301), [#511](https://github.com/huggingface/smolagents/pull/511), [#851](https://github.com/huggingface/smolagents/pull/851) | Stale test merges; blocked |
| [#888](https://github.com/huggingface/smolagents/pull/888), [#963](https://github.com/huggingface/smolagents/pull/963) | Wraith and selected upstream tests passed |
| [#1439](https://github.com/huggingface/smolagents/pull/1439) | Wraith and selected upstream tests passed |
| [#1457](https://github.com/huggingface/smolagents/pull/1457), [#1458](https://github.com/huggingface/smolagents/pull/1458), [#1635](https://github.com/huggingface/smolagents/pull/1635) | Stale test merges; blocked |
| [#1769](https://github.com/huggingface/smolagents/pull/1769) | Wraith and selected upstream tests passed |

Each completed comparison passed 16 cases in both versions. Each unchanged upstream
subset passed 25 tests with one skip; the selected nodes are recorded in
`examples/workflow-agent/source.json`. This was not the complete upstream suite.
On the tested Mac, each base/candidate comparison plus evidence took about five
seconds with four jobs and warm dependencies. Setup, installation, build and human
work are excluded. There were no provider calls.

The first batch initially copied an old saved binary without `ci check`, producing
two setup failures. Those results remain preserved. A fresh study used the same
queue with the current binary; preparation now checks capability before creating
an experiment. Setup failures are not agent regressions or useful catches.

[Sanitized results](evidence/upstream-study.json) and the
[pinned reproduction queue](evidence/upstream-queue.json) preserve exact revisions,
selection rules, fingerprints, blocked candidates, and earlier attempts.

## What the passes mean

Source review after evaluation found a relevance gap. PR #888 changes documentation.
PR #963 changes CodeAgent image handling, while this suite runs ToolCallingAgent.
PR #1439 adds an image limit that the cases do not enable. PR #1769 changes template
hooks for planning, fallback answers and managed agents; the cases do not explicitly
assert those paths. No line or branch coverage was measured.

The suite is useful for its specified final-answer validation, streaming, memory
and callback contracts. These passes do not show that the new features work, that
all changed behavior was exercised, or that Wraith would have caught a bug in it.
They also cannot estimate a false-positive rate, reviewer effort, time savings,
customer demand, or return on investment.

The next study should use a second actively changing agent workflow and define its
user-facing requirements before selecting changes. Include multistep tool use,
failed-tool recovery and handoffs when they belong to that workflow. Evaluate both
feature acceptance and old behavior; measure which findings the existing tests
already detect. A useful catch must be reviewed against an actual requirement.

## Reproduce without authoring cases

From a current source checkout:

```sh
cargo build --workspace --locked
python3 scripts/upstream-pilot.py --root .wraith/upstream-study reproduce --install
```

This installs pinned dependencies into a new virtual environment, retrieves the
exact public test merges, checks their archive fingerprints, runs the offline
comparisons and upstream subset, and saves JSON/HTML evidence. Git, Rust and Python
3.12+ are required. Pinned test merges can become unavailable upstream; that is a
setup failure, not a regression. The socket guard is cooperative isolation.

Read `.wraith/upstream-study/report.md`; native HTML reports are under `runs/`.
A sibling `.wraith/upstream-study-reference` holds the frozen baseline preparation.
Both directories are preserved; choose a new explicit root for another experiment.
`verify` checks frozen inputs, dependencies, selections and completed evidence.

The `upstream-study` job in the upstream study workflow runs this same pinned
reproduction with read-only permissions and no provider secrets. It fails if the
recorded classifications change. Replays verify compatibility; they are not new
product observations. It runs when the research inputs change or by manual dispatch,
so it adds no job to ordinary application PRs. There is no recurring polling job: the empty mainline queue
and stale merges provide no reason to generate more identical reports.

For new research, `prepare --study <prepared-workflow-study> --binary <current-binary>`
freezes the suite and a bounded rule. `select --upstream <clone> --tip <commit>` selects
mainline revisions; `--mode open-prs` with `select-prs` selects public PRs and requires
GitHub CLI access. `--offset` permits a separately frozen later batch. Only selection
uses the network; `run` executes the recorded queue offline. Research `run` exit 0
means evidence collection completed, including blocked/failing candidates. Use the
native `wraith ci check` exit code for an application gate.
