#!/usr/bin/env python3
"""
setup_real_projects.py
1. 清空飞书 项目主表 / 任务表 的现有记录
2. 从 GitHub 读取 7 个真实 Project，写入 项目主表
3. 同步每个 Project 的 items 到 任务表
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import lark_oapi as lark

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"
STATE_FILE = ROOT / "state" / "github_sync_state.json"

GITHUB_ORG = "goodidea-ggn"

# GitHub project number -> 飞书项目ID（slug）
PROJECT_ID_MAP = {
    1: "ggn-workspace-agent",
    2: "ggn-workspace-frontend",
    3: "strategy-chat",
    4: "tech-assistant",
    5: "xingtu-selector",
    6: "draft-audit",
    8: "yuntu-datapicker",
}

STATUS_MAP = {
    "Todo":        "待处理",
    "In Progress": "进行中",
    "In review":   "进行中",
    "Done":        "已完成",
    "Blocked":     "阻塞",
    "OPEN":        "待处理",
    "CLOSED":      "已完成",
    "open":        "待处理",
    "closed":      "已完成",
}

TYPE_LABELS = {"bug": "bug", "feature": "feature", "ops": "ops",
               "quality": "quality", "doc": "doc", "growth": "growth"}


def detect_type(labels: list[str]) -> str:
    for lbl in labels:
        t = TYPE_LABELS.get(lbl.lower())
        if t:
            return t
    return "feature"


def to_ts_ms(date_str: str | None) -> int | None:
    if not date_str:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 飞书客户端
# ---------------------------------------------------------------------------

def build_client() -> lark.Client:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET are required.")
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.ERROR)
        .build()
    )


def load_setup() -> dict:
    return json.loads(SETUP_FILE.read_text())


# ---------------------------------------------------------------------------
# 清空表
# ---------------------------------------------------------------------------

def list_all_record_ids(cli: lark.Client, app_token: str, table_id: str) -> list[str]:
    ids = []
    page_token = None
    while True:
        req_builder = (
            lark.bitable.v1.ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(500)
        )
        if page_token:
            req_builder.page_token(page_token)
        resp = cli.bitable.v1.app_table_record.list(req_builder.build())
        if not resp.success():
            raise RuntimeError(f"List failed: {resp.code} {resp.msg}")
        items = resp.data.items or []
        ids.extend(r.record_id for r in items)
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return ids


def clear_table(cli: lark.Client, app_token: str, table_id: str, name: str) -> None:
    ids = list_all_record_ids(cli, app_token, table_id)
    if not ids:
        print(f"  {name}: 已空，跳过")
        return
    # 批量删除，每次最多 500
    for i in range(0, len(ids), 500):
        batch = ids[i:i+500]
        req = (
            lark.bitable.v1.BatchDeleteAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .request_body(
                lark.bitable.v1.BatchDeleteAppTableRecordRequestBody.builder()
                .records(batch)
                .build()
            )
            .build()
        )
        resp = cli.bitable.v1.app_table_record.batch_delete(req)
        if not resp.success():
            raise RuntimeError(f"Delete failed: {resp.code} {resp.msg}")
    print(f"  {name}: 已删除 {len(ids)} 条")


# ---------------------------------------------------------------------------
# 写入记录
# ---------------------------------------------------------------------------

def batch_create(cli: lark.Client, app_token: str, table_id: str, rows: list[dict]) -> list[str]:
    records = [lark.bitable.v1.AppTableRecord.builder().fields(r).build() for r in rows]
    req = (
        lark.bitable.v1.BatchCreateAppTableRecordRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .request_body(
            lark.bitable.v1.BatchCreateAppTableRecordRequestBody.builder()
            .records(records)
            .build()
        )
        .build()
    )
    resp = cli.bitable.v1.app_table_record.batch_create(req)
    if not resp.success():
        raise RuntimeError(f"BatchCreate failed: {resp.code} {resp.msg}")
    return [r.record_id for r in (resp.data.records or [])]


# ---------------------------------------------------------------------------
# GitHub 数据
# ---------------------------------------------------------------------------

def fetch_github_projects() -> list[dict]:
    result = subprocess.run(
        ["gh", "project", "list", "--owner", GITHUB_ORG, "--format", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["projects"]


GQL_ITEMS_QUERY = """
query($org: String!, $number: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            ... on Issue {
              title url assignees(first:10){ nodes{ login } }
              author { login }
              labels(first:5){ nodes{ name } }
              milestone { dueOn }
              updatedAt
            }
            ... on PullRequest {
              title url assignees(first:10){ nodes{ login } }
              author { login }
              labels(first:5){ nodes{ name } }
              updatedAt
            }
            ... on DraftIssue {
              title
            }
          }
        }
      }
    }
  }
}
"""


def fetch_project_items(number: int) -> list[dict]:
    items = []
    cursor = None
    while True:
        variables = {"org": GITHUB_ORG, "number": number, "cursor": cursor}
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={GQL_ITEMS_QUERY}",
             "-f", f"org={GITHUB_ORG}", "-F", f"number={number}",
             *((["-f", f"cursor={cursor}"]) if cursor else [])],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        proj = data["data"]["organization"]["projectV2"]["items"]
        items.extend(proj["nodes"])
        if not proj["pageInfo"]["hasNextPage"]:
            break
        cursor = proj["pageInfo"]["endCursor"]
    return items


# ---------------------------------------------------------------------------
# 构建行数据
# ---------------------------------------------------------------------------

def build_project_row(gh_proj: dict) -> dict:
    number = gh_proj["number"]
    project_id = PROJECT_ID_MAP.get(number, f"project-{number}")
    return {
        "项目ID":        project_id,
        "项目名称":      gh_proj["title"],
        "Captain":       "待确认",
        "业务侧需求人":   "待确认",
        "所属业务线":    "其他",
        "GitHub Project": gh_proj["url"],
        "当前载具阶段":   "验证中",
        "目标载具阶段":   "试运行",
        "当前阶段状态":   "黄灯",
        "当前主线":       "待确认",
        "当前在做":       "待确认",
        "当前卡点":       "待确认",
        "是否可升级":     "待评估",
    }


def build_task_rows(items: list[dict], project_id: str) -> list[dict]:
    rows = []
    for raw in items:
        content = raw.get("content") or {}

        # 标题（DraftIssue 只有 title，没有 url/author）
        title = content.get("title", "") or ""
        url = content.get("url", "")

        # 负责人：优先 assignees，fallback PR/Issue author
        assignee_nodes = (content.get("assignees") or {}).get("nodes", [])
        assignees = [a.get("login", "") for a in assignee_nodes if a.get("login")]
        if not assignees and content.get("author"):
            assignees = [content["author"].get("login", "")]

        # 状态
        status_field = raw.get("status") or {}
        raw_status = status_field.get("name", "") if isinstance(status_field, dict) else ""
        status = STATUS_MAP.get(raw_status, "待处理")

        # 类型
        label_nodes = (content.get("labels") or {}).get("nodes", [])
        labels = [lbl.get("name", "") for lbl in label_nodes]
        task_type = detect_type(labels)

        updated_ts = to_ts_ms(content.get("updatedAt"))

        row = {
            "任务ID":     f"gh-{raw.get('id', '')}",
            "关联项目ID":  project_id,
            "任务标题":    title,
            "类型":        task_type,
            "来源":        "GitHub",
            "当前状态":    status,
            "负责人":      ", ".join(assignees) if assignees else "待确认",
            "GitHub 链接": url,
        }
        if updated_ts:
            row["更新时间"] = updated_ts
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    setup = load_setup()
    app_token = setup["app_token"]
    tables = setup["tables"]

    cli = build_client()

    # 1. 清空 项目主表 和 任务表
    print("=== 清空旧数据 ===")
    clear_table(cli, app_token, tables["项目主表"], "项目主表")
    clear_table(cli, app_token, tables["任务表"], "任务表")

    # 2. 拉 GitHub Projects
    print("\n=== 写入真实项目 ===")
    gh_projects = fetch_github_projects()
    project_rows = [build_project_row(p) for p in gh_projects
                    if p["number"] in PROJECT_ID_MAP]
    batch_create(cli, app_token, tables["项目主表"], project_rows)
    print(f"  项目主表: 写入 {len(project_rows)} 个项目")

    # 3. 同步所有 Project items 到任务表
    print("\n=== 同步 GitHub 任务 ===")
    state = {}
    total = 0
    for gh_proj in gh_projects:
        number = gh_proj["number"]
        if number not in PROJECT_ID_MAP:
            continue
        project_id = PROJECT_ID_MAP[number]
        items = fetch_project_items(number)
        if not items:
            print(f"  #{number} {gh_proj['title']}: 0 条，跳过")
            continue
        rows = build_task_rows(items, project_id)
        record_ids = batch_create(cli, app_token, tables["任务表"], rows)
        for item, rid in zip(items, record_ids):
            state[item.get("id", "")] = rid
        total += len(rows)
        print(f"  #{number} {gh_proj['title']}: 同步 {len(rows)} 条")

    # 4. 保存 state
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    print(f"\n完成。项目 {len(project_rows)} 个，任务 {total} 条。")


if __name__ == "__main__":
    main()
