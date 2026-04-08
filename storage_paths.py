import os
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LEGACY_DATA_DIR = BASE_DIR / "data"


def _resolved_data_dir():
    configured = (os.getenv("BOT_DATA_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    render_disk = (os.getenv("RENDER_DISK_PATH") or "").strip()
    if render_disk:
        return (Path(render_disk).expanduser().resolve() / "trading-bot").resolve()

    return LEGACY_DATA_DIR


DATA_DIR = _resolved_data_dir()


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def migrate_legacy_file(relative_path: str):
    ensure_data_dir()
    target = DATA_DIR / relative_path
    if DATA_DIR == LEGACY_DATA_DIR:
        return target

    legacy = LEGACY_DATA_DIR / relative_path
    if not target.exists() and legacy.exists() and legacy.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
    return target


def migrate_legacy_tree(relative_path: str):
    ensure_data_dir()
    target = DATA_DIR / relative_path
    if DATA_DIR == LEGACY_DATA_DIR:
        return target

    legacy = LEGACY_DATA_DIR / relative_path
    if not target.exists() and legacy.exists() and legacy.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy, target, dirs_exist_ok=True)
    return target
