use std::{path::Path, time::Duration};
use wraith_core::{cancellation::Cancellation, config, error::Error, runner, snapshot};

fn fixture(directory: &Path, mode: &str) -> config::Config {
    std::fs::write(directory.join("agent.py"), r#"
import json, os, pathlib, subprocess, sys, time
request = json.loads(sys.stdin.readline())
name = request['scenarioId']
mode = sys.argv[1]
if mode == 'tree':
    subprocess.Popen([sys.executable, '-c', "import pathlib,time,sys; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('escaped')", 'orphan-' + name])
if mode != 'quick':
    pathlib.Path('ready-' + name).write_text(str(os.getpid()))
    while not pathlib.Path('release-' + name).exists(): time.sleep(0.01)
print(json.dumps({'protocolVersion':1, 'scenarioId':name, 'output':request['input']}))
"#).unwrap();
    let python = if cfg!(windows) { "python" } else { "python3" };
    config::parse(&serde_json::json!({"version":1,"agent":{"command":format!("{python} agent.py {mode}"),"timeout_ms":10000},"tests":(0..4).map(|n|serde_json::json!({"id":format!("case-{n}"),"input":{"number":n},"expect":{"json":[{"path":"/number","check":{"op":"equals","value":n}}]}})).collect::<Vec<_>>()} ).to_string()).unwrap()
}

async fn ready(directory: &Path, id: usize) {
    tokio::time::timeout(Duration::from_secs(8), async {
        while std::fs::read_to_string(directory.join(format!("ready-case-{id}")))
            .ok()
            .and_then(|text| text.parse::<u32>().ok())
            .is_none()
        {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
}
fn release(directory: &Path, id: usize) {
    std::fs::write(directory.join(format!("release-case-{id}")), "ok").unwrap();
}

#[tokio::test]
async fn jobs_bound_active_processes_and_reassemble_out_of_order_completions() {
    let dir = tempfile::tempdir().unwrap();
    let cfg = fixture(dir.path(), "barrier");
    let directory = dir.path().to_path_buf();
    let task = tokio::spawn(async move {
        runner::run_with_options(
            &cfg,
            &directory,
            None,
            &runner::RunOptions {
                jobs: 2,
                ..Default::default()
            },
        )
        .await
    });
    ready(dir.path(), 0).await;
    ready(dir.path(), 1).await;
    tokio::time::sleep(Duration::from_millis(100)).await;
    assert!(!dir.path().join("ready-case-2").exists());
    release(dir.path(), 1);
    ready(dir.path(), 2).await;
    assert!(!dir.path().join("ready-case-3").exists());
    release(dir.path(), 2);
    ready(dir.path(), 3).await;
    release(dir.path(), 0);
    release(dir.path(), 3);
    let run = task.await.unwrap().unwrap();
    assert!(run.scenarios.iter().all(|s| s.passed));
    assert_eq!(
        run.scenarios
            .iter()
            .map(|s| s.scenario.id.as_str())
            .collect::<Vec<_>>(),
        ["case-0", "case-1", "case-2", "case-3"]
    );
    snapshot::validate(&run).unwrap();
}

#[tokio::test]
async fn parallel_samples_keep_identity_and_invalid_jobs_execute_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let cfg = fixture(dir.path(), "quick");
    let mut options = runner::RunOptions {
        jobs: 3,
        samples: 3,
        ..Default::default()
    };
    let run = runner::run_with_options(&cfg, dir.path(), None, &options)
        .await
        .unwrap();
    assert_eq!(run.scenarios.len(), 12);
    for (index, result) in run.scenarios.iter().enumerate() {
        assert_eq!(result.scenario.id, format!("case-{}", index / 3));
        assert_eq!(result.sample_index, index as u32 % 3 + 1);
    }
    snapshot::validate(&run).unwrap();
    for jobs in [0, 33] {
        options.jobs = jobs;
        assert!(matches!(
            runner::run_with_options(&cfg, dir.path(), None, &options).await,
            Err(Error::Config(_))
        ));
    }
    options.jobs = 2;
    options.request_budget = Some(dir.path().join("budget.json"));
    assert!(matches!(
        runner::run_with_options(&cfg, dir.path(), None, &options).await,
        Err(Error::Config(_))
    ));
    assert!(!dir.path().join("budget.json").exists());
}

#[cfg(any(unix, windows))]
#[tokio::test]
async fn parallel_cancellation_and_drop_kill_all_active_trees_and_stop_pending_work() {
    for abort in [false, true] {
        let dir = tempfile::tempdir().unwrap();
        let cfg = fixture(dir.path(), "tree");
        let directory = dir.path().to_path_buf();
        let token = Cancellation::default();
        let options = runner::RunOptions {
            jobs: 2,
            cancellation: token.clone(),
            ..Default::default()
        };
        let task = tokio::spawn(async move {
            runner::run_with_options(&cfg, &directory, None, &options).await
        });
        ready(dir.path(), 0).await;
        ready(dir.path(), 1).await;
        if abort {
            task.abort();
            assert!(task.await.unwrap_err().is_cancelled());
        } else {
            token.cancel();
            assert!(matches!(task.await.unwrap(), Err(Error::Cancelled)));
        }
        tokio::time::sleep(Duration::from_millis(3300)).await;
        assert!(!dir.path().join("ready-case-2").exists());
        assert!(!dir.path().join("ready-case-3").exists());
        for id in 0..2 {
            assert!(!dir.path().join(format!("orphan-case-{id}")).exists());
            #[cfg(unix)]
            {
                let pid: i32 = std::fs::read_to_string(dir.path().join(format!("ready-case-{id}")))
                    .unwrap()
                    .parse()
                    .unwrap();
                assert_eq!(
                    nix::sys::signal::kill(nix::unistd::Pid::from_raw(pid), None),
                    Err(nix::errno::Errno::ESRCH),
                    "direct child must be reaped"
                );
            }
        }
    }
}
