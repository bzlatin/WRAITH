use std::path::Path;
use wraith_core::{config, model::RunErrorKind, runner};

const FIXTURE: &str = r#"
import json, sys, time, subprocess, pathlib
mode = sys.argv[1]
request = json.loads(sys.stdin.readline())
response = {'protocolVersion': 1, 'scenarioId': request['scenarioId'], 'output': {'text': '20 PTO days'}, 'toolCalls': [{'name': 'search_documents'}], 'retrievals': [{'source': 'employee_handbook'}], 'usage': {'inputTokens': 200, 'outputTokens': 58}}
if mode == 'timeout': time.sleep(10)
if mode in ['tree', 'exit-tree']:
    subprocess.Popen([sys.executable, '-c', "import time,pathlib; time.sleep(2); pathlib.Path('orphan-marker').write_text('orphan')"])
    pathlib.Path('agent-ready').write_text('ready')
    if mode == 'exit-tree':
        print(json.dumps(response))
        sys.exit(0)
    time.sleep(10)
if mode == 'bad': print('Starting agent...')
if mode == 'empty': sys.exit(0)
if mode == 'exit':
    print('useful diagnostic', file=sys.stderr)
    sys.exit(7)
if mode == 'stderr': sys.stderr.write('x' * 1000000)
if mode == 'oversized': print('x' * 1100000)
if mode == 'version': response['protocolVersion'] = 8
if mode == 'id': response['scenarioId'] = 'wrong'
if mode == 'overflow': response['usage'] = {'inputTokens': 18446744073709551615, 'outputTokens': 1}
if mode == 'multiple': print(json.dumps(response))
print(json.dumps(response))
"#;

fn fixture(directory: &Path, mode: &str) -> config::Config {
    std::fs::write(directory.join("agent.py"), FIXTURE).unwrap();
    let python = if cfg!(windows) { "python" } else { "python3" };
    config::parse(&format!("version: 1\nagent:\n  command: '{python} agent.py {mode}'\n  timeout_ms: 3000\ntests:\n- id: pto\n  input: {{text: PTO}}\n  expect:\n    output_contains: ['20']\n    tools_called: [search_documents]\n    sources: {{include: [employee_handbook]}}\n    tokens: {{max: 400}}\n")).unwrap()
}

#[tokio::test]
async fn valid_response_and_large_stderr_do_not_deadlock() {
    let dir = tempfile::tempdir().unwrap();
    for mode in ["ok", "stderr"] {
        let config = fixture(dir.path(), mode);
        let snapshot = runner::run(&config, dir.path(), None).await.unwrap();
        assert!(snapshot.scenarios[0].passed, "{snapshot:?}");
        let path = dir.path().join("saved.json");
        wraith_core::snapshot::save(&path, &snapshot).unwrap();
        assert!(wraith_core::snapshot::load(&path).unwrap().scenarios[0].passed);
        let mut corrupt = snapshot;
        corrupt.scenarios[0].passed = false;
        assert!(wraith_core::snapshot::validate(&corrupt).is_err());
    }
}

#[tokio::test]
async fn protocol_and_exit_failures_are_classified_with_diagnostics() {
    let dir = tempfile::tempdir().unwrap();
    for mode in [
        "bad",
        "empty",
        "oversized",
        "version",
        "id",
        "overflow",
        "multiple",
        "exit",
    ] {
        let config = fixture(dir.path(), mode);
        let snapshot = runner::run(&config, dir.path(), None).await.unwrap();
        let result = &snapshot.scenarios[0];
        assert!(!result.passed);
        let error = result.run.error.as_ref().unwrap();
        assert_eq!(
            error.kind,
            if mode == "exit" {
                RunErrorKind::Exit
            } else {
                RunErrorKind::Protocol
            },
            "{error:?}"
        );
        if mode == "bad" {
            assert!(error.message.contains("write logs to stderr"));
        }
        if mode == "exit" {
            assert!(error.message.contains("useful diagnostic"));
        }
    }
}

#[tokio::test]
async fn spawn_failure_timeout_and_unknown_filter() {
    let dir = tempfile::tempdir().unwrap();
    let mut config = fixture(dir.path(), "timeout");
    config.agent.timeout_ms = 100;
    let run = runner::run(&config, dir.path(), None).await.unwrap();
    assert_eq!(
        run.scenarios[0].run.error.as_ref().unwrap().kind,
        RunErrorKind::Timeout
    );
    assert!(run.scenarios[0].run.duration_ms < 2000);
    config.agent.command = "wraith-executable-that-does-not-exist".into();
    let run = runner::run(&config, dir.path(), None).await.unwrap();
    assert_eq!(
        run.scenarios[0].run.error.as_ref().unwrap().kind,
        RunErrorKind::Spawn
    );
    assert!(
        runner::run(&config, dir.path(), Some("unknown"))
            .await
            .is_err()
    );
}

#[cfg(any(unix, windows))]
#[tokio::test]
async fn timeout_kills_ordinary_descendants() {
    let dir = tempfile::tempdir().unwrap();
    let mut config = fixture(dir.path(), "tree");
    config.agent.timeout_ms = 500;
    let run = runner::run(&config, dir.path(), None).await.unwrap();
    assert_eq!(
        run.scenarios[0].run.error.as_ref().unwrap().kind,
        RunErrorKind::Timeout
    );
    assert!(
        dir.path().join("agent-ready").exists(),
        "test must actually spawn a descendant"
    );
    tokio::time::sleep(std::time::Duration::from_millis(2200)).await;
    assert!(!dir.path().join("orphan-marker").exists());
}

#[cfg(any(unix, windows))]
#[tokio::test]
async fn cooperative_and_task_cancellation_kill_descendants() {
    use wraith_core::{cancellation::Cancellation, error::Error};
    for abort_task in [false, true] {
        let dir = tempfile::tempdir().unwrap();
        let config = fixture(dir.path(), "tree");
        let directory = dir.path().to_path_buf();
        let cancellation = Cancellation::default();
        let options = runner::RunOptions {
            samples: 2,
            cancellation: cancellation.clone(),
            request_budget: None,
        };
        let task = tokio::spawn(async move {
            runner::run_with_options(&config, &directory, None, &options).await
        });
        tokio::time::timeout(std::time::Duration::from_secs(3), async {
            while !dir.path().join("agent-ready").exists() {
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        if abort_task {
            task.abort();
            assert!(task.await.unwrap_err().is_cancelled());
        } else {
            cancellation.cancel();
            assert!(matches!(task.await.unwrap(), Err(Error::Cancelled)));
        }
        tokio::time::sleep(std::time::Duration::from_millis(2200)).await;
        assert!(!dir.path().join("orphan-marker").exists());
    }
}

#[tokio::test]
async fn parent_exit_with_descendant_pipe_is_still_bounded() {
    let dir = tempfile::tempdir().unwrap();
    let mut config = fixture(dir.path(), "exit-tree");
    config.agent.timeout_ms = 500;
    let run = runner::run(&config, dir.path(), None).await.unwrap();
    assert_eq!(
        run.scenarios[0].run.error.as_ref().unwrap().kind,
        RunErrorKind::Timeout
    );
    assert!(run.scenarios[0].run.duration_ms < 2000);
    assert!(dir.path().join("agent-ready").exists());
    tokio::time::sleep(std::time::Duration::from_millis(2200)).await;
    assert!(!dir.path().join("orphan-marker").exists());
}

#[tokio::test]
async fn sampling_and_precancel_validation() {
    let dir = tempfile::tempdir().unwrap();
    let config = fixture(dir.path(), "ok");
    let mut options = runner::RunOptions {
        samples: 3,
        ..Default::default()
    };
    let run = runner::run_with_options(&config, dir.path(), None, &options)
        .await
        .unwrap();
    assert_eq!(run.samples_per_scenario, 3);
    assert_eq!(
        run.scenarios
            .iter()
            .map(|s| s.sample_index)
            .collect::<Vec<_>>(),
        [1, 2, 3]
    );
    wraith_core::snapshot::validate(&run).unwrap();
    options.samples = 0;
    assert!(
        runner::run_with_options(&config, dir.path(), None, &options)
            .await
            .is_err()
    );
    options.samples = 1;
    options.cancellation.cancel();
    assert!(matches!(
        runner::run_with_options(&config, dir.path(), None, &options).await,
        Err(wraith_core::error::Error::Cancelled)
    ));
}
