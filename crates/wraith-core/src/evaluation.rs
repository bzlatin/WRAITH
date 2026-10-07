use crate::{
    config::Scenario,
    model::{AgentRun, EvaluationResult, Evaluator},
};
use serde_json::{Value, json};

pub fn evaluate(scenario: &Scenario, run: &AgentRun) -> Vec<EvaluationResult> {
    let mut results = Vec::new();
    let response = run.response.as_ref();
    // Text checks intentionally target a string output or output.text, not JSON keys.
    let text = response.and_then(|r| {
        r.output
            .as_str()
            .or_else(|| r.output.get("text").and_then(Value::as_str))
    });
    let tools: Vec<_> = response
        .map(|r| r.tool_calls.iter().map(|t| t.name.as_str()).collect())
        .unwrap_or_default();
    let sources: Vec<_> = response
        .map(|r| {
            r.retrievals
                .iter()
                .filter_map(|r| r.source.as_deref())
                .collect()
        })
        .unwrap_or_default();
    let mut add = |evaluator, expected: Value, observed: Value, passed, message: String| {
        results.push(EvaluationResult {
            evaluator,
            expected,
            observed,
            passed: run.error.is_none() && passed,
            message,
        });
    };
    let e = &scenario.expect;
    for assertion in &e.json {
        let result = assertion.evaluate(response.map(|r| &r.output));
        add(
            Evaluator::JsonOutput,
            json!(assertion),
            result.observed,
            result.passed,
            result.message,
        );
    }
    for (kind, items, required) in [
        (Evaluator::OutputContains, &e.output_contains, true),
        (Evaluator::OutputNotContains, &e.output_not_contains, false),
    ] {
        for item in items {
            add(
                kind,
                json!(item),
                json!(text),
                text.is_some_and(|t| t.contains(item) == required),
                format!(
                    "output text must {}contain {item:?}",
                    if required { "" } else { "not " }
                ),
            );
        }
    }
    for (kind, items, required) in [
        (Evaluator::ToolsCalled, &e.tools_called, true),
        (Evaluator::ToolsNotCalled, &e.tools_not_called, false),
    ] {
        for item in items {
            add(
                kind,
                json!(item),
                json!(tools),
                tools.contains(&item.as_str()) == required,
                format!(
                    "tool {item:?} must {}be called",
                    if required { "" } else { "not " }
                ),
            );
        }
    }
    for source in &e.sources.include {
        add(
            Evaluator::SourceIncluded,
            json!(source),
            json!(sources),
            sources.contains(&source.as_str()),
            format!("retrieval sources must include {source:?}"),
        );
    }
    if let Some(limit) = &e.latency_ms {
        add(
            Evaluator::MaxLatency,
            json!(limit.max),
            json!(run.duration_ms),
            run.duration_ms <= limit.max,
            format!("wall-clock latency must be <= {}ms", limit.max),
        );
    }
    if let Some(limit) = &e.tokens {
        let tokens = response
            .and_then(|r| r.usage.as_ref())
            .and_then(|u| u.total());
        add(
            Evaluator::MaxTokens,
            json!(limit.max),
            json!(tokens),
            tokens.is_some_and(|n| n <= limit.max),
            format!(
                "total tokens must be <= {}; missing usage fails this expectation",
                limit.max
            ),
        );
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{AgentResponse, RunError, RunErrorKind};
    #[test]
    fn missing_text_and_usage_do_not_pass_negative_or_budget_checks() {
        let config = crate::config::parse("version: 1\nagent: {command: agent}\ntests:\n- id: s\n  input: hi\n  expect:\n    output_not_contains: [bad]\n    tokens: {max: 20}\n").unwrap();
        let mut run = AgentRun {
            scenario_id: "s".into(),
            input: json!("hi"),
            started_at_unix_ms: 0,
            completed_at_unix_ms: 0,
            duration_ms: 0,
            response: Some(AgentResponse {
                protocol_version: 1,
                scenario_id: "s".into(),
                output: json!({"answer": "ok"}),
                tool_calls: vec![],
                retrievals: vec![],
                usage: None,
                estimated_cost_usd: None,
                metadata: Default::default(),
            }),
            error: None,
        };
        assert!(evaluate(&config.tests[0], &run).iter().all(|e| !e.passed));
        run.response.as_mut().unwrap().output = json!("good");
        assert!(evaluate(&config.tests[0], &run)[0].passed);
        run.error = Some(RunError {
            kind: RunErrorKind::Timeout,
            message: "timeout".into(),
        });
        assert!(evaluate(&config.tests[0], &run).iter().all(|e| !e.passed));
    }
}
