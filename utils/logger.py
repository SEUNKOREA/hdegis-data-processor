import logging
import sys
from typing import Optional

_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str,
               level: str | int = "INFO",
               stream: Optional[object] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    # if already configured – return as‑is
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # stop double‑logs
    return logger