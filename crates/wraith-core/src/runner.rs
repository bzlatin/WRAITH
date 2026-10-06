use crate::{
    cancellation::Cancellation,
    config::{AgentConfig, Config, Scenario, command_args},
    error::Error,
    evaluation::evaluate,
    model::*,
    process::Process,
};
use std::{
    path::Path,
    process::Stdio,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    process::Command,
};

const STDOUT_LIMIT: usize = 1024 * 1024;
const STDERR_LIMIT: usize = 64 * 1024;

pub fn unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}

/// Drains the pipe even after the retention limit, preventing child pipe deadlocks.
async fn capture(
    mut pipe: impl AsyncRead + Unpin,
    limit: usize,
) -> std::io::Result<(Vec<u8>, bool)> {
    let mut kept = Vec::new();
    let mut exceeded = false;
    let mut buffer = [0; 8192];
    loop {
        let n = pipe.read(&mut buffer).await?;
        if n == 0 {
            return Ok((kept, exceeded));
        }
        let retain = n.min(limit.saturating_sub(kept.len()));
        kept.extend_from_slice(&buffer[..retain]);
        exceeded |= retain < n;
    }
}

fn failure(kind: RunErrorKind, message: impl Into<String>) -> RunError {
    RunError {
        kind,
        message: message.into(),
    }
}

async fn invoke(
    agent: &AgentConfig,
    scenario: &Scenario,
    directory: &Path,
    cancellation: &Cancellation,
) -> Result<AgentResponse, RunError> {
    let args =
        command_args(&agent.command).map_err(|e| failure(RunErrorKind::Spawn, e.to_string()))?;
    let mut command = Command::new(&args[0]);
    command
        .args(&args[1..])
        .current_dir(directory)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut process = Process::spawn(command).map_err(|e| failure(RunErrorKind::Spawn, format!("Could not execute agent command {:?}: {e}\nWorking directory: {}\nCheck agent.command, the executable installation, and paths relative to the configuration.", agent.command, directory.display())))?;
    let (mut stdin, stdout, stderr) = process
        .take_pipes()
        .map_err(|e| failure(RunErrorKind::Io, e.to_string()))?;
    let mut request = serde_json::to_vec(&AgentRequest {
        protocol_version: PROTOCOL_VERSION,
        scenario_id: &scenario.id,
        input: &scenario.input,
        metadata: &scenario.metadata,
    })
    .map_err(|e| failure(RunErrorKind::Protocol, e.to_string()))?;
    request.push(b'\n');
    let work = async {
        let write = async {
            stdin.write_all(&request).await?;
            stdin.shutdown().await?;
            drop(stdin);
            Ok::<_, std::io::Error>(())
        };
        tokio::try_join!(
            write,
            capture(stdout, STDOUT_LIMIT),
            capture(stderr, STDERR_LIMIT),
            process.wait()
        )
    };
    let outcome = tokio::select! {
        biased;
        _ = cancellation.cancelled() => Err(failure(RunErrorKind::Cancelled, "Agent invocation cancelled.")),
        result = tokio::time::timeout(Duration::from_millis(agent.timeout_ms), work) => {
            result.map_err(|_| failure(RunErrorKind::Timeout, format!("Agent {:?} exceeded {}ms. The process was terminated. Increase agent.timeout_ms or investigate a stuck agent.", agent.command, agent.timeout_ms)))
                .and_then(|result| result.map_err(|e| failure(RunErrorKind::Io, format!("Agent I/O failed for {:?}: {e}. Check that the agent reads stdin and writes a response before exiting.", agent.command))))
        }
    };
    // Cleanup runs outside the cancelled exchange and has its own bounded deadline.
    process.terminate().map_err(|e| {
        failure(
            RunErrorKind::Io,
            format!("Could not terminate agent process tree: {e}"),
        )
    })?;
    tokio::time::timeout(Duration::from_secs(5), process.wait())
        .await
        .map_err(|_| {
            failure(
                RunErrorKind::Io,
                "Agent cleanup exceeded 5s after termination.",
            )
        })?
        .map_err(|e| {
            failure(
                RunErrorKind::Io,
                format!("Could not reap agent process: {e}"),
            )
        })?;
    let (_, (stdout, excessive), (stderr, truncated), status) = outcome?;
    if !status.success() {
        return Err(failure(
            RunErrorKind::Exit,
            format!(
                "Agent {:?} exited with {status}.\nStderr (up to 64 KiB{}):\n{}",
                agent.command,
                if truncated { ", truncated" } else { "" },
                String::from_utf8_lossy(&stderr)
            ),
        ));
    }
    if excessive {
        return Err(failure(
            RunErrorKind::Protocol,
            "Agent stdout exceeded 1 MiB. Emit one bounded JSON response; write logs to stderr.",
        ));
    }
    let response: AgentResponse = serde_json::from_slice(&stdout).map_err(|e| failure(RunErrorKind::Protocol, format!("WRAITH could not parse the response from {:?}: {e}\nExpected one JSON response on stdout. Received (first 512 bytes):\n{}\nTip: write logs to stderr and reserve stdout for the WRAITH protocol.", agent.command, String::from_utf8_lossy(&stdout[..stdout.len().min(512)]))))?;
    response
        .validate(&scenario.id)
        .map_err(|e| failure(RunErrorKind::Protocol, e))?;
    Ok(response)
}

#[derive(Debug, Clone)]
pub struct RunOptions {
    pub samples: u32,
    pub cancellation: Cancellation,
}

impl Default for RunOptions {
    fn default() -> Self {
        Self {
            samples: 1,
            cancellation: Cancellation::default(),
        }
    }
}

pub async fn run_scenario(
    agent: &AgentConfig,
    scenario: &Scenario,
    directory: &Path,
) -> ScenarioResult {
    run_observation(agent, scenario, directory, 1, &Cancellation::default()).await
}

async fn run_observation(
    agent: &AgentConfig,
    scenario: &Scenario,
    directory: &Path,
    sample_index: u32,
    cancellation: &Cancellation,
) -> ScenarioResult {
    let started_at_unix_ms = unix_ms();
    let clock = Instant::now();
    let outcome = invoke(agent, scenario, directory, cancellation).await;
    let (response, error) = match outcome {
        Ok(response) => (Some(response), None),
        Err(error) => (None, Some(error)),
    };
    let run = AgentRun {
        scenario_id: scenario.id.clone(),
        input: scenario.input.clone(),
        started_at_unix_ms,
        completed_at_unix_ms: unix_ms(),
        duration_ms: clock.elapsed().as_millis().min(u64::MAX as u128) as u64,
        response,
        error,
    };
    let evaluations = evaluate(scenario, &run);
    let passed = run.error.is_none() && evaluations.iter().all(|e| e.passed);
    ScenarioResult {
        sample_index,
        scenario: scenario.clone(),
        run,
        evaluations,
        passed,
    }
}

pub async fn run(
    config: &Config,
    directory: &Path,
    selected: Option<&str>,
) -> Result<RunSnapshot, Error> {
    run_with_options(
        config,
        directory,
        selected,
        &RunOptions {
            samples: 1,
            cancellation: Cancellation::default(),
        },
    )
    .await
}

pub async fn run_with_options(
    config: &Config,
    directory: &Path,
    selected: Option<&str>,
    options: &RunOptions,
) -> Result<RunSnapshot, Error> {
    if !(1..=1000).contains(&options.samples) {
        return Err(Error::Config(
            "samples: expected an integer from 1 to 1000".into(),
        ));
    }
    if selected.is_some_and(|id| !config.tests.iter().any(|s| s.id == id)) {
        return Err(Error::Config(format!(
            "Unknown scenario {selected:?}. Check tests[].id in the configuration."
        )));
    }
    let mut scenarios = Vec::new();
    for scenario in config
        .tests
        .iter()
        .filter(|s| selected.is_none_or(|id| id == s.id))
    {
        for sample_index in 1..=options.samples {
            if options.cancellation.is_cancelled() {
                return Err(Error::Cancelled);
            }
            let result = run_observation(
                &config.agent,
                scenario,
                directory,
                sample_index,
                &options.cancellation,
            )
            .await;
            if options.cancellation.is_cancelled()
                || result
                    .run
                    .error
                    .as_ref()
                    .is_some_and(|e| e.kind == RunErrorKind::Cancelled)
            {
                return Err(Error::Cancelled);
            }
            scenarios.push(result);
        }
    }
    Ok(RunSnapshot {
        schema_version: SCHEMA_VERSION,
        wraith_version: env!("CARGO_PKG_VERSION").into(),
        created_at_unix_ms: unix_ms(),
        samples_per_scenario: options.samples,
        comparison: config.comparison.clone(),
        thresholds: config.thresholds.clone(),
        scenarios,
    })
}
