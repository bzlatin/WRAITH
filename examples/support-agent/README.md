# Standalone support agent

A small offline application for testing Wraith's usefulness during code changes.
It has corpus retrieval, order lookup, audience filtering, escalation, and ordinary
component tests. It runs without Wraith and makes no provider requests.

From this directory:

```sh
python3 -m support_agent --question "What is the refund policy?"
python3 -m unittest discover -s tests -v
```

Python 3.10+ and its standard library are sufficient. Caller identity and audience
are synthetic trusted inputs; this is not production authentication.

[requirements.md](requirements.md) defines the promises. `contracts.json` supplies
Wraith's frozen end-to-end checks. `tasks.json` adds acceptance checks for four
normal development tasks; those new features are separate from regression gates.

Use [the automated trial](../../docs/automated-trial.md) to let Codex implement the
tasks in isolated copies, compare them, and preserve findings. Existing component
tests, fixtures, and expectations cannot be changed inside a candidate.

Controlled defects verify engineering behavior. Regressions during Codex's work
remain simulated development; neither demonstrates adoption or live model quality.
