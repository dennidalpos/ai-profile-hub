# Google authentication environment audit

Reviewed on 2026-11-14 for Gemini CLI 0.68.0 and experimental Antigravity CLI (`agy`) 1.5.9. Versions were read from the installed package metadata and `agy --version`; no personal authentication files or account sessions were inspected.

## Inherited inputs

The launcher applies these rules to locally launched Google clients. Web profiles use separate browser data directories.

| Input | Launcher behavior |
| --- | --- |
| `GEMINI_API_KEY`, `GOOGLE_API_KEY` | Remove inherited API keys. |
| `GOOGLE_APPLICATION_CREDENTIALS`, `google_application_credentials` | Remove inherited credential-file pointers, including the lowercase spelling accepted by Google's authentication library on Unix. |
| `GOOGLE_CLOUD_ACCESS_TOKEN`, `GOOGLE_GENAI_USE_GCA` | Remove the external OAuth token and its selector. |
| `GOOGLE_GENAI_USE_VERTEXAI`, `GEMINI_CLI_USE_COMPUTE_ADC`, `CLOUD_SHELL` | Remove inherited Vertex/metadata authentication selectors. |
| `GEMINI_CLI_AUTH_OVERRIDE` | Remove the parent client's internal authentication relaunch override. |
| `AGY_ADC_AUTH` | Remove Antigravity's inherited ADC selector. |
| `GOOGLE_GEMINI_BASE_URL`, `GOOGLE_VERTEX_BASE_URL`, `GEMINI_CLI_CUSTOM_HEADERS` | Refuse the launch if nonempty. The message names the variable without showing its value. An administrator must resolve managed configurations; unmanaged environments can restart Hub without the override. |
| `HOME`, `GEMINI_CLI_HOME`, `CLOUDSDK_CONFIG` | Use directories belonging to the selected profile. Also redirect Windows user/application directories or Unix XDG directories. |
| `GEMINI_FORCE_FILE_STORAGE` | Set to `true` for Gemini CLI. |
| `GEMINI_CLI_SYSTEM_SETTINGS_PATH`, `GEMINI_CLI_SYSTEM_DEFAULTS_PATH` | Preserve administrator settings pointers. Hub does not rewrite the referenced files or force a different authentication method in client settings. |
| Project, region, quota project, proxy and certificate settings | Preserve these settings. They are not proof of an account identity. |

The gateway refusal follows the explicit product decision to stop on an inherited routing conflict instead of silently discarding a potentially required enterprise gateway. Environment filtering changes the child command only.

## Official sources

- Gemini CLI 0.68.0 [authentication selection, gateway routing and custom headers](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/packages/core/src/core/contentGenerator.ts), [OAuth token and credential-file precedence](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/packages/core/src/code_assist/oauth2.ts), and [system settings, relaunch override and environment loading](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/packages/cli/src/config/settings.ts).
- Gemini CLI 0.68.0 [enterprise configuration](https://github.com/google-gemini/gemini-cli/blob/v0.68.0/docs/cli/enterprise.md) describes system overrides and `GEMINI_CLI_HOME`. The installed Google authentication library also accepts lowercase `google_application_credentials`; this compatibility input is removed defensively.
- Antigravity's [authentication documentation](https://antigravity.google/docs/install/) documents Google sign-in, shared keyring sessions, `AGY_ADC_AUTH`, API-key provider selection and custom Gemini endpoints. Its [CLI settings documentation](https://antigravity.google/docs/cli/using/) gives the configuration directory. These pages are unversioned; they document the public surface as reviewed, rather than proving the internals of every `agy` 1.5.9 build.

## Verification limits

Synthetic command tests cover removed selectors, separate profile homes and Cloud SDK directories, gateway refusal without value disclosure, and preservation of administrator pointers and file contents. They do not establish provider identity isolation.

Gemini can load authentication from workspace or profile `.env` and settings files after startup. Those explicit client configurations remain under the client's trust and policy rules. Antigravity documents silent OS-keyring sign-in shared across its local surfaces; redirecting process directories does not establish an isolated keyring. Antigravity clients therefore remain experimental. Verify two dedicated test accounts after sign-in and restart before qualifying any real account combination.
