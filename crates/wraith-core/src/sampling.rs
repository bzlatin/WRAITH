use crate::model::{RunSnapshot, ScenarioResult};
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    Passed,
    Regression,
    Inconclusive,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StatisticalResult {
    pub scenario_id: String,
    pub check: String,
    pub baseline_failures: u32,
    pub candidate_failures: u32,
    pub samples_per_version: u32,
    pub observed_increase_pp: f64,
    pub lower_increase_pp: f64,
    pub upper_increase_pp: f64,
    pub allowed_increase_pp: f64,
    pub family_size: usize,
    pub alpha: f64,
    pub method: &'static str,
    pub decision: Decision,
    pub message: String,
}

/// Two-sided Hoeffding bound on the difference of independent Bernoulli means.
/// Union bound covers all prespecified endpoints, without requiring independence
/// between endpoints. For equal n, radius = sqrt(ln(2 * family / alpha) / n).
pub(crate) fn decide(
    scenario_id: &str,
    check: String,
    failures: (u32, u32),
    count: u32,
    family_size: usize,
    policy: &crate::config::StatisticalPolicy,
) -> StatisticalResult {
    let observed = (f64::from(failures.1) - f64::from(failures.0)) / f64::from(count) * 100.0;
    // Subtract logarithms to avoid overflow for very small positive alpha.
    let radius =
        (((2.0 * family_size as f64).ln() - policy.alpha.ln()) / f64::from(count)).sqrt() * 100.0;
    let lower = (observed - radius).max(-100.0);
    let upper = (observed + radius).min(100.0);
    let (decision, message) = if count < policy.min_samples {
        (
            Decision::Inconclusive,
            format!(
                "Need at least {} samples per version; observed {count}. Collect a prespecified larger sample before gating.",
                policy.min_samples
            ),
        )
    } else if lower > policy.max_failure_rate_increase_pp {
        (
            Decision::Regression,
            "The entire simultaneous interval exceeds the allowed increase.".into(),
        )
    } else if upper <= policy.max_failure_rate_increase_pp {
        (
            Decision::Passed,
            "The entire simultaneous interval is within the allowed increase.".into(),
        )
    } else {
        (Decision::Inconclusive, "The interval crosses the allowance. Evidence establishes neither acceptable behavior nor a regression; do not treat this as a pass.".into())
    };
    StatisticalResult {
        scenario_id: scenario_id.into(),
        check,
        baseline_failures: failures.0,
        candidate_failures: failures.1,
        samples_per_version: count,
        observed_increase_pp: observed,
        lower_increase_pp: lower,
        upper_increase_pp: upper,
        allowed_increase_pp: policy.max_failure_rate_increase_pp,
        family_size,
        alpha: policy.alpha,
        method: "hoeffding_union_bound",
        decision,
        message,
    }
}

/// Group independent observations by their stable scenario identity.
pub fn groups(run: &RunSnapshot) -> BTreeMap<&str, Vec<&ScenarioResult>> {
    let mut groups: BTreeMap<&str, Vec<&ScenarioResult>> = BTreeMap::new();
    for result in &run.scenarios {
        groups.entry(&result.scenario.id).or_default().push(result);
    }
    groups
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PassInterval {
    pub lower_percent: f64,
    pub upper_percent: f64,
}

/// Wilson 95% score interval for an observed binomial pass proportion.
/// Descriptive only: callers cannot assume adapter observations are independent.
pub fn pass_interval(passed: u32, count: u32) -> PassInterval {
    if count == 0 {
        return PassInterval {
            lower_percent: 0.0,
            upper_percent: 100.0,
        };
    }
    let n = f64::from(count);
    let p = f64::from(passed) / n;
    let z2 = 1.959963984540054_f64.powi(2);
    let center = p + z2 / (2.0 * n);
    let radius = 1.959963984540054 * (p * (1.0 - p) / n + z2 / (4.0 * n * n)).sqrt();
    let denominator = 1.0 + z2 / n;
    PassInterval {
        lower_percent: ((center - radius) / denominator * 100.0).max(0.0),
        upper_percent: ((center + radius) / denominator * 100.0).min(100.0),
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SampleSummary {
    pub scenario_id: String,
    pub count: u32,
    pub passed: u32,
    pub failed: u32,
    pub execution_errors: u32,
    pub pass_rate_percent: f64,
    pub pass_interval_95: PassInterval,
}

pub(crate) fn summarize(id: &str, observations: &[&ScenarioResult]) -> SampleSummary {
    let count = observations.len() as u32;
    let passed = observations.iter().filter(|s| s.passed).count() as u32;
    SampleSummary {
        scenario_id: id.into(),
        count,
        passed,
        failed: count - passed,
        execution_errors: observations
            .iter()
            .filter(|s| s.run.error.is_some())
            .count() as u32,
        pass_rate_percent: f64::from(passed) / f64::from(count) * 100.0,
        pass_interval_95: pass_interval(passed, count),
    }
}

pub fn summaries(run: &RunSnapshot) -> Vec<SampleSummary> {
    groups(run)
        .into_iter()
        .map(|(id, results)| summarize(id, &results))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn simultaneous_bounds_match_formula_and_correct_for_every_endpoint() {
        let p = crate::config::StatisticalPolicy {
            min_samples: 20,
            max_failure_rate_increase_pp: 17.0,
            alpha: 0.05,
        };
        let single = decide("s", "rate".into(), (0, 100), 1000, 1, &p);
        assert!((single.upper_increase_pp - 16.073614619).abs() < 0.000001);
        assert_eq!(single.decision, Decision::Passed);
        let multiple = decide("s", "rate".into(), (0, 100), 1000, 1000, &p);
        assert_eq!(multiple.decision, Decision::Inconclusive);
        assert!(multiple.upper_increase_pp > single.upper_increase_pp);
        let mut boundary = p.clone();
        boundary.max_failure_rate_increase_pp = single.upper_increase_pp;
        assert_eq!(
            decide("s", "rate".into(), (0, 100), 1000, 1, &boundary).decision,
            Decision::Passed
        );
        boundary.max_failure_rate_increase_pp = single.lower_increase_pp;
        assert_eq!(
            decide("s", "rate".into(), (0, 100), 1000, 1, &boundary).decision,
            Decision::Inconclusive
        );
        boundary.alpha = f64::MIN_POSITIVE;
        assert!(
            decide("s", "rate".into(), (0, 0), 20, 1, &boundary)
                .upper_increase_pp
                .is_finite()
        );
    }

    #[test]
    fn intervals_match_known_binomial_values_and_show_small_sample_uncertainty() {
        let half = pass_interval(50, 100);
        assert!((half.lower_percent - 40.38315).abs() < 0.0001);
        assert!((half.upper_percent - 59.61685).abs() < 0.0001);
        assert!(pass_interval(1, 1).lower_percent < 21.0);
        assert!(pass_interval(100, 100).lower_percent > 96.0);
        assert!(pass_interval(0, 10).upper_percent > 27.0);
    }
}
