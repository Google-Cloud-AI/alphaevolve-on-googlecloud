# ✨ Edit & Add Code Here

This directory is for your **Custom Experiments**.

To add a new experiment:
1. Clone an existing folder (e.g., `circle_packing_cloud_batch/`).
2. Implement your `main.py` (initial algorithm) and `evaluator.py` (scoring logic).
3. Provide a `run_experiment.py` to act as the experiment entrypoint (instantiate your search space and launch loop).
4. **For Cloud Batch execution:** Update `evaluator.Dockerfile` **only** if your experiment requires custom system-level libraries (e.g. custom apt-get packages). For simple base image changes (e.g. newer CUDA version), you can alternatively specify it during deployment using the `--vars base_evaluator_image=...` flag.
5. If your evaluation logic requires compiled libraries, provide a `Makefile` with an `all` target. It will be compiled automatically on scale-out workers.
