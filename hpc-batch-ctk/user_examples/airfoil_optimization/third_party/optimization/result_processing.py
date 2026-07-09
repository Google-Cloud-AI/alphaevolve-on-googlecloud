# Originally from: https://github.com/NielsBongers/openfoam-airfoil-optimization
# Licensed under the GNU General Public License v3.0 (see LICENSE in this directory).

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from .parameters import Parameters  # type: ignore


def process_result(
    x: np.array,
    parameters: Parameters,
    case_uuid: str,
    case_path: Path,
    no_clipping: bool,
    block_mesh_result: bool,
    check_mesh_result: bool,
    simple_result: bool,
    has_converged: bool,
    cl: Optional[float] = None,
    cd: Optional[float] = None,
):
    """Saving the results to a CSV.

    Args:
        x (np.array): The six CST parameters.
        parameters (Parameters): Settings used during the simulation.
        case_uuid (str): UUID.
        case_path (Path): Path to the case.
        block_mesh_result (bool): Results from blockMesh.
        check_mesh_result (bool): Results from checkMesh.
        simple_result (bool): Result from SIMPLE.
        cl (Optional[float], optional): Coefficient of lift. Defaults to None.
        cd (Optional[float], optional): Coefficient of drag. Defaults to None.
    """
    timestamp = datetime.now().isoformat(timespec="microseconds")

    parameters.csv_path.parent.mkdir(exist_ok=True, parents=True)
    if not parameters.csv_path.exists() or parameters.csv_path.stat().st_size == 0:
        with open(parameters.csv_path, "w") as f:
            f.write("timestamp,UUID,run_name,x0,x1,x2,x3,x4,x5,no_clipping,block_mesh,check_mesh,simple,convergence,v_x,v_y,v_z,cl,cd\n")
    with open(parameters.csv_path, "a") as f:
        f.write(
            f'{timestamp},{case_uuid},"{parameters.run_name}",{x[0]},{x[1]},{x[2]},{x[3]},{x[4]},{x[5]},{no_clipping},{block_mesh_result},{check_mesh_result},{simple_result},{has_converged},{parameters.fluid_velocity[0]},{parameters.fluid_velocity[1]},{parameters.fluid_velocity[2]},{cl},{cd}\n'
        )
    try:
        shutil.rmtree(case_path) if not parameters.is_debug else None
    except Exception:
        # I got an error the folder was already gone - perhaps it was deleted manually - but I don't care if that gives an error.
        pass
