# Setting up Google Cloud AlphaEvolve — a walkthrough for whoever is doing this for me

This guide is written so you can set up a working AlphaEvolve environment on
**any personal Gmail account** (no company/Workspace account needed) and hand
the finished configuration back to me. Follow the steps in order; each one
notes exactly what to send me at the end.

Total time: roughly 20-30 minutes, plus a few minutes of waiting for a
license/API to activate.

---

## What you'll end up with

By the end, you'll have:
1. A Google Cloud project with billing enabled
2. An active Gemini Enterprise license assigned to your Google account
3. A Gemini Enterprise "app" (this is what AlphaEvolve calls an "engine")
4. The `gcloud` CLI and `ae` CLI installed and authenticated
5. A verified, working `ae` configuration

**At the very end, send me these four things:**
- The Google account email you used
- The Project ID (looks like `something-123456-ab1`)
- The Engine/App ID (looks like `gemini-enterprise-1234567890_1234567890123`)
- Confirmation that `ae --json experiment list` ran without an error (see
  Step 10)

---

## Step 1 — Prerequisites

- A Google account. **Any Gmail account works** — you do not need a Google
  Workspace/company account or an existing Google Cloud organization.
- A credit card, to enable billing on the Google Cloud project. Google Cloud
  and Gemini Enterprise both have free-trial/free-tier options, but billing
  still needs to be *enabled* (a card on file) even if you're not charged
  immediately.
- A terminal (macOS, Linux, or Windows — all supported).

---

## Step 2 — Install the Google Cloud CLI (`gcloud`)

Follow Google's official installer for your OS:
https://docs.cloud.google.com/sdk/docs/install-sdk

Confirm it worked:
```shell
gcloud --version
```

---

## Step 3 — Install `uv` (Python package manager)

Follow the official installer:
https://docs.astral.sh/uv/#installation

Confirm it worked:
```shell
uv --version
```

---

## Step 4 — Sign in with `gcloud`

```shell
gcloud auth login
gcloud auth application-default login
```
Both commands open a browser window — sign in with the Gmail account you're
setting this up on. The second command sets up "Application Default
Credentials" (ADC), which is how the `ae` CLI actually authenticates (not
the first command alone).

---

## Step 5 — Create a Google Cloud project

You can do this in the console (https://console.cloud.google.com/) via
"Create Project", or from the terminal:
```shell
gcloud projects create <a-unique-project-id> --name="AlphaEvolve"
gcloud config set project <a-unique-project-id>
```
Project IDs must be globally unique — if the one you pick is taken, add
random digits.

**Note the Project ID** — you'll send it to me at the end.

---

## Step 6 — Enable billing on the project

In the console: https://console.cloud.google.com/billing — link a billing
account (create one with your credit card if you don't have one yet) to the
project you just created. This is required before any of the APIs below or
Gemini Enterprise will fully work.

---

## Step 7 — Enable the required APIs

```shell
gcloud services enable \
  discoveryengine.googleapis.com \
  aiplatform.googleapis.com
```
- `discoveryengine.googleapis.com` is what actually serves AlphaEvolve.
- `aiplatform.googleapis.com` serves the underlying Gemini models.

---

## Step 8 — Set up Gemini Enterprise (the part that's easy to get wrong)

AlphaEvolve is served through Google's **Gemini Enterprise** product. This
step needs two things: an active **license**, and a Gemini Enterprise
**app** (which AlphaEvolve calls an "engine").

### 8a. Get an active Gemini Enterprise license

Go to the Gemini Enterprise section of the Cloud Console for your project.
There should be a **"Start free"** option for a trial, or a paid
subscription flow if the trial isn't available/has been used before.

Important details that caused real problems for us and are worth getting
right:
- **Any edition works** (Business, Standard, Plus, Pay-as-you-go, or
  Frontline) — all of them include the search + assistant capability that
  AlphaEvolve's API needs. You do not need to pick a specific "premium" tier.
- Licenses are purchased at the **billing account** level, but must then be
  **explicitly assigned to your specific user** on this specific project.
  Just "having a subscription" at an org level is not enough — go into the
  license/user-management screen and confirm your Gmail account shows as
  actively licensed, not just that a subscription exists.
- If you ever see an error like `"User must have an active license in
  order to be granted access. Current state is EXPIRED"` when using `ae`,
  it means this step needs to be redone/renewed for your specific account.

### 8b. Create a Gemini Enterprise app (the "engine")

1. In the Gemini Enterprise console page, click **"Create app"**.
2. Give it a name (an app ID is generated automatically).
3. Select **global** as the location.
4. Enter an organization name (any name is fine — it's just a label).
5. Click **Create**.

You do **not** need to go on to create a data store / connect data sources
for AlphaEvolve to work — that part of the Gemini Enterprise quickstart is
for building a search app, which isn't what we need here. Just creating the
app itself is enough to get an engine ID.

Once created, open the app and copy its **ID** field — it looks like:
```
gemini-enterprise-1234567890_1234567890123
```

**Note this Engine/App ID** — you'll send it to me at the end.

---

## Step 9 — Install the `ae` CLI

```shell
uv tool install "git+https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud.git#subdirectory=skills"
```

Confirm it worked (note: the flag is `version`, not `--version`):
```shell
ae version
```

---

## Step 10 — Configure and verify

```shell
ae config --project=<PROJECT_ID> --engine=<ENGINE_ID> --location=global
```

Then verify the whole chain actually works end-to-end:
```shell
ae --json config discover
ae --json engine list
ae --json experiment list
```
- `config discover` should show your project.
- `engine list` should show the app you created in Step 8b.
- `experiment list` should return an empty list (`[]`) or existing
  experiments — **not** an error. If it returns a `400` error mentioning
  "license" or "EXPIRED", go back to Step 8a — the app/engine and APIs are
  fine, but the license assignment isn't.

If all three commands run cleanly, you're done.

---

## Step 11 — Send me the results

Send me:
1. The Gmail address you used
2. The Project ID
3. The Engine/App ID
4. Confirmation that `ae --json experiment list` ran without an error

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `403 Forbidden` | Account lacks the right IAM role | Grant the `Discovery Engine Editor` role on the project to your account |
| "Could not automatically determine credentials" | ADC not set up | Re-run `gcloud auth application-default login` |
| `ae config discover` shows no project | No default gcloud project set | `gcloud config set project <PROJECT_ID>`, then retry |
| `ae engine list` is empty | No Gemini Enterprise app created yet | Redo Step 8b |
| `400` error: `"User must have an active license... Current state is EXPIRED"` | License not active/assigned for this account | Redo Step 8a — check the license is both purchased **and** assigned to your specific user on this project |
| Engine's `solutionType` is `SOLUTION_TYPE_SEARCH` instead of `SOLUTION_TYPE_CHAT` | Possible app-type mismatch when creating the app in Step 8b | Note it and send it to me — this may need a different app configuration; don't spend too long on it, just report what you see |

---

## Sources

- [Install and Configure AlphaEvolve — Google Cloud Docs](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/get-started)
- [Get started with AlphaEvolve on Google Cloud — Codelab](https://codelabs.developers.google.com/alphaevolve-on-google-cloud-1)
- [Gemini Enterprise Quickstart](https://docs.cloud.google.com/gemini/enterprise/docs/quickstart-gemini-enterprise)
- [Set up Gemini Enterprise as an administrator](https://docs.cloud.google.com/gemini/enterprise/docs/before-you-begin)
- [Frequently asked questions about Gemini Enterprise subscriptions and licenses](https://docs.cloud.google.com/gemini/enterprise/docs/licenses-faqs)
- [Compare editions of Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/editions)
- [Quickstart: Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk)
- `skills/README.md` in this repo (the `ae` CLI install command and prerequisites)
