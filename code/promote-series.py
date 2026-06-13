#!/usr/bin/env python3
"""Promote posts in _posts/ into a series under _series/<slug>/.

Usage:
    promote-series.py "<series_name>" <post_slug_or_filename> [<more_posts>...]

Each post is moved into _series/<series_slug>/<N>-<original-slug>.md
with `series:` and `part:` fields added to its front matter.
"""
import sys
import subprocess
import re
from pathlib import Path

BLOG_DIR = Path.home() / "jyaenugu.github.io"
POSTS_DIR = BLOG_DIR / "_posts"
SERIES_DIR = BLOG_DIR / "_series"


def run(cmd):
    return subprocess.run(cmd, cwd=BLOG_DIR, check=True, capture_output=True, text=True)


def slugify(text):
    text = re.sub(r"[^\w\s가-힣-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:60] or "series"


def find_post(query):
    """Find a post in _posts/ matching the query (filename or slug substring)."""
    q = query.strip()
    if q.endswith(".md"):
        q = q[:-3]
    candidates = list(POSTS_DIR.glob(f"*{q}*.md"))
    if not candidates:
        return None
    if len(candidates) > 1:
        exact = [c for c in candidates if c.stem.endswith(q) or c.stem == q]
        if len(exact) == 1:
            return exact[0]
        print(f"Ambiguous match for '{query}':", file=sys.stderr)
        for c in candidates:
            print(f"  - {c.name}", file=sys.stderr)
        return None
    return candidates[0]


FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def update_front_matter(content, series_name, part):
    """Add/overwrite series and part fields in the YAML front matter."""
    m = FRONT_MATTER_RE.match(content)
    if not m:
        fm = f'series: "{series_name}"\npart: {part}\n'
        return f"---\n{fm}---\n\n{content}"

    fm_lines = m.group(1).splitlines()
    body = m.group(2)
    fm_lines = [
        line for line in fm_lines
        if not re.match(r"^\s*(series|part)\s*:", line)
    ]
    fm_lines.append(f'series: "{series_name}"')
    fm_lines.append(f"part: {part}")
    return "---\n" + "\n".join(fm_lines) + "\n---\n" + body


def strip_date_prefix(stem):
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)


def main():
    if len(sys.argv) < 3:
        print("Usage: promote-series.py '<series_name>' <post1> [<post2> ...]", file=sys.stderr)
        sys.exit(1)

    series_name = sys.argv[1].strip()
    post_queries = sys.argv[2:]
    series_slug = slugify(series_name)
    target_dir = SERIES_DIR / series_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(target_dir.glob("*.md"))
    next_part = len(existing) + 1

    run(["git", "pull", "--rebase", "--quiet"])

    moved = []
    for i, query in enumerate(post_queries):
        src = find_post(query)
        if src is None:
            print(f"Post not found: {query}", file=sys.stderr)
            sys.exit(1)

        part_num = next_part + i
        original_slug = strip_date_prefix(src.stem)
        dst = target_dir / f"{part_num:02d}-{original_slug}.md"

        content = src.read_text(encoding="utf-8")
        new_content = update_front_matter(content, series_name, part_num)
        dst.write_text(new_content, encoding="utf-8")
        src.unlink()

        moved.append((src.name, dst.relative_to(BLOG_DIR).as_posix(), part_num))

    for src_name, dst_rel, _ in moved:
        run(["git", "add", dst_rel])
        run(["git", "add", "--", f"_posts/{src_name}"])

    msg_parts = ", ".join(str(p) for _, _, p in moved)
    commit_msg = f"series: '{series_name}' promote part(s) {msg_parts}"
    run(["git", "commit", "-m", commit_msg])
    run(["git", "push"])

    print(f"✓ Promoted to series '{series_name}':")
    for src_name, dst_rel, part_num in moved:
        print(f"  {part_num}부: {src_name} → {dst_rel}")


if __name__ == "__main__":
    main()
