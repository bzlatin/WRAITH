mod cases;
mod ci;
mod project;
mod render;
mod report;
mod workflow;
use clap::{Parser, Subcommand, ValueEnum};
use std::{
    path::{Path, PathBuf},
    process::ExitCode,
};
use wraith_core::{cancellation::Cancellation, comparison, config, error::Error, runner, snapshot};

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
    Init {
        #[arg(long)]
        entrypoint: Option<String>,
        #[arg(long, value_parser=["python","typescript"])]
        language: Option<String>,
        #[arg(long)]
        runtime: Option<String>,
        #[arg(long, default_value="offline", value_parser=["offline","live"])]
        mode: String,
        #[arg(long)]
        model: Option<String>,
        #[arg(long)]
        require_env: Vec<String>,
        #[arg(long, default_value="json", value_parser=["json","tools","rag"])]
        template: String,
        #[arg(long)]
        demo: bool,
    },
    /// Print the validated configuration as JSON.
    Config,
    /// Diagnose configuration and dependencies without executing your agent.
    Doctor {
        #[arg(long, value_enum, default_value_t=Output::Human)]
        output: Output,
    },
    /// Save an accepted baseline and begin an experiment.
    Baseline {
        #[arg(long, value_parser=clap::value_parser!(u32).range(1..=1000))]
        samples: Option<u32>,
        #[arg(long)]
        replace: bool,
        #[arg(long)]
        allow_live: bool,
        #[arg(long, value_parser=clap::value_parser!(u32).range(1..=10000))]
        max_requests: Option<u32>,
        #[arg(long, value_enum, default_value_t=Output::Human)]
        output: Output,
    },
    /// Evaluate current code against the accepted baseline and write a report.
    Check {
        #[arg(long, value_parser=clap::value_parser!(u32).range(1..=1000))]
        samples: Option<u32>,
        #[arg(long)]
        allow_live: bool,
        #[arg(long, value_enum, default_value_t=Output::Human)]
        output: Output,
    },
    /// List completed local baselines and checks.
    History {
        #[arg(long, value_enum, default_value_t=Output::Human)]
        output: Output,
    },
    /// Create or refresh the local HTML history or a specific run report.
    Report {
        #[arg(long)]
        run: Option<String>,
        #[arg(long)]
        html: Option<PathBuf>,
    },
    /// Add reviewed scenarios from inputs or saved failures.
    Cases {
        #[command(subcommand)]
        command: cases::Commands,
    },
    /// Generate an offline pull-request evaluation workflow.
    Ci {
        #[command(subcommand)]
        command: ci::Commands,
    },
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
        /// Write a self-contained HTML comparison report.
        #[arg(long)]
        html: Option<PathBuf>,
        #[arg(long, value_enum, default_value_t = Output::Human)]
        output: Output,
    },
}

#[derive(Clone, Copy, ValueEnum)]
enum Output {
    Human,
    Json,
}

async fn execute(cli: Cli, cancellation: Cancellation) -> Result<u8, Error> {
    match cli.command {
        Commands::Init {
            entrypoint,
            language,
            runtime,
            mode,
            model,
            require_env,
            template,
            demo,
        } => {
            project::init(
                &cli.config,
                project::InitOptions {
                    entrypoint,
                    language,
                    runtime,
                    mode,
                    model,
                    required_env: require_env,
                    template,
                    demo,
                },
            )?;
            Ok(0)
        }
        Commands::Config => {
            let (config, _) = config::load(&cli.config)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&config).map_err(|e| Error::Config(e.to_string()))?
            );
            Ok(0)
        }
        Commands::Doctor { output } => {
            let (value, passed) = project::doctor(&cli.config)?;
            if matches!(output, Output::Json) {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&value)
                        .map_err(|e| Error::Config(e.to_string()))?
                );
            } else {
                for check in value["checks"].as_array().unwrap() {
                    println!(
                        "{}  {}",
                        check["status"].as_str().unwrap_or("info").to_uppercase(),
                        check["message"].as_str().unwrap_or("")
                    );
                }
            }
            Ok(if passed { 0 } else { 2 })
        }
        Commands::Baseline {
            samples,
            replace,
            allow_live,
            max_requests,
            output,
        } => {
            workflow::execute(
                &cli.config,
                true,
                workflow::Options {
                    samples,
                    replace,
                    allow_live,
                    max_requests,
                    json: matches!(output, Output::Json),
                },
                cancellation,
            )
            .await
        }
        Commands::Check {
            samples,
            allow_live,
            output,
        } => {
            workflow::execute(
                &cli.config,
                false,
                workflow::Options {
                    samples,
                    replace: false,
                    allow_live,
                    max_requests: None,
                    json: matches!(output, Output::Json),
                },
                cancellation,
            )
            .await
        }
        Commands::History { output } => {
            let records = workflow::history(project::directory(&cli.config))?;
            if matches!(output, Output::Json) {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&records)
                        .map_err(|e| Error::Artifact(e.to_string()))?
                );
            } else if records.is_empty() {
                println!("No completed runs. Start with wraith baseline.");
            } else {
                for record in records {
                    println!(
                        "{}  {}  {}  {} samples",
                        record.id, record.kind, record.outcome, record.samples
                    );
                }
            }
            Ok(0)
        }
        Commands::Report { run, html } => {
            let path = workflow::render_saved(&cli.config, run.as_deref(), html.as_deref())?;
            println!("Report: {}", path.display());
            Ok(0)
        }
        Commands::Cases { command } => {
            cases::execute(&cli.config, command)?;
            Ok(0)
        }
        Commands::Ci { command } => {
            ci::execute(&cli.config, command)?;
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
                request_budget: None,
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
            html,
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
            if let Some(path) = html {
                report::save(&path, &c, Some(&b), Some(&report), None)?;
            }
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
