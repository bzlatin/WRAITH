use crate::{
    config::{ComparisonOptions, Config, IncreaseThreshold},
    error::Error,
    model::{Evaluator, RunSnapshot, ScenarioResult},
    sampling::{Decision, SampleSummary, StatisticalResult, decide, groups, summarize},
    snapshot::validate,
};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ChangeKind {
    StructuredOutputRegression,
    PassToFail,
    FailToPass,
    ToolSelectionRegression,
    SourceRegression,
    OutputRegression,
    PolicyRegression,
    LatencyRegression,
    TokenRegression,
    CostRegression,
    SuccessRateRegression,
    ErrorRegression,
    ToolSelectionChanged,
    SourcesChanged,
    ToolArgumentsRegression,
    DocumentRegression,
    InstrumentationMissing,
    FailureRateRegression,
    OutputChanged,
    ObservedFailureRateChanged,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Info,
    Warning,
    Failure,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Change {
    pub scenario_id: String,
    pub classification: ChangeKind,
    pub severity: Severity,
    pub baseline: Value,
    pub candidate: Value,
    pub message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Metrics {
    pub success_rate: f64,
    pub mean_latency_ms: f64,
    pub mean_tokens: Option<f64>,
    pub mean_cost_usd: Option<f64>,
}

pub fn metrics(run: &RunSnapshot) -> Metrics {
    let count = run.scenarios.len() as f64;
    let mean_tokens = run.scenarios.iter().try_fold(0.0, |sum, s| {
        Some(sum + s.run.response.as_ref()?.usage.as_ref()?.total()? as f64 / count)
    });
    let mean_cost_usd = run.scenarios.iter().try_fold(0.0, |sum, s| {
        Some(sum + s.run.response.as_ref()?.estimated_cost_usd? / count)
    });
    Metrics {
        success_rate: run.scenarios.iter().filter(|s| s.passed).count() as f64 / count * 100.0,
        mean_latency_ms: run
            .scenarios
            .iter()
            .map(|s| s.run.duration_ms as f64 / count)
            .sum(),
        mean_tokens,
        mean_cost_usd,
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ThresholdResult {
    pub metric: String,
    pub baseline: Option<f64>,
    pub candidate: Option<f64>,
    pub allowed: f64,
    pub passed: bool,
    pub classification: Option<ChangeKind>,
    pub message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScenarioSampling {
    pub baseline: SampleSummary,
    pub candidate: SampleSummary,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ComparisonReport {
    pub schema_version: u32,
    pub policy_source: String,
    pub comparison: ComparisonOptions,
    pub samples_per_scenario: u32,
    pub sampling_note: String,
    pub scenario_sampling: Vec<ScenarioSampling>,
    pub statistical_results: Vec<StatisticalResult>,
    pub baseline_metrics: Metrics,
    pub candidate_metrics: Metrics,
    pub changes: Vec<Change>,
    pub thresholds: Vec<ThresholdResult>,
    pub passed: bool,
    pub execution_errors: bool,
    pub inconclusive: bool,
}

fn increase(
    metric: &str,
    baseline: Option<f64>,
    candidate: Option<f64>,
    threshold: &IncreaseThreshold,
) -> ThresholdResult {
    let allowed = threshold.max_increase_percent;
    let (passed, message) = match (baseline, candidate) {
        (Some(0.0), Some(c)) => (c == 0.0, if c == 0.0 { "Both values are zero.".into() } else { "Baseline is zero; a positive candidate exceeds any finite percentage allowance.".into() }),
        (Some(b), Some(c)) => {
            let percent = (c - b) / b * 100.0;
            (percent <= allowed, format!("Increase {percent:.2}%; allowed {allowed:.2}%"))
        }
        _ => (false, "Metric is missing from at least one scenario; a configured threshold cannot be verified.".into()),
    };
    ThresholdResult {
        metric: metric.into(),
        baseline,
        candidate,
        allowed,
        passed,
        classification: if !passed && baseline.is_some() && candidate.is_some() {
            match metric {
                "latency" => Some(ChangeKind::LatencyRegression),
                "tokens" => Some(ChangeKind::TokenRegression),
                "cost" => Some(ChangeKind::CostRegression),
                _ => None,
            }
        } else {
            None
        },
        message,
    }
}

pub fn compare(baseline: &RunSnapshot, candidate: &RunSnapshot) -> Result<ComparisonReport, Error> {
    compare_with_policy(baseline, candidate, None)
}

pub fn compare_with_policy(
    baseline: &RunSnapshot,
    candidate: &RunSnapshot,
    policy: Option<&Config>,
) -> Result<ComparisonReport, Error> {
    validate(baseline)?;
    validate(candidate)?;
    if baseline.samples_per_scenario != candidate.samples_per_scenario {
        return Err(Error::Comparison(
            "Sample counts differ. Rerun both versions with the same --samples value.".into(),
        ));
    }
    let b = groups(baseline);
    let c = groups(candidate);
    if !b.keys().eq(c.keys()) {
        return Err(Error::Comparison("Scenario IDs differ. Rerun both versions against the same suite (and the same --scenario filter).".into()));
    }
    if let Some(policy) = policy {
        let expected: BTreeMap<_, _> = policy.tests.iter().map(|s| (s.id.as_str(), s)).collect();
        if !b.keys().eq(expected.keys()) || b.iter().any(|(id, s)| s[0].scenario != *expected[id]) {
            return Err(Error::Comparison("Trusted policy scenarios do not match the complete saved suite. Rerun both versions against the trusted configuration.".into()));
        }
    }
    let comparison = policy
        .map(|p| &p.comparison)
        .unwrap_or(&candidate.comparison);
    comparison.validate()?;
    if let Some(policy) = policy {
        policy.thresholds.validate()?;
    }
    let mut changes = Vec::new();
    let mut scenario_sampling = Vec::new();
    let mut statistical_results = Vec::new();
    // All endpoints count, including unchanged/passing checks; never select only
    // adverse observations after seeing the data.
    let family_size = b.values().map(|s| 1 + s[0].evaluations.len()).sum();
    for (id, before) in &b {
        // Keys were validated identical above; each group is nonempty by construction.
        let after = &c[id];
        if before[0].scenario != after[0].scenario {
            return Err(Error::Comparison(format!(
                "Scenario {id:?} has changed input, metadata, or expectations. Rerun the baseline against this suite."
            )));
        }
        let (scenario_changes, summary) = compare_observations(
            id,
            before,
            after,
            comparison,
            family_size,
            &mut statistical_results,
        );
        changes.extend(scenario_changes);
        scenario_sampling.push(summary);
    }
    let baseline_metrics = metrics(baseline);
    let candidate_metrics = metrics(candidate);
    let mut thresholds = Vec::new();
    let t = policy
        .map(|p| &p.thresholds)
        .unwrap_or(&candidate.thresholds);
    if let Some(t) = &t.success_rate {
        let decline = baseline_metrics.success_rate - candidate_metrics.success_rate;
        thresholds.push(ThresholdResult {
            metric: "success_rate".into(),
            baseline: Some(baseline_metrics.success_rate),
            candidate: Some(candidate_metrics.success_rate),
            allowed: t.regression,
            passed: decline <= t.regression,
            classification: (decline > t.regression).then_some(ChangeKind::SuccessRateRegression),
            message: format!(
                "Decline {decline:.2} percentage points; allowed {:.2}",
                t.regression
            ),
        });
    }
    for (metric, before, after, limit) in [
        (
            "latency",
            Some(baseline_metrics.mean_latency_ms),
            Some(candidate_metrics.mean_latency_ms),
            &t.latency,
        ),
        (
            "tokens",
            baseline_metrics.mean_tokens,
            candidate_metrics.mean_tokens,
            &t.tokens,
        ),
        (
            "cost",
            baseline_metrics.mean_cost_usd,
            candidate_metrics.mean_cost_usd,
            &t.cost,
        ),
    ] {
        if let Some(limit) = limit {
            thresholds.push(increase(metric, before, after, limit));
        }
    }
    let execution_errors = candidate.scenarios.iter().any(|s| s.run.error.is_some());
    let failed = changes.iter().any(|c| c.severity == Severity::Failure)
        || thresholds.iter().any(|t| !t.passed);
    let inconclusive = !execution_errors
        && !failed
        && statistical_results
            .iter()
            .any(|s| s.decision == Decision::Inconclusive);
    let passed = !execution_errors
        && !inconclusive
        && changes.iter().all(|c| c.severity != Severity::Failure)
        && thresholds.iter().all(|t| t.passed);
    Ok(ComparisonReport {
        schema_version: 4,
        policy_source: if policy.is_some() { "trusted_config" } else { "candidate_snapshot" }.into(),
        comparison: comparison.clone(),
        samples_per_scenario: candidate.samples_per_scenario,
        sampling_note: if comparison.statistical.is_some() {
            "Statistical rate gate: simultaneous Hoeffding intervals with a union-bound correction across all scenario and expectation endpoints. Requires independent observations, stable distributions, and fixed sample sizes. Exact trace gates and suite thresholds remain strict."
        } else {
            "Independent observations; observed failure-rate changes gate strictly. Wilson 95% pass-rate intervals are descriptive under independent binomial sampling assumptions, not a significance test or proof of causality."
        }.into(),
        scenario_sampling,
        statistical_results,
        baseline_metrics,
        candidate_metrics,
        changes,
        thresholds,
        passed,
        execution_errors,
        inconclusive,
    })
}

fn compare_observations(
    id: &str,
    before: &[&ScenarioResult],
    after: &[&ScenarioResult],
    comparison: &ComparisonOptions,
    family_size: usize,
    statistical_results: &mut Vec<StatisticalResult>,
) -> (Vec<Change>, ScenarioSampling) {
    let mut changes = Vec::new();
    let bs = summarize(id, before);
    let cs = summarize(id, after);
    let mut rate_decision = |check: String, failures: (u32, u32)| {
        comparison.statistical.as_ref().map(|p| {
            let result = decide(id, check, failures, bs.count, family_size, p);
            let decision = result.decision;
            statistical_results.push(result);
            decision
        })
    };
    let overall_decision = rate_decision("scenario failure rate".into(), (bs.failed, cs.failed));
    let mut add = |classification, severity, baseline, candidate, message: String| {
        changes.push(Change {
            scenario_id: id.into(),
            classification,
            severity,
            baseline,
            candidate,
            message,
        });
    };
    if bs.passed != cs.passed {
        let regression = cs.passed < bs.passed;
        let gated_regression =
            regression && overall_decision.is_none_or(|d| d == Decision::Regression);
        let kind = if gated_regression {
            if bs.count == 1 {
                ChangeKind::PassToFail
            } else {
                ChangeKind::FailureRateRegression
            }
        } else if regression {
            ChangeKind::ObservedFailureRateChanged
        } else {
            ChangeKind::FailToPass
        };
        add(
            kind,
            if gated_regression {
                Severity::Failure
            } else {
                Severity::Info
            },
            json!(bs.passed),
            json!(cs.passed),
            format!(
                "Observed passes changed: {}/{} -> {}/{}. Samples are independent, not paired.",
                bs.passed, bs.count, cs.passed, cs.count
            ),
        );
    }
    if cs.execution_errors > bs.execution_errors {
        add(
            ChangeKind::ErrorRegression,
            Severity::Failure,
            json!(bs.execution_errors),
            json!(cs.execution_errors),
            "Candidate has more execution errors.".into(),
        );
    }
    for (index, expected) in before[0].evaluations.iter().enumerate() {
        let failed_before = before
            .iter()
            .filter(|s| !s.evaluations[index].passed)
            .count();
        let failed_after = after
            .iter()
            .filter(|s| !s.evaluations[index].passed)
            .count();
        let decision = rate_decision(
            format!("expectation {index}: {}", expected.message),
            (failed_before as u32, failed_after as u32),
        );
        if failed_after > failed_before {
            let kind = match expected.evaluator {
                Evaluator::JsonOutput => ChangeKind::StructuredOutputRegression,
                Evaluator::OutputContains | Evaluator::OutputNotContains => {
                    ChangeKind::OutputRegression
                }
                Evaluator::ToolsCalled => ChangeKind::ToolSelectionRegression,
                Evaluator::ToolsNotCalled => ChangeKind::PolicyRegression,
                Evaluator::SourceIncluded => ChangeKind::SourceRegression,
                Evaluator::MaxLatency => ChangeKind::LatencyRegression,
                Evaluator::MaxTokens => ChangeKind::TokenRegression,
            };
            let observations = |samples: &[&crate::model::ScenarioResult]| -> Value {
                if samples.len() == 1 {
                    samples[0].evaluations[index].observed.clone()
                } else {
                    json!({"failures": samples.iter().filter(|s| !s.evaluations[index].passed).count(), "samples": samples.len()})
                }
            };
            let gated = decision.is_none_or(|d| d == Decision::Regression);
            add(
                if gated {
                    kind
                } else {
                    ChangeKind::ObservedFailureRateChanged
                },
                if gated {
                    Severity::Failure
                } else {
                    Severity::Info
                },
                observations(before),
                observations(after),
                after
                    .iter()
                    .find(|s| !s.evaluations[index].passed)
                    .map(|s| s.evaluations[index].message.clone())
                    .unwrap_or_else(|| expected.message.clone()),
            );
        }
    }
    if bs.execution_errors == 0 && cs.execution_errors == 0 {
        changes.extend(behavior_changes(id, before, after, comparison));
    }
    (
        changes,
        ScenarioSampling {
            baseline: bs,
            candidate: cs,
        },
    )
}

fn behavior_changes(
    id: &str,
    before: &[&ScenarioResult],
    after: &[&ScenarioResult],
    comparison: &ComparisonOptions,
) -> Vec<Change> {
    let mut changes = Vec::new();
    let mut add = |classification, severity, baseline, candidate, message: String| {
        changes.push(Change {
            scenario_id: id.into(),
            classification,
            severity,
            baseline,
            candidate,
            message,
        });
    };
    let tools = |samples: &[&crate::model::ScenarioResult]| -> BTreeSet<String> {
        samples
            .iter()
            .filter_map(|s| s.run.response.as_ref())
            .flat_map(|r| r.tool_calls.iter().map(|t| t.name.clone()))
            .collect()
    };
    let sources = |samples: &[&crate::model::ScenarioResult]| -> BTreeSet<String> {
        samples
            .iter()
            .filter_map(|s| s.run.response.as_ref())
            .flat_map(|r| r.retrievals.iter().filter_map(|r| r.source.clone()))
            .collect()
    };
    let bt = tools(before);
    let ct = tools(after);
    if bt != ct {
        add(
            ChangeKind::ToolSelectionChanged,
            Severity::Warning,
            json!(bt),
            json!(ct),
            "Observed tool names changed; configured expectations determine the gate.".into(),
        );
    }
    let bsources = sources(before);
    let csources = sources(after);
    if bsources != csources {
        add(
            ChangeKind::SourcesChanged,
            Severity::Warning,
            json!(bsources),
            json!(csources),
            "Observed retrieval sources changed; configured expectations determine the gate."
                .into(),
        );
    }
    let outputs = |samples: &[&ScenarioResult]| {
        sorted_json(
            samples
                .iter()
                .filter_map(|s| s.run.response.as_ref())
                .map(|r| r.output.clone()),
        )
    };
    let before_outputs = outputs(before);
    let after_outputs = outputs(after);
    if before_outputs != after_outputs {
        add(
            ChangeKind::OutputChanged,
            Severity::Info,
            json!(before_outputs),
            json!(after_outputs),
            "Output observations changed; expectations determine the gate.".into(),
        );
    }
    for (enabled, kind, label, projection) in [
        (
            comparison.tool_arguments,
            ChangeKind::ToolArgumentsRegression,
            "tool arguments",
            Projection::Arguments,
        ),
        (
            comparison.document_ids,
            ChangeKind::DocumentRegression,
            "retrieval document identities",
            Projection::Documents,
        ),
    ] {
        if !enabled {
            continue;
        }
        let bv = project(before, projection);
        let cv = project(after, projection);
        match (bv, cv) {
            (Some(bv), Some(cv)) if bv != cv => add(
                kind,
                Severity::Failure,
                json!(bv),
                json!(cv),
                format!(
                    "Opt-in exact comparison of {label} changed. For samples this compares observed trace multiplicities, not statistical significance."
                ),
            ),
            (bv, cv) if bv.is_none() || cv.is_none() => add(
                ChangeKind::InstrumentationMissing,
                Severity::Failure,
                json!(bv),
                json!(cv),
                format!(
                    "Cannot verify {label}: at least one reported call/retrieval omits its required instrumentation."
                ),
            ),
            _ => {}
        }
    }
    changes
}

#[derive(Clone, Copy)]
enum Projection {
    Arguments,
    Documents,
}

// Compare per-invocation multisets (then the multiset of invocations). This preserves
// multiplicity and sample boundaries but ignores sample/call order and JSON key order.
fn project(
    samples: &[&crate::model::ScenarioResult],
    projection: Projection,
) -> Option<Vec<Value>> {
    let mut observations = Vec::new();
    for sample in samples {
        let response = sample.run.response.as_ref()?;
        let mut trace = Vec::new();
        match projection {
            Projection::Arguments => {
                for tool in &response.tool_calls {
                    let arguments = tool.arguments.as_ref().filter(|v| !v.is_null())?;
                    trace.push(json!({"name": tool.name, "arguments": arguments}));
                }
            }
            Projection::Documents => {
                for retrieval in &response.retrievals {
                    let id = retrieval
                        .document_id
                        .as_ref()
                        .filter(|id| !id.trim().is_empty())?;
                    trace.push(json!({"source": retrieval.source, "documentId": id}));
                }
            }
        }
        observations.push(json!(sorted_json(trace.into_iter())));
    }
    Some(sorted_json(observations.into_iter()))
}

fn sorted_json(values: impl Iterator<Item = Value>) -> Vec<Value> {
    let mut keyed: Vec<_> = values.map(|value| (value.to_string(), value)).collect();
    keyed.sort_by(|a, b| a.0.cmp(&b.0));
    keyed.into_iter().map(|(_, value)| value).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn threshold_boundaries_zero_and_missing_values_are_explicit() {
        let t = IncreaseThreshold {
            max_increase_percent: 25.0,
        };
        assert!(increase("tokens", Some(100.0), Some(125.0), &t).passed);
        assert!(!increase("tokens", Some(100.0), Some(126.0), &t).passed);
        assert!(increase("tokens", Some(0.0), Some(0.0), &t).passed);
        assert!(!increase("tokens", Some(0.0), Some(1.0), &t).passed);
        assert!(!increase("tokens", None, Some(1.0), &t).passed);
    }
}
