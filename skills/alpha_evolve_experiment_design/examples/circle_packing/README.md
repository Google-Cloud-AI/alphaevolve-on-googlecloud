# Circle Packing in Unit Square

Pack 26 non-overlapping circles inside a unit square [0,1]×[0,1] to maximize the
sum of their radii.

## Files

| File                                  | Purpose                           |
| ------------------------------------- | --------------------------------- |
| `initial_program.py`                  | Seed program with EVOLVE-BLOCK    |
:                                       : markers                           :
| `evaluator.py`                        | Evaluation function for the       |
:                                       : AlphaEvolve API                   :
| `test_program.py`                     | Tests for the initial program     |
| `test_evaluator.py`                   | Tests for the evaluator           |
| `example_evaluation.json`             | Sample evaluator output           |
| `pyproject.toml`                      | Project configuration             |
| `.evolve/experiment_description.json` | Complete experiment specification |

## Running Tests

```bash
uv sync
uv run pytest -v
```

## Metric

-   **Name:** `sum_of_radii`
-   **Direction:** maximize
-   **Strategy:** Fixed benchmark with n=26 circles

## Constraints

-   All circles must be fully inside the unit square
-   No two circles may overlap
-   All radii must be non-negative

## Launching

Use the `experiment-runner` skill or the `ae` CLI to launch this experiment.
