use crate::{
    error::{self, Error},
    model::Metadata,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::HashSet,
    path::{Path, PathBuf},
};

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub version: u32,
    pub agent: AgentConfig,
    pub tests: Vec<Scenario>,
    #[serde(default)]
    pub thresholds: Thresholds,
    #[serde(default)]
    pub comparison: ComparisonOptions,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentConfig {
    pub command: String,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
}
fn default_timeout() -> u64 {
    30_000
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComparisonOptions {
    #[serde(default)]
    pub tool_arguments: bool,
    #[serde(default)]
    pub document_ids: bool,
    /// Omit to retain strict observed-rate comparison.
    pub statistical: Option<StatisticalPolicy>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StatisticalPolicy {
    pub min_samples: u32,
    /// Allowed increase in each failure probability, in percentage points.
    pub max_failure_rate_increase_pp: f64,
    /// Family-wise error budget for this one comparison (not repeated peeking).
    pub alpha: f64,
}

impl ComparisonOptions {
    pub fn validate(&self) -> Result<(), Error> {
        if let Some(p) = &self.statistical {
            if !(2..=1000).contains(&p.min_samples)
                || !p.max_failure_rate_increase_pp.is_finite()
                || !(0.0..=100.0).contains(&p.max_failure_rate_increase_pp)
                || !p.alpha.is_finite()
                || !(0.0 < p.alpha && p.alpha <= 0.25)
            {
                return Err(Error::Config("comparison.statistical: min_samples must be 2–1000, max_failure_rate_increase_pp finite and 0–100, and alpha finite and in (0, 0.25]".into()));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Scenario {
    pub id: String,
    pub input: Value,
    #[serde(default)]
    pub metadata: Metadata,
    #[serde(default)]
    pub expect: Expectations,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Expectations {
    #[serde(default)]
    pub json: Vec<crate::json_checks::JsonAssertion>,
    #[serde(default)]
    pub output_contains: Vec<String>,
    #[serde(default)]
    pub output_not_contains: Vec<String>,
    #[serde(default)]
    pub tools_called: Vec<String>,
    #[serde(default)]
    pub tools_not_called: Vec<String>,
    #[serde(default)]
    pub sources: Sources,
    pub latency_ms: Option<Limit>,
    pub tokens: Option<Limit>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Sources {
    #[serde(default)]
    pub include: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Limit {
    pub max: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Thresholds {
    pub success_rate: Option<SuccessThreshold>,
    pub latency: Option<IncreaseThreshold>,
    pub tokens: Option<IncreaseThreshold>,
    pub cost: Option<IncreaseThreshold>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SuccessThreshold {
    pub regression: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IncreaseThreshold {
    pub max_increase_percent: f64,
}

impl Thresholds {
    pub fn validate(&self) -> Result<(), Error> {
        let checks = [
            (
                "success_rate.regression",
                self.success_rate.as_ref().map(|t| t.regression),
                true,
            ),
            (
                "latency.max_increase_percent",
                self.latency.as_ref().map(|t| t.max_increase_percent),
                false,
            ),
            (
                "tokens.max_increase_percent",
                self.tokens.as_ref().map(|t| t.max_increase_percent),
                false,
            ),
            (
                "cost.max_increase_percent",
                self.cost.as_ref().map(|t| t.max_increase_percent),
                false,
            ),
        ];
        for (path, value, bounded) in checks {
            if value.is_some_and(|v| !v.is_finite() || v < 0.0 || (bounded && v > 100.0)) {
                return Err(Error::Config(format!(
                    "thresholds.{path}: expected a finite nonnegative number{}",
                    if bounded {
                        " up to 100 percentage points"
                    } else {
                        ""
                    }
                )));
            }
        }
        Ok(())
    }
}

pub fn validate_scenarios(scenarios: &[Scenario]) -> Result<(), Error> {
    if scenarios.is_empty() {
        return Err(Error::Config(
            "tests: expected at least one scenario".into(),
        ));
    }
    let mut ids = HashSet::new();
    for (i, scenario) in scenarios.iter().enumerate() {
        if scenario.id.trim().is_empty() || !ids.insert(&scenario.id) {
            return Err(Error::Config(format!(
                "tests[{i}].id: expected a nonempty, unique scenario ID; received {:?}",
                scenario.id
            )));
        }
        if scenario.input.is_null() {
            return Err(Error::Config(format!(
                "tests[{i}].input: expected a non-null JSON value"
            )));
        }
        let e = &scenario.expect;
        for assertion in &e.json {
            assertion
                .validate()
                .map_err(|message| Error::Config(format!("tests[{i}].expect.json: {message}")))?;
        }
        for (name, list) in [
            ("output_contains", &e.output_contains),
            ("output_not_contains", &e.output_not_contains),
            ("tools_called", &e.tools_called),
            ("tools_not_called", &e.tools_not_called),
            ("sources.include", &e.sources.include),
        ] {
            let mut unique = HashSet::new();
            if list
                .iter()
                .any(|s| s.trim().is_empty() || !unique.insert(s))
            {
                return Err(Error::Config(format!(
                    "tests[{i}].expect.{name}: expected unique nonempty strings"
                )));
            }
        }
        if e.tools_called
            .iter()
            .any(|s| e.tools_not_called.contains(s))
            || e.output_contains
                .iter()
                .any(|s| e.output_not_contains.contains(s))
        {
            return Err(Error::Config(format!(
                "tests[{i}].expect: contradictory required and forbidden values"
            )));
        }
        for (name, limit) in [("latency_ms", &e.latency_ms), ("tokens", &e.tokens)] {
            if limit.as_ref().is_some_and(|l| l.max == 0) {
                return Err(Error::Config(format!(
                    "tests[{i}].expect.{name}.max: expected a positive integer; received 0"
                )));
            }
        }
    }
    Ok(())
}

pub fn parse(yaml: &str) -> Result<Config, Error> {
    let de = serde_yaml_ng::Deserializer::from_str(yaml);
    let config: Config =
        serde_path_to_error::deserialize(de).map_err(|e| Error::Config(e.to_string()))?;
    if config.version != 1 {
        return Err(Error::Config(format!(
            "version: unsupported schema {}; this WRAITH supports version 1",
            config.version
        )));
    }
    command_args(&config.agent.command)?;
    if config.agent.timeout_ms == 0 || config.agent.timeout_ms > 86_400_000 {
        return Err(Error::Config(
            "agent.timeout_ms: expected an integer between 1 and 86400000".into(),
        ));
    }
    validate_scenarios(&config.tests)?;
    config.thresholds.validate()?;
    config.comparison.validate()?;
    Ok(config)
}

pub fn command_args(command: &str) -> Result<Vec<String>, Error> {
    let args = shell_words::split(command)
        .map_err(|e| Error::Config(format!("agent.command: {e}; check quoting")))?;
    if args.first().is_none_or(|s| s.trim().is_empty()) {
        return Err(Error::Config(
            "agent.command: expected an executable and optional arguments".into(),
        ));
    }
    Ok(args)
}

/// Agent paths and artifact paths are relative to the configuration's directory.
pub fn load(path: &Path) -> Result<(Config, PathBuf), Error> {
    let absolute =
        std::fs::canonicalize(path).map_err(|e| error::io("read configuration", path, e))?;
    let yaml = std::fs::read_to_string(&absolute)
        .map_err(|e| error::io("read configuration", &absolute, e))?;
    let config = parse(&yaml)?;
    let directory = absolute
        .parent()
        .ok_or_else(|| Error::Config("configuration has no parent directory".into()))?
        .to_path_buf();
    Ok((config, directory))
}

#[cfg(test)]
mod tests {
    use super::*;
    const BASE: &str = "version: 1\nagent:\n  command: 'python3 agent.py'\ntests:\n  - id: pto\n    input: {text: hi}\n";
    #[test]
    fn validates_boundary_and_reports_paths() {
        assert!(parse(BASE).is_ok());
        let bad = format!("{BASE}    expect:\n      latency_ms: {{max: five}}\n");
        assert!(
            parse(&bad)
                .unwrap_err()
                .to_string()
                .contains("tests[0].expect.latency_ms.max")
        );
        assert!(parse(&BASE.replace("version: 1", "version: 8")).is_err());
        assert!(parse(&format!("{BASE}    typo: true\n")).is_err());
        assert!(parse(&format!("{BASE}  - id: pto\n    input: hi\n")).is_err());
        assert!(
            parse(&format!(
                "{BASE}thresholds:\n  tokens: {{max_increase_percent: -1}}\n"
            ))
            .is_err()
        );
    }
    #[test]
    fn rejects_invalid_statistical_policies() {
        for policy in [
            "{min_samples: 1, alpha: 0.05, max_failure_rate_increase_pp: 10}",
            "{min_samples: 1001, alpha: 0.05, max_failure_rate_increase_pp: 10}",
            "{min_samples: 20, alpha: 0, max_failure_rate_increase_pp: 10}",
            "{min_samples: 20, alpha: 0.5, max_failure_rate_increase_pp: 10}",
            "{min_samples: 20, alpha: 0.05, max_failure_rate_increase_pp: -1}",
            "{min_samples: 20, alpha: 0.05, max_failure_rate_increase_pp: .nan}",
            "{min_samples: 20, alpha: 0.05, max_failure_rate_increase_pp: 101}",
        ] {
            assert!(parse(&format!("{BASE}comparison:\n  statistical: {policy}\n")).is_err());
        }
    }
    #[test]
    fn command_quotes_are_arguments_not_shell_execution() {
        assert_eq!(
            command_args("python3 'path with spaces/agent.py' '$SECRET'").unwrap(),
            ["python3", "path with spaces/agent.py", "$SECRET"]
        );
        assert!(command_args("'").is_err());
        assert!(command_args(" ").is_err());
    }
}
