from __future__ import annotations

import asyncio
import io
import logging
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote, unquote
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .storage import Storage

log = logging.getLogger(__name__)

SOURCES = {
    "rsed": "https://instructions.yanao.ru/shelves/rsed-yanao",
    "esku": "http://apbook.yanao.int/books/gis-esku",
    "kb": "https://kb.yanao.ru/books",
}

FILES_SHARE = "https://files.yanao.ru/s/7MKQp8Xqm9NDQT9"
FILES_DAV = "https://files.yanao.ru/public.php/webdav/"
FILES_TOKEN = "7MKQp8Xqm9NDQT9"
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".pptx", ".xlsx", ".odt", ".rtf", ".txt", ".md"}
MAX_DOCUMENT_SIZE = 30 * 1024 * 1024


def _links(html: str, base: str, pattern: re.Pattern[str]) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    result = set()
    for tag in soup.select("a[href]"):
        url = urljoin(base, tag.get("href", "")).split("#", 1)[0]
        if pattern.search(urlparse(url).path):
            result.add(url)
    return result


def _parse_page(html: str, url: str) -> dict[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1")
    content_node = soup.select_one(".page-content") or soup.select_one("main")
    if not title_node or not content_node:
        return None
    for node in content_node.select("script, style, nav, .page-actions, .comments-container"):
        node.decompose()
    title = " ".join(title_node.stripped_strings)
    content = " ".join(content_node.stripped_strings)
    if len(content) < 20:
        return None
    return {"title": title, "content": content, "url": url}


async def _get(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return response.text


async def _fetch_pages(client: httpx.AsyncClient, urls: set[str]) -> list[dict[str, str]]:
    semaphore = asyncio.Semaphore(8)

    async def one(url: str):
        async with semaphore:
            try:
                return _parse_page(await _get(client, url), url)
            except Exception as exc:
                log.warning("Не удалось загрузить %s: %s", url, exc)
                return None

    return [page for page in await asyncio.gather(*(one(url) for url in sorted(urls))) if page]


def _download_url(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    if parent == ".":
        parent = "/"
    return f"{FILES_SHARE}/download?path={quote(parent, safe='/')}&files={quote(PurePosixPath(path).name)}"


def _xml_text(data: bytes, patterns: tuple[str, ...]) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = []
        for name in archive.namelist():
            if any(re.fullmatch(pattern, name) for pattern in patterns):
                root = ET.fromstring(archive.read(name))
                parts.extend(node.text for node in root.iter() if node.text)
    return " ".join(parts)


def _extract_document(data: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return " ".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        return _xml_text(data, (r"word/document.xml", r"word/header\d+.xml", r"word/footer\d+.xml"))
    if suffix == ".pptx":
        return _xml_text(data, (r"ppt/slides/slide\d+.xml",))
    if suffix == ".xlsx":
        return _xml_text(data, (r"xl/sharedStrings.xml", r"xl/worksheets/sheet\d+.xml"))
    if suffix == ".odt":
        return _xml_text(data, (r"content.xml",))
    if suffix == ".doc":
        with tempfile.NamedTemporaryFile(suffix=".doc") as source:
            source.write(data)
            source.flush()
            result = subprocess.run(
                ["antiword", source.name], capture_output=True, check=True, timeout=30
            )
        return result.stdout.decode("utf-8", errors="ignore")
    text = data.decode("utf-8", errors="ignore")
    if suffix == ".rtf":
        text = re.sub(r"\\'[0-9a-fA-F]{2}|\\[a-zA-Z]+-?\d* ?|[{}]", " ", text)
    return text


async def _files_metadata(client: httpx.AsyncClient) -> list[dict]:
    response = await client.request(
        "PROPFIND", FILES_DAV, headers={"Depth": "infinity"}, auth=(FILES_TOKEN, "")
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"d": "DAV:"}
    files = []
    for item in root.findall("d:response", ns):
        prop = item.find("d:propstat/d:prop", ns)
        if prop is None or prop.find("d:resourcetype/d:collection", ns) is not None:
            continue
        href = unquote(item.findtext("d:href", "", ns))
        path = href.removeprefix("/public.php/webdav/")
        suffix = PurePosixPath(path).suffix.lower()
        size = int(prop.findtext("d:getcontentlength", "0", ns) or 0)
        if suffix not in DOCUMENT_EXTENSIONS or size > MAX_DOCUMENT_SIZE:
            continue
        etag = (prop.findtext("d:getetag", "", ns) or "").strip('"')
        files.append({"path": path, "suffix": suffix, "size": size, "fingerprint": etag})
    return files


async def _index_files(client: httpx.AsyncClient, storage: Storage) -> list[dict[str, str]]:
    metadata = await _files_metadata(client)
    cached = storage.cached_pages("files")
    semaphore = asyncio.Semaphore(5)

    async def one(meta: dict) -> dict[str, str]:
        public_url = _download_url(meta["path"])
        previous = cached.get(public_url)
        if previous and previous["fingerprint"] == meta["fingerprint"]:
            return dict(previous)
        async with semaphore:
            dav_url = FILES_DAV + quote(meta["path"], safe="/")
            try:
                response = await client.get(dav_url, auth=(FILES_TOKEN, ""))
                response.raise_for_status()
                content = await asyncio.to_thread(_extract_document, response.content, meta["suffix"])
            except Exception as exc:
                log.warning("Не удалось обработать документ %s: %s", meta["path"], exc)
                content = ""
        title = PurePosixPath(meta["path"]).name
        folder = str(PurePosixPath(meta["path"]).parent).replace("/", " / ")
        return {
            "title": title,
            "url": public_url,
            "content": re.sub(r"\s+", " ", f"{folder} {title} {content}").strip(),
            "fingerprint": meta["fingerprint"],
        }

    return await asyncio.gather(*(one(meta) for meta in metadata))


async def rebuild(storage: Storage) -> dict[str, int]:
    headers = {"User-Agent": "YANAO-MAX-Search-Bot/1.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
        shelf_html = await _get(client, SOURCES["rsed"])
        book_urls = _links(shelf_html, SOURCES["rsed"], re.compile(r"^/books/[^/]+$"))
        rsed_page_urls: set[str] = set()
        sorted_book_urls = sorted(book_urls)
        for book_url, book_html in zip(sorted_book_urls, await asyncio.gather(*(_get(client, u) for u in sorted_book_urls))):
            rsed_page_urls |= _links(book_html, book_url, re.compile(r"^/books/[^/]+/page/[^/]+$"))

        esku_html = await _get(client, SOURCES["esku"])
        esku_page_urls = _links(esku_html, SOURCES["esku"], re.compile(r"^/books/gis-esku/page/[^/]+$"))

        kb_books_html = await _get(client, SOURCES["kb"])
        kb_book_urls = _links(kb_books_html, SOURCES["kb"], re.compile(r"^/books/[^/]+$"))
        kb_page_urls: set[str] = set()
        sorted_kb_book_urls = sorted(kb_book_urls)
        kb_book_pages = await asyncio.gather(*(_get(client, url) for url in sorted_kb_book_urls))
        for book_url, book_html in zip(sorted_kb_book_urls, kb_book_pages):
            kb_page_urls |= _links(book_html, book_url, re.compile(r"^/books/[^/]+/page/[^/]+$"))

        rsed_pages, esku_pages, kb_pages, file_pages = await asyncio.gather(
            _fetch_pages(client, rsed_page_urls),
            _fetch_pages(client, esku_page_urls),
            _fetch_pages(client, kb_page_urls),
            _index_files(client, storage),
        )
    if not rsed_pages or not esku_pages or not kb_pages or not file_pages:
        raise RuntimeError("Индекс не обновлён: один из источников вернул 0 страниц")
    storage.replace_source("rsed", rsed_pages)
    storage.replace_source("esku", esku_pages)
    storage.replace_source("kb", kb_pages)
    storage.replace_source("files", file_pages)
    return storage.counts()
