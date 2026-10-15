# Live support-agent example

A small synthetic support application with real OpenAI tool selection, local policy
retrieval, approval/customer checks, and a model-generated structured final answer.
It uses no production customer data or external actions. Refunds only append an
in-memory fixture receipt.

The adapter calls the pinned `gpt-4.1-mini-2025-04-14` snapshot using the
[Responses function-calling API](https://developers.openai.com/api/docs/guides/function-calling).
It has no third-party runtime dependencies. The supplied model is documented with
[function calling and structured output support](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

Use the [live evaluation guide](../../docs/live-pilot.md) from a source checkout.
Preparation makes no provider request. Live execution requires explicit permission,
an environment credential, and a fixed shared budget. The runner refuses reuse of
an attempted experiment and never automatically replaces its baseline or budget.
Ten cases use at most three provider attempts each, across baseline and one intended
equivalent prompt refactor: **60 attempts maximum in total**, no retries.

`cases.json` contains reviewed contracts for public policy values, order ownership,
refund approval, missing evidence, prompt injection, and Unicode requests. Application
checks control authorization; model instructions do not replace them. The adapter
records tools at actual execution, retrieved source IDs, and observed token usage.
Every HTTP attempt reserves budget first, including failures. Provider errors stop
later requests. `store: false` disables API response storage; provider data handling
still applies to explicitly submitted synthetic inputs.

One observation per scenario is a functional check. These cases do not establish
production quality, an independent application integration, statistical equivalence,
customer demand, or a causal prompt effect. Model variability can explain a changed
observation; inspect saved outputs and traces before classifying it.

The initial 40-request run is preserved separately in the guide. The current
workflow can look up an order, issue its refund, and generate the final answer.
Execution requires trusted intent, approval, ownership, and the requested order;
matching receipts confirm completion and prevent duplicate execution. The runner
requires a complete passing baseline before spending requests on the candidate.
Offline tests cover these boundaries. Live results are reported separately from
unit tests and from the original experiment.
