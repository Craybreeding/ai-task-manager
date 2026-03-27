#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["lark-oapi", "python-dotenv"]
# ///
"""
github_sync.py — Sync-G 模块
从 GitHub Projects 拉取卡片，同步到飞书多维表格 任务表。

依赖:
    pip install lark-oapi python-dotenv
    gh CLI 已登录 (gh auth status)

用法:
    python scripts/github_sync.py --org <org> --project <project_number> --project-id <飞书项目ID>
    python scripts/github_sync.py --org goodidea-ggn --project 1 --project-id captain-hireflow --dry-run
    python scripts/github_sync.py --org goodidea-ggn --project 1 --project-id captain-hireflow --issues-only
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 路径 & 配置
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"
STATE_FILE = ROOT / "state" / "github_sync_state.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"github_sync_{datetime.now().strftime('%Y%m%d')}.log"

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 加载飞书配置
# ---------------------------------------------------------------------------

def load_setup() -> dict:
    data = json.loads(SETUP_FILE.read_text())
    return {
        "app_token": data["app_token"],
        "table_id": data["tables"]["任务表"],
    }


# ---------------------------------------------------------------------------
# 飞书客户端
# ---------------------------------------------------------------------------

def build_client():
    import lark_oapi as lark
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET are required.")
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


# ---------------------------------------------------------------------------
# GitHub: 通过 gh CLI 拉取 Project 卡片
# ---------------------------------------------------------------------------

def fetch_github_project_items(org: str, project_number: int) -> list[dict]:
    """用 gh project item-list 拉取所有卡片，返回原始 JSON 列表。"""
    cmd = [
        "gh", "project", "item-list", str(project_number),
        "--owner", org,
        "--format", "json",
        "--limit", "500",
    ]
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    items = data.get("items", [])
    log.info("Fetched %d items from GitHub project #%s", len(items), project_number)
    return items


def fetch_github_issues(org: str, repo: str) -> list[dict]:
    """用 gh issue list 拉取仓库所有 issue（含 PR）。"""
    cmd = [
        "gh", "issue", "list",
        "--repo", f"{org}/{repo}",
        "--state", "all",
        "--json", "number,title,state,assignees,url,updatedAt,labels,milestone,closedAt",
        "--limit", "500",
    ]
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    items = json.loads(result.stdout)
    log.info("Fetched %d issues from %s/%s", len(items), org, repo)
    return items


# ---------------------------------------------------------------------------
# 字段映射
# ---------------------------------------------------------------------------

# GitHub status -> 飞书 当前状态
STATUS_MAP = {
    "Todo":        "待处理",
    "In Progress": "进行中",
    "Done":        "已完成",
    "Blocked":     "阻塞",
    "OPEN":        "待处理",
    "CLOSED":      "已完成",
    "open":        "待处理",
    "closed":      "已完成",
}

# GitHub label -> 飞书 类型
TYPE_LABELS = {
    "bug":      "bug",
    "feature":  "feature",
    "ops":      "ops",
    "quality":  "quality",
    "doc":      "doc",
    "growth":   "growth",
}


def detect_type(labels: list[str]) -> str:
    for label in labels:
        t = TYPE_LABELS.get(label.lower())
        if t:
            return t
    return "feature"  # 默认


def to_ts_ms(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        # ISO 8601: 2026-03-24T12:00:00Z
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def parse_project_item(raw: dict, feishu_project_id: str) -> dict:
    """将 gh project item-list 返回的卡片映射为飞书任务表字段。"""
    github_id = raw.get("id", "")
    content = raw.get("content", {}) or {}

    # assignees 是字符串列表
    assignees = raw.get("assignees", [])
    assignees = [a if isinstance(a, str) else a.get("login", "") for a in assignees]

    raw_status = raw.get("status", "") or ""
    status = STATUS_MAP.get(raw_status, "待处理")

    # labels 在 content 里
    labels = [lbl.get("name", "") if isinstance(lbl, dict) else str(lbl)
              for lbl in (content.get("labels", []) or [])]
    task_type = detect_type(labels)

    url = content.get("url") or raw.get("url", "")
    updated_ts = to_ts_ms(raw.get("updatedAt") or content.get("updatedAt"))

    return {
        "_github_id": github_id,
        "fields": {
            "任务ID":    f"gh-{github_id}",
            "关联项目ID": feishu_project_id,
            "任务标题":   raw.get("title", "") or content.get("title", ""),
            "类型":       task_type,
            "来源":       "GitHub",
            "当前状态":   status,
            "负责人":     ", ".join(assignees),
            "GitHub 链接": url,
            **({"更新时间": updated_ts} if updated_ts else {}),
        },
    }


def parse_issue(raw: dict, feishu_project_id: str) -> dict:
    """将 gh issue list 返回的 issue 映射为飞书任务表字段。"""
    number = raw.get("number", 0)
    github_id = f"issue-{number}"
    assignees = [a.get("login", "") for a in raw.get("assignees", [])]
    raw_state = raw.get("state", "open")
    status = STATUS_MAP.get(raw_state.upper(), "待处理")

    labels = [lbl.get("name", "") for lbl in raw.get("labels", [])]
    task_type = detect_type(labels)

    milestone = raw.get("milestone") or {}
    due_ts = to_ts_ms(milestone.get("dueOn"))
    updated_ts = to_ts_ms(raw.get("updatedAt"))

    return {
        "_github_id": github_id,
        "fields": {
            "任务ID":    f"gh-{github_id}",
            "关联项目ID": feishu_project_id,
            "任务标题":   raw.get("title", ""),
            "类型":       task_type,
            "来源":       "GitHub",
            "当前状态":   status,
            "负责人":     ", ".join(assignees),
            "GitHub 链接": raw.get("url", ""),
            **({"截止时间": due_ts} if due_ts else {}),
            **({"更新时间": updated_ts} if updated_ts else {}),
        },
    }


# ---------------------------------------------------------------------------
# 状态管理：github_id -> bitable record_id
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 飞书 Bitable 写入
# ---------------------------------------------------------------------------

def upsert_record(client, app_token: str, table_id: str, fields: dict, existing_record_id: str | None) -> str:
    import lark_oapi as lark

    record = lark.bitable.v1.AppTableRecord.builder().fields(fields).build()

    if existing_record_id:
        request = (
            lark.bitable.v1.UpdateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(existing_record_id)
            .request_body(record)
            .build()
        )
        resp = client.bitable.v1.app_table_record.update(request)
        if not resp.success():
            raise RuntimeError(f"Update failed: {resp.code} {resp.msg}")
        return existing_record_id
    else:
        request = (
            lark.bitable.v1.CreateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .request_body(record)
            .build()
        )
        resp = client.bitable.v1.app_table_record.create(request)
        if not resp.success():
            raise RuntimeError(f"Create failed: {resp.code} {resp.msg}")
        return resp.data.record.record_id


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def sync(
    org: str,
    project_number: int | None,
    feishu_project_id: str,
    repo: str | None = None,
    dry_run: bool = False,
) -> None:
    log.info(
        "=== Sync-G started (org=%s project=%s repo=%s feishu_project_id=%s dry_run=%s) ===",
        org, project_number, repo, feishu_project_id, dry_run,
    )

    # 1. 拉取 GitHub 数据
    parsed: list[dict] = []

    if project_number is not None:
        raw_items = fetch_github_project_items(org, project_number)
        parsed = [parse_project_item(r, feishu_project_id) for r in raw_items]

    if repo:
        raw_issues = fetch_github_issues(org, repo)
        issue_parsed = [parse_issue(r, feishu_project_id) for r in raw_issues]
        # 去重（project 里已有的 issue 可能重复，按 github_id 合并）
        existing_ids = {p["_github_id"] for p in parsed}
        for ip in issue_parsed:
            if ip["_github_id"] not in existing_ids:
                parsed.append(ip)

    if not parsed:
        log.warning("No items fetched. Check --org/--project/--repo args.")
        return

    if dry_run:
        log.info("[dry-run] Would upsert %d records. Skipping Feishu writes.", len(parsed))
        for p in parsed:
            print(json.dumps(p["fields"], ensure_ascii=False, indent=2))
        return

    # 2. 加载配置和状态
    setup = load_setup()
    app_token = setup["app_token"]
    table_id = setup["table_id"]
    state = load_state()

    # 3. 构建飞书客户端
    client = build_client()

    # 4. 逐条 upsert
    ok, fail = 0, 0
    for p in parsed:
        github_id = p["_github_id"]
        existing_record_id = state.get(github_id)
        try:
            record_id = upsert_record(client, app_token, table_id, p["fields"], existing_record_id)
            state[github_id] = record_id
            ok += 1
            log.info("Upserted [%s] -> record %s", github_id, record_id)
        except Exception as e:
            log.error("Failed [%s]: %s", github_id, e)
            fail += 1

    # 5. 持久化状态
    save_state(state)
    log.info("=== Sync-G finished. ok=%d fail=%d ===", ok, fail)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync-G: GitHub -> Feishu Bitable 任务表")
    parser.add_argument("--org",        required=True,              help="GitHub org or username")
    parser.add_argument("--project",    type=int, default=None,     help="GitHub project number (可选)")
    parser.add_argument("--repo",       default=None,               help="GitHub repo name，用于同步 Issues（可选）")
    parser.add_argument("--project-id", required=True,              help="飞书 关联项目ID，例如 captain-hireflow")
    parser.add_argument("--dry-run",    action="store_true",        help="只打印，不写飞书")
    args = parser.parse_args()

    if args.project is None and args.repo is None:
        parser.error("至少提供 --project 或 --repo 中的一个")

    sync(
        org=args.org,
        project_number=args.project,
        feishu_project_id=args.project_id,
        repo=args.repo,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
