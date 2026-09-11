# Setting up a Google Cloud + Gemini Enterprise account for AlphaEvolve


Total time: roughly 10-15 minutes. 

---

## What you'll end up with

1. A Google Cloud project with billing enabled
2. An active Gemini Enterprise license, assigned to the Google account
3. A Gemini Enterprise "app" (what AlphaEvolve calls an "engine")

**At the very end, those things are needed for api:**
- The Google account email you used
- The Project ID (looks like `something-123456-ab1`)
- The Engine/App ID (looks like `gemini-enterprise-1234567890_1234567890123`)

---

## Step 1 — Prerequisites

- A Google account. Any Gmail account works.
- A credit card, to enable billing on the Google Cloud project. There are
  free-trial/free-tier options, but billing still needs a card on file even
  if nothing is charged immediately.

---

## Step 2 — Create a Google Cloud project

Go to https://console.cloud.google.com/ , sign in with the Gmail account,
and click **"Create Project"** (top of the page, next to the project
selector). Give it any name and confirm.

**Note the Project ID** shown on the project's dashboard — you'll send it
to me at the end.

---

## Step 3 — Enable billing on the project

Go to https://console.cloud.google.com/billing , and link a billing account
(create one with a credit card if there isn't one yet) to the project from
Step 2.

---

## Step 4 — Set up Gemini Enterprise

### 4a. Get an active license

Go to the Gemini Enterprise section of the Cloud Console for this project.
There should be a **"Start free"** option for a trial, or a paid
subscription flow if the trial isn't available.

Two things that are easy to get wrong here:
- **Any edition works** (Business, Standard, Plus, Pay-as-you-go, or
  Frontline) — all of them include what's needed. No need for a specific
  "premium" tier.
- Licenses are purchased at the billing-account level, but must then be
  **explicitly assigned to the specific Google account** you're setting
  this up on — go into the license/user-management screen and confirm the
  account shows as actively licensed, not just that a subscription exists
  somewhere.

### 4b. Create a Gemini Enterprise app

1. In the Gemini Enterprise console page, click **"Create app"**.
2. Give it any name (an app ID is generated automatically).
3. Select **global** as the location.
4. Enter any organization name — it's just a label.
5. Click **Create**.

You do **not** need to set up a data store or connect any data sources —
that's for building a search app, which isn't needed here. Just creating
the app itself is enough.

Once created, open the app and copy its **ID** field — it looks like:
```
gemini-enterprise-1234567890_1234567890123
```


---

## Step 5 — Grant access to whoever will actually use it

Creating the project makes you its **Owner** by default, and setting up
Gemini Enterprise on it typically makes you its **Gemini Enterprise Admin**
too — both automatic, nothing extra to do for that part.

But that alone doesn't let anyone else use it. If a different person is going to actually
run things against this project, they need **two separate grants from you
as the admin** — without both, they'll hit errors even with the right
project/engine ID in hand:

1. **IAM access on the project** — go to **IAM & Admin → Add principal**,
   enter their Google account email, and grant them the
   **`Discovery Engine Editor`** role (at minimum).

2. **A Gemini Enterprise license assigned specifically to their email** —
   go to the Gemini Enterprise user/license management page and add them
   as a licensed user. This is separate from #1 and easy to miss: having
   project access does **not** automatically come with a license. Without
   it, they'll see an error like `"User must have an active license...
   Current state is EXPIRED"` even though the project itself works fine.

Once both are granted, that person can sign in with **their own** Google
account on their own machine — no need to share your login/password with
them.

---

## Step 6 — Send back the results

Send back:
1. The Gmail address used to create the project
2. The Project ID
3. The Engine/App ID
4. Confirmation of which email(s) were granted access in Step 5, if
   applicable

That's everything needed to take it from here.
