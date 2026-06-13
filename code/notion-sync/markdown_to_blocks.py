"""Convert markdown text to Notion block objects.

Supports: heading (h1-h3), paragraph, bullet/ordered lists, code fence,
blockquote, horizontal rule, inline bold/italic/code/links. Obsidian-style
wiki links [[...]] are rendered as plain text.

Notion limits:
- rich_text per block: 2000 chars
- children append per request: 100 blocks
"""
from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

MD = MarkdownIt("commonmark", {"breaks": False, "html": False})

NOTION_LANGUAGES = {
    "abap", "arduino", "bash", "basic", "c", "clojure", "coffeescript", "c++",
    "c#", "css", "dart", "diff", "docker", "elixir", "elm", "erlang", "flow",
    "fortran", "f#", "gherkin", "glsl", "go", "graphql", "groovy", "haskell",
    "html", "java", "javascript", "json", "julia", "kotlin", "latex", "less",
    "lisp", "livescript", "lua", "makefile", "markdown", "markup", "matlab",
    "mermaid", "nix", "objective-c", "ocaml", "pascal", "perl", "php",
    "plain text", "powershell", "prolog", "protobuf", "python", "r", "reason",
    "ruby", "rust", "sass", "scala", "scheme", "scss", "shell", "sql", "swift",
    "typescript", "vb.net", "verilog", "vhdl", "visual basic", "webassembly",
    "xml", "yaml",
}

LANGUAGE_ALIASES = {
    "sh": "shell",
    "zsh": "shell",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "rb": "ruby",
    "yml": "yaml",
    "md": "markdown",
}


def _normalize_lang(lang: str) -> str:
    if not lang:
        return "plain text"
    lang = lang.lower().strip()
    lang = LANGUAGE_ALIASES.get(lang, lang)
    return lang if lang in NOTION_LANGUAGES else "plain text"


def _rich_text(content: str, annotations: dict | None = None, link: str | None = None) -> dict:
    chunk = {"type": "text", "text": {"content": content[:2000]}}
    if link:
        chunk["text"]["link"] = {"url": link}
    if annotations:
        chunk["annotations"] = annotations
    return chunk


def _inline_to_rich(tokens: list[Token]) -> list[dict]:
    out: list[dict] = []
    stack = {"bold": False, "italic": False, "code": False, "strikethrough": False}
    link_url: str | None = None

    def emit(text: str):
        if not text:
            return
        ann = {k: v for k, v in stack.items() if v}
        out.append(_rich_text(text, annotations=ann if ann else None, link=link_url))

    for t in tokens:
        if t.type == "text":
            emit(t.content)
        elif t.type == "softbreak" or t.type == "hardbreak":
            emit("\n")
        elif t.type == "code_inline":
            stack["code"] = True
            emit(t.content)
            stack["code"] = False
        elif t.type == "strong_open":
            stack["bold"] = True
        elif t.type == "strong_close":
            stack["bold"] = False
        elif t.type == "em_open":
            stack["italic"] = True
        elif t.type == "em_close":
            stack["italic"] = False
        elif t.type == "s_open":
            stack["strikethrough"] = True
        elif t.type == "s_close":
            stack["strikethrough"] = False
        elif t.type == "link_open":
            link_url = t.attrs.get("href") if t.attrs else None
        elif t.type == "link_close":
            link_url = None
    return out or [_rich_text("")]


def _list_block(li_inline: list[Token], list_type: str) -> dict:
    rich = _inline_to_rich(li_inline)
    return {"type": list_type, list_type: {"rich_text": rich}}


def _walk_list(tokens: list[Token], i: int, list_type: str) -> tuple[int, list[dict]]:
    items: list[dict] = []
    depth = 1
    i += 1
    while i < len(tokens) and depth > 0:
        t = tokens[i]
        if t.type in ("bullet_list_open", "ordered_list_open"):
            depth += 1
            i += 1
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
            i += 1
        elif t.type == "list_item_open" and depth == 1:
            inline_tokens: list[Token] = []
            j = i + 1
            while j < len(tokens) and tokens[j].type != "list_item_close":
                if tokens[j].type == "inline":
                    inline_tokens = tokens[j].children or []
                    break
                j += 1
            items.append(_list_block(inline_tokens, list_type))
            while j < len(tokens) and tokens[j].type != "list_item_close":
                j += 1
            i = j + 1
        else:
            i += 1
    return i, items


def render(markdown_text: str) -> list[dict]:
    if not markdown_text.strip():
        return []
    tokens = MD.parse(markdown_text)
    blocks: list[dict] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            level = min(int(t.tag[1]), 3)
            inline = tokens[i + 1]
            rich = _inline_to_rich(inline.children or [])
            blocks.append({"type": f"heading_{level}", f"heading_{level}": {"rich_text": rich}})
            i += 3
        elif t.type == "paragraph_open":
            inline = tokens[i + 1]
            rich = _inline_to_rich(inline.children or [])
            if rich and any(c["text"]["content"].strip() for c in rich):
                blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
            i += 3
        elif t.type == "bullet_list_open":
            i, items = _walk_list(tokens, i, "bulleted_list_item")
            blocks.extend(items)
        elif t.type == "ordered_list_open":
            i, items = _walk_list(tokens, i, "numbered_list_item")
            blocks.extend(items)
        elif t.type in ("fence", "code_block"):
            content = t.content
            lang = _normalize_lang(t.info if t.type == "fence" else "")
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [_rich_text(content)],
                    "language": lang,
                },
            })
            i += 1
        elif t.type == "blockquote_open":
            inner: list[Token] = []
            depth = 1
            j = i + 1
            while j < len(tokens) and depth > 0:
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                    if depth == 0:
                        break
                inner.append(tokens[j])
                j += 1
            inner_blocks = _render_token_stream(inner)
            quote_rich = []
            children = []
            if inner_blocks and inner_blocks[0]["type"] == "paragraph":
                quote_rich = inner_blocks[0]["paragraph"]["rich_text"]
                children = inner_blocks[1:]
            blocks.append({
                "type": "quote",
                "quote": {"rich_text": quote_rich or [_rich_text("")], **({"children": children} if children else {})},
            })
            i = j + 1
        elif t.type == "hr":
            blocks.append({"type": "divider", "divider": {}})
            i += 1
        else:
            i += 1
    return blocks


def _render_token_stream(tokens: list[Token]) -> list[dict]:
    md_text = ""
    blocks: list[dict] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "paragraph_open":
            inline = tokens[i + 1]
            rich = _inline_to_rich(inline.children or [])
            if rich:
                blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
            i += 3
        else:
            i += 1
    return blocks
