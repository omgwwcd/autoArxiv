from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

from .arxiv import fetch_recent_papers, populate_article_texts
from .config import load_config
from .filtering import select_papers
from .mailer import send_digest_email
from .reporting import render_email_html, write_report
from .store import load_seen_ids, save_seen_ids
from .summarizer import enrich_papers


def _load_env() -> None:
    """从 .env 文件加载环境变量（如果没有的话）"""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value and os.environ.get(key) is None:
                os.environ[key] = value


def setup_logging() -> logging.Logger:
    """配置日志：输出到 outputs/ 目录，每次运行一个文件，同时打印到 stdout"""
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"run_{timestamp}.log"

    logger = logging.getLogger("autoarxiv")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # 文件 handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    # 屏幕 handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger


def main() -> None:
    _load_env()
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("auto_arxiv 开始运行")
    logger.info("=" * 50)

    parser = argparse.ArgumentParser(description="Generate and send a daily arXiv digest.")
    parser.add_argument("--config", default=os.getenv("TOPICS_CONFIG", "config/topics.toml"))
    parser.add_argument("--seen-store", default=os.getenv("SEEN_STORE", "data/seen_papers.json"))
    parser.add_argument("--reports-dir", default=os.getenv("REPORTS_DIR", "reports"))
    args = parser.parse_args()

    config = load_config(args.config)
    logger.info(f"配置加载: offset={config.digest.target_day_offset}, max={config.digest.max_papers_per_run}")

    seen_ids = load_seen_ids(args.seen_store)
    logger.info(f"已加载 {len(seen_ids)} 篇已处理论文")

    categories = [category for topic in config.topics for category in topic.categories]
    logger.info(f"抓取分类: {categories}, 最大候选: {config.digest.max_candidates}")

    try:
        papers = fetch_recent_papers(
            categories=categories,
            max_results=config.digest.max_candidates,
            timezone_name=config.digest.timezone,
            target_day_offset=config.digest.target_day_offset,
        )
        logger.info(f"arXiv API 返回 {len(papers)} 篇论文")
    except requests.RequestException as e:
        logger.error(f"arXiv API 请求失败: {e}")
        papers = []

    selected = select_papers(config, papers, seen_ids)
    logger.info(f"关键词筛选后: {len(selected)} 篇")

    if selected:
        logger.info(f"开始下载 PDF ({len(selected)} 篇)...")
        populate_article_texts(selected)
        logger.info(f"PDF 下载完成，开始 LLM 摘要生成...")
        enrich_papers(config, selected)
        logger.info(f"LLM 摘要生成完成")
    else:
        logger.info("无新论文，跳过 PDF 和摘要")

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

    logger.info(f"报告已生成: {report_path}")
    logger.info(f"处理论文数: {len(selected)}")
    logger.info(f"邮件发送: {'成功' if email_sent else '失败/跳过'}")
    logger.info("运行完成")


if __name__ == "__main__":
    main()
