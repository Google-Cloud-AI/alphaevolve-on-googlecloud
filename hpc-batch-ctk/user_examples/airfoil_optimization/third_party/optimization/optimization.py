# Originally from: https://github.com/NielsBongers/openfoam-airfoil-optimization
# Licensed under the GNU General Public License v3.0 (see LICENSE in this directory).

import shutil
import uuid

import numpy as np
import pandas as pd

from third_party.airfoil_mesher.airfoil_mesher import mesh_airfoil
from src.kulfan_converter.kulfan_to_coord import CST_shape
from third_party.utils.logging_setup import get_logger
from third_party.utils.openfoam_interfaces import (
    read_force_coefficients,
    run_blockmesh,
    run_checkmesh,
    run_simple,
    set_fluid_velocities,
)

from ..optimization.parameters import Parameters  # type: ignore
from ..optimization.result_processing import process_result  # type: ignore


def funct(x: np.array, parameters: Parameters) -> float:
    """Optimization function.

    Args:
        x (np.array): The six CST parameters to generate the airfoil with.
        parameters (Parameters): Settings dataclass.

    Returns:
        float: Goal function performance.
    """
    logger = get_logger(__name__)

    case_uuid = str(uuid.uuid4()) if not parameters.is_debug else parameters.run_name

    wu = x[0:3]  # Upper surface
    wl = x[3:6]  # Lower surface

    dz = 0
    N = 50

    airfoil_CST = CST_shape(wl, wu, dz, N)
    airfoil_coordinates = airfoil_CST.airfoil_coor()

    logger.info(f"Running case {case_uuid} with {x}")

    case_path = parameters.cases_folder / case_uuid
    template_path = parameters.template_path

    # blockMesh seems to accept cases where the bottom part of the airfoil clips into the top. This should prevent that.
    top_section = airfoil_coordinates[
        1:
    ][
        0 : 25 - 1
    ]  # We skip the first entry (that's (1.0, 0.0), and the last (because that's (0.0 0.0)). Now the top section has the same x as the bottom section.

    bottom_section = airfoil_coordinates[
        1:
    ][
        25:
    ][
        ::-1
    ]  # We then do the same here, except we reverse the order, so that now the x-coordinates line up.

    top_bottom_difference = top_section[:, 1] - bottom_section[:, 1]

    if (top_bottom_difference < 0).any():
        logger.info("Airfoil clipping detected")

        process_result(
            x=x,
            parameters=parameters,
            case_uuid=case_uuid,
            case_path=case_path,
            no_clipping=False,
            block_mesh_result=False,
            check_mesh_result=False,
            simple_result=False,
            has_converged=False,
        )
        return np.inf

    if case_path.exists():
        shutil.rmtree(case_path)
    case_path.mkdir(exist_ok=True, parents=True)
    shutil.copytree(src=template_path, dst=case_path, dirs_exist_ok=True)

    set_fluid_velocities(case_path, parameters.fluid_velocity)
    mesh_airfoil(airfoil_coordinates=airfoil_coordinates, case_path=case_path)

    block_mesh_result = run_blockmesh(case_path=case_path)
    check_mesh_result = run_checkmesh(case_path=case_path)

    if not (
        block_mesh_result and check_mesh_result
    ):  # blockMesh is giving errors or checkMesh is complaining.
        logger.debug(
            f"Encountered error. Skipping {case_uuid}. blockMesh: {block_mesh_result}. checkMesh: {check_mesh_result}"
        )
        process_result(
            x=x,
            parameters=parameters,
            case_uuid=case_uuid,
            case_path=case_path,
            no_clipping=True,
            block_mesh_result=block_mesh_result,
            check_mesh_result=check_mesh_result,
            simple_result=False,
            has_converged=False,
        )
        return np.inf

    # Creating the .foam file
    with open(
        case_path / (parameters.run_name + ".foam"),
        "w",
    ) as _:
        pass

    simple_result = run_simple(case_path, case_uuid)

    if not simple_result:  # SIMPLE has failed to run.
        logger.debug(f"Encountered error with SIMPLE. Skipping {case_uuid}.")
        process_result(
            x=x,
            parameters=parameters,
            case_uuid=case_uuid,
            case_path=case_path,
            no_clipping=True,
            block_mesh_result=block_mesh_result,
            check_mesh_result=check_mesh_result,
            simple_result=simple_result,
            has_converged=False,
            cl=np.nan,
            cd=np.nan,
        )
        return np.inf

    # We now got data: let's read it and post-process a bit.
    df = read_force_coefficients(case_path)
    df["cl_cd_ratio"] = df["Cl"] / df["Cd"]

    # I noticed it doesn't converge in a lot of cases, so I added this to check.
    converged_std_cl_cd_ratio = df[df["# Time"] > 1500]["cl_cd_ratio"].std()
    if converged_std_cl_cd_ratio > 1.0:
        logger.info(f"Solver failed to converge: std = {converged_std_cl_cd_ratio}")
        process_result(
            x=x,
            parameters=parameters,
            case_uuid=case_uuid,
            case_path=case_path,
            no_clipping=True,
            block_mesh_result=block_mesh_result,
            check_mesh_result=check_mesh_result,
            simple_result=simple_result,
            has_converged=False,
            cl=np.nan,
            cd=np.nan,
        )
        return np.inf

    lift_drag_ratio = df["cl_cd_ratio"].iloc[-1]

    logger.debug(f"Got {lift_drag_ratio}")
    logger.info(f"Successfully ran: {case_uuid} - {lift_drag_ratio}")

    if df["Cd"].iloc[-1] < 0:
        logger.info(f"Got {df['Cd'].iloc[-1]}: penalizing.")

        process_result(
            x=x,
            parameters=parameters,
            case_uuid=case_uuid,
            case_path=case_path,
            no_clipping=True,
            block_mesh_result=block_mesh_result,
            check_mesh_result=check_mesh_result,
            simple_result=simple_result,
            has_converged=True,
            cl=df["Cl"].iloc[-1],
            cd=df["Cd"].iloc[-1],
        )
        return np.inf

    process_result(
        x=x,
        parameters=parameters,
        case_uuid=case_uuid,
        case_path=case_path,
        no_clipping=True,
        block_mesh_result=block_mesh_result,
        check_mesh_result=check_mesh_result,
        simple_result=simple_result,
        has_converged=True,
        cl=df["Cl"].iloc[-1],
        cd=df["Cd"].iloc[-1],
    )

    return -np.abs(
        lift_drag_ratio
    )  # Positive or negative doesn't matter; we can fly upside down too.
