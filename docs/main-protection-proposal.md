# Proposal: protecting `main` and keeping release evidence

Status: proposal only. Nothing described here has been applied to the repository settings. Each setting needs the owner's approval, and each applied setting is verified by reading it back (`gh api repos/<owner>/<repo>/rulesets`).

Observed on 2026-11-15: `main` has no branch protection and no ruleset, the repository is public, and the maintainer pushes directly to `main`. The `Test and build` workflow runs on every push; its jobs are `quality` and `verify` (Ubuntu, macOS and Windows on Python 3.11 and 3.13).

## 1. Ruleset for `main`

| Rule | Proposed value | Reason |
|---|---|---|
| Block deletion | on | `main` is the release source |
| Block force pushes | on | keeps tested commits reachable |
| Required status checks | `quality` and the six `verify` jobs | no commit becomes the release base without passing CI |
| Require a pull request | off while there is a single maintainer; on once there is a second reviewer | direct pushes stay possible for the owner, who is the only reviewer today |
| Bypass list | repository owner only | lets the maintainer fix a broken CI configuration |
| Automation (Dependabot) | opens pull requests and never pushes to `main`; its pull requests need the same checks | no extra bypass needed |

With "require a pull request" off, the required checks apply to pull requests and to merge commits, but not to a direct push by the owner. Turning the pull-request rule on makes the checks binding for every change.

## 2. Release evidence

Before any binary is published, a release candidate should keep, for the exact commit:

- `tests.xml` and `coverage.xml` from the Linux 3.13 job (`dist/evidence/`);
- the package inventory and notice review result from `scripts/build.py`;
- SHA-256 checksums of each package;
- a build provenance attestation for each package.

Proposed retention: the current workflow uploads none of this. Add an artifact upload with 90-day retention to the package build in `test.yml`, and copy the files to the release when it is published. Verify by downloading the artifacts of one run and checking that the checksums match the package.

## 3. Open decisions for the owner

1. Apply the ruleset in section 1 as written, or with the pull-request rule on.
2. Choose the retention period for release evidence.
3. Confirm that no binary is distributed before the open legal and notice reviews in `docs/verification.md` are closed.
