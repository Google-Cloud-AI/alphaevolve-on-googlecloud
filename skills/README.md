# AlphaEvolve Skills

## Overview
The AlphaEvolve skill allows you to run AlphaEvolve experiments directly from an agentic coding assistant (e.g. Antigravity). Using this skill, your coding assistant will guide you through the entire AlphaEvolve workflow, including configuring the experiment, running the evolutionary loop, building monitoring and observability reporting, and integrating the best result back into your code.

Everything ships as one skill, [`alpha_evolve`](alpha_evolve/). Only its `SKILL.md` is loaded when the skill triggers; it picks the phase that matches your request and reads that phase's guide on demand. See [`alpha_evolve/README.md`](alpha_evolve/README.md) for the file layout.

| Phase | What it does |
| --- | --- |
| Consultant | Read-only. Answers questions on fit, experiment design, best practices, and troubleshooting, based strictly on the expert reference guide. |
| Setup | Installs and finds the `ae` CLI, checks credentials and the Gemini Enterprise license, and configures `ae`. |
| Design | Scaffolds experiments: problem definition, initial seed program, and evaluator, via a test-driven workflow. |
| Runner | Validates the evaluator, configures the backend, and launches the experiment with the `ae` CLI. |
| Monitor | Runs the local evaluation control loop and gives periodic live progress reports. |
| Post-experiment | Analyzes completed runs, produces visual reports, and integrates the best evolved code back into your codebase. |

The skill detects where you are and chains the phases end to end. It replaces the six skills of earlier versions (`alpha_evolve_consultant`, `alpha_evolve_experiment_design`, `alpha_evolve_monitor`, `alpha_evolve_orchestrator`, `alpha_evolve_post_experiment`, `alpha_evolve_runner`).

Important limitations of this version:

* **Python Only:** the skill currently only supports evolving Python code.
  * **Note:** the AlphaEvolve skills were tested with Python version 3.13.7 and above.
* **Single Code Location Only:** so far, we tested the skill only to evolve one code location at a time. Context from multiple files can be included, but we did not test simultaneously optimizing multiple evolve blocks yet.
* **Operating System:** The skill works on Linux, macOS, and Windows.

## Prerequisites

1. The Google Cloud CLI (gcloud) is a pre-requisite for this Getting Started guide. Please install the Google Cloud CLI using the official [installation instructions](https://docs.cloud.google.com/sdk/docs/install-sdk).  This will be required for authentication.
   * You can confirm proper installation of the Google Cloud CLI by executing the following command:

```shell
gcloud --version
```

2. Before getting started with the AlphaEvolve Skill, you'll need to authenticate by running this command in a shell:

```shell
gcloud auth application-default login
```

3. Uv (uv)  is also required to assist with package management. Install uv by using the official [installation instructions](https://docs.astral.sh/uv/#installation) . You can confirm a successful installation by running the following command:

```shell
uv --version
```

4. A [Google Cloud Platform (GCP)](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects) project needs to be created / provisioned with the billing account configured, and a [Gemini Enterprise Engine](https://docs.cloud.google.com/gemini/enterprise/docs/quickstart-gemini-enterprise) created.

5. You need an active Gemini Enterprise license assigned to you in that project. Any Gemini Enterprise tier grants access, including a trial license. Without one, creating an experiment fails with `LICENSE_WITHOUT_SUBSCRIPTION_TIER`.

## Setup

Setup has two steps: install the `ae` CLI (required by the skill), then install the skill into your coding assistant. Both pull directly from the AlphaEvolve repo, so **cloning is optional** — a local clone is only needed if you want to install the skill from an offline source (see step 2).

1. Install the `ae` CLI from source. Since `uv` is already a prerequisite, install it straight from the repo without cloning:

```shell
uv tool install "git+https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud.git#subdirectory=skills"
```

   * `uv` is recommended — it's already a prerequisite and installs `ae` in isolation on your PATH; `pipx` does the same, and plain `pip` works inside an active virtualenv.
   * `#subdirectory=skills` installs the `ae` CLI **only**; the AlphaEvolve skill is installed separately in step 2.
   * If you installed `ae` before the skills were merged into one, upgrade it first with `uv tool upgrade ae-cli`. Older versions of `ae skills install` look for the six former skill directories and fail.

**Tip:** You can verify the installation of the `ae` CLI by running:

```shell
# Note: do not use --version
ae version
```

2. Install the skill into your coding assistant:

```shell
ae skills install
```

   * With no arguments, this auto-detects a local checkout (a directory holding the `alpha_evolve` skill directory, or a repo root with a `skills/` subdirectory), and otherwise fetches the skill from the GitHub repo (`Google-Cloud-AI/alphaevolve-on-googlecloud`, ref `main`).
   * It then shows a menu to choose the destination coding assistant (Gemini CLI, Antigravity, Claude Code, or OpenAI Codex) or a custom path.
   * It also removes the six former `alpha_evolve_*` skill directories from the destination, after asking (or without asking, with `--force`).

## Usage

### Getting Started

1. Open your coding agent/assistant. Confirm the AlphaEvolve skill has been loaded by submitting the below prompt. 

```
List all skills that are readily available without using another tool or skill
```

2. Confirm that the `alpha-evolve` skill is returned, and that none of the six former `alpha_evolve_*` skills are.
3. Review [`alpha_evolve/README.md`](alpha_evolve/README.md) and [`alpha_evolve/SKILL.md`](alpha_evolve/SKILL.md) to learn what the skill does.
4. Now you're ready to leverage the AlphaEvolve skill for the end-to-end implementation of AlphaEvolve. 
   1. We recommend using Gemini 3.5 Flash for the coding assistant. 

Now it's time to get started with executing your first experiment with AlphaEvolve!

1. Open an example algorithm. For the purposes of this Getting Started Guide, we'll leverage the following code:
   1. As you can see, the code already contains EVOLVE-BLOCK-START / EVOLVE-BLOCK-END comments to indicate which parts of the code should be evolved. The code also contains an evaluation function.
   2. **Note**:  When you know what code you want to optimize and how to evaluate it: add these elements manually to your code before you start.
      1. Otherwise: let the coding assistant help with this. For example, you can submit the following prompt(s) to your coding assistant: 
         1. "Prepare the currently opened file for optimization with AlphaEvolve" or 
         2. "Help me find locations in my code that could be optimized with AlphaEvolve".

```py
"""Initial program for the circle packing problem.

Goal: Pack N circles into a unit square, maximizing the sum of their radii.
No circles may overlap and all circles must be fully contained in the square.

Usage:
    python initial_program.py
"""

from typing import Any, Mapping

# EVOLVE-BLOCK-START

import numpy as np


def construct_packing(n: int, random_seed: int):
  """Construct an arrangement of n circles in a unit square.

  Args:
      n: Number of circles.
      random_seed: Random seed for reproducibility.

  Returns:
      Tuple of (centers, radii, sum_of_radii).
  """
  rng = np.random.default_rng(random_seed)
  centers = np.zeros((n, 2))

  centers[0] = [0.5, 0.5]

  for i in range(min(8, n - 1)):
    angle = 2 * np.pi * i / 8
    centers[i + 1] = [0.5 + 0.3 * np.cos(angle), 0.5 + 0.3 * np.sin(angle)]

  for i in range(max(0, min(n - 9, 16))):
    angle = 2 * np.pi * i / 16 * rng.uniform(0.9, 1.1)
    centers[i + 9] = [0.5 + 0.7 * np.cos(angle), 0.5 + 0.7 * np.sin(angle)]

  centers = np.clip(centers, 0.01, 0.99)
  radii = _compute_max_radii(centers)
  return centers, radii, float(np.sum(radii))


def _compute_max_radii(centers: np.ndarray) -> np.ndarray:
  """Compute maximum valid radii so circles don't overlap or exit the square."""
  n = centers.shape[0]
  radii = np.ones(n)

  for i in range(n):
    x, y = centers[i]
    radii[i] = min(x, y, 1 - x, 1 - y)

  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist:
        scale = dist / (radii[i] + radii[j] + 1e-7)
        radii[i] *= scale
        radii[j] *= scale

  return radii


# EVOLVE-BLOCK-END


def _circles_overlap(centers: np.ndarray, radii: np.ndarray) -> bool:
  n = centers.shape[0]
  for i in range(n):
    for j in range(i + 1, n):
      dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
      if radii[i] + radii[j] > dist:
        return True
  return False


def evaluate(inputs: Mapping[str, Any]) -> dict[str, float]:
  """Construct a packing and evaluate its score."""
  n = inputs["n"]
  random_seed = inputs.get("random_seed", 42)
  centers, radii, _ = construct_packing(n, random_seed=random_seed)

  if centers.shape != (n, 2) or not np.isfinite(centers).all():
    return {"sum_of_radii": -np.inf}
  if not ((radii[:, None] <= centers) & (centers <= 1 - radii[:, None])).all():
    return {"sum_of_radii": -np.inf}
  if (
      radii.shape != (n,)
      or not np.isfinite(radii).all()
      or not (0 <= radii).all()
  ):
    return {"sum_of_radii": -np.inf}
  if _circles_overlap(centers, radii):
    return {"sum_of_radii": -np.inf}

  return {"sum_of_radii": float(np.sum(radii))}


if __name__ == "__main__":
  scores = evaluate({"n": 26})
  for metric, value in scores.items():
    print(f"{metric}: {value}")
```

2. Prompt your coding assistant to optimize your code with AlphaEvolve. For example, you could instruct your agent with:
   1. "Use alpha_evolve to optimize the code of this model to make it faster."
   2. "Set up an AlphaEvolve experiment to find a better algorithm for this scheduling function."
   3. "Evolve this loss function to improve convergence on this XYZ benchmark."
   4. **Note**: In our experience, the skill works best when you provide a markdown file that explicitly defines the problem, outlines the objective, and gives relevant background information (e.g. constraints, evaluation criteria, or known baselines).

3. The assistant will then guide you through the process.

4. When everything is set up, the assistant will ask for your confirmation to start the experiment. It will then run the local evaluation loop in the background and periodically update you on its progress.

5. When the experiment is completed, the assistant will provide a summary and help you integrate the best performing program into your original code. 
   1. In our example, the initial sum_of_radii score of 0.941 was improved by +169.9% to 2.541:

This completes the AlphaEvolve Skills Getting Started Guide! Please provide any and all feedback on AlphaEvolve and AlphaEvolve skill usage to your Google Cloud Account Team.

### Example Prompts

```
"Prepare the currently opened file for optimization with AlphaEvolve"

"Help me find locations in my code that could be optimized with AlphaEvolve"

"Use alpha_evolve to optimize the code of this model to make it faster."

"Set up an AlphaEvolve experiment to find a better algorithm for this scheduling function."

"Evolve this loss function to improve convergence on this XYZ benchmark."

"Use AlphaEvolve to optimize the construct_packing() function in the currently opened file using the evaluate() function for evaluation"
```

### Tips / Best Practices

* **When you already know what code you want to optimize and how to evaluate it**: add these elements manually to your code before you start.
  * **Otherwise**: let the coding assistant help with this, for example: "prepare the currently opened file for optimization with AlphaEvolve" or "help me find locations in my code that could be optimized with AlphaEvolve".

## Appendix

### Supplemental Resources

### Podman

Podman (`podman`) can optionally be used to run AlphaEvolve experiments in a rootless sandbox to avoid side effects on the system. Note: Podman is optional. The AlphaEvolve skill works fine without Podman. 

1. Install Podman using the official Podman installation documentation [https://podman.io/docs/installation](https://podman.io/docs/installation)
2. Confirm installation by running the following command:

```shell
podman --version
```

3. Use the following command to configure the infrastructure resources needed for Podman. These commands allocate a dedicated block of unprivileged system IDs to your account, which is required by Podman to manage its internal files and users.
   1. Note that if multiple users want to use the skill on the same system, they need to use different system ID ranges (e.g. 200000-265535).

```shell
sudo usermod --add-subuids 100000-165535 $USER
sudo usermod --add-subgids 100000-165535 $USER
```

4. Now, when using your coding agent/assistant, you would prompt for skill use while qualifying that Podman should be used:

```
Optimize this code with AlphaEvolve. Use Podman.
```
