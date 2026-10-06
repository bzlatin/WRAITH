mod render;
use clap::{Parser, Subcommand, ValueEnum};
use std::{
    path::{Path, PathBuf},
    process::ExitCode,
};
use wraith_core::{
    cancellation::Cancellation,
    comparison, config,
    error::{self, Error},
    runner, snapshot,
};

#[derive(Parser)]
#[command(
    name = "wraith",
    version,
    about = "Catch agent regressions before they ship."
)]
struct Cli {
    #[arg(long, global = true, default_value = "wraith.yaml")]
    config: PathBuf,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Create a configuration and a deterministic example agent.
    Init,
    /// Execute scenarios against the configured agent.
    Run {
        #[arg(long)]
        scenario: Option<String>,
        #[arg(long)]
        save: Option<String>,
        #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u32).range(1..=1000))]
        samples: u32,
        #[arg(long, value_enum, default_value_t = Output::Human)]
        output: Output,
    },
    /// Compare saved names or explicit JSON file paths.
    Compare {
        baseline: String,
        candidate: String,
        /// Enforce thresholds and comparison options from a trusted configuration.
        #[arg(long)]
        policy: Option<PathBuf>,
        #[arg(long, value_enum, default_value_t = Output::Human)]
        output: Output,
    },
}

#[derive(Clone, Copy, ValueEnum)]
enum Output {
    Human,
    Json,
}

const EXAMPLE_CONFIG: &str = include_str!("../../../wraith.yaml");
const EXAMPLE_AGENT: &str = include_str!("../../../examples/python-agent/agent.py");

fn init(path: &Path) -> Result<(), Error> {
    let directory = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let agent_path = directory.join("wraith_agent.py");
    for p in [path, agent_path.as_path()] {
        if p.exists() {
            return Err(Error::Config(format!(
                "{} already exists. Init never overwrites files; choose a new --config path in an empty directory.",
                p.display()
            )));
        }
    }
    std::fs::create_dir_all(directory)
        .map_err(|e| error::io("create configuration directory", directory, e))?;
    let contents = EXAMPLE_CONFIG.replace("examples/python-agent/agent.py", "wraith_agent.py");
    #[cfg(windows)]
    let contents = contents.replacen("python3 ", "python ", 1);
    // create_new closes the race between existence checks and writes.
    use std::io::Write;
    for (p, contents) in [
        (agent_path.as_path(), EXAMPLE_AGENT),
        (path, contents.as_str()),
    ] {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(p)
            .map_err(|e| error::io("create starter file", p, e))?;
        file.write_all(contents.as_bytes())
            .map_err(|e| error::io("write starter file", p, e))?;
    }
    let runs = directory.join(".wraith/runs");
    std::fs::create_dir_all(&runs).map_err(|e| error::io("create run directory", &runs, e))?;
    println!(
        "Created {} and {}.\nRun: wraith --config {} run --save baseline\nThe starter agent requires Python 3; WRAITH itself does not.",
        path.display(),
        agent_path.display(),
        path.display()
    );
    Ok(())
}

async fn execute(cli: Cli, cancellation: Cancellation) -> Result<u8, Error> {
    match cli.command {
        Commands::Init => {
            init(&cli.config)?;
            Ok(0)
        }
        Commands::Run {
            scenario,
            save,
            samples,
            output,
        } => {
            let (config, directory) = config::load(&cli.config)?;
            // Validate the save name before executing potentially expensive agents.
            let save_path = save
                .as_deref()
                .map(|name| snapshot::named_path(&directory, name))
                .transpose()?;
            let options = runner::RunOptions {
                samples,
                cancellation: cancellation.clone(),
            };
            let run = runner::run_with_options(&config, &directory, scenario.as_deref(), &options)
                .await?;
            if cancellation.is_cancelled() {
                return Err(Error::Cancelled);
            }
            if let Some(path) = &save_path {
                snapshot::save(path, &run)?;
            }
            match output {
                Output::Human => {
                    render::run(&run);
                    if let Some(path) = save_path {
                        println!("Saved: {}", path.display());
                    }
                }
                Output::Json => println!(
                    "{}",
                    serde_json::to_string_pretty(&run)
                        .map_err(|e| Error::Artifact(e.to_string()))?
                ),
            }
            Ok(if run.scenarios.iter().any(|s| s.run.error.is_some()) {
                2
            } else if run.scenarios.iter().all(|s| s.passed) {
                0
            } else {
                1
            })
        }
        Commands::Compare {
            baseline,
            candidate,
            policy,
            output,
        } => {
            // Comparing artifacts requires no agent or configuration parsing.
            let directory = cli
                .config
                .parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or(Path::new("."));
            let b = snapshot::load(&snapshot::resolve(directory, &baseline)?)?;
            let c = snapshot::load(&snapshot::resolve(directory, &candidate)?)?;
            let trusted = policy.as_deref().map(config::load).transpose()?;
            let report = comparison::compare_with_policy(
                &b,
                &c,
                trusted.as_ref().map(|(config, _)| config),
            )?;
            match output {
                Output::Human => render::comparison(&baseline, &candidate, &report),
                Output::Json => println!(
                    "{}",
                    serde_json::to_string_pretty(&report)
                        .map_err(|e| Error::Artifact(e.to_string()))?
                ),
            }
            Ok(if report.execution_errors {
                2
            } else if report.passed {
                0
            } else if report.inconclusive {
                3
            } else {
                1
            })
        }
    }
}

#[tokio::main]
async fn main() -> ExitCode {
    let cli = Cli::parse();
    let cancellation = Cancellation::default();
    let execution = execute(cli, cancellation.clone());
    tokio::pin!(execution);
    let result = tokio::select! {
        biased;
        signal = tokio::signal::ctrl_c() => {
            cancellation.cancel();
            // Await the same future so the runner can terminate and reap its child.
            let _ = execution.await;
            match signal {
                Ok(()) => Err(Error::Cancelled),
                Err(source) => Err(Error::Io { action: "listen for", path: "Ctrl-C".into(), source }),
            }
        }
        result = &mut execution => result,
    };
    match result {
        Ok(code) => ExitCode::from(code),
        Err(Error::Cancelled) => {
            eprintln!("{}", Error::Cancelled);
            ExitCode::from(130)
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
    }
}
