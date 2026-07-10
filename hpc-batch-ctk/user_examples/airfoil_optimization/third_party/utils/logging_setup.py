# Originally from: https://github.com/NielsBongers/openfoam-airfoil-optimization
# Licensed under the GNU General Public License v3.0 (see LICENSE in this directory).

import logging
from pathlib import Path


def get_logger(logger_name: str) -> logging.Logger:
    """Creates a logger.

    Args:
        logger_name (str): Name for the logger.

    Returns:
        logging.Logger: Logger object
    """
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
        handlers=[
            logging.FileHandler("logs/file.log", mode="a"),
            logging.StreamHandler(),
        ],
    )

    return logging.getLogger(logger_name)
