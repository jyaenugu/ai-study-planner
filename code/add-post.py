#!/usr/bin/env python3
"""Create a new Jekyll post and push it."""
import sys
import datetime
import subprocess
import re
from pathlib import Path

BLOG_DIR = Path.home() / "jyaenugu.github.io"
POSTS_DIR = BLOG_DIR / "_posts"


def run(cmd):
    return subprocess.run(cmd, cwd=BLOG_DIR, check=True, capture_output=True, text=True)


def slugify(text):
    text = re.sub(r"[^\w\s가-힣-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:60] or "post"


def main():
    if len(sys.argv) < 3:
        print("Usage: add-post.py '<title>' '<body>'", file=sys.stderr)
        sys.exit(1)

    title = sys.argv[1].strip()
    body = sys.argv[2]

    now = datetime.datetime.now()
    today = now.date().isoformat()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S +0900")
    slug = slugify(title)

    filename = f"{today}-{slug}.md"
    path = POSTS_DIR / filename

    if path.exists():
        print(f"File already exists: {path}", file=sys.stderr)
        sys.exit(1)

    run(["git", "pull", "--rebase", "--quiet"])

    front_matter = f"""---
title: "{title}"
date: {timestamp}
---

"""
    path.write_text(front_matter + body.rstrip() + "\n", encoding="utf-8")

    run(["git", "add", f"_posts/{filename}"])
    msg = f"post: {title[:50]}{'...' if len(title) > 50 else ''}"
    run(["git", "commit", "-m", msg])
    run(["git", "push"])

    print(f"✓ Post created: {filename}")


if __name__ == "__main__":
    main()
