from pathlib import Path
import os


def data_root() -> Path:
    """Beschreibbarer Datenordner, unabhängig vom Installationsort."""
    configured = os.environ.get("DIENSTLEISTERKARTEN_HOME")
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Dienstleisterkarten"
    return Path.home() / ".dienstleisterkarten"


def ensure_directories(root: Path | None = None) -> dict[str, Path]:
    root = root or data_root()
    paths = {name: root / name for name in ("daten", "exporte", "sicherungen")}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
