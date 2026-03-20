from __future__ import annotations

import time
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import quote_plus
from xml.etree import ElementTree

from pypdf import PdfReader
import requests

from .models import Paper

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_recent_papers(categories: Iterable[str], max_results: int, lookback_days: int) -> list[Paper]:
    category_terms = sorted(set(categories))
    if not category_terms:
        return []

    query = " OR ".join(f"cat:{term}" for term in category_terms)
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={quote_plus(query)}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )

    response = _request_with_retries(url, timeout=45)
    response.raise_for_status()

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    root = ElementTree.fromstring(response.text)
    papers: list[Paper] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        paper = _parse_entry(entry)
        if paper.published >= cutoff:
            papers.append(paper)

    return papers


def populate_article_texts(papers: list[Paper], max_pages: int = 15, max_chars: int = 24000) -> None:
    for paper in papers:
        try:
            response = _request_with_retries(paper.pdf_url, timeout=90)
            response.raise_for_status()
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


def _request_with_retries(url: str, timeout: int, max_attempts: int = 3) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return requests.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(2 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without an exception: {url}")


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
