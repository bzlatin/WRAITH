use crate::workflow::Record;
use serde_json::Value;
use std::{fs, path::Path};
use wraith_core::{
    comparison::{ComparisonReport, metrics},
    error::{self, Error},
    model::RunSnapshot,
};

pub fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn pretty(value: &impl serde::Serialize) -> String {
    escape(&serde_json::to_string_pretty(value).unwrap_or_else(|_| "unavailable".into()))
}
fn shell(title: &str, body: &str) -> String {
    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\"><title>{}</title><style>{}</style></head><body><main>{body}</main></body></html>",
        escape(title),
        include_str!("report.css")
    )
}
fn write(path: &Path, contents: &str) -> Result<(), Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| error::io("create report directory", parent, e))?;
    }
    fs::write(path, contents).map_err(|e| error::io("write report", path, e))
}
fn timestamp(milliseconds: u64) -> String {
    let seconds = milliseconds / 1000;
    let mut days = seconds / 86400;
    if days > 2_932_896 {
        return format!("{milliseconds} Unix ms");
    }
    let mut year = 1970u64;
    let leap = |year: u64| {
        year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400))
    };
    loop {
        let length = if leap(year) { 366 } else { 365 };
        if days < length {
            break;
        }
        days -= length;
        year += 1;
    }
    let lengths = [
        31,
        if leap(year) { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    let mut month = 0usize;
    while days >= lengths[month] {
        days -= lengths[month];
        month += 1;
    }
    format!(
        "{year:04}-{:02}-{:02} {:02}:{:02}:{:02} UTC",
        month + 1,
        days + 1,
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60
    )
}

fn number(value: Option<f64>) -> String {
    value
        .map(|n| format!("{n:.2}"))
        .unwrap_or_else(|| "unavailable".into())
}
fn evidence(before: &impl serde::Serialize, after: &impl serde::Serialize) -> String {
    format!(
        "<div class=\"evidence\"><div><h4>Baseline</h4><pre>{}</pre></div><div><h4>Candidate</h4><pre>{}</pre></div></div>",
        pretty(before),
        pretty(after)
    )
}

pub fn save(
    path: &Path,
    run: &RunSnapshot,
    baseline: Option<&RunSnapshot>,
    comparison: Option<&ComparisonReport>,
    record: Option<&Record>,
) -> Result<(), Error> {
    let value = comparison
        .map(serde_json::to_value)
        .transpose()
        .map_err(|e| Error::Artifact(e.to_string()))?;
    save_value(path, run, baseline, value.as_ref(), record)
}

pub fn save_value(
    path: &Path,
    run: &RunSnapshot,
    baseline: Option<&RunSnapshot>,
    comparison: Option<&Value>,
    record: Option<&Record>,
) -> Result<(), Error> {
    let state = record.map(|r| r.outcome.as_str()).unwrap_or_else(|| {
        if run.scenarios.iter().any(|s| s.run.error.is_some()) {
            "error"
        } else if comparison.is_some_and(|v| v["inconclusive"] == true) {
            "inconclusive"
        } else if comparison
            .map(|v| v["passed"] == false)
            .unwrap_or_else(|| run.scenarios.iter().any(|s| !s.passed))
        {
            "failed"
        } else {
            "passed"
        }
    });
    let message = match state {
        "passed" if comparison.is_some() => "No new configured regressions detected.",
        "passed" => "Configured baseline checks passed.",
        "inconclusive" => "More evidence is needed before this change can pass.",
        "error" => "Execution or instrumentation failed. Fix the setup before judging behavior.",
        _ => "Configured checks failed. Review the evidence below.",
    };
    let mut body = format!(
        "<header><h1>Wraith evaluation</h1><p class=\"status {}\">{message}</p><p class=\"muted\">{} scenarios · {} observations per scenario</p>",
        if state == "failed" { "failure" } else { state },
        wraith_core::sampling::groups(run).len(),
        run.samples_per_scenario
    );
    if let Some(r) = record {
        body.push_str(&format!("<p class=\"meta\">Run <code>{}</code> · {} · {} · model {}</p><p class=\"meta muted\">Commit {}{} · captured {}</p>",escape(&r.id),escape(&r.kind),escape(&r.mode),escape(r.model.as_deref().unwrap_or("not declared")),escape(r.git_commit.as_deref().unwrap_or("unavailable")),if r.git_dirty{" (working tree changes)"}else{""},timestamp(r.created_at_unix_ms)));
    }
    if record.is_some() {
        body.push_str("<nav><a href=\"../../index.html\">Run history</a></nav>");
    }
    body.push_str("</header><div class=\"scope\"><p>These checks cover the configured scenarios and expectations. Passing does not establish overall answer quality or safety.</p>");
    if run.samples_per_scenario == 1 {
        body.push_str("<p class=\"muted\">One observation per version is a smoke check, not statistical evidence of equivalence.</p>");
    }
    body.push_str("</div>");
    let mut performance = String::new();
    performance.push_str(
        "<h2>Recorded performance</h2><div class=\"table-wrap\"><table><thead><tr><th>Metric</th>",
    );
    performance.push_str(if baseline.is_some() {
        "<th>Baseline</th><th>Candidate</th>"
    } else {
        "<th>Recorded run</th>"
    });
    performance.push_str("</tr></thead><tbody>");
    let after = metrics(run);
    let before = baseline.map(metrics);
    for (name, b, a) in [
        (
            "Passing observations (%)",
            before.as_ref().map(|m| m.success_rate),
            Some(after.success_rate),
        ),
        (
            "Mean latency (ms)",
            before.as_ref().map(|m| m.mean_latency_ms),
            Some(after.mean_latency_ms),
        ),
        (
            "Tokens per observation",
            before.as_ref().and_then(|m| m.mean_tokens),
            after.mean_tokens,
        ),
        (
            "Estimated USD per observation",
            before.as_ref().and_then(|m| m.mean_cost_usd),
            after.mean_cost_usd,
        ),
    ] {
        performance.push_str(&format!("<tr><td>{name}</td>"));
        if baseline.is_some() {
            performance.push_str(&format!("<td>{}</td>", number(b)));
        }
        performance.push_str(&format!("<td>{}</td></tr>", number(a)));
    }
    performance.push_str("</tbody></table></div>");
    if let Some(report) = comparison {
        if let Some(thresholds) = report["thresholds"].as_array() {
            for t in thresholds.iter().filter(|t| t["passed"] == false) {
                body.push_str(&format!(
                    "<p class=\"failure\">{}</p>",
                    escape(t["message"].as_str().unwrap_or("Metric threshold failed"))
                ));
            }
        }
        if let Some(stats) = report["statisticalResults"].as_array() {
            if !stats.is_empty() {
                body.push_str(
                    "<details><summary>Statistical decisions and uncertainty</summary><pre>",
                );
                body.push_str(&pretty(stats));
                body.push_str("</pre></details>");
            }
        }
    }
    body.push_str("<h2>Scenario evidence</h2>");
    if run.samples_per_scenario > 1 {
        body.push_str("<p class=\"muted\">Observation numbers identify saved outputs. Baseline and candidate samples are independent, not paired.</p>");
    }
    let mut groups = wraith_core::sampling::groups(run)
        .into_iter()
        .collect::<Vec<_>>();
    groups.sort_by_key(|(id, items)| (!items.iter().any(|s| !s.passed), id.to_string()));
    for (id, items) in groups {
        let failed = items.iter().any(|s| !s.passed);
        let passed = items.iter().filter(|s| s.passed).count();
        body.push_str(&format!("<section class=\"scenario\"><div class=\"scenario-head\"><h3>{}</h3><span class=\"status {}\">{passed}/{} observations passed</span></div>",escape(id),if failed{"failure"}else{"pass"},items.len()));
        if let Some(changes) = comparison.and_then(|v| v["changes"].as_array()) {
            for change in changes.iter().filter(|c| c["scenarioId"] == id) {
                body.push_str(&format!(
                    "<p class=\"{}\"><strong>{}</strong> — {}</p>",
                    escape(change["severity"].as_str().unwrap_or("muted")),
                    escape(change["classification"].as_str().unwrap_or("Change")),
                    escape(change["message"].as_str().unwrap_or(""))
                ));
            }
        }
        for item in items {
            if let Some(error) = &item.run.error {
                body.push_str(&format!(
                    "<p class=\"error\">{}</p>",
                    escape(&error.message)
                ));
            }
            for check in item.evaluations.iter().filter(|e| !e.passed) {
                body.push_str(&format!("<div class=\"check\"><p class=\"failure\"><strong>Failed expectation · observation {}</strong></p><p>{}</p><div class=\"evidence\"><div><h4>Expected</h4><pre>{}</pre></div><div><h4>Observed</h4><pre>{}</pre></div></div></div>",item.sample_index,escape(&check.message),pretty(&check.expected),pretty(&check.observed)));
            }
            let before = baseline.and_then(|b| {
                b.scenarios
                    .iter()
                    .find(|s| s.scenario.id == id && s.sample_index == item.sample_index)
            });
            body.push_str(&format!(
                "<details><summary>Final output · observation {}</summary>{}</details>",
                item.sample_index,
                evidence(
                    &before
                        .and_then(|s| s.run.response.as_ref())
                        .map(|r| &r.output),
                    &item.run.response.as_ref().map(|r| &r.output)
                )
            ));
            body.push_str(&format!("<details><summary>All checks and recorded traces · observation {}</summary><pre>{}</pre></details>",item.sample_index,pretty(&serde_json::json!({"checks":item.evaluations,"response":item.run.response}))));
        }
        body.push_str("</section>");
    }
    body.push_str(&performance);
    write(path, &shell("Wraith evaluation", &body))
}

pub fn index(directory: &Path, records: &[Record]) -> Result<(), Error> {
    let mut body="<header><h1>Wraith run history</h1><p>Saved baselines and checks for this local project.</p></header>".to_owned();
    if records.is_empty() {
        body.push_str("<p class=\"empty\">No completed workflow runs yet. Run <code>wraith baseline</code>, then <code>wraith check</code>.</p>");
    } else {
        body.push_str("<div class=\"table-wrap\"><table class=\"history\"><thead><tr><th>Run</th><th>Outcome</th><th>Code</th><th>Mode / model</th><th>Captured at (UTC)</th></tr></thead><tbody>");
        for r in records {
            body.push_str(&format!("<tr><td><a href=\"history/{}/report.html\">{} · {}</a></td><td class=\"status {}\">{}</td><td><code>{}</code>{}</td><td>{} / {}</td><td>{}</td></tr>",escape(&r.id),escape(&r.kind),escape(&r.id),if r.outcome=="failed"{"failure"}else{&r.outcome},escape(&r.outcome),escape(r.git_commit.as_deref().unwrap_or("unavailable")),if r.git_dirty{" · modified"}else{""},escape(&r.mode),escape(r.model.as_deref().unwrap_or("not declared")),timestamp(r.created_at_unix_ms)));
        }
        body.push_str("</tbody></table></div>");
    }
    body.push_str("<p class=\"muted\">History contains local application inputs and outputs. Nothing is uploaded by Wraith.</p>");
    write(
        &directory.join(".wraith/index.html"),
        &shell("Wraith run history", &body),
    )
}

#[cfg(test)]
mod tests {
    #[test]
    fn timestamps_are_utc_and_bound_extreme_artifacts() {
        assert_eq!(super::timestamp(0), "1970-01-01 00:00:00 UTC");
        assert_eq!(super::timestamp(951782400000), "2000-02-29 00:00:00 UTC");
        assert!(super::timestamp(u64::MAX).ends_with("Unix ms"));
    }
}
