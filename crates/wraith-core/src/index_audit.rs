//! Exact, read-only reconciliation of trusted, sorted ingestion exports.
//! This contract is independent of agent run/comparison schemas.
use crate::{cancellation::Cancellation, error::Error};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use std::{
    cmp::Ordering,
    collections::BTreeSet,
    io::{BufRead, Read},
};

const MAX_LINE: u64 = 1024 * 1024;
const MAX_ID: usize = 1024;
const MAX_FINDINGS: usize = 1000;
const MAX_EXAMPLES: usize = 20;

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(deny_unknown_fields)]
pub struct Header {
    pub schema_version: u32,
    pub kind: String,
    pub scope: String,
    /// Exporter's common frozen generation, not a wall-clock timestamp.
    pub generation: String,
    pub complete: bool,
    pub stable: bool,
    pub record_count: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    tenant: String,
    document_id: String,
    state: State,
    /// True only after this revision's ingestion/visibility barrier has settled.
    settled: bool,
    revision: Option<String>,
    expected_chunks: Option<Vec<String>>,
    job_id: Option<String>,
}

#[derive(Debug, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum State {
    Present,
    Deleted,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Inventory {
    tenant: String,
    document_id: String,
    chunks: Vec<Chunk>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Chunk {
    id: String,
    revision: Option<String>,
}

type Key = (String, String);

trait Row: DeserializeOwned {
    fn key(&self) -> Key;
    fn validate(&self) -> Result<(), Error>;
}

fn invalid(message: impl Into<String>) -> Error {
    Error::Artifact(message.into())
}
fn identifier(value: &str) -> Result<(), Error> {
    if value.trim().is_empty() || value.len() > MAX_ID || value.chars().any(char::is_control) {
        return Err(invalid(
            "Index identifiers must be nonblank, at most 1024 bytes, and contain no control characters",
        ));
    }
    Ok(())
}
fn unique<'a>(values: impl Iterator<Item = &'a str>) -> Result<(), Error> {
    let mut seen = BTreeSet::new();
    for value in values {
        identifier(value)?;
        if !seen.insert(value) {
            return Err(invalid("Duplicate chunk ID in an index export row"));
        }
    }
    Ok(())
}
impl Row for Manifest {
    fn key(&self) -> Key {
        (self.tenant.clone(), self.document_id.clone())
    }
    fn validate(&self) -> Result<(), Error> {
        if let Some(revision) = &self.revision {
            identifier(revision)?;
        }
        if let Some(job) = &self.job_id {
            identifier(job)?;
        }
        if let Some(chunks) = &self.expected_chunks {
            unique(chunks.iter().map(String::as_str))?;
            if self.state == State::Deleted && !chunks.is_empty() {
                return Err(invalid(
                    "Deleted documents must not declare expected chunks",
                ));
            }
        }
        Ok(())
    }
}
impl Row for Inventory {
    fn key(&self) -> Key {
        (self.tenant.clone(), self.document_id.clone())
    }
    fn validate(&self) -> Result<(), Error> {
        unique(self.chunks.iter().map(|c| c.id.as_str()))?;
        for chunk in &self.chunks {
            if let Some(revision) = &chunk.revision {
                identifier(revision)?;
            }
        }
        Ok(())
    }
}

struct Stream<R> {
    reader: R,
    header: Header,
    read: u64,
    previous: Option<Key>,
}
fn line<T: DeserializeOwned>(reader: &mut impl BufRead) -> Result<Option<T>, Error> {
    let mut bytes = Vec::new();
    let n = reader
        .take(MAX_LINE + 1)
        .read_until(b'\n', &mut bytes)
        .map_err(|_| invalid("Could not read index export"))?;
    if n == 0 {
        return Ok(None);
    }
    if n as u64 > MAX_LINE {
        return Err(invalid("Index export row exceeds 1 MiB"));
    }
    // Do not echo source content or serde's unknown-field values in diagnostics.
    serde_json::from_slice(&bytes).map(Some).map_err(|_| {
        invalid("Invalid index JSONL record; check required fields, types, and schema")
    })
}
impl<R: BufRead> Stream<R> {
    fn new(mut reader: R, kind: &str) -> Result<Self, Error> {
        let header: Header = line(&mut reader)?
            .ok_or_else(|| invalid("Index export is empty; a versioned header is required"))?;
        if header.schema_version != 1 {
            return Err(invalid(format!(
                "Unsupported index schema {}; expected 1",
                header.schema_version
            )));
        }
        if header.kind != kind {
            return Err(invalid(format!("Expected {kind} export")));
        }
        identifier(&header.scope)?;
        identifier(&header.generation)?;
        Ok(Self {
            reader,
            header,
            read: 0,
            previous: None,
        })
    }
    fn next<T: Row>(&mut self) -> Result<Option<T>, Error> {
        let row: Option<T> = line(&mut self.reader)?;
        if let Some(row) = &row {
            self.read += 1;
            if self.read > self.header.record_count {
                return Err(invalid(
                    "Index export has more rows than its declared record_count",
                ));
            }
            let key = row.key();
            identifier(&key.0)?;
            identifier(&key.1)?;
            if self.previous.as_ref().is_some_and(|p| p >= &key) {
                return Err(invalid(
                    "Index export rows must be unique and sorted by (tenant, document_id) in UTF-8 byte order",
                ));
            }
            row.validate()?;
            self.previous = Some(key);
        } else if self.read != self.header.record_count {
            return Err(invalid(
                "Index export is truncated: record_count does not match rows read",
            ));
        }
        Ok(row)
    }
}

#[derive(Debug, Serialize, PartialEq, Eq, Clone, Copy)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Passed,
    Failed,
    Pending,
    Unknown,
}
#[derive(Debug, Serialize)]
pub struct RevisionMismatch {
    pub chunk_id: String,
    pub observed_revision: String,
}

#[derive(Debug, Serialize)]
pub struct Finding {
    pub tenant: String,
    pub document_id: String,
    pub job_id: Option<String>,
    pub status: Status,
    pub reason: String,
    pub next_action: String,
    pub expected_revision: Option<String>,
    pub expected_chunks: Option<usize>,
    pub observed_chunks: usize,
    pub missing_count: usize,
    pub unexpected_count: usize,
    pub stale_count: usize,
    pub missing_examples: Vec<String>,
    pub unexpected_examples: Vec<String>,
    pub stale_examples: Vec<RevisionMismatch>,
}
#[derive(Debug, Default, Serialize)]
pub struct Counts {
    pub documents: u64,
    pub expected_chunks: u64,
    pub observed_chunks: u64,
    pub passed: u64,
    pub failed: u64,
    pub pending: u64,
    pub unknown: u64,
}
#[derive(Debug, Serialize)]
pub struct Audit {
    pub schema_version: u32,
    pub manifest: Header,
    pub inventory: Header,
    pub status: Status,
    pub summary: Counts,
    pub coverage_issues: Vec<String>,
    pub findings: Vec<Finding>,
    pub omitted_findings: u64,
}
impl Audit {
    pub fn exit_code(&self) -> u8 {
        match self.status {
            Status::Passed => 0,
            Status::Failed => 1,
            Status::Pending | Status::Unknown => 3,
        }
    }
    fn add(&mut self, finding: Finding) {
        self.summary.documents += 1;
        self.summary.expected_chunks += finding.expected_chunks.unwrap_or(0) as u64;
        self.summary.observed_chunks += finding.observed_chunks as u64;
        match finding.status {
            Status::Passed => self.summary.passed += 1,
            Status::Failed => self.summary.failed += 1,
            Status::Pending => self.summary.pending += 1,
            Status::Unknown => self.summary.unknown += 1,
        }
        if finding.status != Status::Passed {
            if self.findings.len() < MAX_FINDINGS {
                self.findings.push(finding);
            } else {
                self.omitted_findings += 1;
                // Keep failures before uncertain results even when the report is capped.
                if finding.status == Status::Failed && self.summary.failed <= MAX_FINDINGS as u64 {
                    if let Some(i) = self
                        .findings
                        .iter()
                        .rposition(|f| f.status != Status::Failed)
                    {
                        self.findings[i] = finding;
                    }
                }
            }
        }
    }
}

fn compare(manifest: Option<&Manifest>, inventory: Option<&Inventory>, trusted: bool) -> Finding {
    let key = manifest
        .map(Row::key)
        .or_else(|| inventory.map(Row::key))
        .unwrap();
    let observed = inventory.map(|i| i.chunks.as_slice()).unwrap_or(&[]);
    let mut f = Finding {
        tenant: key.0,
        document_id: key.1,
        job_id: manifest.and_then(|m| m.job_id.clone()),
        status: Status::Unknown,
        reason: String::new(),
        next_action: String::new(),
        expected_revision: manifest.and_then(|m| m.revision.clone()),
        expected_chunks: manifest.and_then(|m| m.expected_chunks.as_ref().map(Vec::len)),
        observed_chunks: observed.len(),
        missing_count: 0,
        unexpected_count: 0,
        stale_count: 0,
        missing_examples: vec![],
        unexpected_examples: vec![],
        stale_examples: vec![],
    };
    if !trusted {
        f.reason = "Export coverage or stability is unverified".into();
        f.next_action =
            "Finish both exports against one frozen generation, then check again".into();
        return f;
    }
    let Some(m) = manifest else {
        f.reason = "Index document has no authoritative manifest entry".into();
        f.next_action = "Resolve its source identity or supply an explicit deletion tombstone; do not delete on this evidence alone".into();
        return f;
    };
    if !m.settled {
        f.status = Status::Pending;
        f.reason = "Ingestion or its visibility grace period has not settled".into();
        f.next_action = "Wait for the ingestion/visibility barrier, then export again".into();
        return f;
    }
    if m.state == State::Deleted {
        if observed.is_empty() {
            f.status = Status::Passed;
        } else {
            f.status = Status::Failed;
            f.reason = "Chunks remain for an explicit deletion tombstone".into();
            f.unexpected_count = observed.len();
            f.unexpected_examples = observed
                .iter()
                .take(MAX_EXAMPLES)
                .map(|c| c.id.clone())
                .collect();
            f.next_action = "Inspect the deletion job and retry scoped cleanup through the owning application; re-export to verify".into();
        }
        return f;
    }
    let (Some(expected), Some(revision)) = (&m.expected_chunks, &m.revision) else {
        f.reason = "Expected chunk manifest or source revision is unavailable".into();
        f.next_action = "Export the intended chunk IDs and revision from the ingestion plan, before writes occur".into();
        return f;
    };
    if observed.iter().any(|c| c.revision.is_none()) {
        f.reason = "An observed chunk has no revision metadata".into();
        f.next_action =
            "Preserve the source revision in every chunk's payload, then re-export".into();
        return f;
    }
    let expected: BTreeSet<_> = expected.iter().map(String::as_str).collect();
    let actual: BTreeSet<_> = observed.iter().map(|c| c.id.as_str()).collect();
    let missing: Vec<_> = expected.difference(&actual).copied().collect();
    let unexpected: Vec<_> = actual.difference(&expected).copied().collect();
    let stale: BTreeSet<_> = observed
        .iter()
        .filter(|c| c.revision.as_ref() != Some(revision))
        .map(|c| c.id.as_str())
        .collect();
    f.missing_count = missing.len();
    f.unexpected_count = unexpected.len();
    f.stale_count = stale.len();
    f.missing_examples = missing
        .into_iter()
        .take(MAX_EXAMPLES)
        .map(str::to_owned)
        .collect();
    f.unexpected_examples = unexpected
        .into_iter()
        .take(MAX_EXAMPLES)
        .map(str::to_owned)
        .collect();
    f.stale_examples = stale
        .into_iter()
        .take(MAX_EXAMPLES)
        .map(|id| RevisionMismatch {
            chunk_id: id.to_owned(),
            observed_revision: observed
                .iter()
                .find(|c| c.id == id)
                .and_then(|c| c.revision.clone())
                .expect("validated revision"),
        })
        .collect();
    if f.missing_count + f.unexpected_count + f.stale_count == 0 {
        f.status = Status::Passed;
    } else {
        f.status = Status::Failed;
        f.reason = "Serving chunks do not match the intended ingestion manifest".into();
        f.next_action = "Inspect the recorded ingestion job, reconcile missing/stale/extra chunk IDs through the application, and re-export".into();
    }
    f
}

/// Streaming merge: two rows plus a bounded report in memory, regardless of corpus size.
/// Exports must attest a common frozen generation; this cannot establish snapshot
/// consistency, retrieval exposure, or correctness of the exporter itself.
pub fn check(
    manifest: impl BufRead,
    inventory: impl BufRead,
    cancellation: &Cancellation,
) -> Result<Audit, Error> {
    let mut left = Stream::new(manifest, "manifest")?;
    let mut right = Stream::new(inventory, "inventory")?;
    if left.header.scope != right.header.scope {
        return Err(invalid("Index export scopes differ"));
    }
    let mut issues = Vec::new();
    if left.header.generation != right.header.generation {
        issues.push("Export generations differ".into());
    }
    if !left.header.complete || !right.header.complete {
        issues.push("An export is incomplete".into());
    }
    if !left.header.stable || !right.header.stable {
        issues.push("Concurrent changes or snapshot consistency are unresolved".into());
    }
    let trusted = issues.is_empty();
    let mut audit = Audit {
        schema_version: 1,
        manifest: left.header.clone(),
        inventory: right.header.clone(),
        status: Status::Unknown,
        summary: Counts::default(),
        coverage_issues: issues,
        findings: vec![],
        omitted_findings: 0,
    };
    let mut m: Option<Manifest> = left.next()?;
    let mut i: Option<Inventory> = right.next()?;
    while m.is_some() || i.is_some() {
        if cancellation.is_cancelled() {
            return Err(Error::Cancelled);
        }
        let order = match (&m, &i) {
            (Some(m), Some(i)) => m.key().cmp(&i.key()),
            (Some(_), None) => Ordering::Less,
            (None, Some(_)) => Ordering::Greater,
            _ => unreachable!(),
        };
        match order {
            Ordering::Equal => {
                audit.add(compare(m.as_ref(), i.as_ref(), trusted));
                m = left.next()?;
                i = right.next()?;
            }
            Ordering::Less => {
                audit.add(compare(m.as_ref(), None, trusted));
                m = left.next()?;
            }
            Ordering::Greater => {
                audit.add(compare(None, i.as_ref(), trusted));
                i = right.next()?;
            }
        }
    }
    if cancellation.is_cancelled() {
        return Err(Error::Cancelled);
    }
    if audit.summary.documents == 0 {
        audit
            .coverage_issues
            .push("No document requirements were evaluated".into());
    }
    audit.status = if audit.summary.failed > 0 {
        Status::Failed
    } else if audit.summary.unknown > 0 || !audit.coverage_issues.is_empty() {
        Status::Unknown
    } else if audit.summary.pending > 0 {
        Status::Pending
    } else {
        Status::Passed
    };
    audit.findings.sort_by_key(|f| {
        (
            if f.status == Status::Failed { 0 } else { 1 },
            f.tenant.clone(),
            f.document_id.clone(),
        )
    });
    Ok(audit)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};
    fn export(kind: &str, rows: &[Value]) -> String {
        let header = json!({"schema_version":1,"kind":kind,"scope":"support","generation":"g1",
            "complete":true,"stable":true,"record_count":rows.len()});
        std::iter::once(header)
            .chain(rows.iter().cloned())
            .map(|r| r.to_string() + "\n")
            .collect()
    }
    fn manifest() -> Value {
        json!({"tenant":"a","document_id":"policy","state":"present","settled":true,"revision":"8","expected_chunks":["0","1","2"],"job_id":"job-42"})
    }
    fn inventory(ids: &[&str]) -> Value {
        json!({"tenant":"a","document_id":"policy","chunks": ids.iter().map(|id|json!({"id":id,"revision":"8"})).collect::<Vec<_>>()})
    }
    fn run(m: &[Value], i: &[Value]) -> Audit {
        check(
            export("manifest", m).as_bytes(),
            export("inventory", i).as_bytes(),
            &Cancellation::default(),
        )
        .unwrap()
    }
    #[test]
    fn partial_and_equal_count_wrong_ids_cannot_pass() {
        assert_eq!(
            run(&[manifest()], &[inventory(&["0", "1", "2"])]).exit_code(),
            0
        );
        for ids in [&["0", "2"][..], &["0", "1", "9"][..], &[][..]] {
            let r = run(&[manifest()], &[inventory(ids)]);
            assert_eq!(r.exit_code(), 1);
            assert!(r.findings[0].missing_count > 0);
            assert_eq!(r.findings[0].job_id.as_deref(), Some("job-42"));
        }
    }
    #[test]
    fn same_ids_wrong_revision_fails() {
        let mut i = inventory(&["0", "1", "2"]);
        i["chunks"][1]["revision"] = json!("7");
        let r = run(&[manifest()], &[i]);
        assert_eq!(r.findings[0].stale_examples[0].chunk_id, "1");
        assert_eq!(r.findings[0].stale_examples[0].observed_revision, "7");
        assert_eq!(r.exit_code(), 1);
    }
    #[test]
    fn deletion_needs_explicit_tombstone() {
        let m = json!({"tenant":"a","document_id":"policy","state":"deleted","settled":true});
        assert_eq!(run(std::slice::from_ref(&m), &[]).exit_code(), 0);
        assert_eq!(run(&[m], &[inventory(&["0"])]).exit_code(), 1);
        assert_eq!(run(&[], &[inventory(&["0"])]).exit_code(), 3);
    }
    #[test]
    fn uncertain_metadata_and_normal_lag_are_inconclusive() {
        let mut m = manifest();
        m["settled"] = json!(false);
        assert_eq!(run(&[m], &[]).status, Status::Pending);
        for field in ["revision", "expected_chunks"] {
            let mut m = manifest();
            m.as_object_mut().unwrap().remove(field);
            assert_eq!(run(&[m], &[inventory(&["0", "1", "2"])]).exit_code(), 3);
        }
        let mut i = inventory(&["0", "1", "2"]);
        i["chunks"][0].as_object_mut().unwrap().remove("revision");
        assert_eq!(run(&[manifest()], &[i]).exit_code(), 3);
    }
    #[test]
    fn incomplete_unstable_and_different_generation_never_pass_or_invent_failure() {
        for (field, value) in [
            ("complete", json!(false)),
            ("stable", json!(false)),
            ("generation", json!("g2")),
        ] {
            let m = export("manifest", &[manifest()]);
            let i = export("inventory", &[inventory(&["0"])]);
            let mut lines: Vec<Value> = i
                .lines()
                .map(|l| serde_json::from_str(l).unwrap())
                .collect();
            lines[0][field] = value;
            let i: String = lines.iter().map(|v| v.to_string() + "\n").collect();
            let result = check(m.as_bytes(), i.as_bytes(), &Cancellation::default()).unwrap();
            assert_eq!(result.exit_code(), 3);
            assert_eq!(result.summary.failed, 0);
            assert_eq!(result.coverage_issues.len(), 1);
        }
    }
    #[test]
    fn identities_are_tenant_scoped_and_empty_manifest_is_not_green() {
        let mut other = inventory(&["0", "1", "2"]);
        other["tenant"] = json!("b");
        let r = run(&[manifest()], &[other]);
        assert_eq!(r.summary.failed, 1);
        assert_eq!(r.summary.unknown, 1);
        assert_eq!(r.exit_code(), 1);
        assert_eq!(run(&[], &[]).exit_code(), 3);
        let mut m = manifest();
        m["expected_chunks"] = json!([]);
        assert_eq!(run(&[m], &[]).exit_code(), 0);
    }
    #[test]
    fn corrupt_exports_are_rejected_instead_of_saving_partial_success() {
        let m = export("manifest", &[manifest()]);
        let valid = export("inventory", &[inventory(&["0", "1", "2"])]);
        for bad in [
            valid.lines().next().unwrap().to_owned() + "\n",
            valid.clone() + "{}\n",
            valid.replace("\"schema_version\":1", "\"schema_version\":99"),
            valid.replace("\"scope\":\"support\"", "\"scope\":\"other\""),
            export("inventory", &[inventory(&["0", "0"])]),
            export("inventory", &[inventory(&["0"]), inventory(&["1"])]),
        ] {
            assert!(check(m.as_bytes(), bad.as_bytes(), &Cancellation::default()).is_err());
        }
        let mut later = manifest();
        later["document_id"] = json!("z");
        assert!(
            check(
                export("manifest", &[later, manifest()]).as_bytes(),
                valid.as_bytes(),
                &Cancellation::default()
            )
            .is_err()
        );
        let oversized = " ".repeat(MAX_LINE as usize + 1);
        assert!(
            check(
                oversized.as_bytes(),
                valid.as_bytes(),
                &Cancellation::default()
            )
            .is_err()
        );
    }
    #[test]
    fn report_caps_do_not_change_decision_or_totals() {
        let mut ms = vec![];
        for n in 0..1100 {
            let mut m = manifest();
            m["document_id"] = json!(format!("{n:05}"));
            m["settled"] = json!(false);
            ms.push(m);
        }
        ms.last_mut().unwrap()["settled"] = json!(true);
        let r = run(&ms, &[]);
        assert_eq!(r.exit_code(), 1);
        assert_eq!(r.summary.pending, 1099);
        assert_eq!(r.summary.failed, 1);
        assert_eq!(r.omitted_findings, 100);
        assert_eq!(r.findings.len(), 1000);
        assert_eq!(r.findings[0].status, Status::Failed);
    }
    #[test]
    fn cancelled_scan_returns_no_report() {
        let token = Cancellation::default();
        token.cancel();
        assert!(matches!(
            check(
                export("manifest", &[manifest()]).as_bytes(),
                export("inventory", &[]).as_bytes(),
                &token
            ),
            Err(Error::Cancelled)
        ));
    }
}
