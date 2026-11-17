# Proposal: protecting `main` and keeping release evidence

Status: section 1 was applied on 2026-11-15 as the active ruleset `Protect main` (id 27336801) with the owner's approval and verified by reading it back (`gh api repos/<owner>/<repo>/rulesets`). Section 2 (release evidence) is still a proposal.

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

A ruleset applies required checks to every push, so a direct push of an untested commit is rejected for anyone without bypass. The repository admin role is on the bypass list, which is why the owner can still push directly. Turning the pull-request rule on makes the checks binding for the owner as well.

## 2. Release evidence

Before any binary is published, a release candidate should keep, for the exact commit:

- `tests.xml` and `coverage.xml` from the Linux 3.13 job (`dist/evidence/`);
- the package inventory and notice review result from `scripts/build.py`;
- SHA-256 checksums of each package;
- a build provenance attestation for each package.

Decision (owner, 2026-11-17): retention is 90 days, with provenance attestation. Implemented as:

- `test.yml` uploads `dist/evidence/` (`tests.xml`, `coverage.xml`) from the Linux 3.13 job as `test-evidence-<sha>`, 90 days.
- `release-candidate.yml` (manual only, publishes nothing) builds the package on each OS, runs the package smoke, writes `package-inventory.txt` and `SHA256SUMS` with `scripts/release_evidence.py`, attests the checksums with `actions/attest-build-provenance`, and uploads package and evidence as `release-candidate-<OS>`, 90 days.
- On publication, copy the evidence to the release.

Not yet verified: neither workflow has run. Verify by dispatching `release-candidate.yml` once, downloading the artifacts, running `sha256sum -c SHA256SUMS` and `gh attestation verify`.

## 3. Open decisions for the owner

1. Apply the ruleset in section 1 as written, or with the pull-request rule on.
2. Choose the retention period for release evidence.
3. Confirm that no binary is distributed before the open legal and notice reviews in `docs/verification.md` are closed.
