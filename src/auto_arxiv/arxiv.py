from __future__ import annotations

import time
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import quote_plus
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import fitz
from pypdf import PdfReader
import requests

from .models import Paper

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_recent_papers(
    categories: Iterable[str],
    max_results: int,
    timezone_name: str,
    target_day_offset: int,
) -> list[Paper]:
    category_terms = sorted(set(categories))
    if not category_terms:
        return []

    query = " OR ".join(f"cat:{term}" for term in category_terms)
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={quote_plus(query)}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )

    response = _request_with_retries(url, timeout=45)
    if response.status_code == 429 and max_results > 40:
        fallback_url = (
            "https://export.arxiv.org/api/query?"
            f"search_query={quote_plus(query)}&sortBy=submittedDate&sortOrder=descending&max_results=40"
        )
        response = _request_with_retries(fallback_url, timeout=45)
    response.raise_for_status()

    local_tz = ZoneInfo(timezone_name)
    target_local_date = datetime.now(local_tz).date() - timedelta(days=target_day_offset)
    root = ElementTree.fromstring(response.text)
    papers: list[Paper] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        paper = _parse_entry(entry)
        if _matches_target_local_date(paper.published, local_tz, target_local_date):
            papers.append(paper)

    return papers


def populate_article_texts(papers: list[Paper], max_pages: int = 15, max_chars: int = 24000) -> None:
    for paper in papers:
        try:
            response = _request_with_retries(paper.pdf_url, timeout=90)
            response.raise_for_status()
            paper.figure_bytes, paper.figure_subtype = _extract_candidate_figure(response.content, max_pages=max_pages)
            reader = PdfReader(BytesIO(response.content))

            chunks: list[str] = []
            for page in reader.pages[:max_pages]:
                text = page.extract_text() or ""
                text = " ".join(text.split())
                if text:
                    chunks.append(text)
                if sum(len(chunk) for chunk in chunks) >= max_chars:
                    break

            article_text = "\n".join(chunks).strip()
            paper.article_text = article_text[:max_chars] if article_text else paper.abstract
        except Exception:
            # PDF extraction can fail on malformed files; fall back to the arXiv abstract.
            paper.article_text = paper.abstract


def _request_with_retries(url: str, timeout: int, max_attempts: int = 5) -> requests.Response:
    last_error: Exception | None = None
    last_response: requests.Response | None = None
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "autoArxivDigest/1.0 (+https://github.com/shallow777/autoArxiv)"},
            )
            if response.status_code == 429:
                last_response = response
                if attempt < max_attempts - 1:
                    retry_after = response.headers.get("Retry-After", "").strip()
                    sleep_seconds = _compute_retry_sleep_seconds(retry_after, attempt)
                    time.sleep(sleep_seconds)
                    continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(2 * (attempt + 1))
    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without an exception: {url}")


def _compute_retry_sleep_seconds(retry_after: str, attempt: int) -> int:
    if retry_after.isdigit():
        return max(1, int(retry_after))
    return min(60, 5 * (attempt + 1))


def _matches_target_local_date(published_utc: datetime, local_tz: ZoneInfo, target_local_date: date) -> bool:
    published_local_date = published_utc.astimezone(local_tz).date()
    return published_local_date == target_local_date


def _extract_candidate_figure(pdf_bytes: bytes, max_pages: int) -> tuple[bytes | None, str]:
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return None, ""

    best_image: tuple[int, bytes, str] | None = None
    try:
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                image = document.extract_image(xref)
                image_bytes = image.get("image")
                image_ext = image.get("ext", "")
                width = int(image.get("width", 0))
                height = int(image.get("height", 0))
                area = width * height
                if not image_bytes or area < 120000:
                    continue
                if best_image is None or area > best_image[0]:
                    best_image = (area, image_bytes, image_ext)
    finally:
        document.close()

    if best_image is None:
        return None, ""
    _, image_bytes, image_ext = best_image
    subtype = "jpeg" if image_ext in {"jpg", "jpeg"} else image_ext
    return image_bytes, subtype


def _parse_entry(entry: ElementTree.Element) -> Paper:
    arxiv_id = _text(entry, "atom:id").rsplit("/", 1)[-1]
    title = " ".join(_text(entry, "atom:title").split())
    abstract = " ".join(_text(entry, "atom:summary").split())
    published = _parse_dt(_text(entry, "atom:published"))
    updated = _parse_dt(_text(entry, "atom:updated"))
    authors = [
        _text(author, "atom:name")
        for author in entry.findall("atom:author", ATOM_NS)
    ]
    categories = [node.attrib["term"] for node in entry.findall("atom:category", ATOM_NS)]
    abs_url = _text(entry, "atom:id")
    pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        article_text="",
        published=published,
        updated=updated,
        authors=authors,
        categories=categories,
        abs_url=abs_url,
        pdf_url=pdf_url,
    )


def _text(node: ElementTree.Element, path: str) -> str:
    value = node.findtext(path, default="", namespaces=ATOM_NS)
    return value.strip()


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
