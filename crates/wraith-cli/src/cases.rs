use crate::workflow;
use clap::Subcommand;
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
};
use wraith_core::{
    config::{self, Expectations, Scenario},
    error::{self, Error},
    snapshot,
};

#[derive(Subcommand)]
pub enum Commands {
    /// Add a reviewed regression case from JSON input or a saved run.
    Add {
        #[arg(long)]
        id: String,
        #[arg(
            long,
            conflicts_with = "from_run",
            required_unless_present = "from_run"
        )]
        input: Option<PathBuf>,
        #[arg(long, conflicts_with = "input")]
        from_run: Option<PathBuf>,
        /// Scenario to copy from a saved run (first observation is used).
        #[arg(long, requires = "from_run")]
        scenario: Option<String>,
        /// JSON expectation object. Required: observed output is never assumed correct.
        #[arg(long)]
        expect: PathBuf,
    },
}

fn read(path: &Path) -> Result<Value, Error> {
    serde_json::from_slice(&fs::read(path).map_err(|e| error::io("read case", path, e))?)
        .map_err(|e| Error::Config(format!("{}: {e}", path.display())))
}

pub fn execute(path: &Path, command: Commands) -> Result<(), Error> {
    let Commands::Add {
        id,
        input,
        from_run,
        scenario,
        expect,
    } = command;
    let (mut cfg, _) = config::load(path)?;
    let expectations: Expectations = serde_json::from_value(read(&expect)?)
        .map_err(|e| Error::Config(format!("Expectations: {e}")))?;
    let (input, metadata) = if let Some(file) = input {
        (read(&file)?, Default::default())
    } else {
        let run = snapshot::load(
            from_run
                .as_ref()
                .ok_or_else(|| Error::Config("Specify --input or --from-run".into()))?,
        )?;
        let source = if let Some(id) = scenario {
            run.scenarios.iter().find(|s| s.scenario.id == id)
        } else if wraith_core::sampling::groups(&run).len() == 1 {
            run.scenarios.first()
        } else {
            return Err(Error::Config(
                "Choose --scenario when a run contains multiple cases".into(),
            ));
        }
        .ok_or_else(|| Error::Config("Scenario missing from saved run".into()))?;
        (
            source.scenario.input.clone(),
            source.scenario.metadata.clone(),
        )
    };
    cfg.tests.push(Scenario {
        id: id.clone(),
        input,
        metadata,
        expect: expectations,
    });
    config::validate_scenarios(&cfg.tests)?;
    workflow::atomic_json(path, &cfg)?;
    println!(
        "Added {id}. Review the expectations, then deliberately refresh the baseline with wraith baseline --replace. Existing history is retained."
    );
    Ok(())
}
