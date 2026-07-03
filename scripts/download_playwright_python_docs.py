#!/usr/bin/env python3
"""Download stable Playwright Python docs and convert them to Markdown."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


BASE_URL = "https://playwright.dev"
SITEMAP_URL = f"{BASE_URL}/python/sitemap.xml"
DOC_PREFIX = f"{BASE_URL}/python/docs/"
OUT_DIR = Path("docs/playwright-python")
USER_AGENT = "bit-browser-auto-doc-fetcher/1.0"


@dataclass(frozen=True)
class DocPage:
    url: str
    title: str
    category: str
    slug: str
    output_path: Path
    headings: tuple[str, ...]


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def stable_doc_urls() -> list[str]:
    xml = fetch_text(SITEMAP_URL)
    root = ET.fromstring(xml)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]
    docs = [
        url
        for url in urls
        if url.startswith(DOC_PREFIX) and "/python/docs/next/" not in url
    ]
    return sorted(set(docs), key=lambda value: value.replace("/api/", "/zz-api/"))


def attrs_to_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): value or "" for key, value in attrs}


def class_names(attrs: dict[str, str]) -> set[str]:
    return set(attrs.get("class", "").split())


def absolute_href(href: str) -> str:
    if not href:
        return href
    return urljoin(BASE_URL, href)


class MarkdownExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.in_doc = False
        self.doc_div_depth = 0
        self.skip_depth = 0
        self.in_pre = False
        self.pre_lang = ""
        self.pre_parts: list[str] = []
        self.list_stack: list[str] = []
        self.link_stack: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs_raw: list[tuple[str, str | None]]) -> None:
        attrs = attrs_to_dict(attrs_raw)
        classes = class_names(attrs)

        if not self.in_doc:
            if tag == "div" and {"theme-doc-markdown", "markdown"} <= classes:
                self.in_doc = True
                self.doc_div_depth = 1
            return

        if self.skip_depth:
            self.skip_depth += 1
            return

        if tag in {"script", "style", "svg", "noscript", "x-search"}:
            self.skip_depth = 1
            return

        if tag == "a" and "hash-link" in classes:
            self.skip_depth = 1
            return

        if self.in_pre:
            if tag == "br":
                self.pre_parts.append("\n")
            return

        if tag == "div":
            self.doc_div_depth += 1

        if tag == "pre":
            self.in_pre = True
            self.pre_parts = []
            self.pre_lang = self._language_from_attrs(attrs)
            return

        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            self._blank()
            self.parts.append("#" * level + " ")
        elif tag == "p":
            self._blank()
        elif tag in {"ul", "ol"}:
            self.list_stack.append(tag)
            self._newline()
        elif tag == "li":
            self._newline()
            indent = "  " * max(0, len(self.list_stack) - 1)
            marker = "1. " if self.list_stack and self.list_stack[-1] == "ol" else "- "
            self.parts.append(indent + marker)
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("_")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a":
            href = absolute_href(attrs.get("href", ""))
            self.link_stack.append((href, len(self.parts)))
        elif tag == "img":
            alt = attrs.get("alt", "").strip()
            src = absolute_href(attrs.get("src", ""))
            if src:
                self.parts.append(f"![{alt}]({src})")
        elif tag == "blockquote":
            self._blank()
            self.parts.append("> ")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_doc:
            return

        if self.skip_depth:
            self.skip_depth -= 1
            if tag == "div" and self.doc_div_depth:
                self.doc_div_depth -= 1
            return

        if self.in_pre:
            if tag == "pre":
                code = "".join(self.pre_parts).strip("\n")
                self._blank()
                self.parts.append(f"```{self.pre_lang}\n{code}\n```")
                self._blank()
                self.in_pre = False
                self.pre_parts = []
                self.pre_lang = ""
            return

        if re.fullmatch(r"h[1-6]", tag):
            self._blank()
        elif tag == "p":
            self._blank()
        elif tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()
            self._blank()
        elif tag == "li":
            self._newline()
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("_")
        elif tag == "code":
            self.parts.append("`")
        elif tag == "a" and self.link_stack:
            href, start = self.link_stack.pop()
            if href:
                text = "".join(self.parts[start:]).strip()
                if text:
                    self.parts[start:] = [f"[{text}]({href})"]
        elif tag == "blockquote":
            self._blank()

        if tag == "div":
            self.doc_div_depth -= 1
            if self.doc_div_depth <= 0:
                self.in_doc = False

    def handle_data(self, data: str) -> None:
        if not self.in_doc or self.skip_depth:
            return
        if self.in_pre:
            self.pre_parts.append(data)
        else:
            self.parts.append(data.replace("\u200b", ""))

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"([^\n])\n(```)", r"\1\n\n\2", text)
        text = re.sub(r"(```)\n([^\n])", r"\1\n\n\2", text)
        return text.strip() + "\n"

    def _blank(self) -> None:
        if not self.parts:
            return
        current = "".join(self.parts[-3:])
        if not current.endswith("\n\n"):
            if current.endswith("\n"):
                self.parts.append("\n")
            else:
                self.parts.append("\n\n")

    def _newline(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    @staticmethod
    def _language_from_attrs(attrs: dict[str, str]) -> str:
        classes = attrs.get("class", "")
        match = re.search(r"language-([a-zA-Z0-9_+-]+)", classes)
        return match.group(1) if match else ""


def html_to_markdown(html: str) -> str:
    parser = MarkdownExtractor()
    parser.feed(html)
    parser.close()
    return parser.markdown()


def page_title(markdown: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def page_headings(markdown: str) -> tuple[str, ...]:
    headings = []
    for match in re.finditer(r"^(#{2,4})\s+(.+)$", markdown, re.MULTILINE):
        text = re.sub(r"\s+", " ", match.group(2)).strip()
        if text and text not in headings:
            headings.append(text)
    return tuple(headings)


def output_path_for_url(url: str) -> tuple[str, str, Path]:
    slug = url.removeprefix(DOC_PREFIX).strip("/")
    if slug.startswith("api/"):
        name = slug.removeprefix("api/")
        return "api", name, OUT_DIR / "api" / f"{name}.md"
    return "guides", slug, OUT_DIR / "guides" / f"{slug}.md"


def source_header(url: str) -> str:
    return (
        "<!--\n"
        "Downloaded from the official Playwright Python documentation.\n"
        f"Source: {url}\n"
        f"Snapshot date: {date.today().isoformat()}\n"
        "Generated by scripts/download_playwright_python_docs.py.\n"
        "-->\n\n"
    )


def write_doc(url: str) -> DocPage:
    html = fetch_text(url)
    markdown = html_to_markdown(html)
    category, slug, path = output_path_for_url(url)
    title = page_title(markdown, slug)
    headings = page_headings(markdown)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source_header(url) + markdown, encoding="utf-8")
    return DocPage(url, title, category, slug, path, headings)


def chunk(items: Iterable[str], size: int) -> Iterable[list[str]]:
    batch: list[str] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def rel(path: Path) -> str:
    return path.relative_to(OUT_DIR).as_posix()


def limited_topics(page: DocPage, limit: int = 18) -> str:
    topics = [heading for heading in page.headings if heading.lower() not in {"methods", "properties", "events"}]
    if not topics:
        return ""
    visible = topics[:limit]
    suffix = f"; +{len(topics) - limit} more" if len(topics) > limit else ""
    return " - " + "; ".join(visible) + suffix


def write_index(pages: list[DocPage]) -> None:
    guides = [page for page in pages if page.category == "guides"]
    apis = [page for page in pages if page.category == "api"]

    guide_by_slug = {page.slug: page for page in guides}
    api_by_slug = {page.slug: page for page in apis}

    def link(page: DocPage) -> str:
        return f"[{page.title}]({rel(page.output_path)})"

    quick_targets = [
        ("安装/启动/脚本结构", ["intro", "library", "running-tests", "writing-tests"]),
        ("定位元素与自动等待", ["locators", "other-locators", "actionability"]),
        ("点击、输入、上传、键鼠操作", ["input"]),
        ("页面、弹窗、多标签、导航", ["pages", "dialogs", "navigations"]),
        ("浏览器上下文、认证态、隔离会话", ["browser-contexts", "auth"]),
        ("网络拦截、Mock、API 测试", ["network", "mock", "api-testing"]),
        ("截图、视频、下载、Trace 调试", ["screenshots", "videos", "downloads", "trace-viewer", "debug"]),
        ("Frame、句柄、页面求值", ["frames", "handles", "evaluating"]),
        ("CDP/连接已有 Chromium", ["class-browsertype", "class-browser", "class-browsercontext", "class-page"]),
    ]

    lines = [
        "# Playwright Python 文档目录",
        "",
        f"- 官方来源: {DOC_PREFIX}",
        f"- Sitemap: {SITEMAP_URL}",
        f"- 快照日期: {date.today().isoformat()}",
        f"- 本地页面数: {len(pages)} 个，其中指南 {len(guides)} 个，API {len(apis)} 个。",
        "",
        "## 给 AI 的查找建议",
        "",
        "- 先看下面的“常见任务入口”，再进入具体页面。",
        "- 查 API 方法名时优先用 `rg \"page.goto|locator.click|connect_over_cdp\" docs/playwright-python`。",
        "- 指南页在 `guides/`，类 API 在 `api/`；每个页面顶部都保留官方 Source URL。",
        "- 本项目接管比特浏览器窗口时，重点看 `BrowserType.connect_over_cdp`、`BrowserContext`、`Page`、`Locator`。",
        "",
        "## 常见任务入口",
        "",
    ]

    for label, slugs in quick_targets:
        targets = []
        for slug in slugs:
            page = guide_by_slug.get(slug) or api_by_slug.get(slug)
            if page:
                targets.append(link(page))
        if targets:
            lines.append(f"- {label}: " + ", ".join(targets))

    lines.extend(["", "## 指南目录", ""])
    for page in guides:
        lines.append(f"- {link(page)}{limited_topics(page)}")

    lines.extend(["", "## API 目录", ""])
    for page in apis:
        lines.append(f"- {link(page)}{limited_topics(page, limit=12)}")

    lines.append("")
    (OUT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_manifest(pages: list[DocPage]) -> None:
    manifest = {
        "source": DOC_PREFIX,
        "sitemap": SITEMAP_URL,
        "snapshot_date": date.today().isoformat(),
        "page_count": len(pages),
        "pages": [
            {
                "title": page.title,
                "url": page.url,
                "category": page.category,
                "slug": page.slug,
                "path": rel(page.output_path),
                "headings": list(page.headings),
            }
            for page in pages
        ],
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages: list[DocPage] = []
    urls = stable_doc_urls()
    for batch in chunk(urls, 10):
        for url in batch:
            print(f"Downloading {url}")
            pages.append(write_doc(url))
            time.sleep(0.05)
    write_index(pages)
    write_manifest(pages)
    print(f"Wrote {len(pages)} pages to {OUT_DIR}")


if __name__ == "__main__":
    main()
