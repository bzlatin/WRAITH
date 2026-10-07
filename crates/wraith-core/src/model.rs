use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub type Metadata = Map<String, Value>;
pub const PROTOCOL_VERSION: u32 = 1;
pub const SCHEMA_VERSION: u32 = 4;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentRequest<'a> {
    pub protocol_version: u32,
    pub scenario_id: &'a str,
    pub input: &'a Value,
    pub metadata: &'a Metadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AgentResponse {
    pub protocol_version: u32,
    pub scenario_id: String,
    pub output: Value,
    #[serde(default)]
    pub tool_calls: Vec<ToolCall>,
    #[serde(default)]
    pub retrievals: Vec<Retrieval>,
    pub usage: Option<TokenUsage>,
    pub estimated_cost_usd: Option<f64>,
    #[serde(default)]
    pub metadata: Metadata,
}

impl AgentResponse {
    pub fn validate(&self, scenario_id: &str) -> Result<(), String> {
        if self.protocol_version != PROTOCOL_VERSION {
            return Err(format!(
                "Unsupported protocolVersion {}. Expected {PROTOCOL_VERSION}.",
                self.protocol_version
            ));
        }
        if self.scenario_id != scenario_id {
            return Err(format!(
                "Response scenarioId {:?} does not match {:?}.",
                self.scenario_id, scenario_id
            ));
        }
        if self.output.is_null() {
            return Err("output must be a non-null JSON value.".into());
        }
        if self.tool_calls.iter().any(|t| t.name.trim().is_empty()) {
            return Err("toolCalls[].name must not be empty.".into());
        }
        if self.usage.as_ref().is_some_and(|u| u.total().is_none()) {
            return Err("usage token total exceeds the supported integer range.".into());
        }
        if self
            .estimated_cost_usd
            .is_some_and(|c| !c.is_finite() || c < 0.0)
        {
            return Err("estimatedCostUsd must be finite and nonnegative.".into());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ToolCall {
    pub name: String,
    pub arguments: Option<Value>,
    pub result: Option<Value>,
    pub duration_ms: Option<u64>,
    pub success: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Retrieval {
    pub source: Option<String>,
    pub document_id: Option<String>,
    pub chunk_id: Option<String>,
    pub score: Option<f64>,
    #[serde(default)]
    pub metadata: Metadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TokenUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
}

impl TokenUsage {
    pub fn total(&self) -> Option<u64> {
        self.input_tokens.checked_add(self.output_tokens)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RunErrorKind {
    Spawn,
    Io,
    Exit,
    Timeout,
    Protocol,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RunError {
    pub kind: RunErrorKind,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AgentRun {
    pub scenario_id: String,
    pub input: Value,
    pub started_at_unix_ms: u64,
    pub completed_at_unix_ms: u64,
    pub duration_ms: u64,
    pub response: Option<AgentResponse>,
    pub error: Option<RunError>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Evaluator {
    JsonOutput,
    OutputContains,
    OutputNotContains,
    ToolsCalled,
    ToolsNotCalled,
    SourceIncluded,
    MaxLatency,
    MaxTokens,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvaluationResult {
    pub evaluator: Evaluator,
    pub expected: Value,
    pub observed: Value,
    pub passed: bool,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ScenarioResult {
    pub sample_index: u32,
    pub scenario: crate::config::Scenario,
    pub run: AgentRun,
    pub evaluations: Vec<EvaluationResult>,
    pub passed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RunSnapshot {
    pub schema_version: u32,
    pub wraith_version: String,
    pub created_at_unix_ms: u64,
    pub samples_per_scenario: u32,
    pub comparison: crate::config::ComparisonOptions,
    pub thresholds: crate::config::Thresholds,
    pub scenarios: Vec<ScenarioResult>,
}
