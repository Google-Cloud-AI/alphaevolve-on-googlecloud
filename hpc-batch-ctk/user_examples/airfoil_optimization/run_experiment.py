# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import logging
import os
import sys
import shutil
from pathlib import Path
from typing import Any, Mapping
import nest_asyncio
import numpy as np
import matplotlib.pyplot as plt

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env
from alpha_evolve.utils import read_file_from_gcs

from evaluator import (
    AIRFOIL_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    evaluate as airfoil_evaluation,
)

# Import CST_shape to visualize the final optimized airfoil
from src.kulfan_converter.kulfan_to_coord import CST_shape

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V2P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv("_USER_EXPERIMENT_NAME", "airfoil-optimization")

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "10")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "23")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "22")


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str):
    """Uploads a local file to a GCS bucket."""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path))
        print(f"Successfully uploaded {local_path.name} to GCS: gs://{bucket_name}/{blob_name}")
    except Exception as e:
        print(f"Failed to upload {local_path.name} to GCS: {e}")


def visualize_airfoil(x: np.ndarray, title: str, output_path: Path):
    """Reconstructs and plots the airfoil geometry from CST parameters and saves to output_path."""
    wu = x[0:3]  # Upper surface parameters
    wl = x[3:6]  # Lower surface parameters
    dz = 0
    N = 50

    try:
        airfoil_CST = CST_shape(wl, wu, dz, N)
        coords = airfoil_CST.airfoil_coor()

        plt.figure(figsize=(10, 4))
        plt.plot(coords[:, 0], coords[:, 1], "b-", linewidth=2, label="Airfoil Profile")
        plt.fill(coords[:, 0], coords[:, 1], "cyan", alpha=0.2)
        plt.title(title, fontsize=14, pad=15)
        plt.xlabel("x/c", fontsize=12)
        plt.ylabel("y/c", fontsize=12)
        plt.axis("equal")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()
        plt.savefig(output_path, dpi=300)
        plt.close()
        print(f"Saved airfoil visualization to {output_path}")
    except Exception as e:
        print(f"Failed to visualize airfoil: {e}")


def run_polar_sweep_and_plot(best_x: np.ndarray, output_dir: Path):
    """Runs an AoA sweep for the best airfoil geometry and plots performance curves."""
    from third_party.utils.openfoam_interfaces import _should_use_docker, _find_openfoam_bashrc
    
    can_run = _should_use_docker() or shutil.which("blockMesh") is not None or _find_openfoam_bashrc() is not None
    if not can_run:
        print("\n=========================================")
        print("WARNING: OpenFOAM ('blockMesh') was not found in the current environment (local or docker).")
        print("Skipping local polar sweep simulations and plotting.")
        print("=========================================\n")
        return

    print("\n=========================================")
    print("STARTING POLAR SWEEP FOR BEST AIRFOIL PROFILE")
    print("=========================================")
    
    # Define AoA range to sweep (from 0 to 15 degrees in steps of 2.5)
    aoas = [0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0]
    
    # Setup a temporary clean sweep directory
    sweep_cases_dir = Path("polar_sweep_cases")
    if sweep_cases_dir.exists():
        shutil.rmtree(sweep_cases_dir)
    sweep_cases_dir.mkdir(parents=True, exist_ok=True)
    
    temp_csv_path = output_dir / "polar_sweep_raw.csv"
    if temp_csv_path.exists():
        temp_csv_path.unlink()
        
    from third_party.optimization.optimization import funct, Parameters
    
    for aoa in aoas:
        print(f"\n--> Evaluating AoA = {aoa} degrees...")
        # Free-stream velocity magnitude is 100 m/s
        alpha_rad = np.radians(aoa)
        v_x = 100.0 * np.cos(alpha_rad)
        v_y = 100.0 * np.sin(alpha_rad)
        velocity = np.array([v_x, v_y, 0.0])
        
        run_params = Parameters(
            run_name=f"polar_aoa_{aoa}",
            cases_folder=sweep_cases_dir,
            template_path=Path("third_party/openfoam_template"),
            is_debug=True,
            csv_path=temp_csv_path,
            fluid_velocity=velocity,
        )
        
        try:
            # Run the standard OpenFOAM solver interface for this specific AoA
            score = funct(best_x, run_params)
            print(f"    Finished AoA = {aoa} with score (negative absolute Cl/Cd): {score}")
        except Exception as e:
            print(f"    ERROR evaluating AoA = {aoa}: {e}")
            
    # Read the generated CSV to plot the results
    if temp_csv_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(temp_csv_path)
            
            # Parse AoA from the run name (e.g. polar_aoa_5.0 -> 5.0)
            df['aoa'] = df['run_name'].apply(lambda name: float(name.split('_')[-1]))
            df = df.sort_values(by='aoa')
            
            # Filter out failed runs (where any essential OpenFOAM step failed)
            # The CSV columns map to no_clipping, block_mesh, check_mesh, simple.
            df['failed'] = ~(df[['no_clipping', 'block_mesh', 'check_mesh', 'simple']]).all(axis=1)
            df_valid = df[df['failed'] == False].copy()
            
            if df_valid.empty:
                print("ERROR: No simulations converged or succeeded in the sweep. Cannot plot curves.")
                return
                
            # Calculate Cl/Cd ratio
            df_valid['cl_cd'] = df_valid['cl'] / df_valid['cd']
            
            print("\n--- Polar Sweep Data Summary ---")
            print(df_valid[['aoa', 'cl', 'cd', 'cl_cd']])
            print("--------------------------------")
            
            # Save tabular results to a neat CSV in output_dir
            df_valid.to_csv(output_dir / "polar_sweep_results.csv", index=False)
            
            # Plot 1: Lift and Drag Coefficients vs AoA
            fig, ax1 = plt.subplots(figsize=(10, 6))
            
            color = 'tab:blue'
            ax1.set_xlabel('Angle of Attack (degrees)', fontsize=12)
            ax1.set_ylabel('Lift Coefficient ($C_l$)', color=color, fontsize=12)
            line1 = ax1.plot(df_valid['aoa'], df_valid['cl'], 'o-', color=color, linewidth=2, label='Lift Coefficient ($C_l$)')
            ax1.tick_params(axis='y', labelcolor=color)
            ax1.grid(True, linestyle='--', alpha=0.5)
            
            ax2 = ax1.twinx()  
            color = 'tab:red'
            ax2.set_ylabel('Drag Coefficient ($C_d$)', color=color, fontsize=12)
            line2 = ax2.plot(df_valid['aoa'], df_valid['cd'], 's--', color=color, linewidth=2, label='Drag Coefficient ($C_d$)')
            ax2.tick_params(axis='y', labelcolor=color)
            
            lines = line1 + line2
            labels = [l.get_label() for l in lines]
            ax1.legend(lines, labels, loc='upper left')
            
            plt.title('Aerodynamic Coefficients vs. Angle of Attack', fontsize=14, pad=15)
            fig.tight_layout()  
            plot_coef_path = output_dir / "polar_coefficients.png"
            plt.savefig(plot_coef_path, dpi=300)
            plt.close()
            print(f"Saved coefficients plot to {plot_coef_path}")
            
            # Plot 2: Lift-to-Drag Ratio vs AoA
            plt.figure(figsize=(10, 6))
            plt.plot(df_valid['aoa'], df_valid['cl_cd'], 'D-g', linewidth=2.5, label='Lift-to-Drag ($C_l/C_d$)')
            plt.title('Lift-to-Drag Ratio vs. Angle of Attack', fontsize=14, pad=15)
            plt.xlabel('Angle of Attack (degrees)', fontsize=12)
            plt.ylabel('Lift-to-Drag Ratio ($C_l/C_d$)', fontsize=12)
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.legend()
            
            plot_ld_path = output_dir / "polar_lift_drag.png"
            plt.savefig(plot_ld_path, dpi=300)
            plt.close()
            print(f"Saved Lift-to-Drag ratio plot to {plot_ld_path}")
            
        except Exception as e:
            print(f"Failed to read and plot sweep results: {e}")
        finally:
            # Cleanup raw sweep CSV
            if temp_csv_path.exists():
                temp_csv_path.unlink()
    else:
        print("ERROR: No sweep results CSV was generated.")
        
    # Clean up temp sweep case folders
    if sweep_cases_dir.exists():
        shutil.rmtree(sweep_cases_dir)
    print("Cleanup completed.")


def main():
    logging.basicConfig(level=logging.INFO)

    exp_config = {
        "title": "Airfoil Search Optimization",
        "problem_description": (
            "Evolve a physics-aware search algorithm in Python to find the best 6 CST parameters "
            "of a 2D airfoil to maximize Cl/Cd (Lift-to-Drag ratio) within exactly 10 actual OpenFOAM simulations.\n\n"
            "Note that the evaluation environment only supports standard libraries, numpy, scipy, "
            "and scikit-learn (1.8+). You can use scikit-learn (e.g., sklearn.gaussian_process) "
            "for surrogate models or regressor heuristics. Do NOT import or use other external "
            "packages like GPy, scikit-optimize, tensorflow, or torch, as they are not installed "
            "in the environment."
        ),
        "program_language": "python",
        "run_settings": {
            "max_programs": MAX_PROGRAMS_GENERATED,
            "concurrency": CONCURRENCY,
            "max_duration": MAX_DURATION,
            "idle_timeout": IDLE_TIMEOUT,
        },
        "generation_settings": {
            "models": parse_models_from_env(MODEL)
        },
    }

    initial_program = {
        "content": {
            "files": [
                {
                    "path": "main.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        },
        "evaluation": {
            "scores": {
                "scores": [{"metric": AIRFOIL_EVALUATION_METRIC, "score": 17.54}]
            }
        },
    }

    nest_asyncio.apply()
    controller = AlphaEvolveController()
    asyncio.run(controller.run_loop(
        evaluator_function=airfoil_evaluation,
        exp_config=exp_config,
        initial_program=initial_program
    ))

    # Visualize the best program found
    list_params = {"order_by": "lift_to_drag_ratio asc"}
    response = controller.list_programs(params=list_params)

    if response and "alphaEvolvePrograms" in response:
        top_programs = response["alphaEvolvePrograms"]
        top_programs.sort(
            key=lambda p: get_score(p, AIRFOIL_EVALUATION_METRIC), reverse=True
        )

        best_prog = top_programs[0]
        best_prog_id = best_prog.get("name").split("/")[-1]
        best_score = get_score(best_prog, AIRFOIL_EVALUATION_METRIC)
        
        print(f"\n=========================================")
        print(f"BEST PROGRAM FOUND: {best_prog_id} (Score: {best_score})")
        print(f"=========================================")
        
        # Download its optimal CST parameters from GCS leaderboards
        blob_name = f"{USER_EXPERIMENT_NAME}/best_x/{best_prog_id}.json"
        print(f"Fetching optimized parameters from GCS: gs://{BUCKET_NAME}/{blob_name}")
        best_x_data = read_file_from_gcs(BUCKET_NAME, blob_name)
        
        if best_x_data:
            best_x = np.array(best_x_data["best_x"])
            print(f"Successfully retrieved CST parameters for {best_prog_id}: {best_x}")
            
            # Run visualizer plot
            output_dir = Path("results")
            output_dir.mkdir(parents=True, exist_ok=True)
            visualize_path = output_dir / "optimized_airfoil.png"
            visualize_airfoil(
                best_x,
                f"Optimized Airfoil Profile (Lift-to-Drag Score: {best_score:.2f})",
                visualize_path,
            )
            upload_to_gcs(visualize_path, BUCKET_NAME, f"{USER_EXPERIMENT_NAME}/results/{visualize_path.name}")
            
            # Run the polar sweep and save plots!
            run_polar_sweep_and_plot(best_x, output_dir)
 
            # Upload polar sweep results to GCS
            for file_name in ["polar_coefficients.png", "polar_lift_drag.png", "polar_sweep_results.csv"]:
                file_path = output_dir / file_name
                if file_path.exists():
                    upload_to_gcs(file_path, BUCKET_NAME, f"{USER_EXPERIMENT_NAME}/results/{file_name}")
        else:
            print(f"WARNING: Could not find optimal CST parameters file in GCS for program {best_prog_id}.")
    else:
        print("No programs found to visualize.")


if __name__ == "__main__":
    if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
        print("Please set the _PROJECT_ID environment variable.")
        sys.exit(1)
    if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
        print("Please set the _CLOUD_BUCKET_NAME environment variable.")
        sys.exit(1) 
    main()
