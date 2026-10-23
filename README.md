# bili-up-analyst

> 一个基于 [bilibili-cli](https://github.com/public-clis/bilibili-cli) 的 AI Agent Skill：把一个 B 站 UP 主的历史视频，批量整理成**可学习的"认知档案"**——思维模式、核心论点、观点演变、预测账本与金句库。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## 它解决什么问题

想系统学习某个 UP 主的"认知与思维"，手动刷几十上百期视频是不现实的：内容分散在视频里、没有字幕、没有摘要，逐个看完再整理既费时又费 token。

`bili-up-analyst` 把这件事变成一条固定流水线：

- **抓取层（0 token）**：通过 `bilibili-cli` 拉视频清单、字幕 / AI 摘要，无字幕时用本地 faster-whisper 转写；全部落盘缓存、断点续跑。
- **蒸馏层（子 agent 隔离）**：每期视频由一个独立 subagent 按固定 rubric 提取成一篇 ≤800 字的"认知笔记"，主上下文不读原始字幕。
- **综合层（分层 reduce）**：分桶摘要 → 跨期综合，产出认知档案、预测账本、金句库；支持增量更新。

## 工作流程

```
UP 主 (UID / 空间链接 / 昵称)
        │  scripts/up_index.py            # 视频清单（日期、期数、播放、时长）
        ▼
   index.json / index.md
        │  scripts/fetch_content.py       # 字幕优先 → AI 摘要 → 本地 ASR 兜底
        ▼
   raw/<日期>_<标题>.json|.md            # 原始字幕/转写（可读、可复查）
        │  逐期 subagent（见 references/extraction-framework.md）
        ▼
   notes/<日期>_<标题>.md                # 每期认知笔记（≤800 字，给综合用）
   digests/<日期>_<标题>.md              # 每期原味精编（2000–3500 字，给人读）
        │  分桶摘要 + cross-video synthesis（见 references/synthesis-framework.md）
        ▼
   report.md  quotes.md  predictions.md  # 认知档案 / 金句库 / 预测账本
```

## 功能特性

- 🎬 **批量抓取**：`bili user-videos` 风格的清单 + 字幕/摘要/音频转写，支持 `--since/--until/--limit/--bvid` 与断点续跑。
- 📄 **文件名可读**：`raw/` 与 `notes/` 统一用 `<发布日期>_<视频标题>`，不用 BV 号；bvid 保留在索引与文件头。
- 🧠 **固定认知提取 rubric**：一句话结论、论点与证据、关键数据、推理链条、思维模型、可证伪预测、立场与盲区、金句。
- 📖 **原味精编**：每期另产出一份 3000–4500 字的「原味精编」——按原视频顺序保留原话、比喻、例子与数字（压缩到原文 30–45%）；并自动把**整期「内容精编」全文**追加到原笔记末尾（覆盖全片，不是只截开头），原来的 9 节格式保持不变。
- 📊 **自动汇总**：从 67 篇笔记 0 token 汇总出 201 条预测账本 + 232 条金句（示例规模）。
- 🔁 **增量更新**：只抓新增、只蒸馏新增，重复分析成本≈重跑一次综合。
- 💰 **Token 经济**：raw 约 8–10k token/期只进子 agent；主上下文 20 期综合 < 2 万 token。
- 🔐 **本地优先**：所有内容落盘在本机，登录凭证复用 `bilibili-cli` 的 `~/.bilibili-cli/credential.json`。

## 安装

### 1. 安装 bilibili-cli 并登录

```bash
# 任选其一
pip install bilibili-cli            # 或 pipx / uv tool install bilibili-cli
# 或从源码：
git clone https://github.com/public-clis/bilibili-cli.git
cd bilibili-cli && pip install -e .

bili login          # 扫码登录；充电专属/会员视频需要对应权限
bili status         # 确认已登录
```

> 本 skill 的脚本需要能 `import bili_cli`。如果 bilibili-cli 是源码克隆，设置环境变量
> `BILI_CLI_PROJECT=/path/to/bilibili-cli`，或在项目目录下运行。

### 2. 安装本 skill

把本仓库放到你的 skills 目录即可（不同 agent 的目录不同，按你的环境选择）：

```bash
git clone https://github.com/buyou-claw/bili-up-analyst.git
cp -r bili-up-analyst ~/.agents/skills/          # DSH / Claude Code 等常见位置
# 或者软链接：
ln -s "$PWD/bili-up-analyst" ~/.agents/skills/bili-up-analyst
```

Windows PowerShell：

```powershell
git clone https://github.com/buyou-claw/bili-up-analyst.git
Copy-Item -Recurse .\bili-up-analyst "$env:USERPROFILE\.agents\skills\bili-up-analyst"
# 或一键安装：
python .\bili-up-analyst\scripts\install.py
```

### 3.（可选）无字幕视频的本地转写

```bash
pip install faster-whisper
```

模型默认自动下载（`small`）；国内网络可预下载 CTranslate2 模型并设置
`BILI_ASR_MODEL=/path/to/faster-whisper-small`（本机示例：
`modelscope.cn/models/pengzhendong/faster-whisper-small`）。

## 快速开始

在任意目录（已登录 bilibili-cli）：

```bash
export SKILL=/path/to/bili-up-analyst

# 1) 建索引：最近 20 期
python "$SKILL/scripts/up_index.py" 290663424 --max 20

# 2) 抓内容（先字幕，快；无字幕的再加 --mode auto 走 ASR，建议后台跑）
python "$SKILL/scripts/fetch_content.py" --up-dir "<analysis>/<昵称>_<UID>" --mode subtitle
python "$SKILL/scripts/fetch_content.py" --up-dir "<analysis>/<昵称>_<UID>" --mode auto

# 3) 校验笔记（在 subagent 完成蒸馏之后）
python "$SKILL/scripts/notes_check.py" --up-dir "<analysis>/<昵称>_<UID>" --since 2026-09-01

# 4) 自动汇总预测/金句
python "$SKILL/scripts/aggregate_notes.py" --up-dir "<analysis>/<昵称>_<UID>"
```

> 蒸馏与综合是 agent 的职责：让每个视频开一个独立 subagent，读
> `references/extraction-framework.md` + `references/digest-framework.md` + `show_content.py` 的输出，
> 分别写短笔记到 `NOTE_FILE`、原味精编到 `DIGEST_FILE`。完整流程见 [SKILL.md](./SKILL.md)。

## 输出结构

```
<analysis>/<昵称>_<UID>/
├── index.json / index.md          # 视频清单（含 bvid、日期、期数、播放）
├── raw/<日期>_<标题>.json|.md     # 原始字幕/转写（用户可读）
├── notes/<日期>_<标题>.md         # 每期认知笔记（≤800 字，给综合用）
├── digests/<日期>_<标题>.md       # 每期原味精编（2000–3500 字，给人读）
├── synthesis/                     # 分桶摘要 + quotes_all.md + predictions_intro.md
├── report.md                      # 认知档案主报告
├── quotes.md                      # 精选金句库
└── predictions.md                 # 预测账本（自动汇总 + 人工盘点）
```

默认输出到 `<bilibili-cli 项目>/analysis/`；用 `BILI_ANALYSIS_DIR` 可改到任意目录。

## Token 经济（实测）

| 做法 | 主上下文 token |
|---|---|
| 朴素：主 agent 逐期读字幕 | ≈ 8–10k token/期（20 期 ≈ 13 万+） |
| 本 skill：子 agent 蒸馏 + 只回灌笔记 | ≈ 2 万（索引 + N 篇笔记 + 综合） |
| 增量更新 | 只处理新增 + 重跑综合，≈ 几千 |

- 抓取 / 转写 / 切片 / 汇总全部由脚本完成，不消耗 token；
- raw 内容只进子 agent 上下文，笔记 ≤800 字跨期传递；
- 每期 `digests/`（2000–3500 字）只给人读，**不进入综合上下文**；综合只读 notes；
- 大样本（>40 期）用"分桶摘要 → 最终综合"两层 reduce。

## 配置

| 环境变量 | 说明 |
|---|---|
| `BILI_CLI_PROJECT` | bilibili-cli 源码目录（脚本用它 import `bili_cli`；已 pip 安装且 Python 能找到时可省略） |
| `BILI_ANALYSIS_DIR` | 分析输出根目录（默认 `<project>/analysis`） |
| `BILI_ASR_MODEL` | faster-whisper 模型目录或尺寸名（默认自动下载 `small`） |
| `BILI_ASR_THREADS` | ASR CPU 线程数（默认全部核心；多进程并行时设 8） |
| `BILI_ASR_BEAM` | ASR beam size（默认 1，速度快；要质量可设 5） |

## 常见问题

- **某期没有字幕**：`fetch_content.py --mode auto` 会自动下载音频并用 faster-whisper 转写（20–50 分钟视频约 3–10 分钟）；也可先 `--mode subtitle` 快速扫描，跳过 ASR。
- **充电专属 / 会员视频**：账号需为该 UP 的充电会员或有对应权限，否则该期标记 `none`。
- **`read` 工具读脚本产物报 "binary file"**：若机器安装了透明加密软件（如天锐绿盾），脚本写出的 `.json/.txt` 可能对非白名单进程加密。规则：机器文件只给脚本读，agent 读内容走 `show_content.py`；agent 产出用 `.md`。
- **透明加密环境下安装**：不要用 `python scripts/install.py` 复制文件（Python 进程写出的文件可能被加密，导致 agent 读取异常）；改用 `cp -r` / PowerShell `Copy-Item` 原生复制。
- **ASR 模型下载失败**：设置 `BILI_ASR_MODEL` 指向本地 CTranslate2 模型目录（可自行从 HF/ModelScope 下载 `Systran/faster-whisper-small`）。
- **登录失效**：重新 `bili login`。

## 适用范围与免责声明

- 适合：系统学习某个 UP 主的分析框架、观点演变、判断准确率；做个人知识库与研究。
- 不适合：把模型结论直接当投资建议；批量转载他人视频内容。
- 本项目只做**个人学习用途的内容整理**：音频/字幕/转写文件仅保存在本地，不应再分发；视频内容版权归原作者所有，请遵守 B 站用户协议与著作权法。
- 预测账本记录的是 UP 主个人观点，不是事实断言；使用前请自行核实。

## License

[MIT](./LICENSE) © 2026 bili-up-analyst contributors

本项目的脚本与文档为原创；运行时依赖 [bilibili-cli](https://github.com/public-clis/bilibili-cli)（Apache-2.0）与 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（MIT），它们各自遵循其许可证。
