use std::process::{Command, Output};

fn cli(dir: &std::path::Path, args: &[&str], candidate: bool) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_wraith"));
    command
        .current_dir(dir)
        .args(args)
        .env_remove("WRAITH_EXAMPLE_MODE");
    if candidate {
        command.env("WRAITH_EXAMPLE_MODE", "candidate");
    }
    command.output().unwrap()
}

#[test]
fn init_run_save_compare_and_json_exit_contract() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let original = std::fs::read(dir.path().join("wraith.yaml")).unwrap();
    assert_eq!(cli(dir.path(), &["init"], false).status.code(), Some(2));
    assert_eq!(
        std::fs::read(dir.path().join("wraith.yaml")).unwrap(),
        original
    );
    let baseline = cli(
        dir.path(),
        &["run", "--save", "baseline", "--output", "json"],
        false,
    );
    assert!(
        baseline.status.success(),
        "{}",
        String::from_utf8_lossy(&baseline.stderr)
    );
    let json: serde_json::Value = serde_json::from_slice(&baseline.stdout).unwrap();
    assert_eq!(json["scenarios"].as_array().unwrap().len(), 3);
    let candidate = cli(dir.path(), &["run", "--save", "candidate"], true);
    assert_eq!(candidate.status.code(), Some(1));
    let report = cli(
        dir.path(),
        &["compare", "baseline", "candidate", "--output", "json"],
        false,
    );
    assert_eq!(report.status.code(), Some(1));
    let json: serde_json::Value = serde_json::from_slice(&report.stdout).unwrap();
    assert!(
        json["changes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c["classification"] == "TOOL_SELECTION_REGRESSION")
    );
    assert!(
        cli(dir.path(), &["compare", "baseline", "baseline"], false)
            .status
            .success()
    );
    assert!(
        cli(
            dir.path(),
            &["compare", "baseline", ".wraith/runs/baseline.json"],
            false
        )
        .status
        .success()
    );
    assert_eq!(
        cli(dir.path(), &["run", "--scenario", "missing"], false)
            .status
            .code(),
        Some(2)
    );
    assert_eq!(
        cli(dir.path(), &["run", "--save", "../escape"], false)
            .status
            .code(),
        Some(2)
    );
    let filtered = cli(
        dir.path(),
        &["run", "--scenario", "find-pto-policy", "--output", "json"],
        false,
    );
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&filtered.stdout).unwrap()["scenarios"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    // Saved comparisons remain usable after the config is removed.
    std::fs::remove_file(dir.path().join("wraith.yaml")).unwrap();
    assert!(
        cli(dir.path(), &["compare", "baseline", "baseline"], false)
            .status
            .success()
    );
}

#[test]
fn execution_failure_is_two_and_failed_run_is_still_saved() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("wraith.yaml"),
        "version: 1\nagent: {command: nonexistent-wraith-agent}\ntests:\n- id: test\n  input: hi\n",
    )
    .unwrap();
    let output = cli(
        dir.path(),
        &["run", "--save", "broken", "--output", "json"],
        false,
    );
    assert_eq!(output.status.code(), Some(2));
    assert!(serde_json::from_slice::<serde_json::Value>(&output.stdout).is_ok());
    assert!(dir.path().join(".wraith/runs/broken.json").exists());
    assert_eq!(
        cli(dir.path(), &["compare", "broken", "broken"], false)
            .status
            .code(),
        Some(2)
    );
}

#[test]
fn sampled_cli_schema_and_policy_override() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let result = cli(
        dir.path(),
        &[
            "run",
            "--samples",
            "3",
            "--save",
            "baseline",
            "--output",
            "json",
        ],
        false,
    );
    assert!(result.status.success());
    let value: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(value["schemaVersion"], 4);
    assert_eq!(value["samplesPerScenario"], 3);
    assert_eq!(value["scenarios"].as_array().unwrap().len(), 9);
    assert_eq!(
        cli(
            dir.path(),
            &["run", "--samples", "3", "--save", "candidate"],
            true
        )
        .status
        .code(),
        Some(1)
    );
    let report = cli(
        dir.path(),
        &[
            "compare",
            "baseline",
            "candidate",
            "--policy",
            "wraith.yaml",
            "--output",
            "json",
        ],
        false,
    );
    assert_eq!(report.status.code(), Some(1));
    let value: serde_json::Value = serde_json::from_slice(&report.stdout).unwrap();
    assert_eq!(value["scenarioSampling"][1]["baseline"]["count"], 3);
    assert_eq!(
        cli(dir.path(), &["run", "--samples", "0"], false)
            .status
            .code(),
        Some(2)
    );
}

#[cfg(unix)]
#[test]
fn ctrl_c_cleans_up_and_preserves_existing_snapshot() {
    use std::time::{Duration, Instant};
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"), r#"
import json, sys, subprocess, pathlib, time
json.loads(sys.stdin.readline())
subprocess.Popen([sys.executable, '-c', "import pathlib,time; time.sleep(2); pathlib.Path('orphan').write_text('alive')"])
pathlib.Path('ready').write_text('ready')
time.sleep(10)
"#).unwrap();
    std::fs::write(dir.path().join("wraith.yaml"), "version: 1\nagent: {command: 'python3 agent.py', timeout_ms: 20000}\ntests:\n- id: interrupt\n  input: hi\n").unwrap();
    let runs = dir.path().join(".wraith/runs");
    std::fs::create_dir_all(&runs).unwrap();
    let previous = runs.join("baseline.json");
    std::fs::write(&previous, "preserve existing run").unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_wraith"))
        .current_dir(dir.path())
        .args(["run", "--save", "baseline"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    while !dir.path().join("ready").exists() {
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("agent did not start");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(
        Command::new("python3")
            .args([
                "-c",
                "import os,signal,sys; os.kill(int(sys.argv[1]), signal.SIGINT)",
                &child.id().to_string()
            ])
            .status()
            .unwrap()
            .success()
    );
    let deadline = Instant::now() + Duration::from_secs(5);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("Ctrl-C did not finish cleanup");
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    assert_eq!(status.code(), Some(130));
    assert_eq!(
        std::fs::read_to_string(previous).unwrap(),
        "preserve existing run"
    );
    std::thread::sleep(Duration::from_millis(2200));
    assert!(!dir.path().join("orphan").exists());
}

#[test]
fn inconclusive_is_exit_three_in_human_and_json_reports() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let path = dir.path().join("wraith.yaml");
    let text = std::fs::read_to_string(&path).unwrap();
    std::fs::write(&path, format!("{text}\ncomparison:\n  statistical:\n    min_samples: 20\n    max_failure_rate_increase_pp: 10\n    alpha: 0.05\n")).unwrap();
    for name in ["baseline", "candidate"] {
        assert!(
            cli(
                dir.path(),
                &["run", "--samples", "2", "--save", name],
                false
            )
            .status
            .success()
        );
    }
    let result = cli(
        dir.path(),
        &["compare", "baseline", "candidate", "--output", "json"],
        false,
    );
    assert_eq!(result.status.code(), Some(3));
    let report: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["passed"], false);
    assert_eq!(report["inconclusive"], true);
    let human = cli(dir.path(), &["compare", "baseline", "candidate"], false);
    assert_eq!(human.status.code(), Some(3));
    assert!(
        String::from_utf8(human.stdout)
            .unwrap()
            .contains("INCONCLUSIVE")
    );
}

#[test]
fn baseline_check_history_and_preflight_preserve_evidence() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init", "--demo"], false).status.success());
    // This test verifies workflow state, not a three-second cold-start deadline.
    // Parallel Python starts can exceed that deadline on busy Windows runners.
    let config = dir.path().join("wraith.yaml");
    let (mut suite, _) = wraith_core::config::load(&config).unwrap();
    suite.agent.timeout_ms = 30000;
    std::fs::write(&config, serde_json::to_vec_pretty(&suite).unwrap()).unwrap();
    assert!(cli(dir.path(), &["doctor"], false).status.success());
    let baseline = cli(dir.path(), &["baseline"], false);
    assert!(
        baseline.status.success(),
        "{}\n{}",
        String::from_utf8_lossy(&baseline.stdout),
        String::from_utf8_lossy(&baseline.stderr)
    );
    let pointer = dir.path().join(".wraith/baseline.json");
    let original = std::fs::read(&pointer).unwrap();
    assert_eq!(cli(dir.path(), &["baseline"], false).status.code(), Some(2));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
    let check = cli(dir.path(), &["check", "--output", "json"], true);
    assert_eq!(
        check.status.code(),
        Some(1),
        "{}",
        String::from_utf8_lossy(&check.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&check.stdout).unwrap();
    assert_eq!(result["record"]["outcome"], "failed");
    let html = std::fs::read_to_string(result["report"].as_str().unwrap()).unwrap();
    assert!(html.contains("TOOL_SELECTION_REGRESSION"));
    assert!(html.contains("Final output"));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
    let history = cli(dir.path(), &["history", "--output", "json"], false);
    let records: serde_json::Value = serde_json::from_slice(&history.stdout).unwrap();
    assert_eq!(records.as_array().unwrap().len(), 2);
    let changed = std::fs::read_to_string(&config)
        .unwrap()
        .replace("20 PTO days?", "21 PTO days?");
    // Change a known input reliably, leaving expectations intact.
    std::fs::write(
        &config,
        changed.replace(
            "How many PTO days do employees receive?",
            "How many holidays do employees receive?",
        ),
    )
    .unwrap();
    let check = cli(dir.path(), &["check"], false);
    assert_eq!(check.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&check.stderr).contains("No agent was executed"));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
}

#[test]
fn live_function_adapter_budget_and_opt_in_fail_closed() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"),"def evaluate(input, context):\n    with context.model_call():\n        return {'text':'ok'}\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--language",
                "python",
                "--mode",
                "live"
            ],
            false
        )
        .status
        .success()
    );
    assert_eq!(cli(dir.path(), &["baseline"], false).status.code(), Some(2));
    assert!(!dir.path().join(".wraith/history").exists());
    assert!(
        cli(
            dir.path(),
            &["baseline", "--allow-live", "--max-requests", "2"],
            false
        )
        .status
        .success()
    );
    assert_eq!(cli(dir.path(), &["check"], false).status.code(), Some(2));
    assert!(
        cli(dir.path(), &["check", "--allow-live"], false)
            .status
            .success()
    );
    let result = cli(dir.path(), &["check", "--allow-live"], false);
    assert_eq!(result.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&result.stderr).contains("exhausted"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(dir.path().join(".wraith/baseline.json")).unwrap())
            .unwrap();
    let budget = dir
        .path()
        .join(".wraith/history")
        .join(pointer["id"].as_str().unwrap())
        .join("request-budget.json");
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&std::fs::read(budget).unwrap()).unwrap()["used"],
        2
    );
}

#[test]
fn failed_live_baseline_cannot_silently_reset_its_budget() {
    let dir = tempfile::tempdir().unwrap();
    let agent = dir.path().join("agent.py");
    std::fs::write(&agent, "def evaluate(input, context):\n    with context.model_call():\n        raise RuntimeError('provider failed')\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--mode",
                "live"
            ],
            false
        )
        .status
        .success()
    );
    let args = ["baseline", "--allow-live", "--max-requests", "2"];
    assert_eq!(cli(dir.path(), &args, false).status.code(), Some(2));
    assert!(!dir.path().join(".wraith/baseline.json").exists());
    let attempt_path = dir.path().join(".wraith/live-baseline-attempt.json");
    let attempt = std::fs::read(&attempt_path).unwrap();
    let value: serde_json::Value = serde_json::from_slice(&attempt).unwrap();
    let budget_path = dir
        .path()
        .join(".wraith/history")
        .join(value["budgetId"].as_str().unwrap())
        .join("request-budget.json");
    let budget = std::fs::read(&budget_path).unwrap();
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&budget).unwrap()["used"],
        1
    );
    std::fs::write(&agent, "def evaluate(input, context):\n    with context.model_call():\n        return {'text':'ok'}\n").unwrap();
    let blocked = cli(dir.path(), &args, false);
    assert_eq!(blocked.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&blocked.stderr).contains("No agent was executed"));
    assert_eq!(std::fs::read(&attempt_path).unwrap(), attempt);
    assert_eq!(std::fs::read(&budget_path).unwrap(), budget);
    assert!(
        cli(
            dir.path(),
            &[
                "baseline",
                "--replace",
                "--allow-live",
                "--max-requests",
                "2"
            ],
            false
        )
        .status
        .success()
    );
    assert_ne!(std::fs::read(attempt_path).unwrap(), attempt);
    assert_eq!(std::fs::read(budget_path).unwrap(), budget);
}

#[test]
fn generated_adapter_handles_async_logs_and_escapes_html() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"),"print('import log')\nasync def evaluate(input, context):\n    print('runtime log')\n    context.tool('lookup', {'q':'hello'}, 'found')\n    return {'text':'<script>alert(1)</script>'}\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--language",
                "python",
                "--template",
                "tools"
            ],
            false
        )
        .status
        .success()
    );
    let config_path = dir.path().join("wraith.yaml");
    let mut config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&config_path).unwrap()).unwrap();
    config["tests"][0]["input"] = serde_json::json!({"text":"<img src=x onerror=alert(1)>"});
    config["tests"][0]["metadata"] = serde_json::json!({"audience":"<private>"});
    std::fs::write(config_path, config.to_string()).unwrap();
    let baseline = cli(dir.path(), &["baseline", "--output", "json"], false);
    assert!(
        baseline.status.success(),
        "{}",
        String::from_utf8_lossy(&baseline.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&baseline.stdout).unwrap();
    let html = std::fs::read_to_string(result["report"].as_str().unwrap()).unwrap();
    assert!(!html.contains("<script>"));
    assert!(html.contains("&lt;script&gt;"));
    assert!(html.contains("Request input and metadata"));
    assert!(html.contains("&lt;img src=x onerror=alert(1)&gt;"));
    assert!(html.contains("&lt;private&gt;"));
    assert!(!html.contains("<img src=x"));
    assert_eq!(
        result["run"]["scenarios"][0]["run"]["response"]["toolCalls"][0]["name"],
        "lookup"
    );
}

#[test]
fn import_reviewed_case_and_ci_bootstrap_are_reviewable() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init", "--demo"], false).status.success());
    std::fs::write(
        dir.path().join("input.json"),
        r#"{"text":"reported request"}"#,
    )
    .unwrap();
    std::fs::write(
        dir.path().join("expect.json"),
        r#"{"output_contains":["correct"]}"#,
    )
    .unwrap();
    let args = [
        "cases",
        "add",
        "--id",
        "reported-bug",
        "--input",
        "input.json",
        "--expect",
        "expect.json",
    ];
    let imported = cli(dir.path(), &args, false);
    assert!(
        imported.status.success(),
        "{}",
        String::from_utf8_lossy(&imported.stderr)
    );
    let config = dir.path().join("wraith.yaml");
    let bytes = std::fs::read(&config).unwrap();
    let suite: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(suite["tests"].as_array().unwrap().len(), 4);
    assert_eq!(cli(dir.path(), &args, false).status.code(), Some(2));
    assert_eq!(std::fs::read(&config).unwrap(), bytes);
    assert!(
        Command::new("git")
            .args(["init", "--quiet"])
            .current_dir(dir.path())
            .status()
            .unwrap()
            .success()
    );
    let generated = cli(dir.path(), &["ci", "init"], false);
    assert!(
        generated.status.success(),
        "{}",
        String::from_utf8_lossy(&generated.stderr)
    );
    let workflow = dir.path().join(".github/workflows/wraith.yml");
    let original = std::fs::read(&workflow).unwrap();
    let yaml = String::from_utf8(original.clone()).unwrap();
    assert!(yaml.contains("github.event.pull_request.base.sha"));
    assert!(yaml.contains("wraith-evidence"));
    assert!(!yaml.contains("__CONFIG_JSON__"));
    assert_eq!(
        cli(dir.path(), &["ci", "init"], false).status.code(),
        Some(2)
    );
    assert_eq!(std::fs::read(workflow).unwrap(), original);
}

#[test]
fn batch_import_is_atomic_requires_review_and_preserves_baseline() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init", "--demo"], false).status.success());
    assert!(cli(dir.path(), &["baseline"], false).status.success());
    let pointer = dir.path().join(".wraith/baseline.json");
    let baseline = std::fs::read(&pointer).unwrap();
    let file = dir.path().join("cases.json");
    let config = dir.path().join("wraith.yaml");
    let original = std::fs::read(&config).unwrap();
    for invalid in [
        r#"[]"#,
        r#"[{"id":"missing-review","input":{}}]"#,
        r#"[{"id":"fresh","input":{},"expect":{}},{"id":"fresh","input":{},"expect":{}}]"#,
        r#"[{"id":"fresh","input":{},"expect":{}},{"id":"invalid","input":{},"expect":{"json":[{"path":"bad-pointer","check":{"op":"exists"}}]}}]"#,
    ] {
        std::fs::write(&file, invalid).unwrap();
        assert_eq!(
            cli(
                dir.path(),
                &["cases", "import", "--file", "cases.json"],
                false
            )
            .status
            .code(),
            Some(2)
        );
        assert_eq!(std::fs::read(&config).unwrap(), original);
        assert_eq!(std::fs::read(&pointer).unwrap(), baseline);
    }
    std::fs::write(&file, r#"[{"id":"deny","input":{"approve":false},"metadata":{"reason":"reviewed"},"expect":{"tools_not_called":["delete"]}},{"id":"count","input":{},"expect":{"json":[{"path":"/count","check":{"op":"equals","value":2}}]}}]"#).unwrap();
    let added = cli(
        dir.path(),
        &["cases", "import", "--file", "cases.json"],
        false,
    );
    assert!(
        added.status.success(),
        "{}",
        String::from_utf8_lossy(&added.stderr)
    );
    let suite: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&config).unwrap()).unwrap();
    assert_eq!(suite["tests"].as_array().unwrap().len(), 5);
    assert_eq!(suite["tests"][3]["metadata"]["reason"], "reviewed");
    assert_eq!(std::fs::read(&pointer).unwrap(), baseline);
    // The accepted baseline cannot silently cover a changed suite.
    assert_eq!(cli(dir.path(), &["check"], false).status.code(), Some(2));
}

#[test]
fn doctor_flags_weak_cases_in_mixed_suites_without_running_agent() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("wraith.yaml"), r#"{"version":1,"agent":{"command":"python3 -c 'raise Exception()'"},"tests":[{"id":"empty","input":{}},{"id":"presence","input":{},"expect":{"json":[{"path":"/answer","check":{"op":"exists"}}]}},{"id":"negative-tool","input":{},"expect":{"tools_not_called":["delete"]}},{"id":"equals","input":{},"expect":{"json":[{"path":"/count","check":{"op":"equals","value":2}}]}}]}"#.replace("python3", if cfg!(windows) { "python" } else { "python3" })).unwrap();
    let result = cli(dir.path(), &["doctor", "--output", "json"], false);
    assert!(result.status.success());
    let output: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    let warnings: Vec<_> = output["checks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|c| c["status"] == "warning")
        .map(|c| c["scenarioId"].as_str().unwrap())
        .collect();
    assert_eq!(warnings, ["empty", "presence"]);
    assert!(output["passed"].as_bool().unwrap());
}

#[test]
fn reviewed_init_and_typed_case_flags_preserve_fixed_baselines() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("agent.py"),
        "def evaluate(input):\n    return {'a/b': False, 'count': -2, 'text': input['text']}\n",
    )
    .unwrap();
    let cases = dir.path().join("cases.json");
    std::fs::write(&cases, r#"[{"id":"missing-review","input":{}}]"#).unwrap();
    let init = [
        "init",
        "--entrypoint",
        "agent.py:evaluate",
        "--input-only",
        "--cases",
        "cases.json",
    ];
    assert_eq!(cli(dir.path(), &init, false).status.code(), Some(2));
    assert!(!dir.path().join("wraith_adapter.py").exists());
    assert!(!dir.path().join("wraith.project.json").exists());
    assert!(!dir.path().join("wraith.yaml").exists());
    std::fs::write(&cases, r#"[{"id":"reviewed","input":{"text":"ready"},"expect":{"json":[{"path":"/a~1b","check":{"op":"equals","value":false}}]}}]"#).unwrap();
    let result = cli(dir.path(), &init, false);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(cli(dir.path(), &["baseline"], false).status.success());
    let config = dir.path().join("wraith.yaml");
    let pointer = dir.path().join(".wraith/baseline.json");
    let baseline = std::fs::read(&pointer).unwrap();
    let original = std::fs::read(&config).unwrap();
    let source: serde_json::Value = serde_json::from_slice(&original).unwrap();
    let native: serde_json::Value =
        serde_json::from_slice(&cli(dir.path(), &["history", "--output", "json"], false).stdout)
            .unwrap();
    let run = format!(
        ".wraith/history/{}/run.json",
        native[0]["id"].as_str().unwrap()
    );
    for args in [
        vec![
            "cases",
            "add",
            "--id",
            "bad-json",
            "--from-run",
            &run,
            "--json-equals",
            "/count",
            "invalid-json",
        ],
        vec![
            "cases",
            "add",
            "--id",
            "bad-pointer",
            "--from-run",
            &run,
            "--json-equals",
            "invalid",
            "0",
        ],
    ] {
        assert_eq!(cli(dir.path(), &args, false).status.code(), Some(2));
        assert_eq!(std::fs::read(&config).unwrap(), original);
    }
    let added = cli(
        dir.path(),
        &[
            "cases",
            "add",
            "--id",
            "typed",
            "--from-run",
            &run,
            "--json-equals",
            "/a~1b",
            "false",
            "--json-equals",
            "/count",
            "-2",
            "--contains",
            "ready",
            "--forbid-tool",
            "delete",
        ],
        false,
    );
    assert!(
        added.status.success(),
        "{}",
        String::from_utf8_lossy(&added.stderr)
    );
    let changed: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&config).unwrap()).unwrap();
    assert_eq!(
        changed["tests"][1]["expect"]["json"][0]["check"]["value"],
        false
    );
    assert_eq!(
        changed["tests"][1]["expect"]["json"][1]["check"]["value"],
        -2
    );
    assert_eq!(changed["tests"][1]["input"], source["tests"][0]["input"]);
    assert_eq!(std::fs::read(&pointer).unwrap(), baseline);
    assert_eq!(cli(dir.path(), &["check"], false).status.code(), Some(2));
    assert!(
        cli(dir.path(), &["baseline", "--replace"], false)
            .status
            .success()
    );
    assert!(cli(dir.path(), &["check"], false).status.success());
}

#[test]
fn report_prioritizes_trace_regression_when_observations_pass() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"), "import os\ndef evaluate(input, context):\n    value = 2 if input['changed'] and os.getenv('WRAITH_EXAMPLE_MODE') == 'candidate' else 1\n    context.tool('lookup', {'id': value}, 'ok')\n    return {'text': 'ok'}\n").unwrap();
    std::fs::write(dir.path().join("cases.json"), r#"[{"id":"a-pass","input":{"changed":false},"expect":{"tools_called":["lookup"]}},{"id":"z-trace","input":{"changed":true},"expect":{"tools_called":["lookup"]}}]"#).unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--cases",
                "cases.json"
            ],
            false
        )
        .status
        .success()
    );
    let path = dir.path().join("wraith.yaml");
    let mut cfg: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    cfg["comparison"] = serde_json::json!({"tool_arguments":true});
    std::fs::write(path, cfg.to_string()).unwrap();
    assert!(cli(dir.path(), &["baseline"], false).status.success());
    let candidate = cli(dir.path(), &["check", "--output", "json"], true);
    assert_eq!(candidate.status.code(), Some(1));
    let result: serde_json::Value = serde_json::from_slice(&candidate.stdout).unwrap();
    assert!(
        result["run"]["scenarios"]
            .as_array()
            .unwrap()
            .iter()
            .all(|s| s["passed"] == true)
    );
    let html = std::fs::read_to_string(result["report"].as_str().unwrap()).unwrap();
    assert!(html.find("<h3>z-trace</h3>").unwrap() < html.find("<h3>a-pass</h3>").unwrap());
    assert!(html.contains("Comparison failed · 1/1 observations passed"));
    assert!(html.contains("TOOL_ARGUMENTS_REGRESSION"));
    assert!(html.contains("Comparison evidence"));
    assert!(html.contains("&quot;id&quot;: 1"));
    assert!(html.contains("&quot;id&quot;: 2"));
}
