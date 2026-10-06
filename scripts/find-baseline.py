#!/usr/bin/env python3
"""Find a successful baseline workflow for exactly the PR base commit."""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request


def select_run(runs, base_sha, branch):
    return next((run for run in runs if run.get("head_sha") == base_sha
                 and run.get("head_branch") == branch and run.get("event") == "push"
                 and run.get("conclusion") == "success"), None)


def find_run(repository, base_sha, branch, token, api="https://api.github.com"):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository name")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
        raise ValueError("base SHA must be a full commit hash")
    query = urllib.parse.urlencode({"head_sha": base_sha, "branch": branch,
                                    "event": "push", "status": "success", "per_page": 100})
    url = f"{api.rstrip('/')}/repos/{repository}/actions/workflows/baseline.yml/runs?{query}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=30) as response:
        run = select_run(json.load(response)["workflow_runs"], base_sha, branch)
    if not run:
        raise ValueError("No successful push baseline exists for this exact base SHA. Run the baseline workflow on the base commit; do not substitute an older baseline.")
    return run["id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    try:
        run_id = find_run(args.repository, args.base_sha, args.branch,
                          os.environ["GH_TOKEN"], os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"run-id={run_id}\n")
        print(f"Selected baseline workflow run {run_id} for {args.base_sha}")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"Baseline lookup failed: {error}\n")
