#!/usr/bin/env python3
"""Replace the site avatar and update _config.yml."""
import sys
import shutil
import subprocess
import re
from pathlib import Path

BLOG_DIR = Path.home() / "jyaenugu.github.io"
AVATAR_DIR = BLOG_DIR / "assets" / "img" / "avatar"
CONFIG = BLOG_DIR / "_config.yml"


def run(cmd):
    return subprocess.run(cmd, cwd=BLOG_DIR, check=True, capture_output=True, text=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: set-avatar.py <image_path>", file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.is_file():
        print(f"Image not found: {src}", file=sys.stderr)
        sys.exit(1)

    ext = src.suffix.lower() or ".jpg"
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    for old in AVATAR_DIR.glob("avatar.*"):
        old.unlink()

    dst = AVATAR_DIR / f"avatar{ext}"
    shutil.copy2(src, dst)
    rel_path = "/" + dst.relative_to(BLOG_DIR).as_posix()

    run(["git", "pull", "--rebase", "--quiet"])

    config_text = CONFIG.read_text(encoding="utf-8")
    new_config = re.sub(
        r"^(avatar\s*:).*$",
        f"\\1 {rel_path}",
        config_text,
        count=1,
        flags=re.MULTILINE,
    )
    if new_config == config_text:
        print("Warning: could not find 'avatar:' line in _config.yml", file=sys.stderr)
    CONFIG.write_text(new_config, encoding="utf-8")

    run(["git", "add", "_config.yml", str(dst.relative_to(BLOG_DIR))])
    run(["git", "commit", "-m", f"avatar: update ({dst.name})"])
    run(["git", "push"])

    print(f"✓ Avatar updated: {rel_path}")


if __name__ == "__main__":
    main()
