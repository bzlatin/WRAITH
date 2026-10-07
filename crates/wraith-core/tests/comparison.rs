use serde_json::json;
use wraith_core::{
    comparison::{ChangeKind, Severity, compare},
    config,
    evaluation::evaluate,
    model::*,
};

fn snapshot(tool: &str, source: &str, text: &str, required: bool) -> RunSnapshot {
    let expectations = if required {
        "\n  expect:\n    tools_called: [search_documents]\n    tools_not_called: [delete_document]\n    sources: {include: [employee_handbook]}\n    output_contains: ['20']\n    output_not_contains: [hallucination]\n    latency_ms: {max: 100}\n    tokens: {max: 400}"
    } else {
        ""
    };
    let config = config::parse(&format!(
        "version: 1\nagent: {{command: agent}}\ntests:\n- id: pto\n  input: hi{expectations}\n"
    ))
    .unwrap();
    let run = AgentRun {
        scenario_id: "pto".into(),
        input: json!("hi"),
        started_at_unix_ms: 1,
        completed_at_unix_ms: 51,
        duration_ms: 50,
        response: Some(AgentResponse {
            protocol_version: 1,
            scenario_id: "pto".into(),
            output: json!({"text":text}),
            tool_calls: vec![ToolCall {
                name: tool.into(),
                arguments: None,
                result: None,
                duration_ms: None,
                success: Some(true),
            }],
            retrievals: vec![Retrieval {
                source: Some(source.into()),
                document_id: None,
                chunk_id: None,
                score: None,
                metadata: Default::default(),
            }],
            usage: Some(TokenUsage {
                input_tokens: 200,
                output_tokens: 58,
            }),
            estimated_cost_usd: Some(0.001),
            metadata: Default::default(),
        }),
        error: None,
    };
    let evaluations = evaluate(&config.tests[0], &run);
    let passed = evaluations.iter().all(|e| e.passed);
    RunSnapshot {
        schema_version: SCHEMA_VERSION,
        samples_per_scenario: 1,
        comparison: Default::default(),
        wraith_version: "0.1.0".into(),
        created_at_unix_ms: 1,
        thresholds: Default::default(),
        scenarios: vec![ScenarioResult {
            sample_index: 1,
            scenario: config.tests[0].clone(),
            run,
            evaluations,
            passed,
        }],
    }
}

#[test]
fn classifications_improvements_and_non_gating_differences() {
    let b = snapshot("search_documents", "employee_handbook", "20 days", true);
    let c = snapshot("web_search", "unknown", "hallucination", true);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    for kind in [
        ChangeKind::PassToFail,
        ChangeKind::ToolSelectionRegression,
        ChangeKind::SourceRegression,
        ChangeKind::OutputRegression,
    ] {
        assert!(
            report
                .changes
                .iter()
                .any(|c| c.classification == kind && c.severity == Severity::Failure)
        );
    }
    assert!(compare(&c, &b).unwrap().passed);
    assert!(
        compare(&c, &b)
            .unwrap()
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::FailToPass)
    );
    let b = snapshot("search_documents", "employee_handbook", "20 days", false);
    let c = snapshot("web_search", "unknown", "21 days", false);
    let report = compare(&b, &c).unwrap();
    assert!(report.passed);
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::ToolSelectionChanged)
    );
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::SourcesChanged)
    );
}

#[test]
fn policy_and_budget_expectations_and_aggregate_thresholds() {
    let b = snapshot("search_documents", "employee_handbook", "20 days", true);
    let mut c = snapshot("delete_document", "employee_handbook", "20 days", true);
    c.scenarios[0].run.duration_ms = 200;
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .usage
        .as_mut()
        .unwrap()
        .input_tokens = 500;
    c.scenarios[0].evaluations = evaluate(&c.scenarios[0].scenario, &c.scenarios[0].run);
    let report = compare(&b, &c).unwrap();
    for kind in [
        ChangeKind::PolicyRegression,
        ChangeKind::LatencyRegression,
        ChangeKind::TokenRegression,
    ] {
        assert!(report.changes.iter().any(|c| c.classification == kind));
    }
    let mut c = b.clone();
    c.thresholds = config::Thresholds {
        latency: Some(config::IncreaseThreshold {
            max_increase_percent: 25.0,
        }),
        tokens: Some(config::IncreaseThreshold {
            max_increase_percent: 30.0,
        }),
        cost: Some(config::IncreaseThreshold {
            max_increase_percent: 20.0,
        }),
        ..Default::default()
    };
    assert!(compare(&b, &c).unwrap().passed);
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .estimated_cost_usd = Some(0.002);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    assert!(
        report
            .thresholds
            .iter()
            .any(|t| t.metric == "cost" && !t.passed)
    );
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .estimated_cost_usd = None;
    assert!(
        compare(&b, &c)
            .unwrap()
            .thresholds
            .iter()
            .any(|t| !t.passed && t.message.contains("missing"))
    );
}

#[test]
fn rejects_incompatible_suites_and_flags_new_errors() {
    let b = snapshot("search_documents", "employee_handbook", "20 days", true);
    let changed = snapshot("search_documents", "employee_handbook", "20 days", false);
    assert!(
        compare(&b, &changed)
            .unwrap_err()
            .to_string()
            .contains("expectations")
    );
    let mut c = b.clone();
    c.scenarios[0].run.response = None;
    c.scenarios[0].run.error = Some(RunError {
        kind: RunErrorKind::Timeout,
        message: "timeout".into(),
    });
    c.scenarios[0].passed = false;
    c.scenarios[0].evaluations = evaluate(&c.scenarios[0].scenario, &c.scenarios[0].run);
    let report = compare(&b, &c).unwrap();
    assert!(report.execution_errors);
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::ErrorRegression)
    );
    let mut c = b.clone();
    c.scenarios[0].scenario.id = "other".into();
    c.scenarios[0].run.scenario_id = "other".into();
    c.scenarios[0].run.response.as_mut().unwrap().scenario_id = "other".into();
    assert!(
        compare(&b, &c)
            .unwrap_err()
            .to_string()
            .contains("Scenario IDs differ")
    );
}

fn rescore(run: &mut RunSnapshot) {
    for s in &mut run.scenarios {
        s.evaluations = evaluate(&s.scenario, &s.run);
        s.passed = s.run.error.is_none() && s.evaluations.iter().all(|e| e.passed);
    }
}

fn sampled(passes: &[bool]) -> RunSnapshot {
    let mut run = snapshot("search_documents", "employee_handbook", "20 days", true);
    let original = run.scenarios[0].clone();
    run.samples_per_scenario = passes.len() as u32;
    run.scenarios = passes
        .iter()
        .enumerate()
        .map(|(i, passed)| {
            let mut result = original.clone();
            result.sample_index = i as u32 + 1;
            if !passed {
                result.run.response.as_mut().unwrap().tool_calls[0].name = "web_search".into();
            }
            result
        })
        .collect();
    rescore(&mut run);
    run
}

#[test]
fn independent_samples_compare_counts_not_arbitrary_pairs() {
    let b = sampled(&[true, false, true, false]);
    let c = sampled(&[false, true, false, true]);
    let report = compare(&b, &c).unwrap();
    assert!(report.passed);
    assert_eq!(report.scenario_sampling[0].baseline.passed, 2);
    assert_eq!(report.scenario_sampling[0].candidate.passed, 2);
    assert!(report.changes.is_empty());
    let b = sampled(&[true, true, true, false]);
    let c = sampled(&[true, false, false, false]);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::FailureRateRegression)
    );
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::ToolSelectionRegression)
    );
    assert!(
        compare(&b, &sampled(&[true]))
            .unwrap_err()
            .to_string()
            .contains("Sample counts differ")
    );
}

#[test]
fn exact_argument_and_document_checks_are_opt_in_and_require_instrumentation() {
    let mut b = snapshot("search_documents", "employee_handbook", "20 days", true);
    let response = b.scenarios[0].run.response.as_mut().unwrap();
    response.tool_calls[0].arguments = Some(json!({"query":"PTO", "limit":5}));
    response.retrievals[0].document_id = Some("policy-v1".into());
    rescore(&mut b);
    let mut c = b.clone();
    c.scenarios[0].run.response.as_mut().unwrap().tool_calls[0].arguments =
        Some(json!({"limit":5, "query":"PTO"}));
    c.comparison.tool_arguments = true;
    c.comparison.document_ids = true;
    assert!(compare(&b, &c).unwrap().passed);
    c.scenarios[0].run.response.as_mut().unwrap().tool_calls[0].arguments =
        Some(json!({"query":"salary"}));
    c.scenarios[0].run.response.as_mut().unwrap().retrievals[0].document_id =
        Some("wrong-policy".into());
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::ToolArgumentsRegression)
    );
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::DocumentRegression)
    );
    c.comparison = Default::default();
    assert!(compare(&b, &c).unwrap().passed);
    c.comparison.tool_arguments = true;
    c.scenarios[0].run.response.as_mut().unwrap().tool_calls[0].arguments = None;
    assert!(
        compare(&b, &c)
            .unwrap()
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::InstrumentationMissing)
    );
}

#[test]
fn trace_comparison_ignores_order_but_preserves_multiplicity() {
    let mut b = snapshot("search_documents", "employee_handbook", "20 days", false);
    let response = b.scenarios[0].run.response.as_mut().unwrap();
    response.tool_calls[0].arguments = Some(json!({"query":"PTO"}));
    let mut second = response.tool_calls[0].clone();
    second.arguments = Some(json!({"query":"benefits"}));
    response.tool_calls.push(second);
    let mut c = b.clone();
    c.comparison.tool_arguments = true;
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .tool_calls
        .reverse();
    assert!(compare(&b, &c).unwrap().passed);
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .tool_calls
        .pop();
    assert!(!compare(&b, &c).unwrap().passed);
}

#[test]
fn trusted_policy_prevents_threshold_relaxation_and_removed_scenarios() {
    let b = snapshot("search_documents", "employee_handbook", "20 days", false);
    let mut c = b.clone();
    c.scenarios[0].run.duration_ms = 500;
    let mut policy = config::parse("version: 1\nagent: {command: agent}\ntests:\n- id: pto\n  input: hi\nthresholds:\n  latency: {max_increase_percent: 25}\n").unwrap();
    assert!(compare(&b, &c).unwrap().passed);
    assert!(
        !wraith_core::comparison::compare_with_policy(&b, &c, Some(&policy))
            .unwrap()
            .passed
    );
    policy.tests.push(config::Scenario {
        id: "missing".into(),
        input: json!("hi"),
        metadata: Default::default(),
        expect: Default::default(),
    });
    assert!(wraith_core::comparison::compare_with_policy(&b, &c, Some(&policy)).is_err());
}

#[test]
fn sample_validation_and_schema_one_migration() {
    let run = sampled(&[true, true]);
    let mut duplicate = run.clone();
    duplicate.scenarios[1].sample_index = 1;
    assert!(wraith_core::snapshot::validate(&duplicate).is_err());
    let mut incomplete = run;
    incomplete.scenarios.pop();
    assert!(wraith_core::snapshot::validate(&incomplete).is_err());
    let original = sampled(&[true]);
    let mut legacy = serde_json::to_value(&original).unwrap();
    legacy["schemaVersion"] = json!(1);
    legacy.as_object_mut().unwrap().remove("samplesPerScenario");
    legacy.as_object_mut().unwrap().remove("comparison");
    legacy["scenarios"][0]
        .as_object_mut()
        .unwrap()
        .remove("sampleIndex");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("legacy.json");
    std::fs::write(&path, serde_json::to_vec(&legacy).unwrap()).unwrap();
    let loaded = wraith_core::snapshot::load(&path).unwrap();
    assert_eq!(loaded.schema_version, 4);
    assert!(compare(&loaded, &original).unwrap().passed);
    legacy["scenarios"][0] = json!("invalid");
    std::fs::write(&path, serde_json::to_vec(&legacy).unwrap()).unwrap();
    assert!(wraith_core::snapshot::load(&path).is_err());
}

fn statistical(run: &mut RunSnapshot, min_samples: u32, allowance: f64) {
    run.comparison.statistical = Some(config::StatisticalPolicy {
        min_samples,
        max_failure_rate_increase_pp: allowance,
        alpha: 0.05,
    });
}

#[test]
fn statistical_gates_distinguish_tolerated_regressions_and_uncertainty() {
    let b = sampled(&[true; 1000]);
    let mut c = sampled(&(0..1000).map(|i| i >= 100).collect::<Vec<_>>());
    statistical(&mut c, 100, 20.0);
    let report = compare(&b, &c).unwrap();
    assert!(report.passed); // 10pp observed decline lies wholly within 20pp allowance.
    assert!(!report.inconclusive);
    assert_eq!(report.statistical_results.len(), 8);
    assert!(
        report
            .statistical_results
            .iter()
            .all(|r| r.family_size == 8)
    );
    assert!(
        !report
            .changes
            .iter()
            .any(|c| c.severity == Severity::Failure)
    );

    let mut c = sampled(&[false; 1000]);
    statistical(&mut c, 100, 20.0);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    assert!(!report.inconclusive);
    assert!(
        report
            .changes
            .iter()
            .any(|c| c.classification == ChangeKind::ToolSelectionRegression)
    );

    let b = sampled(&[true; 20]);
    let mut c = b.clone();
    statistical(&mut c, 30, 20.0);
    let report = compare(&b, &c).unwrap();
    assert!(report.inconclusive);
    assert!(!report.passed);
    assert!(
        report
            .statistical_results
            .iter()
            .all(|r| r.message.contains("at least 30"))
    );
    statistical(&mut c, 20, 0.0);
    assert!(compare(&b, &c).unwrap().inconclusive); // No difference isn't proof of no harm.
}

#[test]
fn statistical_policy_cannot_relax_errors_exact_checks_or_explicit_thresholds() {
    let b = sampled(&[true; 10]);
    let mut c = b.clone();
    statistical(&mut c, 20, 20.0);
    c.scenarios[0].run.response = None;
    c.scenarios[0].run.error = Some(RunError {
        kind: RunErrorKind::Timeout,
        message: "timeout".into(),
    });
    rescore(&mut c);
    let report = compare(&b, &c).unwrap();
    assert!(report.execution_errors);
    assert!(!report.passed && !report.inconclusive);

    let mut c = b.clone();
    statistical(&mut c, 20, 20.0);
    c.comparison.tool_arguments = true;
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed && !report.inconclusive); // Missing instrumentation remains failure.

    c.comparison.tool_arguments = false;
    c.thresholds.tokens = Some(config::IncreaseThreshold {
        max_increase_percent: 0.0,
    });
    c.scenarios[0]
        .run
        .response
        .as_mut()
        .unwrap()
        .usage
        .as_mut()
        .unwrap()
        .input_tokens += 1;
    rescore(&mut c);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed && !report.inconclusive);
}

#[test]
fn trusted_policy_overrides_statistical_relaxation_and_schema_two_stays_strict() {
    let b = sampled(&[true; 1000]);
    let mut c = sampled(&(0..1000).map(|i| i >= 100).collect::<Vec<_>>());
    statistical(&mut c, 100, 20.0);
    let mut policy = config::parse(
        "version: 1\nagent: {command: agent}\ntests:\n- id: placeholder\n  input: hi\n",
    )
    .unwrap();
    policy.tests = vec![b.scenarios[0].scenario.clone()];
    assert!(compare(&b, &c).unwrap().passed);
    assert!(
        !wraith_core::comparison::compare_with_policy(&b, &c, Some(&policy))
            .unwrap()
            .passed
    );
    let mut legacy = serde_json::to_value(&b).unwrap();
    legacy["schemaVersion"] = json!(2);
    legacy["comparison"]
        .as_object_mut()
        .unwrap()
        .remove("statistical");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("schema-two.json");
    let bytes = serde_json::to_vec(&legacy).unwrap();
    std::fs::write(&path, &bytes).unwrap();
    let loaded = wraith_core::snapshot::load(&path).unwrap();
    assert_eq!(loaded.schema_version, 4);
    assert!(loaded.comparison.statistical.is_none());
    assert_eq!(bytes, std::fs::read(path).unwrap());
    policy.comparison.statistical = Some(config::StatisticalPolicy {
        min_samples: 1,
        alpha: 0.05,
        max_failure_rate_increase_pp: 20.0,
    });
    assert!(wraith_core::comparison::compare_with_policy(&b, &c, Some(&policy)).is_err());
}

#[test]
fn structured_output_regressions_keep_evidence_and_join_statistical_family() {
    let mut b = snapshot("search_documents", "employee_handbook", "20 days", false);
    b.scenarios[0].scenario.expect.json = vec![serde_json::from_value(json!({
        "path":"/exercises", "each":"/sets", "check":{"op":"range","min":3,"max":3,"integer":true}
    })).unwrap()];
    b.scenarios[0].run.response.as_mut().unwrap().output = json!({"exercises":[{"sets":3}]});
    rescore(&mut b);
    let mut c = b.clone();
    c.scenarios[0].run.response.as_mut().unwrap().output = json!({"exercises":[{"sets":5}]});
    rescore(&mut c);
    let report = compare(&b, &c).unwrap();
    assert!(!report.passed);
    let change = report
        .changes
        .iter()
        .find(|c| c.classification == ChangeKind::StructuredOutputRegression)
        .unwrap();
    assert!(change.message.contains("/exercises/0/sets"));
    assert_eq!(change.candidate[0]["value"], 5);
    statistical(&mut c, 20, 10.0);
    let report = compare(&b, &c).unwrap();
    assert!(report.inconclusive);
    assert_eq!(report.statistical_results.len(), 2);
    assert_eq!(report.statistical_results[0].family_size, 2);
}

#[test]
fn schema_three_migrates_without_rewriting_or_losing_statistical_policy() {
    let mut run = sampled(&[true, true]);
    statistical(&mut run, 20, 10.0);
    let mut legacy = serde_json::to_value(&run).unwrap();
    legacy["schemaVersion"] = json!(3);
    for scenario in legacy["scenarios"].as_array_mut().unwrap() {
        scenario["scenario"]["expect"]
            .as_object_mut()
            .unwrap()
            .remove("json");
    }
    let bytes = serde_json::to_vec(&legacy).unwrap();
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("schema-three.json");
    std::fs::write(&path, &bytes).unwrap();
    let loaded = wraith_core::snapshot::load(&path).unwrap();
    assert_eq!(loaded.schema_version, 4);
    assert!(loaded.comparison.statistical.is_some());
    assert_eq!(std::fs::read(&path).unwrap(), bytes);
    assert!(compare(&loaded, &loaded).unwrap().inconclusive);
}
