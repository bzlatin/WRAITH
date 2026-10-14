# Support-agent feature changes

Three independent patches add policy aliases, normalized pasted order IDs, and
structured handoff details to the synthetic support application. The runner applies
each change to its own baseline copy, then runs frozen component tests, separate
feature acceptance tests, and the same ten Wraith scenarios.

See the [operator guide](../../docs/feature-queue.md) for preparation, offline replay,
optional live spending, saved reports, and interpretation. These are local feature
changes to an authored example, not independent adoption or seeded defects.

`recorded-decisions.json` contains synthetic tool selections and model drafts from
the earlier live baseline. Expected tool return envelopes are reconstructed from
that pinned application and checked against its recorded tool activity. Replay
rejects changed tool results; it does not ask the model to generate a new answer.
