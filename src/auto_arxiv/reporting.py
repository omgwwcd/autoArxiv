from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from .models import AppConfig, Paper


def write_report(reports_dir: str | Path, config: AppConfig, papers: list[Paper]) -> Path:
    output_dir = Path(reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_date = datetime.utcnow().strftime("%Y-%m-%d")
    path = output_dir / f"{report_date}.md"
    path.write_text(_render_markdown(config, papers), encoding="utf-8")
    return path


def render_email_html(config: AppConfig, papers: list[Paper]) -> str:
    items = []
    for index, paper in enumerate(papers, start=1):
        digest = paper.digest
        code_link = str(digest.get("code_link", "")).strip()
        code_link_html = f' | <a href="{escape(code_link)}">Code</a>' if code_link else ""
        figure_html = (
            f'<p style="margin:8px 0;"><img src="cid:{escape(paper.figure_content_id)}" '
            'style="max-width:100%;border:1px solid #d0d7de;border-radius:8px;" '
            'alt="Most important figure"></p>'
            if paper.figure_content_id
            else "<p style=\"margin:8px 0;\">当前未自动提取到可嵌入的论文图片。</p>"
        )
        method = digest.get("method_overview", {})
        implications = digest.get("implications", {})
        figure = digest.get("most_important_figure", {})
        second_figure = digest.get("second_important_figure", {})
        related_recent_papers = digest.get("related_recent_papers", [])
        findings_html = "".join(
            f"<li><strong>{escape(str(item.get('title', 'Finding')))}:</strong> {escape(str(item.get('detail', '')))}</li>"
            for item in digest.get("key_findings", [])
        )
        research_questions_html = "".join(
            f"<li>{escape(str(item))}</li>"
            for item in digest.get("research_questions", [])
        )
        limitations_html = "".join(
            f"<li>{escape(str(item))}</li>"
            for item in digest.get("limitations", [])
        )
        related_papers_html = "".join(
            (
                "<li>"
                f"<strong>{escape(str(item.get('title', '')))}</strong><br>"
                f"<strong>为什么重要：</strong>{escape(str(item.get('why_important', '')))}<br>"
                f"<strong>核心贡献：</strong>{escape(str(item.get('core_contribution', '')))}<br>"
                f"<strong>与当前论文关系：</strong>{escape(str(item.get('relation_to_current_work', '')))}"
                "</li>"
            )
            for item in related_recent_papers
        )
        items.append(
            f"""
            <section style="margin-bottom:24px;padding:16px;border:1px solid #d0d7de;border-radius:10px;">
              <h3 style="margin:0 0 8px 0;">{index}. {escape(paper.title)}</h3>
              <p style="margin:0 0 8px 0;"><strong>Topics:</strong> {escape(', '.join(digest.get('topics', paper.matched_topics)))}</p>
              <p style="margin:0 0 8px 0;"><strong>Authors:</strong> {escape(', '.join(paper.authors))}</p>
              <p style="margin:0 0 8px 0;"><strong>Venue / Year:</strong> {escape(str(digest.get('venue_or_year', paper.published.year)))}</p>
              <p style="margin:0 0 8px 0;">
                <strong>Links:</strong>
                <a href="{escape(paper.abs_url)}">Abstract</a> |
                <a href="{escape(paper.pdf_url)}">PDF</a>
                {code_link_html}
              </p>
              <h4 style="margin:12px 0 6px 0;">1. 一句话结论</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('one_line_takeaway', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">2. 为什么重要</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('why_it_matters', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">3. 研究问题</h4>
              <ol style="margin:0 0 8px 18px;padding:0;">{research_questions_html}</ol>
              <h4 style="margin:12px 0 6px 0;">4. 背景与问题设定</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('background_and_problem_setting', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">5. 方法概览</h4>
              <p style="margin:0 0 8px 0;"><strong>任务 / 环境:</strong> {escape(str(method.get('task_environment', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>变量 / 干预设计:</strong> {escape(str(method.get('condition_intervention_design', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>评价指标:</strong> {escape(str(method.get('evaluation_metrics', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>模型比较:</strong> {escape(str(method.get('model_comparison', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>我的理解:</strong> {escape(str(method.get('my_understanding', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">6. 关键发现</h4>
              <ul style="margin:0 0 8px 18px;padding:0;">{findings_html}</ul>
              <h4 style="margin:12px 0 6px 0;">7. 最重要的图</h4>
              {figure_html}
              <p style="margin:0 0 8px 0;"><strong>图来源:</strong> {escape(str(figure.get('figure_source', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>为什么重要:</strong> {escape(str(figure.get('why_it_matters', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">8. 如何读这张图</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('how_to_read_this_figure', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">9. 次重要图</h4>
              <p style="margin:0 0 8px 0;"><strong>为什么也重要:</strong> {escape(str(second_figure.get('why_it_matters', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">10. 对 Agent / Skill / Memory 的启发</h4>
              <p style="margin:0 0 8px 0;"><strong>对 Agent 系统:</strong> {escape(str(implications.get('for_agent_systems', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>对 Skill:</strong> {escape(str(implications.get('for_skill', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>对 Memory:</strong> {escape(str(implications.get('for_memory', '')))}</p>
              <p style="margin:0 0 8px 0;"><strong>对评测:</strong> {escape(str(implications.get('for_evaluation', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">11. 局限性</h4>
              <ul style="margin:0 0 8px 18px;padding:0;">{limitations_html}</ul>
              <h4 style="margin:12px 0 6px 0;">12. 我的看法 / 个人笔记</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('my_take', '')))}</p>
              <h4 style="margin:12px 0 6px 0;">13. 这篇工作引用的近期高影响力相关文章</h4>
              <ul style="margin:0 0 8px 18px;padding:0;">{related_papers_html or '<li>当前未可靠抽取到近期高影响力相关文章。</li>'}</ul>
              <h4 style="margin:12px 0 6px 0;">14. 总结</h4>
              <p style="margin:0 0 8px 0;">{escape(str(digest.get('final_summary', '')))}</p>
              <p style="margin:0;">
                <a href="{escape(paper.abs_url)}">Abstract</a>
                |
                <a href="{escape(paper.pdf_url)}">PDF</a>
              </p>
            </section>
            """
        )

    body = "\n".join(items) if items else "<p>No new matching papers were found in this run.</p>"
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif;max-width:860px;margin:0 auto;padding:24px;line-height:1.6;color:#24292f;">
        <h1>{escape(config.digest.project_name)}</h1>
        <p>Matched papers: {len(papers)}</p>
        {body}
      </body>
    </html>
    """


def _render_markdown(config: AppConfig, papers: list[Paper]) -> str:
    lines = [
        f"# {config.digest.project_name}",
        "",
        f"- Generated at: {datetime.utcnow().isoformat()}Z",
        f"- Matched papers: {len(papers)}",
        "",
    ]
    if not papers:
        lines.append("No new matching papers were found.")
        lines.append("")
        return "\n".join(lines)

    for index, paper in enumerate(papers, start=1):
        digest = paper.digest
        code_link = str(digest.get("code_link", "")).strip()
        method = digest.get("method_overview", {})
        figure = digest.get("most_important_figure", {})
        second_figure = digest.get("second_important_figure", {})
        implications = digest.get("implications", {})
        related_recent_papers = digest.get("related_recent_papers", [])
        lines.extend(
            [
                f"## {index}. {paper.title}",
                "",
                f"**Topics:** {', '.join(digest.get('topics', paper.matched_topics))}",
                f"**Authors:** {', '.join(paper.authors)}",
                f"**Venue / Year:** {digest.get('venue_or_year', paper.published.year)}",
                f"**Links:** [Abstract]({paper.abs_url}) | [PDF]({paper.pdf_url})"
                + (f" | [Code]({code_link})" if code_link else ""),
                "",
                "### 1. 一句话结论",
                "",
                str(digest.get("one_line_takeaway", "")),
                "",
                "### 2. 为什么重要",
                "",
                str(digest.get("why_it_matters", "")),
                "",
                "### 3. 研究问题",
                "",
                *[f"{idx}. {item}" for idx, item in enumerate(digest.get("research_questions", []), start=1)],
                "",
                "### 4. 背景与问题设定",
                "",
                str(digest.get("background_and_problem_setting", "")),
                "",
                "### 5. 方法概览",
                "",
                f"- 任务 / 环境: {method.get('task_environment', '')}",
                f"- 变量 / 干预设计: {method.get('condition_intervention_design', '')}",
                f"- 评价指标: {method.get('evaluation_metrics', '')}",
                f"- 模型比较: {method.get('model_comparison', '')}",
                f"- 我的理解: {method.get('my_understanding', '')}",
                "",
                "### 6. 关键发现",
                "",
                *[
                    f"- {item.get('title', 'Finding')}: {item.get('detail', '')}"
                    for item in digest.get("key_findings", [])
                ],
                "",
                "### 7. 最重要的图",
                "",
                f"- 图来源: {figure.get('figure_source', '')}",
                f"- 为什么重要: {figure.get('why_it_matters', '')}",
                "",
                "### 8. 如何读这张图",
                "",
                str(digest.get("how_to_read_this_figure", "")),
                "",
                "### 9. 次重要图",
                "",
                f"- 为什么也重要: {second_figure.get('why_it_matters', '')}",
                "",
                "### 10. 对 Agent / Skill / Memory 的启发",
                "",
                f"- 对 Agent 系统: {implications.get('for_agent_systems', '')}",
                f"- 对 Skill: {implications.get('for_skill', '')}",
                f"- 对 Memory: {implications.get('for_memory', '')}",
                f"- 对评测: {implications.get('for_evaluation', '')}",
                "",
                "### 11. 局限性",
                "",
                *[f"- {item}" for item in digest.get("limitations", [])],
                "",
                "### 12. 我的看法 / 个人笔记",
                "",
                str(digest.get("my_take", "")),
                "",
                "### 13. 这篇工作引用的近期高影响力相关文章",
                "",
                *(
                    [
                        f"- {item.get('title', '')}",
                        f"  为什么重要：{item.get('why_important', '')}",
                        f"  核心贡献：{item.get('core_contribution', '')}",
                        f"  与当前论文关系：{item.get('relation_to_current_work', '')}",
                    ]
                    for item in related_recent_papers
                ),
                *([] if related_recent_papers else ["- 当前未可靠抽取到近期高影响力相关文章。"]),
                "",
                "### 14. 总结",
                "",
                str(digest.get("final_summary", "")),
                "",
            ]
        )
    flattened: list[str] = []
    for item in lines:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)
    return "\n".join(flattened)
