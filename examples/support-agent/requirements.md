# Support application contracts

This is an offline mock application, not a production authorization boundary.
Synthetic caller identity and audience are supplied by the trusted experiment.

- Answer policy questions from current, authorized documents and include their IDs.
- Never disclose staff-only documents to a public caller, even within a session
  that previously handled staff input.
- Look up orders only for their owner; unavailable or foreign orders escalate.
- Unsupported questions escalate without inventing an answer.
- Every response has a nonempty text, answered/escalated status, and citation array.
- Formatting and ranking may change while these promises hold.

The application has ordinary component tests. Trial contracts add complete workflow
coverage; test overlap must be reported. Fix these requirements before evaluating
candidates. Candidate implementations may not edit requirements, data, tests, or
trial policy. New task acceptance checks are separate from frozen regression gates.
