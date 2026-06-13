import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".openclaw" / "notion.json"
VAULT_PATH = Path.home() / "Documents" / "Obsidian Vault"
DB_PATH = Path.home() / "openclaw-tools" / "data" / "notion_sync.db"

IGNORE_DIRS = {".obsidian", ".trash", ".git"}
IGNORE_FILES = {".DS_Store"}


def load() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    if not cfg.get("token") or not cfg.get("parent_page_id"):
        raise RuntimeError(f"{CONFIG_PATH} missing token or parent_page_id")
    return cfg
