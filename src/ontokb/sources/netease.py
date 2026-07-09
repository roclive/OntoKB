"""tech.163.com article source: fetch and extract the article body.

Uses BeautifulSoup when available, with a regex fallback. NetEase pages are
GBK/UTF-8 mixed historically; requests' apparent encoding handles it.
"""

from __future__ import annotations

import hashlib
import re

import requests

from ..models import ContentItem

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def item_from_url(url: str) -> ContentItem:
    return ContentItem(
        id="163:" + hashlib.sha1(url.encode()).hexdigest()[:12],
        kind="article", source="netease", url=url,
    )


def fetch_article(item: ContentItem, timeout: int = 20) -> str:
    resp = requests.get(item.url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    if resp.encoding in (None, "ISO-8859-1"):
        resp.encoding = resp.apparent_encoding
    html = resp.text
    title, body = extract_article(html)
    item.title = item.title or title
    if not body:
        raise RuntimeError(f"could not extract article body from {item.url}")
    return body


def extract_article(html: str) -> tuple[str, str]:
    """Return (title, body_text). bs4 path first, regex fallback second."""
    title_m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = (title_m.group(1).strip() if title_m else "").split("_")[0]

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.find(class_="post_body") or soup.find(id="content") or soup.find("article")
        if container:
            for junk in container.find_all(["script", "style", "iframe"]):
                junk.decompose()
            paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
            body = "\n".join(p for p in paras if p)
            if body:
                return title, body

    # regex fallback: paragraphs inside the usual NetEase article container
    container_m = re.search(r'class="post_body"[^>]*>(.*?)</div>', html, re.S)
    scope = container_m.group(1) if container_m else html
    paras = re.findall(r"<p[^>]*>(.*?)</p>", scope, re.S)
    cleaned = []
    for p in paras:
        text = re.sub(r"<[^>]+>", "", p)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cleaned.append(text)
    return title, "\n".join(cleaned)
