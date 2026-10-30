# Setup: `ae` CLI, Credentials, and License

Run these checks before the first `ae` command of a session. Most failed
launches come from a missing CLI, missing credentials, or a missing license, so
settle them first.

> The examples use Unix shell syntax. Adapt them for your platform (e.g.,
> `where` instead of `which` on Windows, PowerShell syntax for environment
> variables).

## 1. What the user needs

Requirement                                     | How to check                                                        | How to fix
----------------------------------------------- | ------------------------------------------------------------------- | ----------
`gcloud` CLI                                    | `gcloud --version`                                                  | Install from https://docs.cloud.google.com/sdk/docs/install-sdk
Application Default Credentials                 | `gcloud auth application-default print-access-token` prints a token | `gcloud auth application-default login`
`uv`                                            | `uv --version`                                                      | Install from https://docs.astral.sh/uv/#installation
Python 3.11.4 or newer                          | `uv run python --version`                                           | `uv python install 3.13`
A Google Cloud project with billing             | `ae --json config discover` shows a project                         | Ask the user which project to use
A Gemini Enterprise app (engine) in the project | `ae --json engine list` is not empty                                | Create one in the Cloud Console (Gemini Enterprise)
A Gemini Enterprise license for the user        | See section 5                                                       | See section 5
IAM role Discovery Engine Editor                | `ae --json config test` does not return 403                         | Ask a project admin to grant the role

The user's own actions (installing `gcloud`, logging in, buying or assigning a
license, granting IAM roles) cannot be done by you. Explain the step, give the
exact command or console page, and wait.

## 2. Install the `ae` CLI

Install it as a `uv` tool, straight from GitHub:

```bash
uv tool install "git+https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud.git#subdirectory=skills"
```

`pipx install` with the same URL also works, and plain `pip` works inside an
active virtualenv. To upgrade an existing install, run `uv tool upgrade ae-cli`.

Verify with `ae version` (there is no `--version` flag).

## 3. Find the `ae` CLI

The `ae` CLI **must** be installed and executable. Follow this discovery
sequence. Do NOT skip steps or guess paths:

1.  **Try the bare command:**

    ```bash
    ae version
    ```

2.  **If that fails, search common install locations:**

    ```bash
    which ae 2>/dev/null || \
      ls ~/.local/bin/ae 2>/dev/null || \
      ls ~/.local/share/uv/tools/ae-cli/bin/ae 2>/dev/null
    ```

3.  **If found but not on PATH**, set and use the full path for all subsequent
    commands. For example: `AE=/home/user/.local/bin/ae && $AE version`

4.  **If not found after steps 1-2**, install it (section 2), with the user's
    consent.

**Do NOT spend more than 3 commands searching for the binary.** If you cannot
find it after the above steps, ask the user: "Where is your `ae` binary
installed?"

## 4. Check the network

Before making any claims about network access, verify connectivity:

```bash
curl -s -o /dev/null -w "%{http_code}" https://discoveryengine.googleapis.com
```

If this returns any HTTP status code (200, 404, etc.), you have network access.
**NEVER claim you lack internet access without running this check.** Only if
`curl` fails with a connection error should you report network issues.

## 5. Gemini Enterprise license

AlphaEvolve runs inside a Gemini Enterprise app, and the API admits only users
who hold a Gemini Enterprise license on the project:

-   Any Gemini Enterprise tier grants access, including a trial license.
-   The license must be **active** and **assigned to the calling user**. An
    expired trial counts as no license.
-   The API checks the license only when an experiment is created. So
    `ae config test` can pass while `ae experiment create` fails with
    `LICENSE_WITHOUT_SUBSCRIPTION_TIER`.

On `LICENSE_WITHOUT_SUBSCRIPTION_TIER`, do not retry. Tell the user that a
Gemini Enterprise admin must assign them a license in the Gemini Enterprise
admin console for this project, or that the project needs a new subscription if
its license has expired.

## 6. Configure `ae`

Configure the project, engine, and location, then test connectivity:

```bash
ae --json config show
ae --json config discover
ae --json engine list
ae config --project=<PROJECT_ID> --engine=<ENGINE_ID> --location=global
ae --json config test
```

`--json` is a global flag, so it goes before the subcommand. The full flow,
including the profile pitfall, the default values, and the configuration table
the user must confirm, is Stage 1 of `references/runner.md`. Error fixes are in
`references/runner/debugging.md`.

## 7. After installing or updating

**After installing or updating the CLI or this skill, restart the agent
session.** Most agent runtimes cache skill files for the duration of a session.
Changes will not take effect until a new session is started.

To install or update this skill itself, run `ae skills install`.
