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
    /// Import a JSON array of reviewed scenarios, including explicit expectations.
    Import {
        #[arg(long)]
        file: PathBuf,
    },
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
        #[arg(long, required_unless_present_any=["json_equals", "require_tool", "forbid_tool", "contains"], conflicts_with_all=["json_equals", "require_tool", "forbid_tool", "contains"])]
        expect: Option<PathBuf>,
        /// Require exact JSON equality at a pointer; repeat for additional fields.
        #[arg(long, num_args=2, value_names=["POINTER", "JSON"], allow_hyphen_values=true)]
        json_equals: Vec<String>,
        #[arg(long)]
        require_tool: Vec<String>,
        #[arg(long)]
        forbid_tool: Vec<String>,
        #[arg(long)]
        contains: Vec<String>,
    },
}

fn read(path: &Path) -> Result<Value, Error> {
    serde_json::from_slice(&fs::read(path).map_err(|e| error::io("read case", path, e))?)
        .map_err(|e| Error::Config(format!("{}: {e}", path.display())))
}

pub fn reviewed(path: &Path) -> Result<Vec<Scenario>, Error> {
    let value = read(path)?;
    let values = value.as_array().filter(|v| !v.is_empty()).ok_or_else(|| {
        Error::Config("Case import requires a nonempty JSON array of reviewed scenarios".into())
    })?;
    if values
        .iter()
        .any(|v| !v.get("expect").is_some_and(Value::is_object))
    {
        return Err(Error::Config("Every imported case needs an explicit reviewed expect object; observed output is never assumed correct".into()));
    }
    let cases: Vec<Scenario> =
        serde_json::from_value(value).map_err(|e| Error::Config(format!("Cases: {e}")))?;
    config::validate_scenarios(&cases)?;
    Ok(cases)
}

pub fn execute(path: &Path, command: Commands) -> Result<(), Error> {
    if let Commands::Import { file } = command {
        let cases = reviewed(&file)?;
        let count = cases.len();
        let (mut cfg, _) = config::load(path)?;
        cfg.tests.extend(cases);
        config::validate_scenarios(&cfg.tests)?;
        workflow::atomic_json(path, &cfg)?;
        println!(
            "Imported {count} reviewed cases. Review the suite, then deliberately refresh the baseline with wraith baseline --replace. Existing history is retained."
        );
        return Ok(());
    }
    let Commands::Add {
        id,
        input,
        from_run,
        scenario,
        expect,
        json_equals,
        require_tool,
        forbid_tool,
        contains,
    } = command
    else {
        unreachable!()
    };
    let (mut cfg, _) = config::load(path)?;
    let expectations: Expectations = if let Some(file) = expect {
        serde_json::from_value(read(&file)?)
            .map_err(|e| Error::Config(format!("Expectations: {e}")))?
    } else {
        let mut expectations = Expectations {
            tools_called: require_tool,
            tools_not_called: forbid_tool,
            output_contains: contains,
            ..Default::default()
        };
        for pair in json_equals.chunks_exact(2) {
            let value = serde_json::from_str(&pair[1])
                .map_err(|e| Error::Config(format!("--json-equals needs a JSON value: {e}")))?;
            expectations
                .json
                .push(wraith_core::json_checks::JsonAssertion {
                    path: pair[0].clone(),
                    each: None,
                    check: wraith_core::json_checks::JsonCheck::Equals { value },
                });
        }
        expectations
    };
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
