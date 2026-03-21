# autoArxiv

一个用于自动抓取 arXiv 新论文、按兴趣主题筛选、提取论文 PDF 正文、通过大模型生成高质量中文论文 digest，并用 GitHub Actions 定时发邮件的自动化项目。

## 当前能力

- 按北京时间精确抓取“前一天新发布”的 arXiv 论文
- 按 `config/topics.toml` 中的研究主题做分层筛选
- 自动去重，避免重复推送
- 下载论文 PDF，默认抽取前 `15` 页正文
- 自动提取论文中的一张候选图并内嵌到邮件中
- 使用大模型基于论文正文生成中文结构化摘要
- 先生成摘要，再让模型自评打分；若低于 `90` 分则自动重写，最多 `5` 轮
- 生成日报 Markdown 归档到 `reports/`
- 通过 SMTP 发送 HTML 邮件
- 用 GitHub Actions 定时执行并提交状态文件

## 摘要模板

当前邮件和 Markdown 报告会按结构化 digest 输出，包含这些部分：

- Title / Topics / Authors / Venue / Links
- One-line takeaway
- Why it matters
- Research questions
- Background and problem setting
- Method overview
- Key findings
- Most important figure
- How to read this figure
- Optional second important figure
- Implications for Agent / Skill / Memory
- Limitations
- My take / Personal notes
- Related high-impact recent papers cited by this work
- Final summary

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
python -m auto_arxiv.main
```

## 主题与筛选

编辑 [config/topics.toml](/Users/hehaixing/Documents/AI/autoArxiv/config/topics.toml)：

- `categories`: arXiv 分类
- `include_keywords`: 必须命中的关键词
- `exclude_keywords`: 排除词
- `required_keyword_groups`: 每一组都至少命中一个关键词，适合收紧主题
- `target_day_offset`: 抓取相对当前日期往前多少天，默认 `1`
- `timezone`: 用哪个时区计算“昨天”，默认 `Asia/Shanghai`
- `max_papers_per_run`: 每次最多发几篇

当前默认主题已经调整为你关心的方向：

- Agent Memory / Agent Skill / Agent RL / Agent Evolve
- RL
- LLM / NLP fallback

筛选顺序目前是：

1. 先找 `Agent / Agent Skill / Agent Memory / Agent RL / Agent Evolve` 强相关论文
2. 如果当天没有命中，再找 `RL` 相关论文
3. 如果前两层都没有，再回退到 `LLM / NLP` 相关论文

每次运行最多保留 `5` 篇论文。

## 时间窗口

抓取时间窗口按配置中的时区和偏移日计算。当前默认设置为：

- `timezone = "Asia/Shanghai"`
- `target_day_offset = 1`

这表示：

- 如果任务在北京时间 `2026-03-21 08:30` 运行
- 会抓取北京时间 `2026-03-20` 新发布的相关论文

## 邮件与图片

- 邮件为 HTML 格式
- 会尝试从论文 PDF 中提取一张候选图，并作为 inline image 嵌入邮件
- 如果当前论文没能稳定提取出图片，邮件中会显示文字提示
- 同时会把摘要归档为 Markdown 到 `reports/`

## 质量控制

当模型可用时，每篇论文的摘要生成流程为：

1. 生成一版摘要
2. 用同一个模型对摘要质量进行评分
3. 如果评分低于 `90`，根据反馈重写
4. 最多循环 `5` 次
5. 若始终未达阈值，则保留分数最高的一版

这会提高摘要质量，但也会增加模型调用次数和运行时间。

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

如果没有配置模型 API key，程序会退化为基于正文片段的简单摘要；如果没有配置 SMTP，则只生成报告，不发邮件。

## Workflow

工作流文件位于 [.github/workflows/daily_digest.yml](/Users/hehaixing/Documents/AI/autoArxiv/.github/workflows/daily_digest.yml)。

- `workflow_dispatch`: 手动运行
- `schedule`: 每天 `00:30 UTC` 运行一次，也就是北京时间每天 `08:30`
- GitHub Actions 的 `schedule` 不是强实时，可能会比设定时间晚几分钟甚至更久
- 成功后会自动提交 `data/seen_papers.json` 和 `reports/`

## 目录说明

- [config/topics.toml](/Users/hehaixing/Documents/AI/autoArxiv/config/topics.toml): 主题、时区、候选池、每日篇数等配置
- [src/auto_arxiv/arxiv.py](/Users/hehaixing/Documents/AI/autoArxiv/src/auto_arxiv/arxiv.py): arXiv 抓取、时间过滤、PDF 文本和图片提取
- [src/auto_arxiv/filtering.py](/Users/hehaixing/Documents/AI/autoArxiv/src/auto_arxiv/filtering.py): 主题筛选与优先级回退
- [src/auto_arxiv/summarizer.py](/Users/hehaixing/Documents/AI/autoArxiv/src/auto_arxiv/summarizer.py): 摘要生成、质量评分、循环重写
- [src/auto_arxiv/reporting.py](/Users/hehaixing/Documents/AI/autoArxiv/src/auto_arxiv/reporting.py): HTML 邮件与 Markdown 报告渲染
- [src/auto_arxiv/mailer.py](/Users/hehaixing/Documents/AI/autoArxiv/src/auto_arxiv/mailer.py): SMTP 发信与 inline image 附件
- [.github/workflows/daily_digest.yml](/Users/hehaixing/Documents/AI/autoArxiv/.github/workflows/daily_digest.yml): GitHub Actions 定时任务

## 后续可继续做的事

- 将 `seen_papers.json` 换成 SQLite 或外部存储，避免文件持续增长
- 对相关性增加“模型二次打分”，进一步压低关键词误判
- 自动抽取第二张关键图，而不只是保留文字位
- 对“近期高影响力相关文章”接入外部 citation / semantic scholar 数据源
- 增加每周趋势汇总 workflow
- 给失败任务自动创建 issue 或发送告警邮件
