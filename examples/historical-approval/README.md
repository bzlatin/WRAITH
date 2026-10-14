# Offline approval workflow

A small application exercising actual PydanticAI tool approval and saved-history
orchestration at three pinned historical revisions. Its tool records receipts in
memory. Models are local functions; no provider is called.

[Run the pilot](../../docs/historical-pilot.md) for source setup, comparisons, and
the finite development queue. This is an upstream framework reproduction wrapped
in a small application, not an independently adopted customer agent.

- `source.json`: public issue/fix provenance and MIT source revisions.
- `contracts.json`: reviewed behavior for fresh/resumed/approved/denied requests.
- `approval_agent.py`: async workflow with observed tool recording.
- `tasks.json` and `acceptance.py`: independent feature work and acceptance checks.
- `requirements.txt`: complete pinned dependency set; upstream packages provide
  metadata while the runner selects the actual exported source through PYTHONPATH.

The retrospective defect is real; the model/tool boundary is deterministic. A
targeted unit test can express the same behavior. Wraith's contribution is the
fixed workflow contract and before/after evidence.
