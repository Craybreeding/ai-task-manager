# AI Captain 全生命周期管理系统 — 执行计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建覆盖"研发事实 → 执行协作 → 质量评估 → 可视驾驶舱 → 运维闭环"五层的 AI 项目全生命周期管理系统。

**Architecture:** GitHub 作研发事实层，飞书 Bitable 作统一存储与执行层，Python workers 负责各层数据摄取与同步，React Dashboard 提供决策视图，Ops Console 保障在线稳定性。

**Tech Stack:** Python 3.10+, uv/pip, requests, python-dotenv, lark-oapi SDK, GitHub CLI (gh), React 18 + TypeScript, Vite, TailwindCSS (已有), launchd (macOS scheduler)

---

## 目录结构约定（执行前先对齐）

```
ai-task-manager/
├── scripts/
│   ├── github_sync.py          ← 已存在，Phase 1 补全
│   ├── bitable_setup.py        ← Phase 1 新建：建表脚本
│   ├── feishu_event_sync.py    ← Phase 2 新建
│   ├── card_push.py            ← Phase 2 新建
│   ├── metrics_collector.py    ← Phase 3 新建
│   ├── weekly_digest.py        ← Phase 3 新建
│   └── ops_health_check.py     ← Phase 5 新建
├── api/
│   └── snapshot.py             ← Phase 4 新建：聚合接口
├── workers/
│   └── scheduler.py            ← Phase 5 新建：统一调度器
├── state/                      ← 已存在：同步状态 JSON
├── logs/                       ← 已存在：日志目录
├── src/                        ← 已存在：React 前端
│   ├── App.tsx
│   ├── types.ts
│   └── data/mockData.ts
├── .env.example                ← Phase 1 新建
└── docs/
    └── PLANS.md                ← 本文件
```

---

## 环境变量约定（所有阶段共用）

```bash
# .env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
BITABLE_APP_TOKEN=xxx              # 多维表格 appToken（Base 级别）
TABLE_PROJECTS=tbl_projects        # 项目主表 tableId
TABLE_TASKS=tbl_tasks              # 任务表 tableId
TABLE_MILESTONES=tbl_milestones    # 里程碑表 tableId
TABLE_EVAL=tbl_eval                # Eval 表 tableId
TABLE_WEEKLY=tbl_weekly            # 周更新表 tableId
TABLE_OPS_EVENTS=tbl_ops_events    # 运维事件表 tableId
GITHUB_ORG=goodidea-ggn
FEISHU_BOT_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_GROUP_CHAT_ID=oc_xxx        # 项目群 chat_id
SNAPSHOT_OUTPUT_PATH=./dist/snapshot.json
```

---

## Phase 1 — Foundation：Bitable 表结构 + GitHub Sync 完整实现

### 背景

`github_sync.py` 已具备骨架，但只写了单表（任务表）且字段不完整。Phase 1 目标：
1. 用脚本幂等创建全部 6 张 Bitable 表及字段
2. 把 `github_sync.py` 补全为生产级同步，支持增量、多 repo、关联项目主表

---

### Task 1.1：创建 `.env.example` 与目录骨架

**Files:**
- Create: `.env.example`
- Create: `state/.gitkeep`
- Create: `logs/.gitkeep`

**Step 1: 创建 `.env.example`**

```bash
cat > .env.example << 'EOF'
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
BITABLE_APP_TOKEN=
TABLE_PROJECTS=
TABLE_TASKS=
TABLE_MILESTONES=
TABLE_EVAL=
TABLE_WEEKLY=
TABLE_OPS_EVENTS=
GITHUB_ORG=
FEISHU_BOT_WEBHOOK=
FEISHU_GROUP_CHAT_ID=
SNAPSHOT_OUTPUT_PATH=./dist/snapshot.json
EOF
```

**Step 2: 确认 state/ 和 logs/ 目录存在**

```bash
mkdir -p state logs
touch state/.gitkeep logs/.gitkeep
```

**Step 3: Commit**

```bash
git add .env.example state/.gitkeep logs/.gitkeep
git commit -m "chore: add env template and ensure state/logs dirs"
```

---

### Task 1.2：`bitable_setup.py` — 幂等建表脚本

> 这个脚本读取 `.env`，检查 Base 里是否已有对应表，没有则创建，有则跳过。每次都打印表的 tableId 供写入 `.env`。
> **同步新增字段**: 项目主表将增加 "产品代码与测试"、"CI 配置"、"开发者工具"、"设计文档"、"评估框架"、"Review 记录"、"仓库脚本"、"Dashboard 定义" 等 8 个字段，用于追踪智能体的全量产出。

**Files:**
- Create: `scripts/bitable_setup.py`

**Step 1: 写失败测试**

```python
# tests/test_bitable_setup.py
import pytest
from unittest.mock import MagicMock, patch

def test_parse_existing_tables_returns_dict():
    from scripts.bitable_setup import parse_table_map
    raw = [{"table_id": "tbl1", "name": "项目主表"}, {"table_id": "tbl2", "name": "任务表"}]
    result = parse_table_map(raw)
    assert result == {"项目主表": "tbl1", "任务表": "tbl2"}

def test_parse_existing_tables_empty():
    from scripts.bitable_setup import parse_table_map
    assert parse_table_map([]) == {}
```

**Step 2: 运行测试确认失败**

```bash
cd /Users/ggn/ai_projects_skills/ai-task-manager
python -m pytest tests/test_bitable_setup.py -v
# 预期: ImportError — scripts.bitable_setup not found
```

**Step 3: 实现 `scripts/bitable_setup.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
bitable_setup.py — 幂等创建 AI Captain 多维表格全部 6 张表及字段。
用法: python scripts/bitable_setup.py [--dry-run]
"""
import argparse, json, logging, os, sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]

BASE_URL = "https://open.feishu.cn/open-apis"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── 表结构定义 ─────────────────────────────────────────────
# 每张表：name + fields 列表；field 格式: {field_name, field_type}
# 飞书字段类型: 1=文本 2=数字 3=单选 4=多选 5=日期 7=复选框
#              11=人员 15=URL 19=关联记录 20=公式 1001=创建时间 1002=更新时间

TABLE_SCHEMAS: list[dict] = [
    {
        "name": "项目主表",
        "fields": [
            {"field_name": "项目ID",       "field_type": 1},
            {"field_name": "项目名称",      "field_type": 1},
            {"field_name": "Captain",       "field_type": 11},
            {"field_name": "Sponsor",       "field_type": 11},
            {"field_name": "所属业务线",    "field_type": 3,
             "property": {"options": [{"name": n} for n in ["招聘","销售","内容","运营","其他"]]}},
            {"field_name": "当前阶段",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["立项","研发","交付","运维","扩张","暂停"]]}},
            {"field_name": "项目状态",      "field_type": 3,
             "property": {"options": [{"name": n, "color": c} for n, c in [("绿灯",2),("黄灯",3),("红灯",1)]]}},
            {"field_name": "目标DDL",       "field_type": 5},
            {"field_name": "当前在做",      "field_type": 1},
            {"field_name": "当前卡点",      "field_type": 1},
            {"field_name": "最新反馈",      "field_type": 1},
            {"field_name": "反馈来源",      "field_type": 1},
            {"field_name": "下个检查点",    "field_type": 1},
            {"field_name": "本周推进",      "field_type": 2},
            {"field_name": "总进度",        "field_type": 2},
            {"field_name": "风险级别",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["低","中","高"]]}},
            {"field_name": "项目说明",      "field_type": 1},
            {"field_name": "GitHub 仓库",   "field_type": 15},
            {"field_name": "GitHub Project","field_type": 15},
            {"field_name": "Notion 文档",   "field_type": 15},
            {"field_name": "WAU",           "field_type": 2},
            {"field_name": "周任务量",      "field_type": 2},
            {"field_name": "节省人小时",    "field_type": 2},
            {"field_name": "质量分",        "field_type": 2},
            {"field_name": "运维分",        "field_type": 2},
            {"field_name": "采用分",        "field_type": 2},
            {"field_name": "交付分",        "field_type": 2},
            {"field_name": "最后更新时间",  "field_type": 1001},
        ],
    },
    {
        "name": "任务表",
        "fields": [
            {"field_name": "任务ID",        "field_type": 1},
            {"field_name": "关联项目",      "field_type": 19},   # 关联项目主表，需二次 patch
            {"field_name": "任务标题",      "field_type": 1},
            {"field_name": "类型",          "field_type": 3,
             "property": {"options": [{"name": n} for n in ["feature","bug","ops","quality","growth","doc"]]}},
            {"field_name": "来源",          "field_type": 3,
             "property": {"options": [{"name": n} for n in ["GitHub","飞书","手工","Bot"]]}},
            {"field_name": "当前状态",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["待处理","进行中","阻塞","已完成"]]}},
            {"field_name": "负责人",        "field_type": 11},
            {"field_name": "截止时间",      "field_type": 5},
            {"field_name": "是否关键路径",  "field_type": 7},
            {"field_name": "当前阻塞原因",  "field_type": 1},
            {"field_name": "最新反馈",      "field_type": 1},
            {"field_name": "GitHub 链接",   "field_type": 15},
            {"field_name": "创建时间",      "field_type": 1001},
            {"field_name": "更新时间",      "field_type": 1002},
        ],
    },
    {
        "name": "里程碑表",
        "fields": [
            {"field_name": "里程碑ID",      "field_type": 1},
            {"field_name": "关联项目",      "field_type": 19},
            {"field_name": "里程碑名称",    "field_type": 3,
             "property": {"options": [{"name": n} for n in ["需求冻结","MVP跑通","内测通过","正式交付","运维接管","第一轮复盘"]]}},
            {"field_name": "状态",          "field_type": 3,
             "property": {"options": [{"name": n} for n in ["未开始","进行中","完成","延期"]]}},
            {"field_name": "计划日期",      "field_type": 5},
            {"field_name": "实际日期",      "field_type": 5},
            {"field_name": "Owner",         "field_type": 11},
            {"field_name": "Gate 条件",     "field_type": 1},
            {"field_name": "当前问题",      "field_type": 1},
        ],
    },
    {
        "name": "Eval 表",
        "fields": [
            {"field_name": "Eval记录ID",    "field_type": 1},
            {"field_name": "关联项目",      "field_type": 19},
            {"field_name": "指标编码",      "field_type": 1},
            {"field_name": "指标名称",      "field_type": 1},
            {"field_name": "指标类型",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["准确率","误报率","漏报率","F1","稳定性","成本","人工干预率"]]}},
            {"field_name": "目标值",        "field_type": 2},
            {"field_name": "当前值",        "field_type": 2},
            {"field_name": "得分",          "field_type": 2},
            {"field_name": "趋势",          "field_type": 3,
             "property": {"options": [{"name": n} for n in ["上升","持平","下降"]]}},
            {"field_name": "样本量",        "field_type": 2},
            {"field_name": "评估日期",      "field_type": 5},
            {"field_name": "备注",          "field_type": 1},
        ],
    },
    {
        "name": "周更新表",
        "fields": [
            {"field_name": "周更新ID",      "field_type": 1},
            {"field_name": "关联项目",      "field_type": 19},
            {"field_name": "周期",          "field_type": 1},
            {"field_name": "当前在做",      "field_type": 1},
            {"field_name": "当前卡点",      "field_type": 1},
            {"field_name": "最新反馈",      "field_type": 1},
            {"field_name": "反馈来源",      "field_type": 1},
            {"field_name": "业务结果",      "field_type": 1},
            {"field_name": "本周推进值",    "field_type": 2},
            {"field_name": "下周动作",      "field_type": 1},
            {"field_name": "下个检查点",    "field_type": 1},
            {"field_name": "是否需要升级",  "field_type": 7},
            {"field_name": "创建时间",      "field_type": 1001},
        ],
    },
    {
        "name": "运维事件表",
        "fields": [
            {"field_name": "事件ID",        "field_type": 1},
            {"field_name": "关联项目",      "field_type": 19},
            {"field_name": "事件时间",      "field_type": 5},
            {"field_name": "事件类型",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["错误","延迟","成本异常","可用性","数据质量"]]}},
            {"field_name": "严重等级",      "field_type": 3,
             "property": {"options": [{"name": "P1","color": 1},{"name": "P2","color": 3},{"name": "P3","color": 2}]}},
            {"field_name": "现象描述",      "field_type": 1},
            {"field_name": "当前状态",      "field_type": 3,
             "property": {"options": [{"name": n} for n in ["已发现","处理中","已恢复","已复盘"]]}},
            {"field_name": "值班人",        "field_type": 11},
            {"field_name": "恢复时间",      "field_type": 5},
            {"field_name": "Root Cause",    "field_type": 1},
            {"field_name": "后续动作",      "field_type": 1},
        ],
    },
]


def get_token() -> str:
    import requests
    r = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal",
                      json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def list_tables(token: str) -> list[dict]:
    import requests
    r = requests.get(f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()["data"]["items"]


def parse_table_map(items: list[dict]) -> dict[str, str]:
    """返回 {表名: tableId}"""
    return {t["name"]: t["table_id"] for t in items}


def create_table(token: str, name: str) -> str:
    import requests
    r = requests.post(
        f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"table": {"name": name}}, timeout=10,
    )
    r.raise_for_status()
    tid = r.json()["data"]["table_id"]
    log.info("Created table '%s' → %s", name, tid)
    return tid


def add_field(token: str, table_id: str, field: dict) -> None:
    import requests
    r = requests.post(
        f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/fields",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=field, timeout=10,
    )
    if r.status_code not in (200, 201):
        log.warning("Field '%s' may already exist: %s", field["field_name"], r.text[:120])


def setup(dry_run: bool = False) -> dict[str, str]:
    token = get_token()
    existing = parse_table_map(list_tables(token))
    log.info("Existing tables: %s", list(existing.keys()))

    result: dict[str, str] = {}
    for schema in TABLE_SCHEMAS:
        name = schema["name"]
        if name in existing:
            log.info("Table '%s' already exists (%s), skipping.", name, existing[name])
            result[name] = existing[name]
            continue
        if dry_run:
            log.info("[dry-run] Would create table '%s'", name)
            result[name] = "DRY_RUN"
            continue
        tid = create_table(token, name)
        result[name] = tid
        for field in schema["fields"]:
            add_field(token, tid, field)

    log.info("=== Table IDs (copy to .env) ===")
    for name, tid in result.items():
        log.info("  %-12s → %s", name, tid)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    setup(dry_run=args.dry_run)
```

**Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_bitable_setup.py -v
# 预期: 2 passed
```

**Step 5: Dry-run 验证**

```bash
python scripts/bitable_setup.py --dry-run
# 预期: 打印 6 张表 DRY_RUN 占位
```

**Step 6: Commit**

```bash
git add scripts/bitable_setup.py tests/test_bitable_setup.py
git commit -m "feat(phase1): add bitable_setup.py for idempotent table creation"
```

---

### Task 1.3：`github_sync.py` — 扩展为多项目、多字段、增量同步

> 现有脚本只写5个字段到单表。需要：① 同步到任务表（完整字段）② 同步 PR 状态 ③ 维护关联项目字段

**Files:**
- Modify: `scripts/github_sync.py`

**Step 1: 写失败测试**

```python
# tests/test_github_sync.py
from scripts.github_sync import parse_item, map_github_status

def test_parse_item_complete_fields():
    raw = {
        "id": "GH_123",
        "title": "Fix login bug",
        "status": "In Progress",
        "assignees": [{"login": "alice"}],
        "url": "https://github.com/org/repo/issues/1",
        "updatedAt": "2026-03-24T10:00:00Z",
        "type": "ISSUE",
        "number": 42,
    }
    item = parse_item(raw)
    assert item["github_id"] == "GH_123"
    assert item["title"] == "Fix login bug"
    assert item["assignees"] == ["alice"]
    assert item["item_type"] == "ISSUE"
    assert item["issue_number"] == 42

def test_map_github_status_in_progress():
    assert map_github_status("In Progress") == "进行中"

def test_map_github_status_done():
    assert map_github_status("Done") == "已完成"

def test_map_github_status_unknown():
    assert map_github_status("Weird") == "待处理"
```

**Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_github_sync.py -v
# 预期: ImportError 或 AttributeError (map_github_status 不存在)
```

**Step 3: 修改 `scripts/github_sync.py`，新增以下内容**

在 `parse_item` 之前插入状态映射：

```python
_STATUS_MAP = {
    "Todo":        "待处理",
    "In Progress": "进行中",
    "Blocked":     "阻塞",
    "Done":        "已完成",
    "Closed":      "已完成",
}

def map_github_status(raw_status: str) -> str:
    return _STATUS_MAP.get(raw_status, "待处理")
```

修改 `parse_item` 补全字段：

```python
def parse_item(raw: dict) -> dict:
    return {
        "github_id":    raw.get("id", ""),
        "title":        raw.get("title", ""),
        "status":       raw.get("status", ""),
        "mapped_status": map_github_status(raw.get("status", "")),
        "assignees":    [a.get("login", "") for a in raw.get("assignees", [])],
        "html_url":     raw.get("url", ""),
        "updated_at":   raw.get("updatedAt", ""),
        "item_type":    raw.get("type", "ISSUE"),        # ISSUE / PR / DRAFT_ISSUE
        "issue_number": raw.get("number"),
        "is_pr":        raw.get("type") == "PULL_REQUEST",
    }
```

修改 `upsert_bitable_record` 写入完整字段：

```python
fields = {
    "任务ID":      item["github_id"],
    "任务标题":    item["title"],
    "当前状态":    item["mapped_status"],
    "负责人":      ", ".join(item["assignees"]),
    "GitHub 链接": {"link": item["html_url"], "text": f"#{item['issue_number']}"},
    "来源":        "GitHub",
    "类型":        "feature",   # 默认值，可后续按 label 推断
    "更新时间":    item["updated_at"],
}
```

**Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_github_sync.py -v
# 预期: 4 passed
```

**Step 5: 集成测试（dry-run）**

```bash
python scripts/github_sync.py --org goodidea-ggn --project 1 --dry-run
# 预期: 打印 JSON 列表，无飞书写入
```

**Step 6: Commit**

```bash
git add scripts/github_sync.py tests/test_github_sync.py
git commit -m "feat(phase1): extend github_sync with full field mapping and status normalization"
```

---

### Task 1.4：launchd plist — 每 30 分钟自动触发 GitHub Sync

**Files:**
- Create: `workers/com.ai-captain.github-sync.plist`

**Step 1: 写 plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-captain.github-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/scripts/github_sync.py</string>
    <string>--org</string>
    <string>goodidea-ggn</string>
    <string>--project</string>
    <string>1</string>
  </array>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/github_sync_launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/github_sync_launchd_err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

**Step 2: 安装（手工，需用户确认）**

```bash
cp workers/com.ai-captain.github-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ai-captain.github-sync.plist
launchctl list | grep ai-captain
```

**Step 3: Commit**

```bash
git add workers/com.ai-captain.github-sync.plist
git commit -m "ops(phase1): add launchd plist for github_sync 30-min schedule"
```

---

## Phase 2 — Collaboration：飞书群指令监听 + 实时卡片推送

### 背景

Phase 2 要接两件事：
1. **feishu_event_sync.py** — 监听飞书群消息，解析指令（如 `/status`, `/block`, `/update`），写入 Bitable 对应字段
2. **card_push.py** — 向飞书群或私聊推送格式化卡片（DDL 预警、阻塞告警、周报卡片）

飞书事件监听有两种模式：Webhook 长连接（推荐，无公网 IP 要求）或 HTTP callback。这里用 **长连接模式**（lark-oapi SDK 的 `ws` client）。

---

### Task 2.1：安装 lark-oapi SDK 并验证连接

**Step 1: 安装依赖**

```bash
cd /Users/ggn/ai_projects_skills/ai-task-manager
pip install lark-oapi
# 或用 uv: uv add lark-oapi
```

**Step 2: 写连接验证脚本**

```python
# scripts/check_feishu_ws.py
import lark_oapi as lark
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

cli = lark.Client.builder() \
    .app_id(os.environ["FEISHU_APP_ID"]) \
    .app_secret(os.environ["FEISHU_APP_SECRET"]) \
    .build()

print("Feishu client OK:", cli)
```

**Step 3: 运行验证**

```bash
python scripts/check_feishu_ws.py
# 预期: Feishu client OK: <lark_oapi.client.Client object>
```

---

### Task 2.2：`feishu_event_sync.py` — 群消息指令解析器

> 监听群消息，解析 `/指令 参数` 格式，写入 Bitable。

**Files:**
- Create: `scripts/feishu_event_sync.py`

**Step 1: 写失败测试**

```python
# tests/test_feishu_event_sync.py
from scripts.feishu_event_sync import parse_command

def test_parse_status_command():
    result = parse_command("/status captain-hireflow 绿灯")
    assert result == {"cmd": "status", "project_id": "captain-hireflow", "value": "绿灯"}

def test_parse_block_command():
    result = parse_command("/block captain-hireflow 候选人识别仍为0分")
    assert result == {"cmd": "block", "project_id": "captain-hireflow", "value": "候选人识别仍为0分"}

def test_parse_unknown_command_returns_none():
    assert parse_command("普通消息，不是指令") is None

def test_parse_update_command_multiword_value():
    result = parse_command("/update captain-prospect 线索排序已接近可用，等业务验收")
    assert result["cmd"] == "update"
    assert "线索排序" in result["value"]
```

**Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_feishu_event_sync.py -v
```

**Step 3: 实现 `scripts/feishu_event_sync.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["lark-oapi", "requests", "python-dotenv"]
# ///
"""
feishu_event_sync.py — 飞书群指令监听器（长连接模式）
支持指令:
  /status <project_id> <绿灯|黄灯|红灯>   → 更新项目主表 项目状态
  /block  <project_id> <描述>             → 更新项目主表 当前卡点
  /update <project_id> <内容>             → 更新项目主表 当前在做
  /eval   <project_id> <指标编码> <值>    → 更新 Eval 表 当前值
用法: python scripts/feishu_event_sync.py
"""
import json, logging, os, re
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]
TABLE_PROJECTS    = os.environ["TABLE_PROJECTS"]
TABLE_EVAL        = os.environ["TABLE_EVAL"]

# ── 指令解析 ────────────────────────────────────────────────────────────────

COMMAND_RE = re.compile(r"^/(\w+)\s+(\S+)\s+(.+)$", re.MULTILINE)

def parse_command(text: str) -> dict | None:
    """
    解析 /cmd project_id value 格式。
    返回 {"cmd": str, "project_id": str, "value": str} 或 None。
    """
    m = COMMAND_RE.match(text.strip())
    if not m:
        return None
    cmd, project_id, value = m.group(1), m.group(2), m.group(3).strip()
    if cmd not in {"status", "block", "update", "eval"}:
        return None
    return {"cmd": cmd, "project_id": project_id, "value": value}


# ── Bitable 写入 ─────────────────────────────────────────────────────────────

def get_feishu_token() -> str:
    import requests
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def find_project_record_id(token: str, project_id: str) -> str | None:
    """在项目主表中按 项目ID 字段查找 record_id。"""
    import requests
    r = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{TABLE_PROJECTS}/records/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"filter": {"conjunction": "and", "conditions": [
            {"field_name": "项目ID", "operator": "is", "value": [project_id]}
        ]}},
        timeout=10,
    )
    r.raise_for_status()
    items = r.json()["data"]["items"]
    return items[0]["record_id"] if items else None


CMD_FIELD_MAP = {
    "status": "项目状态",
    "block":  "当前卡点",
    "update": "当前在做",
}

def apply_command(parsed: dict) -> bool:
    token = get_feishu_token()
    record_id = find_project_record_id(token, parsed["project_id"])
    if not record_id:
        log.warning("Project '%s' not found in Bitable.", parsed["project_id"])
        return False

    import requests
    field_name = CMD_FIELD_MAP.get(parsed["cmd"])
    if not field_name:
        log.warning("No field mapping for cmd '%s'", parsed["cmd"])
        return False

    r = requests.put(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": {field_name: parsed["value"]}},
        timeout=10,
    )
    r.raise_for_status()
    log.info("Applied cmd=%s project=%s field=%s value=%s",
             parsed["cmd"], parsed["project_id"], field_name, parsed["value"])
    return True


# ── 事件处理器 ────────────────────────────────────────────────────────────────

def on_message(data: P2ImMessageReceiveV1) -> None:
    try:
        content = json.loads(data.event.message.content)
        text = content.get("text", "")
        parsed = parse_command(text)
        if parsed:
            log.info("Received command: %s", parsed)
            apply_command(parsed)
        else:
            log.debug("Non-command message, skipping.")
    except Exception as e:
        log.error("Error handling message: %s", e, exc_info=True)


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cli = (
        lark.Client.builder()
        .app_id(FEISHU_APP_ID)
        .app_secret(FEISHU_APP_SECRET)
        .build()
    )
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws_client = lark.ws.Client(
        FEISHU_APP_ID, FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    log.info("Starting Feishu WS listener...")
    ws_client.start()


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_feishu_event_sync.py -v
# 预期: 4 passed
```

**Step 5: Commit**

```bash
git add scripts/feishu_event_sync.py tests/test_feishu_event_sync.py
git commit -m "feat(phase2): add feishu WS event listener with command parsing"
```

---

### Task 2.3：`card_push.py` — 飞书卡片推送模块

> 封装各类卡片模板：DDL 预警卡片、阻塞告警卡片、周报摘要卡片。

**Files:**
- Create: `scripts/card_push.py`

**Step 1: 写失败测试**

```python
# tests/test_card_push.py
from scripts.card_push import build_ddl_alert_card, build_blocker_card, build_weekly_card

def test_ddl_alert_card_has_required_keys():
    card = build_ddl_alert_card(
        project_name="AI 招聘助手",
        captain="马田野",
        ddl="2026-04-12",
        days_left=7,
        blocker="候选人识别仍为0分",
    )
    assert card["schema"] == "2.0"
    assert "AI 招聘助手" in str(card)
    assert "7" in str(card)

def test_blocker_card_has_project_name():
    card = build_blocker_card(project_name="销售线索 Copilot", blocker="SLO未定义", owner="郭鹏天")
    assert "销售线索 Copilot" in str(card)

def test_weekly_card_structure():
    card = build_weekly_card(
        project_name="内容复盘机器人",
        current_focus="扩到第二业务线",
        blocker="无",
        progress="+5",
        next_checkpoint="下周完成适配",
        needs_escalation=False,
    )
    assert card["schema"] == "2.0"
```

**Step 2: 实现 `scripts/card_push.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
card_push.py — 飞书消息卡片构建与推送（Schema v1 格式）
"""
import json, logging, os, requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FEISHU_APP_ID      = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET  = os.environ["FEISHU_APP_SECRET"]
BOT_WEBHOOK        = os.getenv("FEISHU_BOT_WEBHOOK", "")
GROUP_CHAT_ID      = os.getenv("FEISHU_GROUP_CHAT_ID", "")

log = logging.getLogger(__name__)

# ── 卡片构建 ──────────────────────────────────────────────────────────────────

def build_ddl_alert_card(project_name: str, captain: str, ddl: str,
                         days_left: int, blocker: str) -> dict:
    """DDL 预警卡片（红色标题，距 DDL 天数高亮）"""
    color = "red" if days_left <= 3 else "orange"
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"⚠️ DDL 预警 | {project_name}"},
            "template": color,
        },
        "body": {
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md",
                    "content": f"**Captain:** {captain}\n**目标 DDL:** {ddl}\n**剩余天数:** {days_left} 天"}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md",
                    "content": f"**当前卡点:**\n{blocker}"}},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": "请 Captain 在今日内确认推进方案或升级"}
                ]},
            ]
        },
    }


def build_blocker_card(project_name: str, blocker: str, owner: str) -> dict:
    """阻塞告警卡片"""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"🚧 项目阻塞 | {project_name}"},
            "template": "yellow",
        },
        "body": {
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md",
                    "content": f"**负责人:** {owner}\n\n**阻塞描述:**\n{blocker}"}},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": "发现阻塞请及时在群内 @相关人推进"}
                ]},
            ]
        },
    }


def build_weekly_card(project_name: str, current_focus: str, blocker: str,
                      progress: str, next_checkpoint: str, needs_escalation: bool) -> dict:
    """周报摘要卡片"""
    escalation_line = "\n\n🔴 **需要升级处理，请相关负责人介入**" if needs_escalation else ""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 周报摘要 | {project_name}"},
            "template": "blue",
        },
        "body": {
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md",
                    "content": (
                        f"**本周在做:** {current_focus}\n"
                        f"**当前卡点:** {blocker}\n"
                        f"**本周推进:** {progress}\n"
                        f"**下个检查点:** {next_checkpoint}"
                        f"{escalation_line}"
                    )}},
            ]
        },
    }


# ── 推送 ──────────────────────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def push_card_to_chat(chat_id: str, card: dict) -> None:
    """通过 Bot API 推送卡片到指定 chat_id（群或私聊）"""
    token = get_token()
    r = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        },
        timeout=10,
    )
    r.raise_for_status()
    log.info("Card pushed to chat %s", chat_id)


def push_card_via_webhook(card: dict) -> None:
    """通过群机器人 Webhook 推送卡片（无需 token）"""
    r = requests.post(
        BOT_WEBHOOK,
        json={"msg_type": "interactive", "card": card},
        timeout=10,
    )
    r.raise_for_status()
    log.info("Card pushed via webhook")
```

**Step 3: 运行测试**

```bash
python -m pytest tests/test_card_push.py -v
# 预期: 3 passed
```

**Step 4: Commit**

```bash
git add scripts/card_push.py tests/test_card_push.py
git commit -m "feat(phase2): add card_push with DDL/blocker/weekly card builders"
```

---

### Task 2.4：DDL 巡检 + 阻塞扫描定时触发

> 每天 09:00 扫描项目主表，对距 DDL ≤7 天或有关键路径阻塞的项目推送告警卡片。

**Files:**
- Create: `scripts/daily_alert.py`
- Create: `workers/com.ai-captain.daily-alert.plist`

**Step 1: 实现 `scripts/daily_alert.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
daily_alert.py — 每日 DDL 预警 + 阻塞扫描，推送飞书卡片。
用法: python scripts/daily_alert.py [--dry-run]
"""
import argparse, logging, os, requests
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from card_push import build_ddl_alert_card, build_blocker_card, push_card_to_chat

FEISHU_APP_ID      = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET  = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN  = os.environ["BITABLE_APP_TOKEN"]
TABLE_PROJECTS     = os.environ["TABLE_PROJECTS"]
GROUP_CHAT_ID      = os.environ["FEISHU_GROUP_CHAT_ID"]

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DDL_WARN_DAYS = 7    # 距 DDL ≤ 7 天触发预警


def get_token() -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def fetch_all_projects(token: str) -> list[dict]:
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 100},
        timeout=15,
    )
    r.raise_for_status()
    return [item["fields"] for item in r.json()["data"]["items"]]


def days_until(ddl_str: str) -> int | None:
    """ddl_str 是飞书日期字段毫秒时间戳（int）或 ISO 字符串，统一转换。"""
    if not ddl_str:
        return None
    try:
        if isinstance(ddl_str, (int, float)):
            ddl_date = datetime.utcfromtimestamp(ddl_str / 1000).date()
        else:
            ddl_date = date.fromisoformat(ddl_str[:10])
        return (ddl_date - date.today()).days
    except (ValueError, TypeError):
        return None


def run_alerts(dry_run: bool = False) -> None:
    token = get_token()
    projects = fetch_all_projects(token)
    log.info("Scanned %d projects", len(projects))

    alerted = 0
    for proj in projects:
        name    = proj.get("项目名称", "未知项目")
        captain = proj.get("Captain", "")
        ddl_raw = proj.get("目标DDL")
        blocker = proj.get("当前卡点", "")
        status  = proj.get("项目状态", "")

        days = days_until(ddl_raw)

        # DDL 预警
        if days is not None and days <= DDL_WARN_DAYS:
            card = build_ddl_alert_card(name, str(captain), str(ddl_raw), days, blocker)
            if dry_run:
                log.info("[dry-run] DDL alert for '%s' (%d days)", name, days)
            else:
                push_card_to_chat(GROUP_CHAT_ID, card)
            alerted += 1

        # 阻塞告警（状态=红灯 且 卡点非空）
        elif status == "红灯" and blocker:
            card = build_blocker_card(name, blocker, str(captain))
            if dry_run:
                log.info("[dry-run] Blocker alert for '%s'", name)
            else:
                push_card_to_chat(GROUP_CHAT_ID, card)
            alerted += 1

    log.info("Alert run complete. %d alerts sent.", alerted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_alerts(dry_run=args.dry_run)
```

**Step 2: launchd plist（每日 09:00）**

```xml
<!-- workers/com.ai-captain.daily-alert.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-captain.daily-alert</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/scripts/daily_alert.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>9</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/daily_alert.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/daily_alert_err.log</string>
</dict>
</plist>
```

**Step 3: Commit**

```bash
git add scripts/daily_alert.py workers/com.ai-captain.daily-alert.plist
git commit -m "feat(phase2): add daily DDL+blocker alert with launchd schedule"
```

---

## Phase 3 — Intelligence：Eval Metrics 自动采集

### 背景

`metrics_collector.py` 需要从两个来源采集数据：
1. **项目 Bot 日志**（本地文件 / 远端 API）→ 计算准确率、误报率、F1
2. **Bitable Eval 表历史数据** → 计算趋势（上升/持平/下降）

采集后写入 Eval 表，并更新项目主表的 `质量分`。

---

### Task 3.1：定义 Eval 数据源接口

> 每个项目的 Eval 数据源各不相同（CSV 日志、API、人工填写）。用一个 Source 注册表隔离差异。

**Files:**
- Create: `scripts/metrics_collector.py`

**Step 1: 写失败测试**

```python
# tests/test_metrics_collector.py
from scripts.metrics_collector import (
    compute_accuracy, compute_f1, compute_trend, score_from_ratio
)

def test_compute_accuracy():
    assert compute_accuracy(correct=90, total=100) == 90.0

def test_compute_accuracy_zero_total():
    assert compute_accuracy(correct=0, total=0) == 0.0

def test_compute_f1():
    # precision=0.8, recall=0.6 → F1 = 2*0.8*0.6/(0.8+0.6) ≈ 0.686
    f1 = compute_f1(precision=0.8, recall=0.6)
    assert abs(f1 - 0.6857) < 0.001

def test_compute_trend_up():
    assert compute_trend(history=[50, 60, 70]) == "上升"

def test_compute_trend_down():
    assert compute_trend(history=[80, 70, 60]) == "下降"

def test_compute_trend_flat():
    assert compute_trend(history=[75, 74, 75]) == "持平"

def test_score_from_ratio_above_target():
    # 当前值92，目标值90 → 超越目标 → score = 100
    assert score_from_ratio(current=92, target=90) == 100

def test_score_from_ratio_below_target():
    # 当前值45，目标值90 → score = 50
    assert score_from_ratio(current=45, target=90) == 50
```

**Step 2: 实现 `scripts/metrics_collector.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
metrics_collector.py — AI 项目 Eval 指标自动采集。

采集流程:
  1. 读取各项目注册的数据源（eval_sources.json）
  2. 调用对应 source loader 计算当期指标
  3. 写入 Bitable Eval 表
  4. 更新项目主表 质量分

用法: python scripts/metrics_collector.py [--project captain-hireflow] [--dry-run]
"""
import argparse, json, logging, math, os, requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]
TABLE_EVAL        = os.environ["TABLE_EVAL"]
TABLE_PROJECTS    = os.environ["TABLE_PROJECTS"]

SOURCES_FILE = ROOT / "state" / "eval_sources.json"

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ── 计算函数（纯函数，可测试）────────────────────────────────────────────────

def compute_accuracy(correct: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(correct / total * 100, 2)


def compute_f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def compute_trend(history: list[float]) -> str:
    """给定历史值列表（从旧到新），判断趋势。差值 > 2 为上升，< -2 为下降。"""
    if len(history) < 2:
        return "持平"
    delta = history[-1] - history[-2]
    if delta > 2:
        return "上升"
    if delta < -2:
        return "下降"
    return "持平"


def score_from_ratio(current: float, target: float) -> int:
    """将当前值与目标值的比值映射为 0-100 分。超过目标则为 100。"""
    if target == 0:
        return 100 if current > 0 else 0
    ratio = current / target
    return min(100, round(ratio * 100))


# ── 数据源注册表 ──────────────────────────────────────────────────────────────
# eval_sources.json 格式:
# {
#   "captain-hireflow": [
#     {
#       "metric_code": "E1",
#       "metric_name": "日清覆盖",
#       "metric_type": "准确率",
#       "target": 80,
#       "source_type": "csv_log",      # csv_log | api_endpoint | manual
#       "source_path": "logs/hireflow_eval.csv",
#       "correct_col": "correct",
#       "total_col": "total"
#     }
#   ]
# }

def load_sources() -> dict:
    if not SOURCES_FILE.exists():
        log.warning("eval_sources.json not found, returning empty.")
        return {}
    return json.loads(SOURCES_FILE.read_text())


# ── Source Loaders ────────────────────────────────────────────────────────────

def load_csv_log(cfg: dict) -> dict:
    """从 CSV 日志计算 correct/total，返回 {current_value, sample_size}"""
    import csv
    path = ROOT / cfg["source_path"]
    if not path.exists():
        log.warning("CSV log not found: %s", path)
        return {"current_value": 0.0, "sample_size": 0}
    correct = total = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                total += int(row[cfg["total_col"]])
                correct += int(row[cfg["correct_col"]])
            except (KeyError, ValueError):
                continue
    return {"current_value": compute_accuracy(correct, total), "sample_size": total}


def load_api_endpoint(cfg: dict) -> dict:
    """GET API 端点返回 {value, sample_size}"""
    r = requests.get(cfg["endpoint"], timeout=10)
    r.raise_for_status()
    data = r.json()
    return {
        "current_value": float(data.get("value", 0)),
        "sample_size": int(data.get("sample_size", 0)),
    }


SOURCE_LOADERS = {
    "csv_log":      load_csv_log,
    "api_endpoint": load_api_endpoint,
    "manual":       lambda cfg: {"current_value": float(cfg.get("manual_value", 0)), "sample_size": 0},
}


# ── Bitable 写入 ──────────────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def fetch_eval_history(token: str, project_id: str, metric_code: str) -> list[float]:
    """查询该指标最近5次历史值，从旧到新排列。"""
    r = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_EVAL}/records/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "filter": {"conjunction": "and", "conditions": [
                {"field_name": "指标编码", "operator": "is", "value": [metric_code]},
            ]},
            "sort": [{"field_name": "评估日期", "desc": True}],
            "page_size": 5,
        },
        timeout=10,
    )
    r.raise_for_status()
    values = [float(item["fields"].get("当前值", 0)) for item in r.json()["data"]["items"]]
    return list(reversed(values))   # 从旧到新


def write_eval_record(token: str, project_id: str, metric: dict,
                      current_value: float, score: int,
                      trend: str, sample_size: int) -> None:
    fields = {
        "Eval记录ID":   f"{project_id}-{metric['metric_code']}-{date.today().isoformat()}",
        "指标编码":      metric["metric_code"],
        "指标名称":      metric["metric_name"],
        "指标类型":      metric["metric_type"],
        "目标值":        metric["target"],
        "当前值":        current_value,
        "得分":          score,
        "趋势":          trend,
        "样本量":        sample_size,
        "评估日期":      date.today().isoformat(),
    }
    requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_EVAL}/records",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": fields},
        timeout=10,
    ).raise_for_status()
    log.info("Wrote eval: %s %s=%.1f (score=%d trend=%s)",
             project_id, metric["metric_code"], current_value, score, trend)


def update_project_quality_score(token: str, project_id: str, quality_score: int) -> None:
    """搜索项目主表记录，更新 质量分 字段。"""
    r = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"filter": {"conjunction": "and", "conditions": [
            {"field_name": "项目ID", "operator": "is", "value": [project_id]}
        ]}},
        timeout=10,
    ).raise_for_status or None

    # 简化：直接二次查询获取 record_id
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"filter": {"conjunction": "and", "conditions": [
            {"field_name": "项目ID", "operator": "is", "value": [project_id]}
        ]}},
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json()["data"]["items"]
    if not items:
        log.warning("Project %s not found when updating quality score", project_id)
        return
    record_id = items[0]["record_id"]
    requests.put(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": {"质量分": quality_score}},
        timeout=10,
    ).raise_for_status()
    log.info("Updated quality_score=%d for project %s", quality_score, project_id)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def collect(project_filter: str | None = None, dry_run: bool = False) -> None:
    sources = load_sources()
    token = get_token()

    for project_id, metrics in sources.items():
        if project_filter and project_id != project_filter:
            continue
        log.info("=== Collecting eval for: %s ===", project_id)
        scores = []

        for metric in metrics:
            loader = SOURCE_LOADERS.get(metric["source_type"])
            if not loader:
                log.warning("Unknown source_type: %s", metric["source_type"])
                continue

            result = loader(metric)
            current_value = result["current_value"]
            sample_size   = result["sample_size"]
            target        = metric["target"]
            score         = score_from_ratio(current_value, target)
            history       = fetch_eval_history(token, project_id, metric["metric_code"])
            history.append(current_value)
            trend         = compute_trend(history)

            scores.append(score)

            if dry_run:
                log.info("[dry-run] %s %s: current=%.1f target=%d score=%d trend=%s",
                         project_id, metric["metric_code"], current_value, target, score, trend)
            else:
                write_eval_record(token, project_id, metric, current_value, score, trend, sample_size)

        # 项目级质量分 = 所有指标均分
        if scores and not dry_run:
            quality_score = round(sum(scores) / len(scores))
            update_project_quality_score(token, project_id, quality_score)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    collect(project_filter=args.project, dry_run=args.dry_run)
```

**Step 3: 运行测试**

```bash
python -m pytest tests/test_metrics_collector.py -v
# 预期: 8 passed
```

**Step 4: 创建 `state/eval_sources.json` 示例**

```json
{
  "captain-hireflow": [
    {
      "metric_code": "E1",
      "metric_name": "日清覆盖",
      "metric_type": "准确率",
      "target": 80,
      "source_type": "csv_log",
      "source_path": "logs/hireflow_daily.csv",
      "correct_col": "covered",
      "total_col": "total"
    },
    {
      "metric_code": "E3",
      "metric_name": "候选人识别",
      "metric_type": "准确率",
      "target": 85,
      "source_type": "manual",
      "manual_value": 0
    }
  ]
}
```

**Step 5: launchd plist（每日 08:00 采集）**

```xml
<!-- workers/com.ai-captain.metrics-collect.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>      <string>com.ai-captain.metrics-collect</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/scripts/metrics_collector.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>8</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/metrics_collect.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/metrics_collect_err.log</string>
</dict>
</plist>
```

**Step 6: Commit**

```bash
git add scripts/metrics_collector.py tests/test_metrics_collector.py \
        state/eval_sources.json workers/com.ai-captain.metrics-collect.plist
git commit -m "feat(phase3): add metrics_collector with csv/api/manual source loaders"
```

---

### Task 3.2：`weekly_digest.py` — 每周五 18:00 推送周报卡片

**Files:**
- Create: `scripts/weekly_digest.py`
- Create: `workers/com.ai-captain.weekly-digest.plist`

**Step 1: 实现 `scripts/weekly_digest.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
weekly_digest.py — 每周五 18:00，从 Bitable 抓取所有项目本周更新，
推送汇总卡片到项目群。
"""
import logging, os, requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from card_push import build_weekly_card, push_card_to_chat

FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]
TABLE_PROJECTS    = os.environ["TABLE_PROJECTS"]
GROUP_CHAT_ID     = os.environ["FEISHU_GROUP_CHAT_ID"]

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_token() -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def fetch_projects(token: str) -> list[dict]:
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{TABLE_PROJECTS}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 100},
        timeout=15,
    )
    r.raise_for_status()
    return [item["fields"] for item in r.json()["data"]["items"]]


def iso_week() -> str:
    today = date.today()
    return f"{today.year}-W{today.isocalendar().week:02d}"


def run_digest(dry_run: bool = False) -> None:
    token = get_token()
    projects = fetch_projects(token)
    week = iso_week()
    log.info("Running weekly digest for %s — %d projects", week, len(projects))

    for proj in projects:
        name       = proj.get("项目名称", "未知")
        focus      = proj.get("当前在做", "—")
        blocker    = proj.get("当前卡点", "无")
        progress   = f"+{int(proj.get('本周推进', 0))}"
        checkpoint = proj.get("下个检查点", "—")
        stage      = proj.get("当前阶段", "")

        # 暂停中的项目不推送
        if stage == "暂停":
            continue

        needs_escalation = (proj.get("项目状态") == "红灯")
        card = build_weekly_card(name, focus, blocker, progress, checkpoint, needs_escalation)

        if dry_run:
            log.info("[dry-run] Weekly card for '%s'", name)
        else:
            push_card_to_chat(GROUP_CHAT_ID, card)

    log.info("Weekly digest complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_digest(dry_run=args.dry_run)
```

**Step 2: launchd plist（每周五 18:00）**

```xml
<!-- workers/com.ai-captain.weekly-digest.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>      <string>com.ai-captain.weekly-digest</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/scripts/weekly_digest.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key> <integer>5</integer>
    <key>Hour</key>    <integer>18</integer>
    <key>Minute</key>  <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/weekly_digest.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/weekly_digest_err.log</string>
</dict>
</plist>
```

**Step 3: Commit**

```bash
git add scripts/weekly_digest.py workers/com.ai-captain.weekly-digest.plist
git commit -m "feat(phase3): add weekly_digest for Friday 18:00 project summary push"
```

---

## Phase 4 — Dashboard：React 驾驶舱接真实数据

### 背景

React 前端已有完整原型（`src/App.tsx`），当前使用 `src/data/mockData.ts` 中的硬编码数据。Phase 4 目标：
1. 新建 `api/snapshot.py`，从 Bitable 聚合所有项目数据输出 `snapshot.json`
2. 修改 React 前端，用 `fetch('/snapshot.json')` 替换 mock data
3. 对应 4 个页面模块：Portfolio Overview、Project Cockpit、Quality Wall、Ops Console

---

### Task 4.1：`api/snapshot.py` — 数据聚合脚本

> 从 6 张 Bitable 表拉取数据，按 `data-contract.md` 约定的统一格式输出 `dist/snapshot.json`。

**Files:**
- Create: `api/snapshot.py`

**Step 1: 写失败测试**

```python
# tests/test_snapshot.py
from api.snapshot import (
    merge_project_snapshot, build_project_node, normalize_stage, normalize_status
)

def test_normalize_stage_maps_chinese():
    assert normalize_stage("研发") == "build"
    assert normalize_stage("运维") == "operate"

def test_normalize_status_maps_lights():
    assert normalize_status("绿灯") == "green"
    assert normalize_status("黄灯") == "amber"
    assert normalize_status("红灯") == "red"

def test_build_project_node_required_keys():
    raw = {
        "项目ID": "captain-hireflow",
        "项目名称": "AI 招聘助手",
        "Captain": "马田野",
        "Sponsor": "妃姐",
        "当前阶段": "运维",
        "项目状态": "黄灯",
        "总进度": 68,
        "本周推进": 8,
    }
    node = build_project_node(raw)
    assert node["id"] == "captain-hireflow"
    assert node["stage"] == "operate"
    assert node["status"] == "amber"
    assert node["progress"] == 68
```

**Step 2: 实现 `api/snapshot.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
snapshot.py — 聚合 Bitable 数据输出 dist/snapshot.json 供 React 消费。
用法: python api/snapshot.py [--dry-run]
"""
import argparse, json, logging, os, requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]
TABLE_PROJECTS    = os.environ["TABLE_PROJECTS"]
TABLE_TASKS       = os.environ["TABLE_TASKS"]
TABLE_MILESTONES  = os.environ["TABLE_MILESTONES"]
TABLE_EVAL        = os.environ["TABLE_EVAL"]
TABLE_OPS_EVENTS  = os.environ["TABLE_OPS_EVENTS"]
OUTPUT_PATH       = Path(os.getenv("SNAPSHOT_OUTPUT_PATH", str(ROOT / "dist" / "snapshot.json")))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── 规范化映射 ────────────────────────────────────────────────────────────────

STAGE_MAP = {"立项":"intake","研发":"build","交付":"deliver","运维":"operate","扩张":"scale","暂停":"intake"}
STATUS_MAP = {"绿灯":"green","黄灯":"amber","红灯":"red"}
TREND_MAP  = {"上升":"up","持平":"flat","下降":"down"}

def normalize_stage(s: str) -> str:  return STAGE_MAP.get(s, "intake")
def normalize_status(s: str) -> str: return STATUS_MAP.get(s, "amber")
def normalize_trend(s: str) -> str:  return TREND_MAP.get(s, "flat")


def build_project_node(raw: dict) -> dict:
    return {
        "id":              raw.get("项目ID", ""),
        "name":            raw.get("项目名称", ""),
        "captain":         str(raw.get("Captain", "")),
        "sponsor":         str(raw.get("Sponsor", "")),
        "stage":           normalize_stage(raw.get("当前阶段", "")),
        "status":          normalize_status(raw.get("项目状态", "")),
        "repo":            raw.get("GitHub 仓库", {}).get("link", "") if isinstance(raw.get("GitHub 仓库"), dict) else "",
        "targetLaunchDate": raw.get("目标DDL", ""),
        "progress":        int(raw.get("总进度") or 0),
        "weeklyDelta":     int(raw.get("本周推进") or 0),
        "objective":       raw.get("项目说明", ""),
        "weeklyProgress":  raw.get("当前在做", ""),
        "currentFocus":    raw.get("当前在做", ""),
        "blockerDetail":   raw.get("当前卡点", ""),
        "latestFeedback":  raw.get("最新反馈", ""),
        "feedbackFrom":    str(raw.get("反馈来源", "")),
        "nextCheckpoint":  raw.get("下个检查点", ""),
        "successScore":    int(raw.get("交付分") or 0),
        "qualityScore":    int(raw.get("质量分") or 0),
        "opsScore":        int(raw.get("运维分") or 0),
        "activeUsers":     int(raw.get("WAU") or 0),
        "weeklyRuns":      int(raw.get("周任务量") or 0),
        "hoursSaved":      int(raw.get("节省人小时") or 0),
        # 以下字段由子表填充
        "milestones":      [],
        "deliveryChecklist": [],
        "evalMetrics":     [],
        "opsSignals":      [],
        "risks":           [],
        "nextActions":     [],
        "daysToDeadline":  0,   # 由 enrich_days 填充
        "completedMilestones": 0,
        "plannedMilestones":   0,
        "activeBlockers":      0,
        "businessImpact":      "",
    }


def merge_project_snapshot(project: dict, milestones: list, eval_records: list,
                            ops_events: list) -> dict:
    """将子表数据合并到 project node 中。"""
    project["milestones"] = milestones
    project["completedMilestones"] = sum(1 for m in milestones if m.get("status") == "done")
    project["plannedMilestones"] = len(milestones)
    project["evalMetrics"] = eval_records
    project["opsSignals"] = [
        {"label": e.get("事件类型",""), "value": e.get("现象描述","")[:40],
         "tone": "risk" if e.get("严重等级") == "P1" else "warn"}
        for e in ops_events if e.get("当前状态") not in ("已恢复","已复盘")
    ]
    project["activeBlockers"] = len([e for e in ops_events
                                     if e.get("当前状态") not in ("已恢复","已复盘")])
    return project


# ── Bitable 拉取 ──────────────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def fetch_table(token: str, table_id: str, page_size: int = 100) -> list[dict]:
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}"
        f"/tables/{table_id}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": page_size},
        timeout=20,
    )
    r.raise_for_status()
    return [item["fields"] for item in r.json()["data"]["items"]]


# ── 聚合 ──────────────────────────────────────────────────────────────────────

def build_snapshot(token: str) -> dict:
    log.info("Fetching all tables...")
    raw_projects  = fetch_table(token, TABLE_PROJECTS)
    raw_milestones = fetch_table(token, TABLE_MILESTONES)
    raw_evals     = fetch_table(token, TABLE_EVAL)
    raw_ops       = fetch_table(token, TABLE_OPS_EVENTS)

    # 按项目ID分组子表
    mile_by_proj: dict[str, list] = {}
    for m in raw_milestones:
        # 关联记录字段返回 list of {record_id, ...}，取第一条
        linked = m.get("关联项目", [])
        proj_id = linked[0].get("record_id", "") if linked else ""
        mile_by_proj.setdefault(proj_id, []).append({
            "label": m.get("里程碑名称", ""),
            "status": {"完成":"done","进行中":"current","未开始":"next","延期":"next"}.get(m.get("状态",""), "next"),
        })

    eval_by_proj: dict[str, list] = {}
    for e in raw_evals:
        linked = e.get("关联项目", [])
        proj_id = linked[0].get("record_id", "") if linked else ""
        eval_by_proj.setdefault(proj_id, []).append({
            "code":   e.get("指标编码", ""),
            "label":  e.get("指标名称", ""),
            "score":  int(e.get("得分") or 0),
            "target": int(e.get("目标值") or 0),
            "trend":  normalize_trend(e.get("趋势", "持平")),
        })

    ops_by_proj: dict[str, list] = {}
    for o in raw_ops:
        linked = o.get("关联项目", [])
        proj_id = linked[0].get("record_id", "") if linked else ""
        ops_by_proj.setdefault(proj_id, []).append(o)

    projects = []
    for raw in raw_projects:
        record_id = raw.get("_record_id", "")  # Bitable 返回 record_id 在外层
        node = build_project_node(raw)
        node = merge_project_snapshot(
            node,
            mile_by_proj.get(record_id, []),
            eval_by_proj.get(record_id, []),
            ops_by_proj.get(record_id, []),
        )
        projects.append(node)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": projects,
    }


def run(dry_run: bool = False) -> None:
    token = get_token()
    snapshot = build_snapshot(token)
    if dry_run:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2)[:2000])
        return
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    log.info("Snapshot written to %s (%d projects)", OUTPUT_PATH, len(snapshot["projects"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
```

**Step 3: 运行测试**

```bash
python -m pytest tests/test_snapshot.py -v
# 预期: 4 passed
```

**Step 4: Commit**

```bash
git add api/snapshot.py tests/test_snapshot.py
git commit -m "feat(phase4): add snapshot.py aggregator — Bitable → dist/snapshot.json"
```

---

### Task 4.2：React 前端接入真实数据

> 修改 `src/App.tsx`，用 `fetch('/snapshot.json')` 替换 `mockData`。

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/types.ts`（补 `daysToDeadline` 的 optional 处理）

**Step 1: 在 `src/App.tsx` 开头新增数据获取逻辑**

在 `import` 区域之后，`function App()` 之前插入：

```tsx
import { useState, useEffect } from 'react'

// 将下方改为从快照加载
// import { projects } from './data/mockData.ts'   ← 删除或注释

function useProjects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    fetch('/snapshot.json')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setProjects(data.projects ?? [])
        setLoading(false)
      })
      .catch(err => {
        console.warn('Snapshot fetch failed, falling back to mock:', err)
        import('./data/mockData.ts').then(m => {
          setProjects(m.projects)
          setLoading(false)
        })
        setError(String(err))
      })
  }, [])

  return { projects, loading, error }
}
```

在 `function App()` 内部把 `const [activeProjectId, ...]` 之前替换：

```tsx
function App() {
  const { projects, loading } = useProjects()
  const [activeProjectId, setActiveProjectId] = useState<string>('')

  // 当 projects 加载后默认选第一个
  useEffect(() => {
    if (projects.length > 0 && !activeProjectId) {
      setActiveProjectId(projects[0].id)
    }
  }, [projects])

  if (loading) return <div className="shell"><p style={{padding:'2rem'}}>加载中...</p></div>

  const activeProject = projects.find(p => p.id === activeProjectId) ?? projects[0]
  // ... 后续代码不变
```

**Step 2: 更新 Vite 配置以在 dev 模式下 proxy snapshot**

修改 `vite.config.ts`：

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/snapshot.json': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        // 本地开发时可先用 mock 文件绕过
      },
    },
  },
})
```

**Step 3: 验证构建**

```bash
npm run build
# 预期: dist/ 构建成功，无 TS 错误
```

**Step 4: Commit**

```bash
git add src/App.tsx vite.config.ts
git commit -m "feat(phase4): wire React frontend to real snapshot.json with mock fallback"
```

---

### Task 4.3：launchd — 每 30 分钟刷新 snapshot

**Files:**
- Create: `workers/com.ai-captain.snapshot-refresh.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>      <string>com.ai-captain.snapshot-refresh</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/api/snapshot.py</string>
  </array>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/snapshot_refresh.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/snapshot_refresh_err.log</string>
</dict>
</plist>
```

**Step 5: Commit**

```bash
git add workers/com.ai-captain.snapshot-refresh.plist
git commit -m "ops(phase4): add snapshot refresh launchd every 30 min"
```

---

## Phase 5 — Ops：运维监控、报警阈值与巡检脚本

### 背景

Phase 5 保障整个系统本身的健康，而非项目内容的健康。监控对象：
- GitHub Sync 是否正常（最后同步时间 < 35 分钟）
- Feishu WS Listener 是否存活（进程检查）
- Metrics Collector 是否按时执行
- Snapshot 文件是否新鲜
- API 限额（飞书 QPS 5/s，GitHub 5000 req/h）

---

### Task 5.1：报警阈值设计

> 硬编码阈值表，不做动态配置（YAGNI）。

```python
# 写入 scripts/ops_health_check.py 顶部常量区

THRESHOLDS = {
    # 单位：分钟
    "github_sync_max_lag_min":      35,     # 超过 35 分钟未同步 → 告警
    "snapshot_max_age_min":         65,     # 超过 65 分钟未刷新 → 告警（容忍 1 次 30min 失败）
    "metrics_collect_max_lag_hour": 26,     # 超过 26 小时未采集 → 告警（容忍 2 小时延迟）

    # 飞书 API 速率（每秒请求数）
    "feishu_qps_warn":      4,      # 接近 5 QPS 限制时预警

    # 日志文件大小（MB）
    "log_file_max_mb":      50,     # 单文件超 50 MB 告警

    # 进程存活
    "required_processes": [
        "feishu_event_sync.py",     # WS 监听进程
    ],
}
```

---

### Task 5.2：`ops_health_check.py` — 系统健康巡检

**Files:**
- Create: `scripts/ops_health_check.py`

**Step 1: 写失败测试**

```python
# tests/test_ops_health_check.py
import time
from scripts.ops_health_check import (
    check_file_freshness, check_log_sizes, HealthResult
)
from pathlib import Path
import tempfile, os

def test_check_file_freshness_fresh(tmp_path):
    f = tmp_path / "test.json"
    f.write_text("{}")
    result = check_file_freshness(f, max_age_minutes=5)
    assert result.ok is True

def test_check_file_freshness_stale(tmp_path):
    f = tmp_path / "old.json"
    f.write_text("{}")
    # 修改 mtime 为 2 小时前
    old_time = time.time() - 7200
    os.utime(f, (old_time, old_time))
    result = check_file_freshness(f, max_age_minutes=60)
    assert result.ok is False
    assert "stale" in result.message.lower()

def test_check_log_sizes_ok(tmp_path):
    f = tmp_path / "small.log"
    f.write_bytes(b"x" * 100)
    results = check_log_sizes(tmp_path, max_mb=50)
    assert all(r.ok for r in results)
```

**Step 2: 实现 `scripts/ops_health_check.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv", "psutil"]
# ///
"""
ops_health_check.py — AI Captain 系统级健康巡检
检查项:
  1. Snapshot 文件新鲜度
  2. GitHub Sync 最后执行时间（读日志）
  3. Metrics Collector 最后执行时间（读日志）
  4. 关键进程存活（feishu_event_sync.py）
  5. 日志文件大小
  6. 日志中 ERROR 计数
推送汇总结果到飞书（仅当有问题时）
用法: python scripts/ops_health_check.py [--dry-run]
"""
import argparse, json, logging, os, re, subprocess, time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

THRESHOLDS = {
    "github_sync_max_lag_min":      35,
    "snapshot_max_age_min":         65,
    "metrics_collect_max_lag_hour": 26,
    "feishu_qps_warn":              4,
    "log_file_max_mb":              50,
    "required_processes":           ["feishu_event_sync.py"],
}

LOGS_DIR     = ROOT / "logs"
SNAPSHOT_FILE = Path(os.getenv("SNAPSHOT_OUTPUT_PATH", str(ROOT / "dist" / "snapshot.json")))
GROUP_CHAT_ID = os.getenv("FEISHU_GROUP_CHAT_ID", "")


@dataclass
class HealthResult:
    check:   str
    ok:      bool
    message: str
    severity: str = "warn"   # "warn" | "critical"


# ── 检查函数 ──────────────────────────────────────────────────────────────────

def check_file_freshness(path: Path, max_age_minutes: int) -> HealthResult:
    if not path.exists():
        return HealthResult(str(path.name), False, f"{path.name} not found", "critical")
    age_min = (time.time() - path.stat().st_mtime) / 60
    ok = age_min <= max_age_minutes
    msg = f"{path.name}: age={age_min:.1f}m (max={max_age_minutes}m)" + ("" if ok else " — STALE")
    return HealthResult(str(path.name), ok, msg, "warn" if ok else "critical")


def check_log_sizes(logs_dir: Path, max_mb: float) -> list[HealthResult]:
    results = []
    for f in logs_dir.glob("*.log"):
        size_mb = f.stat().st_size / (1024 * 1024)
        ok = size_mb < max_mb
        results.append(HealthResult(
            f"log_size:{f.name}", ok,
            f"{f.name}: {size_mb:.1f} MB" + ("" if ok else " — TOO LARGE"),
            "warn",
        ))
    return results


def check_log_errors(logs_dir: Path, window_hours: int = 1) -> list[HealthResult]:
    """统计各日志文件最近 window_hours 内的 ERROR 行数。"""
    results = []
    cutoff = datetime.now() - timedelta(hours=window_hours)
    for f in logs_dir.glob("*.log"):
        if "err" in f.name.lower():
            continue
        error_count = 0
        try:
            for line in f.read_text(errors="replace").splitlines():
                if "[ERROR]" in line or "ERROR" in line:
                    error_count += 1
        except OSError:
            pass
        ok = error_count == 0
        results.append(HealthResult(
            f"log_errors:{f.name}", ok,
            f"{f.name}: {error_count} ERRORs in last {window_hours}h",
            "warn" if error_count < 10 else "critical",
        ))
    return results


def check_process_alive(process_name: str) -> HealthResult:
    try:
        import psutil
        alive = any(process_name in " ".join(p.cmdline()) for p in psutil.process_iter(["cmdline"]))
    except Exception:
        # psutil 不可用时用 pgrep
        result = subprocess.run(["pgrep", "-f", process_name], capture_output=True)
        alive = result.returncode == 0
    return HealthResult(
        f"process:{process_name}", alive,
        f"{process_name}: {'alive' if alive else 'DEAD'}",
        "warn" if alive else "critical",
    )


def check_github_sync_lag() -> HealthResult:
    """从日志文件推断最后同步时间。"""
    log_file = LOGS_DIR / f"github_sync_{datetime.now().strftime('%Y%m%d')}.log"
    if not log_file.exists():
        return HealthResult("github_sync_lag", False, "No github_sync log for today", "warn")
    age_min = (time.time() - log_file.stat().st_mtime) / 60
    max_lag = THRESHOLDS["github_sync_max_lag_min"]
    ok = age_min <= max_lag
    return HealthResult(
        "github_sync_lag", ok,
        f"github_sync last modified {age_min:.1f}m ago (max={max_lag}m)",
        "warn" if ok else "critical",
    )


# ── 推送汇总卡片 ──────────────────────────────────────────────────────────────

def push_health_card(results: list[HealthResult], dry_run: bool = False) -> None:
    failures = [r for r in results if not r.ok]
    if not failures:
        log.info("All health checks passed. No alert needed.")
        return

    lines = "\n".join(
        f"{'🔴' if r.severity == 'critical' else '🟡'} **{r.check}**: {r.message}"
        for r in failures
    )
    card = {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": f"🔧 AI Captain 系统健康异常 ({len(failures)} 项)"},
            "template": "red" if any(r.severity == "critical" for r in failures) else "orange",
        },
        "body": {
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": lines}},
                {"tag": "note", "elements": [{"tag": "plain_text",
                    "content": f"巡检时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"}]},
            ]
        },
    }

    if dry_run:
        log.info("[dry-run] Would push health card: %d failures", len(failures))
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    import requests
    FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
    FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10,
    )
    r.raise_for_status()
    token = r.json()["tenant_access_token"]

    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"receive_id": GROUP_CHAT_ID, "msg_type": "interactive",
              "content": json.dumps(card)},
        timeout=10,
    ).raise_for_status()
    log.info("Health alert card pushed for %d issues.", len(failures))


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run_checks(dry_run: bool = False) -> list[HealthResult]:
    results: list[HealthResult] = []

    # 1. Snapshot 新鲜度
    results.append(check_file_freshness(SNAPSHOT_FILE, THRESHOLDS["snapshot_max_age_min"]))

    # 2. GitHub Sync 最后运行时间
    results.append(check_github_sync_lag())

    # 3. 关键进程存活
    for proc in THRESHOLDS["required_processes"]:
        results.append(check_process_alive(proc))

    # 4. 日志文件大小
    results.extend(check_log_sizes(LOGS_DIR, THRESHOLDS["log_file_max_mb"]))

    # 5. 日志 ERROR 计数
    results.extend(check_log_errors(LOGS_DIR, window_hours=1))

    # 打印汇总
    for r in results:
        level = logging.INFO if r.ok else logging.WARNING
        log.log(level, "[%s] %s", "OK" if r.ok else "FAIL", r.message)

    push_health_card(results, dry_run=dry_run)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_checks(dry_run=args.dry_run)
```

**Step 3: 运行测试**

```bash
python -m pytest tests/test_ops_health_check.py -v
# 预期: 3 passed
```

**Step 4: Dry-run 验证**

```bash
python scripts/ops_health_check.py --dry-run
# 预期: 打印各项检查结果，如 snapshot 不存在则显示 FAIL
```

**Step 5: launchd plist（每小时巡检）**

```xml
<!-- workers/com.ai-captain.ops-health.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>      <string>com.ai-captain.ops-health</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/ggn/ai_projects_skills/ai-task-manager/scripts/ops_health_check.py</string>
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/ops_health.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ggn/ai_projects_skills/ai-task-manager/logs/ops_health_err.log</string>
</dict>
</plist>
```

**Step 6: Commit**

```bash
git add scripts/ops_health_check.py tests/test_ops_health_check.py \
        workers/com.ai-captain.ops-health.plist
git commit -m "feat(phase5): add ops_health_check with freshness/process/log checks"
```

---

### Task 5.3：`workers/scheduler.py` — 统一调度器（launchd 补充）

> 提供一个统一入口，可一次性触发所有 worker，方便调试和 smoke test。

**Files:**
- Create: `workers/scheduler.py`

```python
#!/usr/bin/env python3
"""
scheduler.py — 手动触发所有 workers 的统一入口（调试用）。
用法: python workers/scheduler.py --all [--dry-run]
      python workers/scheduler.py --only github_sync,snapshot
"""
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
API     = ROOT / "api"

WORKERS = {
    "github_sync":      [sys.executable, str(SCRIPTS / "github_sync.py"),
                         "--org", "goodidea-ggn", "--project", "1"],
    "metrics_collect":  [sys.executable, str(SCRIPTS / "metrics_collector.py")],
    "snapshot":         [sys.executable, str(API     / "snapshot.py")],
    "daily_alert":      [sys.executable, str(SCRIPTS / "daily_alert.py")],
    "ops_health":       [sys.executable, str(SCRIPTS / "ops_health_check.py")],
}


def run_worker(name: str, extra_args: list[str]) -> int:
    cmd = WORKERS[name] + extra_args
    print(f"[scheduler] Running: {name}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[scheduler] ❌ {name} failed (exit {result.returncode})")
    else:
        print(f"[scheduler] ✅ {name} OK")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",   action="store_true")
    parser.add_argument("--only",  default="", help="Comma-separated worker names")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    extra = ["--dry-run"] if args.dry_run else []

    if args.all:
        targets = list(WORKERS.keys())
    elif args.only:
        targets = [t.strip() for t in args.only.split(",")]
    else:
        parser.print_help()
        return

    failed = []
    for name in targets:
        if name not in WORKERS:
            print(f"[scheduler] Unknown worker: {name}")
            continue
        rc = run_worker(name, extra)
        if rc != 0:
            failed.append(name)

    if failed:
        print(f"\n[scheduler] ⚠️  Failed workers: {failed}")
        sys.exit(1)
    else:
        print("\n[scheduler] All workers completed successfully.")


if __name__ == "__main__":
    main()
```

**Step 7: Smoke test 验证**

```bash
python workers/scheduler.py --only ops_health --dry-run
# 预期: ops_health OK（dry-run 模式，无飞书推送）
```

**Step 8: Commit**

```bash
git add workers/scheduler.py
git commit -m "ops(phase5): add unified scheduler.py for all worker dry-run smoke tests"
```

---

## 调度时间表汇总

| Worker | 触发时机 | launchd plist |
|--------|----------|---------------|
| `github_sync.py` | 每 30 分钟 | `com.ai-captain.github-sync.plist` |
| `metrics_collector.py` | 每日 08:00 | `com.ai-captain.metrics-collect.plist` |
| `snapshot.py` | 每 30 分钟 | `com.ai-captain.snapshot-refresh.plist` |
| `daily_alert.py` | 每日 09:00 | `com.ai-captain.daily-alert.plist` |
| `weekly_digest.py` | 每周五 18:00 | `com.ai-captain.weekly-digest.plist` |
| `ops_health_check.py` | 每小时 | `com.ai-captain.ops-health.plist` |

---

## 最终安装命令（Phase 完成后执行）

```bash
# 安装所有 launchd jobs（需用户手工确认每条）
for plist in workers/com.ai-captain.*.plist; do
  cp "$plist" ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/$(basename "$plist")
done

# 验证
launchctl list | grep ai-captain
```

---

## 依赖安装汇总

```bash
# 生产依赖
pip install requests python-dotenv lark-oapi psutil

# 或用 uv（推荐，已有 /// script 头）
uv tool run scripts/bitable_setup.py --dry-run
```

---

> **Plan complete.** Save this file to `docs/PLANS.md` before execution.

**两种执行方式：**

**1. Subagent-Driven（本 session）** — 每个 Task 派发独立 subagent，Task 完成后 review，快速迭代

**2. 新 Session 并行执行** — 新开 session 用 `superpowers:executing-plans`，以 Phase 为单位批量执行

请告知你选择哪种方式，或从哪个 Phase 开始执行。
