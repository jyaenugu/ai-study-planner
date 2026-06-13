#!/usr/bin/env python3
"""Add a news entry (text + image) to the Jekyll blog and push it."""
import sys
import shutil
import datetime
import subprocess
import re
from pathlib import Path

import yaml

BLOG_DIR = Path.home() / "jyaenugu.github.io"
NEWS_FILE = BLOG_DIR / "_data" / "news.yml"
NEWS_IMG_DIR = BLOG_DIR / "assets" / "img" / "news"


def run(cmd):
    return subprocess.run(cmd, cwd=BLOG_DIR, check=True, capture_output=True, text=True)


def slugify(text):
    text = re.sub(r"[^\w\s가-힣-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:40] or "news"


def main():
    if len(sys.argv) < 3:
        print("Usage: add-news.py '<text>' <image_path>", file=sys.stderr)
        sys.exit(1)

    text = sys.argv[1].strip()
    src_image = Path(sys.argv[2]).expanduser().resolve()

    if not src_image.is_file():
        print(f"Image not found: {src_image}", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today().isoformat()
    ext = src_image.suffix.lower() or ".jpg"
    dst_name = f"{today}-{slugify(text)}{ext}"
    NEWS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dst_image = NEWS_IMG_DIR / dst_name
    shutil.copy2(src_image, dst_image)

    rel_image = "/" + dst_image.relative_to(BLOG_DIR).as_posix()

    run(["git", "pull", "--rebase", "--quiet"])

    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []

    entries.insert(0, {"date": today, "text": text, "image": rel_image})

    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(entries, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    run(["git", "add", "_data/news.yml", str(dst_image.relative_to(BLOG_DIR))])
    msg = f"news: {text[:50]}{'...' if len(text) > 50 else ''}"
    run(["git", "commit", "-m", msg])
    run(["git", "push"])

    print(f"✓ News added: {text}")
    print(f"  image: {rel_image}")


if __name__ == "__main__":
    main()
