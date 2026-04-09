import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def pat_provider_from_config():
    config_root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = config_root / "quelware-client" / "pat"

    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    content = path.read_text().splitlines()
    if not content:
        raise ValueError(f"The content of {path} is blank.")
    pat = content[0].strip()  # use the first line and remove whitespaces
    if not pat:
        raise ValueError(f"The content of {path} is blank.")
    return pat
