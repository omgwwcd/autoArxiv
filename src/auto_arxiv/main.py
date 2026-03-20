from __future__ import annotations

import argparse
import os
from datetime import datetime

from .arxiv import fetch_recent_papers, populate_article_texts
from .config import load_config
from .filtering import select_papers
from .mailer import send_digest_email
from .reporting import render_email_html, write_report
from .store import load_seen_ids, save_seen_ids
from .summarizer import enrich_papers


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and send a daily arXiv digest.")
    parser.add_argument("--config", default=os.getenv("TOPICS_CONFIG", "config/topics.toml"))
    parser.add_argument("--seen-store", default=os.getenv("SEEN_STORE", "data/seen_papers.json"))
    parser.add_argument("--reports-dir", default=os.getenv("REPORTS_DIR", "reports"))
    args = parser.parse_args()

    config = load_config(args.config)
    seen_ids = load_seen_ids(args.seen_store)
    categories = [category for topic in config.topics for category in topic.categories]
    papers = fetch_recent_papers(
        categories=categories,
        max_results=config.digest.max_candidates,
        timezone_name=config.digest.timezone,
        target_day_offset=config.digest.target_day_offset,
    )
    selected = select_papers(config, papers, seen_ids)
    populate_article_texts(selected)
    enrich_papers(config, selected)
    for index, paper in enumerate(selected, start=1):
        if paper.figure_bytes and paper.figure_subtype:
            safe_arxiv_id = paper.arxiv_id.replace(".", "-")
            paper.figure_content_id = f"paper-{index}-{safe_arxiv_id}@auto-arxiv.local"

    subject = f"{config.digest.project_name} | {datetime.utcnow().strftime('%Y-%m-%d')}"
    email_html = render_email_html(config, selected)
    report_path = write_report(args.reports_dir, config, selected)
    email_sent = send_digest_email(subject, email_html, selected)

    seen_ids.update(paper.arxiv_id for paper in selected)
    save_seen_ids(args.seen_store, seen_ids)

    print(f"report={report_path}")
    print(f"papers={len(selected)}")
    print(f"email_sent={email_sent}")


if __name__ == "__main__":
    main()
