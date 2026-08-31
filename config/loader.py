from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _project_root() -> Path:
    """Absolute path of the project root (two levels up from this file)."""
    return Path(__file__).resolve().parent.parent


def load_environment(env_file: str | Path | None = None) -> bool:
    """
    Load the .env file into the process environment.

    Args:
        env_file: Optional explicit path to an env file. When omitted, it
            falls back to the BDS_ENV_FILE variable or `<project_root>/.env`.

    Returns:
        True if a dotenv file was found and parsed.
    """
    env_path = env_file or os.getenv(
        "BDS_ENV_FILE", str(_project_root() / ".env")
    )
    return load_dotenv(dotenv_path=Path(env_path), override=False)