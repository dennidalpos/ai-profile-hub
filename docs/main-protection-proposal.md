# Main protection and release evidence

The owner confirmed the active `Protect main` ruleset (27336801) on 2026-11-19. The settings below were verified through the GitHub API. Release evidence uses a 90-day retention policy. The expiry of the release-candidate artifacts remains to be verified.

The `Test and build` workflow runs on every push and checks Ubuntu, macOS and Windows on Python 3.11 and 3.13.

## 1. Ruleset for `main`

| Rule | Active setting | Purpose |
|---|---|---|
| Block deletion | on | `main` is the release source |
| Block force pushes | on | keeps tested commits reachable |
| Required status checks | `quality` and the six `verify` jobs | CI is required for changes subject to the ruleset |
| Require a pull request | on, with one approval | review is required for changes subject to the ruleset |
| Bypass list | repository administrators | authorized direct pushes to `main` remain possible |

The maintainer verifies changes locally before an authorized direct push. Dependabot opens pull requests under the same review and check requirements as other contributors.

## 2. Release evidence

Before any binary is published, a release candidate should keep, for the exact commit:

- `tests.xml` and `coverage.xml` from the Linux 3.13 job (`dist/evidence/`);
- the package inventory and notice review result from `scripts/build.py`;
- SHA-256 checksums of each package;
- a build provenance attestation for each package.

Decision (owner, 2026-11-17): retention is 90 days, with provenance attestation. Implemented as:

- `test.yml` uploads `dist/evidence/` (`tests.xml`, `coverage.xml`) from the Linux 3.13 job as `test-evidence-<sha>`, 90 days.
- `release-candidate.yml` runs manually. It builds and smoke-tests each package, writes `package-inventory.txt` and `SHA256SUMS`, and uses the checksums to attest the package files. It uploads the package and evidence as `release-candidate-<OS>` for 90 days.
- On publication, copy the evidence to the release.

GitHub reported a 90-day Actions retention setting for the repository and approximately 90 days between creation and expiry for the test artifact. [Test run on 2026-11-19](https://github.com/dennidalpos/ai-profile-hub/actions/runs/44528338140)

Checksums and sample provenance attestations passed for the release candidate. A later GitHub API read returned HTTP 404 for that run, so the expiry of its artifacts could not be checked. [Release-candidate verification on 2026-11-18](verification.md#release-candidate-workflow-run-on-2026-11-18)

Complete the [license and notice reviews](verification.md) before distributing standalone binaries.
