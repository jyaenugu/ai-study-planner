#!/usr/bin/env python3
"""blog MCP — wraps ~/openclaw-tools/*.py scripts as MCP tools."""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp.server.fastmcp import FastMCP
from usage_logger import logged

TOOLS_DIR = Path.home() / "openclaw-tools"
BLOG_DIR = Path.home() / "jyaenugu.github.io"
POSTS_DIR = BLOG_DIR / "_posts"
DRAFTS_DIR = BLOG_DIR / "_drafts"

mcp = FastMCP("blog")


def _run_script(name: str, *args: str) -> dict:
    """Run a script in openclaw-tools and return its output."""
    script = TOOLS_DIR / name
    if not script.exists():
        raise RuntimeError(f"script not found: {script}")
    r = subprocess.run(
        ["python3", str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"{name} failed (exit {r.returncode}): {r.stderr.strip()}")
    return {"ok": True, "stdout": r.stdout.strip()}


@mcp.tool()
@logged("blog")
def add_post(title: str, body: str) -> dict:
    """새 Jekyll 포스트 생성 (_posts/YYYY-MM-DD-slug.md) 및 push."""
    return _run_script("add-post.py", title, body)


@mcp.tool()
@logged("blog")
def add_news(text: str, image_path: str) -> dict:
    """뉴스 항목 추가 (텍스트 + 이미지 필수). image_path는 로컬 파일 경로."""
    return _run_script("add-news.py", text, image_path)


@mcp.tool()
@logged("blog")
def promote_to_series(series_name: str, post_slugs: list[str]) -> dict:
    """포스트들을 _series/<series_slug>/ 아래로 옮기고 front matter에 series·part 추가."""
    if not post_slugs:
        raise RuntimeError("post_slugs 비어 있음")
    return _run_script("promote-series.py", series_name, *post_slugs)


@mcp.tool()
@logged("blog")
def set_avatar(image_path: str) -> dict:
    """사이트 프로필 사진 교체 (_config.yml 업데이트) 및 push."""
    return _run_script("set-avatar.py", image_path)


@mcp.tool()
@logged("blog")
def recent_posts(n: int = 10) -> list[dict]:
    """최근 포스트 N개 (제목·날짜·slug·경로). 읽기 전용."""
    if not POSTS_DIR.exists():
        return []
    files = sorted(POSTS_DIR.glob("*.md"), reverse=True)[:n]
    out = []
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
    for f in files:
        m = pat.match(f.name)
        date = m.group(1) if m else None
        slug = m.group(2) if m else f.stem
        title = None
        for line in f.read_text(errors="replace").splitlines()[:15]:
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip("\"'")
                break
        out.append({
            "date": date,
            "slug": slug,
            "title": title or slug,
            "path": str(f.relative_to(BLOG_DIR)),
        })
    return out


@mcp.tool()
@logged("blog")
def list_drafts() -> list[dict]:
    """_drafts/ 디렉토리의 미발행 포스트 목록. 읽기 전용."""
    if not DRAFTS_DIR.exists():
        return []
    out = []
    for f in sorted(DRAFTS_DIR.glob("*.md")):
        title = None
        for line in f.read_text(errors="replace").splitlines()[:15]:
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip("\"'")
                break
        out.append({"slug": f.stem, "title": title or f.stem, "path": str(f.relative_to(BLOG_DIR))})
    return out


if __name__ == "__main__":
    mcp.run()
