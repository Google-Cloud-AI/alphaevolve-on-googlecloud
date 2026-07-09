# CMOS Op-Amp Topology Exploration

This example evolves a CMOS Op-Amp topology in SPICE to maximize Gain while maintaining physical feasibility.

## Details
- **Optimization Goal**: Maximize voltage gain while respecting constraints (no clipping, power efficiency).
- **Programming Language**: SPICE (netlist).
- **Modes Supported**: Cloud Batch.
- **Metric Optimized**: `voltage_gain` (higher is better).

## How to Run
1. Refer to the [Deployment and Execution](../../README.md#deployment-and-execution) section in the root README to deploy the platform.
2. Pass the argument `example_dir=user_examples/netlist_simulation` to the deploy command to build this specific example.
3. Open cells in Jupyter notebook `/opt/jupyter/workspace/run_notebook.ipynb` provided by the server deployment to operate the experiment.

