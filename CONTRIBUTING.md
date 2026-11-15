# Contributing

Follow the [development setup](README.md#build-and-test), then run the test suite and report the result in your pull request. For launcher or packaging changes, include the platform and any smoke checks you ran.

Keep product content in English. Use synthetic profiles and redact logs and screenshots. Keep local builds under the ignored output directories.

Report ordinary bugs through GitHub Issues. For security vulnerabilities, follow the [security policy](SECURITY.md).

## Qt and Nuitka updates

Dependabot proposes Qt (PySide6, shiboken6) and Nuitka updates, major ones included, so they can be tried early. A pull request that changes any of these merges only when all of the following hold:

- `scripts/build.py` prints no notice warning for the new version.
- The native package smoke test (`scripts/smoke_package.py`) passes.
- `THIRD_PARTY_NOTICES.md` and `docs/licenses/` match the new component inventory.
- The README system requirements follow the new Qt supported-platforms page.

A major update can change APIs, supported systems and licensing, so adapt the code on the same pull request and note what changed. Close the pull request if the notices cannot be reviewed yet.
