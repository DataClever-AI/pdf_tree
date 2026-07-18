"""
Pipeline service — thin Streamlit wrapper around src.pipeline.pipeline.

Handles sys.path setup so pages can import this without worrying about paths.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

# Ensure src/ is importable from the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.pipeline.pipeline import PipelineResult, run_pipeline


def build_pipeline(
    pdf_path: Path,
    work_dir: Path,
    *,
    run_docling: bool = True,
    window_size: int = 60,
    window_overlap: int = 6,
    extract_images: bool = True,
    min_image_px: int = 48,
    logger: logging.Logger | None = None,
    on_window_complete: Callable[[int, int, float], None] | None = None,
) -> PipelineResult:
    """Run full pipeline and return PipelineResult for UI consumption."""
    return run_pipeline(
        pdf_path=pdf_path,
        work_dir=work_dir,
        run_docling=run_docling,
        window_size=window_size,
        window_overlap=window_overlap,
        extract_images=extract_images,
        min_image_px=min_image_px,
        logger=logger,
        on_window_complete=on_window_complete,
    )


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)-8s | %(name)s | %(message)s"))
        logger.addHandler(h)
    return logger
