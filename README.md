# autoArxiv

一个用于自动抓取 arXiv 新论文、按兴趣主题筛选、提取论文 PDF 正文、通过 DeepSeek 生成摘要并用 GitHub Actions 定时发邮件的项目模板。

## 功能

- 按 `config/topics.toml` 中的研究主题过滤论文
- 自动去重，避免重复推送
- 下载论文 PDF 并抽取正文片段
- 使用 DeepSeek API 基于论文内容生成中文摘要
- 生成日报 Markdown 归档到 `reports/`
- 通过 SMTP 发送 HTML 邮件
- 用 GitHub Actions 定时执行并提交状态文件

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
python -m auto_arxiv.main
```

## 配置

编辑 [config/topics.toml](/Users/hehaixing/Documents/AI/autoArxiv/config/topics.toml)：

- `categories`: arXiv 分类
- `include_keywords`: 必须命中的关键词
- `exclude_keywords`: 排除词
- `required_keyword_groups`: 每一组都至少命中一个关键词，适合收紧主题
- `max_papers_per_run`: 每次最多发几篇

当前默认主题已经调整为你关心的方向：

- NLP + Agent + Skill / Memory / Evolve 强相关

## GitHub Secrets

在仓库的 `Settings -> Secrets and variables -> Actions` 中配置：

- `LLM_PROVIDER`：固定为 `deepseek`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_FROM`
- `EMAIL_TO`

程序会先下载 arXiv PDF，默认抽取前 `15` 页正文作为论文内容，再调用 DeepSeek 的 `chat/completions` 接口做摘要。没有配置 `DEEPSEEK_API_KEY` 时，会退化为基于抽取到的正文片段生成简单说明；如果不配置 SMTP，则只生成报告，不发邮件。

## Workflow

工作流文件位于 [.github/workflows/daily_digest.yml](/Users/hehaixing/Documents/AI/autoArxiv/.github/workflows/daily_digest.yml)。

- `workflow_dispatch`: 手动运行
- `schedule`: 每天 `00:30 UTC` 运行一次，也就是北京时间每天 `08:30`
- 成功后会自动提交 `data/seen_papers.json` 和 `reports/`

## 后续建议

- 将 `seen_papers.json` 换成 SQLite，避免文件不断增大
- 增加每周趋势汇总 workflow
- 给失败任务自动创建 issue 或发送告警邮件
