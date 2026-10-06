use crate::{
    config::validate_scenarios,
    error::{self, Error},
    evaluation::evaluate,
    model::{RunSnapshot, SCHEMA_VERSION},
};
use std::{
    collections::BTreeMap,
    io::Write,
    path::{Path, PathBuf},
};

pub fn named_path(directory: &Path, name: &str) -> Result<PathBuf, Error> {
    if name.is_empty()
        || name.len() > 128
        || !name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err(Error::Artifact("Run names must contain 1–128 ASCII letters, digits, hyphens, or underscores; use an explicit .json path to load other files.".into()));
    }
    Ok(directory.join(".wraith/runs").join(format!("{name}.json")))
}

pub fn resolve(directory: &Path, reference: &str) -> Result<PathBuf, Error> {
    let path = Path::new(reference);
    if path.extension().is_some_and(|e| e == "json") {
        Ok(directory.join(path))
    } else {
        named_path(directory, reference)
    }
}

pub fn save(path: &Path, snapshot: &RunSnapshot) -> Result<(), Error> {
    let parent = path
        .parent()
        .ok_or_else(|| Error::Artifact("Run path has no parent directory".into()))?;
    std::fs::create_dir_all(parent).map_err(|e| error::io("create run directory", parent, e))?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)
        .map_err(|e| error::io("create temporary run", parent, e))?;
    serde_json::to_writer_pretty(&mut temporary, snapshot)
        .map_err(|e| Error::Artifact(format!("Could not serialize run: {e}")))?;
    temporary
        .write_all(b"\n")
        .map_err(|e| error::io("write run", path, e))?;
    temporary
        .as_file()
        .sync_all()
        .map_err(|e| error::io("flush run", path, e))?;
    temporary
        .persist(path)
        .map_err(|e| error::io("save run", path, e.error))?;
    Ok(())
}

pub fn load(path: &Path) -> Result<RunSnapshot, Error> {
    let contents = std::fs::read(path).map_err(|e| error::io("read run", path, e))?;
    let mut value: serde_json::Value = serde_json::from_slice(&contents)
        .map_err(|e| Error::Artifact(format!("Invalid JSON in {}: {e}", path.display())))?;
    let schema = value.get("schemaVersion").and_then(|v| v.as_u64());
    if schema == Some(1) {
        value["schemaVersion"] = SCHEMA_VERSION.into();
        value["samplesPerScenario"] = 1.into();
        value["comparison"] = serde_json::json!({});
        if let Some(scenarios) = value.get_mut("scenarios").and_then(|v| v.as_array_mut()) {
            for scenario in scenarios {
                let object = scenario.as_object_mut().ok_or_else(|| {
                    Error::Artifact("Schema 1 scenarios must contain objects".into())
                })?;
                object.insert("sampleIndex".into(), 1.into());
            }
        }
    } else if schema == Some(2) {
        // Schema 2 predates statistical policies and therefore always gates strictly.
        value["schemaVersion"] = SCHEMA_VERSION.into();
        if value["comparison"].get("statistical").is_some() {
            return Err(Error::Artifact(
                "Schema 2 cannot contain a statistical policy".into(),
            ));
        }
    } else if schema != Some(u64::from(SCHEMA_VERSION)) {
        return Err(Error::Artifact(format!(
            "Unsupported run schemaVersion {} in {}. This WRAITH supports schemas 1–3; upgrade WRAITH for newer schemas.",
            value
                .get("schemaVersion")
                .unwrap_or(&serde_json::Value::Null),
            path.display()
        )));
    }
    let snapshot: RunSnapshot = serde_json::from_value(value)
        .map_err(|e| Error::Artifact(format!("Invalid run in {}: {e}", path.display())))?;
    validate(&snapshot)?;
    Ok(snapshot)
}

pub fn validate(snapshot: &RunSnapshot) -> Result<(), Error> {
    if snapshot.schema_version != SCHEMA_VERSION {
        return Err(Error::Artifact(
            "Unsupported internal run schema; expected schema 3".into(),
        ));
    }
    if !(1..=1000).contains(&snapshot.samples_per_scenario) {
        return Err(Error::Artifact(
            "samplesPerScenario must be between 1 and 1000".into(),
        ));
    }
    let groups = crate::sampling::groups(snapshot);
    let mut scenarios = Vec::new();
    for (id, observations) in groups {
        let first = observations[0];
        let mut indexes = BTreeMap::new();
        for observation in &observations {
            if observation.scenario != first.scenario
                || observation.sample_index == 0
                || observation.sample_index > snapshot.samples_per_scenario
                || indexes.insert(observation.sample_index, ()).is_some()
            {
                return Err(Error::Artifact(format!(
                    "Inconsistent or duplicate sample for {id:?}"
                )));
            }
        }
        if observations.len() != snapshot.samples_per_scenario as usize {
            return Err(Error::Artifact(format!(
                "Incomplete sample set for {id:?}; expected {} observations",
                snapshot.samples_per_scenario
            )));
        }
        scenarios.push(first.scenario.clone());
    }
    validate_scenarios(&scenarios).map_err(|e| Error::Artifact(e.to_string()))?;
    snapshot
        .thresholds
        .validate()
        .map_err(|e| Error::Artifact(e.to_string()))?;
    snapshot
        .comparison
        .validate()
        .map_err(|e| Error::Artifact(e.to_string()))?;
    for s in &snapshot.scenarios {
        let r = &s.run;
        if r.scenario_id != s.scenario.id
            || r.input != s.scenario.input
            || r.response.is_some() == r.error.is_some()
        {
            return Err(Error::Artifact(format!(
                "Inconsistent run data for {:?}",
                s.scenario.id
            )));
        }
        if let Some(response) = &r.response {
            response.validate(&s.scenario.id).map_err(Error::Artifact)?;
        }
        // Recompute deterministic evaluations rather than trusting serialized pass flags.
        let expected = evaluate(&s.scenario, r);
        if expected != s.evaluations
            || s.passed != (r.error.is_none() && expected.iter().all(|e| e.passed))
        {
            return Err(Error::Artifact(format!(
                "Inconsistent evaluation results for {:?}",
                s.scenario.id
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_cannot_escape_the_run_directory() {
        for name in ["../secret", "", ".", "a/b", "x.json"] {
            assert!(named_path(Path::new("."), name).is_err());
        }
        assert!(named_path(Path::new("."), "baseline-1").is_ok());
    }
    #[test]
    fn rejects_future_schema_before_deserializing_fields() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("run.json");
        std::fs::write(&path, r#"{"schemaVersion":8}"#).unwrap();
        assert!(
            load(&path)
                .unwrap_err()
                .to_string()
                .contains("supports schemas 1–3")
        );
    }
}
