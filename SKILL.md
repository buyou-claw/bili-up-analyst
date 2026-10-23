---
name: bili-up-analyst
description: "分析 B 站 UP 主的历史视频，提炼其认知框架、思维模式、核心论点、观点演变与预测准确率，产出可学习的认知档案。Use when: (1) 用户要求分析/学习某个 UP 主（UID、空间链接或昵称）的思维、认知、观点、金句；(2) 批量抓取并总结某 UP 主的历史视频内容；(3) 追踪某 UP 主观点演变或预测验证；(4) 需要用 bilibili-cli 对 B 站视频做知识沉淀/笔记库。Triggers: 分析这个UP主、学习他的思维、抓取他的历史视频、提取认知、观点演变、给UP主建档案。"
---

# Bili UP Analyst

把 UP 主的历史视频批量转成"可学习的认知档案"：索引 → 抓取内容 → 逐期蒸馏 → 跨期综合 → 增量更新。

## 前置条件

- **bilibili-cli**：本机已安装（`pip install bilibili-cli` 或源码克隆）。脚本通过 `import bili_cli` 或环境变量 `BILI_CLI_PROJECT` 定位项目。
- **Python 3.10+**；本仓库命令里的 `$PY` 指装有 bilibili-cli 的 Python。
- **登录**：`bili login` → `~/.bilibili-cli/credential.json`（失效则重新登录；**充电专属视频需要该 UP 的充电会员**）。
- **ASR（仅无字幕视频需要）**：`pip install faster-whisper`；模型默认自动下载 `small`，或用 `BILI_ASR_MODEL` 指向本地 CTranslate2 模型目录。
- **透明加密环境**（如天锐绿盾）：脚本写出的 `.json/.txt` 用 agent 的 read 工具可能报 "binary file"。
  → 规则：机器文件只给脚本读；agent 读内容走 `scripts/show_content.py`；agent 产出的笔记一律用 `.md`。
- **文件命名**：`raw/` 与 `notes/` 统一用 **`<发布日期>_<视频标题>`**（如 `2026-10-21_《第七百八六期》三季度GDP增长趋势稳定，有哪些亮点？.md`），**不用 BV 号做文件名**；bvid 保留在 `index.json` 与每个文件内容里，供程序索引。

## 固定流程

约定变量（PowerShell / bash 自行适配）：

```text
$SKILL  = 本仓库（skill）所在目录
$PY     = 装有 bilibili-cli 的 python；bilibili-cli 为源码克隆时先 export BILI_CLI_PROJECT=<path>
$UP_DIR = <analysis>/<昵称>_<UID>   （up_index.py 会打印）
```

### Step 1 建索引（0 token）

```bash
python "$SKILL/scripts/up_index.py" <UID或空间链接或昵称> --max 20
```

产出 `<analysis>/<昵称>_<UID>/index.json` + `index.md`。终端只返回统计摘要（总数/日期范围/系列/充电数量/最新几期），**不要把全量列表读进上下文**。

### Step 2 选定范围

- 用户指定期数/时间范围 → 照做；未指定 → 最近 N 期。
- 想分析"认知演变"：按时间均匀抽样（如每 10 期取 1 期）+ 高播放补充。
- 充电专属视频：账号有对应 UP 的充电会员才能取到内容；无权限的会在 Step 3 标记 `none`。

### Step 3 批量抓内容（0 token，可后台跑）

```bash
python "$SKILL/scripts/fetch_content.py" --up-dir "$UP_DIR" --limit 20 --mode auto
```

推荐**两阶段**执行（最快）：
1. 先扫字幕：`--mode subtitle`（几秒/期，大部分视频有 B站 AI 字幕）；
2. 再补缺口：`--mode auto`——已有内容的自动跳过，只对 `none` 的期做本地 ASR（20–50 分钟视频约 3–10 分钟，**必须放后台任务**）。

- `--mode auto`：字幕优先 → AI 摘要补充 → 无字幕才 ASR。
- 断点续跑：已有 `raw/<日期>_<标题>.json` 自动跳过（`source=none` 的在 auto 模式下会自动重试 ASR）；`--force` 强制重抓；`--bvid BV...` 指定单期。
- 范围过滤：`--since 2026-09-01` / `--until 2026-10-21`（按发布日期，含端点），用于扩充历史区间。
- 多期 ASR 可开 2 个后台进程并行（设 `BILI_ASR_THREADS=8`，每个 8 线程），吞吐约翻倍。
- 产出：`raw/<发布日期>_<标题>.json`（机器缓存）+ `raw/<发布日期>_<标题>.md`（用户可读原始字幕）。

### Step 4 逐期蒸馏（map，最关键）

每期产出**两份文件**：短笔记（给跨期综合用，≤800 字）+ 原味精编（给人读，2000–3500 字）。

对每个未处理的 bvid **开独立 subagent**（有 `workflow` 工具就 fan-out，每批 6–8 个；否则串行 subagent）：

```text
Read <SKILL>/references/extraction-framework.md and <SKILL>/references/digest-framework.md first.
Video: <bvid> | Title: <title>
1) python "$SKILL/scripts/show_content.py" --up-dir "$UP_DIR" --bvid <bvid> --part 1 --part-chars 4000
   （输出头部的 NOTE_FILE= / DIGEST_FILE= 就是两份文件的写入路径；part=1/N，依次读 --part 2..N）
2) 写 NOTE_FILE：短笔记（≤800 字，按 extraction-framework.md；给综合用）
3) 写 DIGEST_FILE：原味精编（3000–4500 汉字，按 digest-framework.md；保留原话/例子/叙事顺序，给人读）
   若两份都已存在则跳过；只缺 digest 时补写 digest。
Return only: "DONE <bvid>" or "FAIL <bvid> <reason>".
```

纪律：
- 主 agent **绝不**把 raw 字幕读进上下文（只收 subagent 的一行结果）。
- 已有 `notes/<日期>_<标题>.md` 且 `digests/<日期>_<标题>.md` → 跳过（缓存）。
- 短笔记 ≤800 汉字（≈600 token）；**digest 只给人读，不进入综合上下文**。
- 全部精编完成后跑 `append_digest_excerpt.py`：把精编的**节选**作为最后一段（`## 内容精编（补充）`）追加到原笔记，原 9 节格式不变。

### Step 5 校验笔记（0 token）

```bash
python "$SKILL/scripts/notes_check.py" --up-dir "$UP_DIR" --since 2026-09-01
```

输出：缺失期数、缺章节、字数统计。补齐后再综合。

### Step 6 跨期综合（reduce）

先跑（0 token，自动汇总预测/金句，避免主上下文读全部笔记）：

```bash
python "$SKILL/scripts/aggregate_notes.py" --up-dir "$UP_DIR"
# 若要加人工盘点：先把盘点写到 "$UP_DIR/synthesis/predictions_intro.md"，再跑
python "$SKILL/scripts/aggregate_notes.py" --up-dir "$UP_DIR" --intro "$UP_DIR/synthesis/predictions_intro.md"
```

→ 覆盖写 `predictions.md`（全量账本，可选顶部人工盘点）与 `synthesis/quotes_all.md`；终端只打印统计。

然后按 `references/synthesis-framework.md` 产出：

- `report.md`：认知档案主报告（2500–5000 字）
- `quotes.md`：精选金句库（从 `quotes_all.md` 里挑，不必全量）
- `predictions.md`：在全量账本顶部补写"盘点与跟踪建议"（方向偏好/复查节奏/风险点）

**大样本（>40 期）用分层综合省 token**：
1. 按时间分 2–4 桶（如 9 月上旬 / 9 月下旬 / 10 月），每桶 1 个 subagent，只读该桶 notes（15–20 期/桶），输出 `synthesis/bucket_<时间段>.md`（≈700–900 字：桶内 thesis、观点变化、重要预测、金句、盲区）。
2. 主 agent 只读各桶摘要 + `index.json` 统计 + 旧版 report（如有），写最终 `report.md`；需要时再抽查个别 notes。

需要核对某句原文时，用 `show_content.py` 只回查个别片段，不整篇读。

### Step 7 交付与增量

1. 向用户展示 report.md 的核心结论 + 文件路径（用 present 展示 report.md）。
2. 增量更新：Step 1 重跑 → Step 3（只抓新增）→ Step 4（只蒸馏新增）→ 重跑 Step 6。
3. 用户反馈后可调 rubric 重跑综合（只有 notes 变化才需要重跑，raw 不动）。

## Token 纪律

1. raw 内容（约 8–10k token/期）只进 subagent，不进主上下文。
2. 跨上下文只传 notes（≈600 token/期）；20 期综合主上下文 < 2 万 token。
3. `digests/`（2000–3500 字/期）只给人读，**不进入综合上下文**；综合只用 notes。
4. 抓取/转写/切片/汇总全部由脚本完成，不产生 token。
5. 一切按 bvid 缓存（文件名用"日期_标题"）；重复分析成本 ≈ 只跑一次综合。
6. 先 3 期小样验证框架，再批量跑。

## 产物结构

```
<analysis>/<昵称>_<UID>/
├── index.json / index.md      # 视频清单（脚本产出，含 bvid）
├── raw/<发布日期>_<标题>.json|.md  # 原始资料（字幕/转写）
├── notes/<发布日期>_<标题>.md      # 每期认知笔记（短，≤800 字；给综合用）
├── digests/<发布日期>_<标题>.md    # 每期「原味精编」（2000–3500 字；给人读）
├── synthesis/                 # 大样本：分桶摘要 + quotes_all.md + predictions_intro.md
├── report.md                  # 认知档案（主报告）
├── quotes.md                  # 精选金句库
└── predictions.md             # 预测账本（自动汇总 + 人工盘点）
```

## 脚本（都在 `$SKILL/scripts/`）

- `up_index.py` — 建/刷新视频索引（UP 名自动解析，输出 index.json/md）
- `fetch_content.py` — 抓字幕/AI 摘要/ASR，缓存化；支持 `--since/--until/--limit/--bvid`
- `show_content.py` — 按 bvid 输出分片内容，头部打印 `NOTE_FILE` / `DIGEST_FILE`
- `notes_check.py` — 笔记覆盖率与章节校验；支持 `--since/--until`
- `append_digest_excerpt.py` — 把精编节选追加到笔记末尾（原格式保留，可重复运行）
- `aggregate_notes.py` — 从笔记自动汇总预测账本与金句（0 token）
- `_common.py` / `_asr.py` — 公共工具与本地 ASR（`BILI_ASR_THREADS`/`BILI_ASR_BEAM` 可调）
- `install.py` — 把本 skill 复制到 skills 目录
- `package_skill.py` — 把仓库打包成 `.skill`（zip）

## 排障

- read 工具报 "binary file"：透明加密所致，改用 `show_content.py` 打印。
- 某期无字幕又不想等 ASR：`--mode subtitle`，标记 `none`，蒸馏时注明"仅凭标题/简介推断"。
- 充电专属 403/无权限：确认登录账号是否为该 UP 的充电会员；或试 `--mode subtitle` 看有无公开字幕。
- ASR 慢：后台任务 + `--limit` 分批，不要前台同步等待。
- 登录失效：让用户重新 `bili login`。
- `faster-whisper` 缺失：`pip install faster-whisper`。
- 找不到 bilibili-cli：`pip install bilibili-cli`，或设置 `BILI_CLI_PROJECT`。

## References

- `references/extraction-framework.md` — 单期认知提取 rubric 与短笔记模板（Step 4 必读，给综合用）
- `references/digest-framework.md` — 单期「原味精编」rubric 与模板（Step 4 必读，给人读）
- `references/synthesis-framework.md` — 综合报告/金句/预测账本模板（Step 6 必读）
