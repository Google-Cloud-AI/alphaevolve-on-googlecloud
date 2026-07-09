# Airfoil Optimization (OpenFOAM)

This example evolves a physics-aware search algorithm in Python to optimize the aerodynamic shape of a 2D airfoil. The algorithm optimizes the 6 Kulfan Class Shape Transformation (CST) parameters of the airfoil to maximize the lift-to-drag ratio ($C_l/C_d$) within a budget of 10 actual OpenFOAM simulations.

## Details
- **Optimization Goal**: Evolve a Python optimization algorithm that coordinates CST parameter selection and surrogate models to locate the highest-performance airfoil shape.
- **Programming Language**: Python (with OpenFOAM physics solver execution).
- **Modes Supported**: Cloud Batch.
- **Metric Optimized**: `lift_to_drag_ratio` (higher is better, calculated using OpenFOAM `simpleFoam`).

## OpenFOAM solver environment
- The evaluations are run in an OpenFOAM docker container (`opencfd/openfoam-run:2406`). 
- **Post-Optimization Analysis**: At the end of the experiment, a polar sweep is automatically run across multiple Angles of Attack (0.0 to 15.0 degrees in steps of 2.5) for the best airfoil. The sweep generates coefficients plots (`polar_coefficients.png` and `polar_lift_drag.png`) and tabular data (`polar_sweep_results.csv`), uploading them to your GCS experiment bucket.
- **Note on Polar Sweep execution**: The polar sweep requires OpenFOAM to be installed on the environment executing the main controller script (`run_experiment.py`). If OpenFOAM is not installed in the controller container (which runs on `python:3.12-slim-bookworm` by default), the polar sweep is cleanly skipped. To execute the polar sweep in the cloud, you can deploy the controller container using `opencfd/openfoam-run:2406` as the `base_controller_image`.

## How to Run
1. Refer to the [Deployment and Execution](../../README.md#deployment-and-execution) section in the root README to deploy the platform.
2. Deploy the experiment configuration using `gcluster` with the preferred variables for this example:   ```bash
   gcluster deploy alpha-evolve-experiment.yaml \
     -d alpha-evolve-deployment.yaml \
     -o ../deployment \
     --vars project_id=[gcp-project-id] \
     --vars existing_bucket_name=[YOUR_BUCKET_NAME] \
     --vars region=[YOUR_REGION] \
     --vars="user_experiment_name=airfoil" \
     --vars base_evaluator_image=opencfd/openfoam-run:2406 \
     --vars example_dir=user_examples/airfoil_optimization \
     --vars max_duration_seconds=7200 \
     --vars concurrency=10 \
     --vars max_duration=24 \
     --vars idle_timeout=5 \
     -w --auto-approve
   ```

- **Experiment Lifetime Configurations**:
  - `max_duration`: The absolute maximum wall-clock time the experiment run can execute from start in hours (valid range: 1 to 24, default: 6).
  - `idle_timeout`: The maximum period of inactivity allowed in hours before the experiment is automatically paused. This must be strictly less than `max_duration` (default: 5).

3. Open the Jupyter notebook `/opt/jupyter/workspace/run_notebook.ipynb` provided by the server deployment to operate the experiment.
