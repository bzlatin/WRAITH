use serde_json::json;
use std::{fs, process::Command};

#[test]
fn index_reports_are_escaped_immutable_and_fail_closed() {
    let dir = tempfile::tempdir().unwrap();
    let header = |kind| json!({"schema_version":1,"kind":kind,"scope":"demo","generation":"g1","complete":true,"stable":true,"record_count":1});
    let manifest = json!({"tenant":"demo","document_id":"<script>alert(1)</script>","state":"present","settled":true,"revision":"2","expected_chunks":["0","1"]});
    let inventory = json!({"tenant":"demo","document_id":"<script>alert(1)</script>","chunks":[{"id":"0","revision":"1"}]});
    fs::write(
        dir.path().join("manifest.jsonl"),
        format!("{}\n{}\n", header("manifest"), manifest),
    )
    .unwrap();
    fs::write(
        dir.path().join("inventory.jsonl"),
        format!("{}\n{}\n", header("inventory"), inventory),
    )
    .unwrap();
    let invoke = |extra: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_wraith"))
            .current_dir(dir.path())
            .args([
                "index",
                "check",
                "--manifest",
                "manifest.jsonl",
                "--inventory",
                "inventory.jsonl",
            ])
            .args(extra)
            .output()
            .unwrap()
    };
    let result = invoke(&[
        "--json",
        "report.json",
        "--html",
        "report.html",
        "--output",
        "json",
    ]);
    assert_eq!(
        result.status.code(),
        Some(1),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let parsed: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(parsed["summary"]["failed"], 1);
    let html = fs::read_to_string(dir.path().join("report.html")).unwrap();
    assert!(!html.contains("<script>"));
    assert!(html.contains("&lt;script&gt;"));
    assert!(html.contains("default-src 'none'"));
    assert_eq!(invoke(&["--html", "report.html"]).status.code(), Some(2));
    assert_eq!(
        fs::read_to_string(dir.path().join("report.html")).unwrap(),
        html
    );
    fs::write(
        dir.path().join("inventory.jsonl"),
        format!("{}\n", header("inventory")),
    )
    .unwrap();
    let result = invoke(&["--json", "invalid.json"]);
    assert_eq!(result.status.code(), Some(2));
    assert!(!dir.path().join("invalid.json").exists());
    assert!(!dir.path().join("wraith.yaml").exists());
}
