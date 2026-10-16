# Startup recommendation: code context for parallel coding agents

October 16, 2026. Research and a proposed investment decision, not an implemented
pivot, release, spending authorization or evidence of paid demand. This document
responds to the owner's request to reassess the earlier proposals. Existing Wraith
utilities and evidence remain available; do not relabel them as validation of this
idea. No private app/account data is used in the recommendation.

## Recommendation

Investigate an open-source, local code-context engine for developers using coding
agents on TypeScript projects, with explicit Git worktree isolation and incremental
updates. Its job: give the agent relevant definitions, references and tests from
the checkout it is actually changing, in a bounded amount of context.

Proposed promise: **Give your coding agent the right code from the right checkout.**

Developers keep their existing coding agent and test command. They point the tool
at a local repository and add one MCP server, or use the CLI. No business-account
connections, cloud indexing account, embedding provider or GPU is required for
the first version. A later team product would manage shared indexes and access;
an enterprise offering would add private deployment, permission synchronization,
operational controls and supported upgrades.

This is entry into an existing market. There is no established empty category or
exclusive feature here. The opportunity is a narrower, better-executed experience
for a specific workflow. That experience must beat free alternatives before we
invest in a hosted service.

## Why the earlier process failed

The original regression engine, ingestion checks and finance prototype produced
working software. Their tests did not establish a recurring reason for a developer
to adopt them or a buyer to pay. Work repeatedly advanced from an interesting
engineering observation to another implementation queue without resolving those
questions. The finance exercise also required multiple accounts and substantial
normalization before reaching its intended answer.

For this decision, freeze additional finance connectors and broad Wraith feature
expansion. Do not discard the existing work or force its architecture into this
product. A possible new product must earn its own implementation and name.

## Alternatives considered

| Direction | Attraction | Reason for ranking |
| --- | --- | --- |
| Local code context for coding agents | One local input; used during ordinary development; measurable performance and correctness; CPU-based first version | First choice, conditional on a competitive result. Competition is strong and free options exist. |
| Self-service external API sandboxes | Clear integration-testing use; REA can assist authorized investigation | Second choice. Stateful fidelity and maintained provider coverage are substantial ongoing work. [Speedscale](https://speedscale.com/pricing/) already offers free local mocking and paid collaboration/private deployment. A broad catalog or custom-work service does not fit the current goal. |
| AI telemetry processing and governance | Recurring operational data; a plausible enterprise control plane | Defer. [Cribl](https://cribl.io/solutions/initiatives/ai-observability/) already explicitly markets AI collection, normalization, redaction and routing. [OpenTelemetry's redaction processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/redactionprocessor/README.md) is a free baseline. A production telemetry intermediary brings availability and sensitive-data responsibilities. |
| General AI observability or spend dashboard | Existing commercial category | Defer. [Langfuse](https://langfuse.com/pricing) lists a free tier and a $29/month Core entry plan, alongside enterprise plans. Broad feature replication or a modest discount is insufficient positioning. |

The ordering is founder-fit judgment, not a numerical estimate of startup success.

## What the current research establishes

Primary sources were inspected: product documentation, current public pricing,
maintainer documentation and user-authored GitHub reports. No paid product was
benchmarked, customer contacted, software installed or REA analysis executed for
this memo. Listed prices do not establish conversion, actual contract value or
revenue. Search was qualitative, not a representative issue census.

### Existing supply and price pressure

| Product | Documented offer on research date | Implication |
| --- | --- | --- |
| [Augment Context Engine](https://www.augmentcode.com/product/context-engine-mcp) and [pricing](https://www.augmentcode.com/pricing) | Context retrieval through MCP, local updates and multiple sources. Standard is $20/month for the team with $20 usage included, plus top-ups; enterprise is custom. | Interoperability, local updates and low entry pricing already exist. Do not claim them as unique or quote vendor performance claims as our results. |
| [Sourcebot pricing](https://www.sourcebot.dev/pricing) and [repository](https://github.com/sourcebot-dev/sourcebot) | Self-hosted code search/navigation and MCP; free Basic up to five users, Pro $20/user/month, custom enterprise. Documents local Git directories, repository permissions and a Docker deployment. | Private deployment, shared search and inexpensive team access are already served. A generic private context server is insufficient. |
| [Serena](https://github.com/oraios/serena) | Free code intelligence through language servers, with retrieval and editing tools | This is the most important local baseline. Our tool needs a demonstrated advantage in the selected workflow, not just fewer features. |
| [Claude Context](https://github.com/zilliztech/claude-context/blob/master/docs/troubleshooting/faq.md) | A fully local configuration is documented using Milvus and Ollama | Local semantic search is possible today. Its setup offers a comparison for a version without a separate vector service; avoiding embeddings can also reduce retrieval quality. |
| [Sourcegraph pricing](https://sourcegraph.com/pricing) | Enterprise code understanding, MCP/API/CLI and administration; $16,000 minimum annual contract | There is an established enterprise offer around code intelligence. This price does not establish demand for our smaller product or imply equivalent capabilities. |

Do not compare our hypothetical flat price with an incumbent's enterprise price
while omitting its free or inexpensive alternative. Do not assume SSO alone will
turn a free utility into an enterprise business.

### Concrete workflow reports

- [Serena discussion #677](https://github.com/oraios/serena/discussions/677): a
  developer describes roughly 1.5 minutes of Kotlin reindexing per worktree and
  asks about copying cached data; the maintainer gives a workaround. This is a
  historical workflow report with a practical solution, not an unsolved outage.
- [Serena issue #1496](https://github.com/oraios/serena/issues/1496): a report of
  agent teammates retaining the primary checkout context while their shell is in
  a worktree. Current [worktree documentation](https://github.com/oraios/serena/blob/main/docs/02-usage/999_additional-usage.md)
  explicitly addresses project-root selection. Test the current release; do not
  sell a historical bug as a present universal limitation.
- [Serena issue #2145](https://github.com/oraios/serena/issues/2145): a large-project
  user reports expensive filesystem polling before symbol queries. Discussion
  explicitly weighs correctness against refresh performance. These are reported
  measurements from that setup, not independently reproduced performance numbers.
- [Serena issue #1814](https://github.com/oraios/serena/issues/1814): a report of
  reference lookup returning empty after a language-server failure. This motivates
  explicit incomplete/error states; an upstream fix may resolve it completely.
- [Continue's indexing documentation](https://github.com/continuedev/continue/blob/main/core/indexing/README.md)
  describes content-addressed reuse across branches and notes a branch/repository
  scoping limitation in its full-text index. This establishes existing techniques
  and a documented limitation, not a fresh reproduction of current behavior.

Together these motivate tests for indexing cost, checkout identity, freshness and
honest partial results. They do not prove a large unmet market, independent buyer
demand or that worktree support is unique. Several reports concern the same
project and should not be counted as independent markets.

## Initial customer and recurring job

Start with developers and small product teams using coding agents frequently on
TypeScript/JavaScript repositories with multiple packages or several worktrees.
Avoid promising every language, every enterprise repository and every internal
knowledge source at launch.

Example task: change a subscription eligibility function. The agent needs its
definition, callers, the entitlement type, existing tests and the API boundary.
The tool returns a compact context bundle with file/line citations and the checked
snapshot, rather than an uncited architecture summary. If resolution is partial,
it says so. It does not claim that a list of likely tests proves all affected
behavior has been found.

The repeated job is finding and refreshing this context during code changes.
Individual adoption needs useful results immediately. Team payment would buy
shared operation, administration and supported deployment after the local engine
has earned repeat use.

## Product boundary for a first implementation

Proposed implementation budget: ten focused engineering days, not a delivery
guarantee. Do not start a separate dashboard, provider connector catalog or cloud
platform inside this budget.

1. Read-only CLI and stdio MCP server. Index local Git repositories without
   executing their build scripts, package hooks or repository-supplied binaries.
2. TypeScript/JavaScript first. Search source and definitions; resolve imports and
   references only where supported. Distinguish exact/compiler-resolved relations
   from lexical candidates. Dynamic behavior and unsupported files stay explicit.
3. A task-context result that combines ranked snippets, supported relationships
   and candidate tests under a requested size budget. No generated whole-repository
   prose required. Retain native file search as a fallback.
4. Explicit repository/worktree identity, file hashes and snapshot state. Reuse
   unchanged content safely, isolate dirty files and detect branch switches,
   deletes, renames and concurrent edits. Return a stale/incomplete response when
   freshness cannot be established. Git HEAD alone cannot identify dirty content.
5. One portable executable if feasible; embedded storage and CPU lexical/syntax
   processing. Verify whether an embedded SQLite/search library and existing
   parser can serve the task before creating a custom storage engine. No mandatory
   embeddings or remote model calls in the retrieval path.
6. Ignore private/configuration files by default, constrain reads to approved
   roots, and keep repository text as untrusted data. Local indexing does not keep
   snippets private from a remote model when the user explicitly sends them there.

These are proposed requirements, not current Wraith commands or completed features.
Language-server fidelity, memory use and packaging may force a narrower first
version. Respect dependency licenses; inspect the exact version before reusing
code. This memo does not select a new distribution license.

## Competitive test before more product work

**First two engineering days:** install/run competitors on public repositories,
record versions/configuration, and freeze a small workload. This is the first
implementation step if the owner adopts the proposal. No competitor benchmark has
run yet. Do not require customer accounts to run the free/local baseline.

Use three TypeScript repositories with checked-in tests and multiple packages.
Freeze selection rules and tasks before developing the candidate. Include ordinary
lookup tasks and historical code-change tasks with unchanged acceptance tests;
call historical reproduction what it is. Keep a held-out set and do not alter tests
to favor the proposed engine.

Compare the same agent/model with native file search, current Serena and our
candidate. Add Sourcebot and Augment where access and resource scope permit; if a
commercial comparison cannot run, label it untested rather than infer a win.
Keep model settings, task information, permissions and budgets equal, counterbalance
run order, and preserve failures and incomplete attempts. Inspect correctness using
unchanged application tests and task acceptance, separately from retrieval metrics.
Live provider calls require a fresh explicit spending authorization; past trial
caps are not reusable.

Record:

- Setup steps and observed intervention; machine setup time separately from human effort.
- Cold indexing time, steady-state and peak memory, index size, update latency and
  concurrent-worktree isolation.
- Relevant code returned and omitted, unresolved references, stale citations and
  behavior on a failed indexer. A planted stale-file control is calibration.
- Completed tasks, unchanged test results, agent input/output and cached-token
  usage, provider cost where measurable, tool calls and elapsed time. A smaller
  snippet is not automatically a smaller bill or faster successful task.

Proposed internal continuation threshold: no cross-worktree result contamination
on the frozen controls; setup under five minutes on the stated supported environment;
and a material end-to-end advantage on the held-out tasks. One candidate target is
at least 20% lower median provider cost or elapsed time with no observed decline
in accepted task completion. Report all tasks and the uncertainty; a small trial
cannot establish statistical equivalence or a universal 20% benefit. If supported
provider billing is unavailable, do not substitute character counts as cost.

If two days of competitor evaluation show no plausible repeated advantage, stop
before building. If the candidate loses the held-out comparison, stop at the end
of the budget; do not extend it by adding languages or new feature queues.

## Business model and distribution

Proposed offer, to test rather than publish now:

| Plan | What people would receive | Price hypothesis |
| --- | --- | --- |
| Open-source local | Useful CLI/MCP retrieval and worktree isolation; no account required | Free |
| Team | Shared index operation, team configuration, bounded hosted usage or a managed customer-side worker, and support | Test around $99–$199/workspace/month after defining resource limits |
| Enterprise | Private deployment, repository permission synchronization, identity provisioning, access audit records, controlled upgrades and an agreed support scope | Test $12k–$30k/year once a buyer requires the actual package |

The first business target is a sustainable small developer-tool company. An
enterprise contract is a later expansion, with procurement, trust and support
costs; it cannot be made self-service merely by adding a pricing card.

For example, 100 workspaces paying $149/month would be $14,900 MRR before
infrastructure, support, acquisition, payment fees and taxes. This is arithmetic,
not a forecast. No customer count, retention or willingness to pay is established.
Resource caps, index reuse and customer-side execution can limit compute expense;
actual per-workspace CPU/storage and support costs must be measured before quoting
unlimited usage or a margin percentage. No model training or GPU fleet is planned.

Acquire users through a genuinely useful free tool, agent setup guides and public,
reproducible comparisons on real repositories. Initial messaging should name the
workflow: **correct code context for parallel coding agents**. Publish speed/cost
claims only after executing the comparison, with versions, workloads and limits.
Do not market it as a universal code-understanding engine, a cheaper equivalent to
all of Sourcegraph, or a business validated by GitHub stars.

After the technical result, offer an opt-in preview when the owner is ready. A
proposed early decision rule is ten outside developers successfully try it, five
return for another development task, and two teams agree to pay the stated price.
Track installation failures and non-returners. These are small-sample decision
rules, not market-size estimates. No outreach or publication is authorized by this
research. Codex can automate implementation, benchmarking and packaging; it cannot
manufacture independent return use or willingness to pay. Before that stage the
proper status is technical candidate, not validated SaaS.

## REA's bounded role

[REA's documentation](https://github.com/morluto/rea) describes local inspection of
JavaScript/Electron applications, native binaries, runtime evidence and saved
network captures. It can help investigate an authorized packaged client's indexing
or compatibility behavior when ordinary source and documentation are insufficient.
It has not been installed or run here.

REA does not reveal a hosted vendor's inaccessible search backend, prove retrieval
quality, provide its data or replace a benchmark. For open-source competitors,
reading their code and tests is the simpler first approach. Use licensed foundations
and our own tested implementation; do not make proprietary-product cloning the
business's advantage. Choose the product from the user's recurring job, then use
REA only if a specific investigation needs it.

## Immediate decision

Recommend one bounded competitive investigation of this workflow. Do not start
another application-profitability integration, general agent evaluator, API catalog
or enterprise control plane alongside it. Keep a written result at each stop point.
Only an observed workflow advantage earns the local product; only repeat use and
a paid commitment earn a commercial service.
