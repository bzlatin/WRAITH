# Add Wraith to PR checks

```sh
wraith ci init
```

This creates `.github/workflows/wraith.yml` in your Git repository. It never
overwrites an existing workflow. Commit the scenario config, adapter, and project
file on the default branch before enabling a required check. Review dependency
installation: the template handles adjacent `package-lock.json` and
`requirements.txt`; other builds/package managers need your normal CI steps.

The template pins a Wraith release version (override with `--version`). That version
must have published native archives and `install.py`; the current local v0.5 code
cannot be installed from GitHub until release publication. The repository is
currently private, so unauthenticated installers also need an accessible release or
an authenticated manual download. Existing Wraith-repo CI remains source-built.

For each PR the generated workflow:

1. Checks out candidate code and the **exact base SHA** separately.
2. Installs the pinned binary and application dependencies.
3. Loads the trusted base configuration through `wraith config`, then evaluates the
   base and candidate using identical scenarios/commands in their respective trees.
4. Compares with the base policy, preserves exits 0/1/2/3, writes a job summary, and
   uploads JSON/HTML evidence retained for 14 days.

It recomputes the base for the PR; it does not depend on an unrelated "latest"
baseline or hide removed tests. A PR introducing the first suite needs a default-
branch bootstrap. Expectation changes need deliberate review and baseline updates.
No provider credentials are supplied; generated workflows reject declared live
suites. Offline fixtures must not make live requests. This is not a network sandbox.
Untrusted PR code runs with read-only repository permissions and no provider secrets.

The workflow file itself runs from PR code and is reviewable; this template is not
an attestation against a malicious contributor rewriting the workflow. Organizations
needing stronger enforcement should place orchestration in an administrator-managed
workflow and protect it through branch/ruleset policy.

Live CI is an explicit follow-on integration: choose a trusted execution context,
credentials, cooperative model-call budget, representative sample counts, and a
noise policy before enabling it. Do not convert inconclusive evidence into success.
See [existing exact-commit artifact CI](ci.md) for the Wraith repository's own setup.
