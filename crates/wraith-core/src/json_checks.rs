//! Small, deterministic assertions over adapter output. Paths are RFC 6901 JSON
//! pointers; no query language, code execution, wildcard expansion, or coercion.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JsonAssertion {
    pub path: String,
    /// If provided, `path` must select a nonempty array; check this pointer on each item.
    pub each: Option<String>,
    pub check: JsonCheck,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum JsonCheck {
    Equals {
        value: Value,
    },
    In {
        values: Vec<Value>,
    },
    NotIn {
        values: Vec<Value>,
    },
    Range {
        min: Option<f64>,
        max: Option<f64>,
        #[serde(default)]
        integer: bool,
    },
    Length {
        min: Option<u64>,
        max: Option<u64>,
    },
    Unique {
        by: Option<String>,
    },
    Exists,
}

pub struct JsonResult {
    pub passed: bool,
    pub observed: Value,
    pub message: String,
}

fn valid_pointer(path: &str) -> bool {
    if !path.is_empty() && !path.starts_with('/') {
        return false;
    }
    let mut chars = path.chars();
    while let Some(ch) = chars.next() {
        if ch == '~' && !matches!(chars.next(), Some('0' | '1')) {
            return false;
        }
    }
    true
}

impl JsonAssertion {
    pub fn validate(&self) -> Result<(), String> {
        if !valid_pointer(&self.path) || self.each.as_ref().is_some_and(|p| !valid_pointer(p)) {
            return Err("path and each must be JSON pointers (empty or starting with /, with only ~0/~1 escapes)".into());
        }
        match &self.check {
            JsonCheck::Range { min, max, .. } => {
                if min.is_none() && max.is_none()
                    || min.is_some_and(|v| !v.is_finite())
                    || max.is_some_and(|v| !v.is_finite())
                    || min.zip(*max).is_some_and(|(a, b)| a > b)
                {
                    return Err("range needs finite min/max bounds with min <= max".into());
                }
            }
            JsonCheck::Length { min, max } => {
                if min.is_none() && max.is_none() || min.zip(*max).is_some_and(|(a, b)| a > b) {
                    return Err("length needs min/max bounds with min <= max".into());
                }
            }
            JsonCheck::In { values } | JsonCheck::NotIn { values } if values.is_empty() => {
                return Err("in/not_in needs at least one value".into());
            }
            JsonCheck::Unique { by: Some(p) } if !valid_pointer(p) => {
                return Err("unique.by must be a JSON pointer".into());
            }
            _ => {}
        }
        Ok(())
    }

    pub fn evaluate(&self, output: Option<&Value>) -> JsonResult {
        let selected = output.and_then(|value| value.pointer(&self.path));
        let mut issues = Vec::new();
        let mut observed = json!({"present": selected.is_some(), "value": selected});
        if let Some(each) = &self.each {
            match selected.and_then(Value::as_array) {
                Some(items) if !items.is_empty() => {
                    let mut evidence = Vec::new();
                    for (index, item) in items.iter().enumerate() {
                        let value = item.pointer(each);
                        let location = format!("{}/{index}{each}", self.path);
                        if !value.is_some_and(|value| self.check.accepts(value)) {
                            issues.push(location.clone());
                        }
                        evidence.push(
                            json!({"path": location, "present": value.is_some(), "value": value}),
                        );
                    }
                    observed = json!(evidence);
                }
                _ => issues.push(format!(
                    "{} must select a nonempty array for each",
                    self.path
                )),
            }
        } else if !selected.is_some_and(|value| self.check.accepts(value)) {
            issues.push(self.path.clone());
        }
        let passed = issues.is_empty();
        JsonResult {
            passed,
            observed,
            message: if passed {
                format!("JSON assertion at {:?} passed", self.path)
            } else {
                format!(
                    "JSON assertion {} failed at {} (missing values and wrong types fail)",
                    json!(self.check),
                    json!(issues)
                )
            },
        }
    }
}

impl JsonCheck {
    fn accepts(&self, value: &Value) -> bool {
        match self {
            Self::Exists => !value.is_null(),
            Self::Equals { value: expected } => value == expected,
            Self::In { values } => values.contains(value),
            Self::NotIn { values } => !value.is_null() && !values.contains(value),
            Self::Range { min, max, integer } => value.as_f64().is_some_and(|v| {
                v.is_finite()
                    && (!integer || v.fract() == 0.0)
                    && min.is_none_or(|m| v >= m)
                    && max.is_none_or(|m| v <= m)
            }),
            Self::Length { min, max } => {
                let length = match value {
                    Value::Array(v) => Some(v.len()),
                    Value::String(v) => Some(v.chars().count()),
                    _ => None,
                };
                length.is_some_and(|n| {
                    min.is_none_or(|m| n as u64 >= m) && max.is_none_or(|m| n as u64 <= m)
                })
            }
            Self::Unique { by } => {
                let Some(items) = value.as_array() else {
                    return false;
                };
                let mut seen = HashSet::new();
                items.iter().all(|item| {
                    let selected = by.as_ref().map_or(Some(item), |p| item.pointer(p));
                    selected
                        .filter(|v| !v.is_null())
                        .is_some_and(|v| seen.insert(v.to_string()))
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn assertion(path: &str, each: Option<&str>, check: JsonCheck) -> JsonAssertion {
        JsonAssertion {
            path: path.into(),
            each: each.map(str::to_owned),
            check,
        }
    }
    #[test]
    fn missing_wrong_type_empty_arrays_and_duplicates_fail_closed() {
        let check = assertion(
            "/exercises",
            Some("/sets"),
            JsonCheck::Range {
                min: Some(3.0),
                max: Some(3.0),
                integer: true,
            },
        );
        assert!(
            check
                .evaluate(Some(&json!({"exercises":[{"sets":3}]})))
                .passed
        );
        for value in [
            json!({}),
            json!({"exercises":[]}),
            json!({"exercises":{}}),
            json!({"exercises":[{}]}),
            json!({"exercises":[{"sets":"3"}]}),
            json!({"exercises":[{"sets":3.1}]}),
        ] {
            assert!(!check.evaluate(Some(&value)).passed);
        }
        assert!(!check.evaluate(None).passed);
        let check = assertion(
            "/exercises",
            None,
            JsonCheck::Unique {
                by: Some("/id".into()),
            },
        );
        assert!(
            !check
                .evaluate(Some(&json!({"exercises":[{"id":"a"},{"id":"a"}]})))
                .passed
        );
        assert!(!check.evaluate(Some(&json!({"exercises":[{}]}))).passed);
        assert!(
            check
                .evaluate(Some(&json!({"exercises":[{"id":"a"},{"id":"b"}]})))
                .passed
        );
    }
    #[test]
    fn pointers_types_membership_and_bounds_are_explicit() {
        let check = assertion(
            "/a~1b/~0key",
            None,
            JsonCheck::Equals {
                value: json!(false),
            },
        );
        assert!(check.evaluate(Some(&json!({"a/b":{"~key":false}}))).passed);
        for op in [
            JsonCheck::In {
                values: vec![json!("barbell")],
            },
            JsonCheck::NotIn {
                values: vec![json!("barbell")],
            },
        ] {
            let check = assertion("/equipment", Some(""), op);
            assert!(!check.evaluate(Some(&json!({"equipment":[null]}))).passed);
        }
        assert!(
            assertion(
                "",
                None,
                JsonCheck::Length {
                    min: Some(2),
                    max: Some(2)
                }
            )
            .evaluate(Some(&json!("é字")))
            .passed
        );
        assert!(!assertion("bad", None, JsonCheck::Exists).validate().is_ok());
        assert!(
            assertion("/bad~2", None, JsonCheck::Exists)
                .validate()
                .is_err()
        );
        assert!(
            assertion(
                "",
                None,
                JsonCheck::Range {
                    min: Some(5.0),
                    max: Some(4.0),
                    integer: false
                }
            )
            .validate()
            .is_err()
        );
        assert!(
            serde_json::from_value::<JsonCheck>(json!({"op":"range","max":3,"typo":true})).is_err()
        );
    }
}
