use wraith_core::{
    comparison::{ComparisonReport, Metrics, metrics},
    model::RunSnapshot,
    sampling::summaries,
};

pub fn run(snapshot: &RunSnapshot) {
    println!(
        "WRAITH\n\nRunning {} scenarios...",
        snapshot.scenarios.len()
    );
    if snapshot.samples_per_scenario > 1 {
        println!(
            "{} independent samples per scenario",
            snapshot.samples_per_scenario
        );
    }
    for result in &snapshot.scenarios {
        println!(
            "{}  {}",
            if result.passed {
                "PASS"
            } else if result.run.error.is_some() {
                "ERROR"
            } else {
                "FAIL"
            },
            if snapshot.samples_per_scenario > 1 {
                format!("{} [sample {}]", result.scenario.id, result.sample_index)
            } else {
                result.scenario.id.clone()
            }
        );
        if let Some(error) = &result.run.error {
            println!("  {}", error.message.replace('\n', "\n  "));
        }
        for evaluation in result.evaluations.iter().filter(|e| !e.passed) {
            println!(
                "  {}\n  Observed: {}",
                evaluation.message, evaluation.observed
            );
        }
    }
    if snapshot.samples_per_scenario > 1 {
        for summary in summaries(snapshot) {
            println!(
                "{}: {}/{} pass ({:.1}%); descriptive Wilson 95% interval {:.1}–{:.1}%",
                summary.scenario_id,
                summary.passed,
                summary.count,
                summary.pass_rate_percent,
                summary.pass_interval_95.lower_percent,
                summary.pass_interval_95.upper_percent
            );
        }
        println!("Sample rates are observations, not a significance test.");
    }
    let passed = snapshot.scenarios.iter().filter(|s| s.passed).count();
    let m = metrics(snapshot);
    println!(
        "\n{passed} passed; {} failed\nMean latency: {:.1}ms\nTokens/task: {}\nEstimated cost/task: {}",
        snapshot.scenarios.len() - passed,
        m.mean_latency_ms,
        number(m.mean_tokens),
        number(m.mean_cost_usd)
    );
}

fn number(value: Option<f64>) -> String {
    value
        .map(|v| format!("{v:.4}"))
        .unwrap_or_else(|| "unavailable".into())
}

fn metric_rows(b: &Metrics, c: &Metrics) {
    println!(
        "{:<22} {:>16} {:>16} {:>14}",
        "METRIC", "BASELINE", "CANDIDATE", "DELTA"
    );
    for (name, before, after, points) in [
        (
            "Success rate (%)",
            Some(b.success_rate),
            Some(c.success_rate),
            true,
        ),
        (
            "Mean latency (ms)",
            Some(b.mean_latency_ms),
            Some(c.mean_latency_ms),
            false,
        ),
        ("Tokens/task", b.mean_tokens, c.mean_tokens, false),
        ("Cost/task (USD)", b.mean_cost_usd, c.mean_cost_usd, false),
    ] {
        let delta = match (before, after) {
            (Some(b), Some(c)) if points => format!("{:+.2} pp", c - b),
            (Some(0.0), Some(0.0)) => "0.00%".into(),
            (Some(0.0), Some(_)) => "from zero".into(),
            (Some(b), Some(c)) => format!("{:+.2}%", (c - b) / b * 100.0),
            _ => "unavailable".into(),
        };
        println!(
            "{name:<22} {:>16} {:>16} {delta:>14}",
            number(before),
            number(after)
        );
    }
}

pub fn comparison(baseline: &str, candidate: &str, report: &ComparisonReport) {
    println!("WRAITH\n\nComparing {baseline} -> {candidate}\n");
    if report.samples_per_scenario > 1 {
        println!(
            "{} samples per scenario. {}\n",
            report.samples_per_scenario, report.sampling_note
        );
        for stats in &report.scenario_sampling {
            println!(
                "{}: baseline {}/{} pass; candidate {}/{} pass\n  Wilson 95% pass intervals: {:.1}–{:.1}% -> {:.1}–{:.1}%",
                stats.baseline.scenario_id,
                stats.baseline.passed,
                stats.baseline.count,
                stats.candidate.passed,
                stats.candidate.count,
                stats.baseline.pass_interval_95.lower_percent,
                stats.baseline.pass_interval_95.upper_percent,
                stats.candidate.pass_interval_95.lower_percent,
                stats.candidate.pass_interval_95.upper_percent
            );
        }
    }
    metric_rows(&report.baseline_metrics, &report.candidate_metrics);
    for result in &report.statistical_results {
        println!(
            "\n{} / {} [{:?}]\n  Failure rate increase: {:+.2} pp; simultaneous interval [{:+.2}, {:+.2}] pp; allowed {:.2} pp\n  {}",
            result.scenario_id,
            result.check,
            result.decision,
            result.observed_increase_pp,
            result.lower_increase_pp,
            result.upper_increase_pp,
            result.allowed_increase_pp,
            result.message
        );
    }
    for change in &report.changes {
        let class = serde_json::to_value(change.classification)
            .ok()
            .and_then(|v| v.as_str().map(str::to_owned))
            .unwrap_or_else(|| "CHANGE".into());
        println!(
            "\n{}: {class}\n  Baseline: {}\n  Candidate: {}\n  {}",
            change.scenario_id, change.baseline, change.candidate, change.message
        );
    }
    for threshold in &report.thresholds {
        println!(
            "\n{} threshold [{}]: {}",
            threshold.metric,
            if threshold.passed { "PASS" } else { "FAIL" },
            threshold.message
        );
    }
    println!(
        "\nRESULT: {}",
        if report.passed {
            "PASSED"
        } else if report.execution_errors {
            "ERROR"
        } else if report.inconclusive {
            "INCONCLUSIVE — MORE EVIDENCE REQUIRED (exit 3)"
        } else {
            "FAILED — REGRESSION DETECTED"
        }
    );
}
