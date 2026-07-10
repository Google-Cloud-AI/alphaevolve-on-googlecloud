# Originally from: https://github.com/NielsBongers/openfoam-airfoil-optimization
# Licensed under the GNU General Public License v3.0 (see LICENSE in this directory).

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from .logging_setup import get_logger

def _find_openfoam_bashrc() -> str | None:
    # Check common locations
    paths = glob.glob("/usr/lib/openfoam/openfoam*/etc/bashrc") + glob.glob("/opt/openfoam*/etc/bashrc")
    if paths:
        return paths[0]
    return None

def _should_use_docker() -> bool:
    # Check if docker binary is available and we are NOT inside the Batch worker environment
    has_docker = shutil.which("docker") is not None
    # Cloud Batch worker sets _JOB_ID or is running as container
    is_in_worker = os.environ.get("_JOB_ID") is not None or os.path.exists("/.dockerenv")
    return has_docker and not is_in_worker

def run_blockmesh(case_path: Path):
    logger = get_logger(__name__)
    
    if _should_use_docker():
        logger.debug("Running blockMesh via Docker wrapper")
        abs_path = case_path.resolve()
        uid = os.getuid()
        gid = os.getgid()
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{uid}:{gid}",
                "-v",
                f"{abs_path}:/home/openfoam",
                "opencfd/openfoam-run:2406",
                "blockMesh",
            ],
            cwd=case_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        logger.debug("Running blockMesh directly in local environment")
        bashrc = _find_openfoam_bashrc()
        if shutil.which("blockMesh") is None and bashrc:
            result = subprocess.run(
                ["/bin/bash", "-c", f"source {bashrc} && blockMesh"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            result = subprocess.run(
                ["blockMesh"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

    logger.debug(f"blockMesh: {result.returncode}")
    return result.returncode == 0


def run_checkmesh(case_path: Path):
    logger = get_logger(__name__)
    
    if _should_use_docker():
        logger.debug("Running checkMesh via Docker wrapper")
        abs_path = case_path.resolve()
        uid = os.getuid()
        gid = os.getgid()
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{uid}:{gid}",
                "-v",
                f"{abs_path}:/home/openfoam",
                "opencfd/openfoam-run:2406",
                "checkMesh",
            ],
            cwd=case_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        logger.debug("Running checkMesh directly in local environment")
        bashrc = _find_openfoam_bashrc()
        if shutil.which("checkMesh") is None and bashrc:
            result = subprocess.run(
                ["/bin/bash", "-c", f"source {bashrc} && checkMesh"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            result = subprocess.run(
                ["checkMesh"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

    logger.debug(f"checkMesh: {result.returncode}")
    logger.debug(f"Output:\n{result.stdout}")

    if result.returncode == 0:
        mesh_checks_failed = re.search(
            pattern="Failed ([0-9]+) mesh checks", string=result.stdout
        )
        mesh_okay = "Mesh OK." in result.stdout

        if mesh_okay:
            logger.debug("Mesh OK!")
            return True

        if mesh_checks_failed:
            logger.warning(f"Mesh checks failed: {mesh_checks_failed.group(1)}")
            return False

    return False


def run_simple(case_path: Path, case_uuid: str):
    logger = get_logger(__name__)
    
    if _should_use_docker():
        logger.debug("Running simpleFoam via Docker wrapper")
        abs_path = case_path.resolve()
        uid = os.getuid()
        gid = os.getgid()
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{uid}:{gid}",
                "-v",
                f"{abs_path}:/home/openfoam",
                "opencfd/openfoam-run:2406",
                "simpleFoam",
            ],
            cwd=case_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        logger.debug("Running simpleFoam directly in local environment")
        bashrc = _find_openfoam_bashrc()
        if shutil.which("simpleFoam") is None and bashrc:
            result = subprocess.run(
                ["/bin/bash", "-c", f"source {bashrc} && simpleFoam"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            result = subprocess.run(
                ["simpleFoam"],
                cwd=case_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

    if not result.returncode == 0:
        logger.debug(f"Case UUID: {case_uuid}\n{result.stderr}")
        logger.warning("Failed to run SIMPLE.")

    return result.returncode == 0


def set_fluid_velocities(case_path: Path, v: np.array):
    velocity_magnitude = np.linalg.norm(v)

    with open(case_path / "system/controlDict", "r") as f:
        control_dict_template = f.read()

    with open(case_path / "0/U", "r") as f:
        u_template = f.read()

    control_dict_template = control_dict_template.replace(
        "{{v_magnitude}}", str(velocity_magnitude)
    )

    alpha = np.arctan2(v[1], v[0])

    lift_x = -np.sin(alpha)
    lift_y = np.cos(alpha)
    lift_z = 0.0
    drag_x = np.cos(alpha)
    drag_y = np.sin(alpha)
    drag_z = 0.0

    control_dict_template = control_dict_template.replace("{{lift_x}}", str(lift_x))
    control_dict_template = control_dict_template.replace("{{lift_y}}", str(lift_y))
    control_dict_template = control_dict_template.replace("{{lift_z}}", str(lift_z))
    control_dict_template = control_dict_template.replace("{{drag_x}}", str(drag_x))
    control_dict_template = control_dict_template.replace("{{drag_y}}", str(drag_y))
    control_dict_template = control_dict_template.replace("{{drag_z}}", str(drag_z))

    u_template = u_template.replace("{{v_x}}", str(v[0]))
    u_template = u_template.replace("{{v_y}}", str(v[1]))
    u_template = u_template.replace("{{v_z}}", str(v[2]))

    with open(case_path / "system/controlDict", "w") as f:
        f.write(control_dict_template)

    with open(case_path / "0/U", "w") as f:
        f.write(u_template)


def read_force_coefficients(case_path: Path):
    force_coefficients_path = case_path / Path(
        r"postProcessing/forceCoeffs/0/coefficient.dat"
    )

    df = pd.read_csv(force_coefficients_path, skiprows=12, sep="\t")
    df.columns = [column_name.strip() for column_name in df.columns]

    return df
