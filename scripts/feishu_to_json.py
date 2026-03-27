#!/usr/bin/env python3
"""
feishu_to_json.py
从飞书多维表格拉取数据，输出 public/data.json 供 React 读取。

用法:
    python3 scripts/feishu_to_json.py
"""
from __future__ import annotations
import json, os
from pathlib import Path
import lark_oapi as lark

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"
OUT_FILE = ROOT / "public" / "data.json"

STATUS_MAP = {"绿灯": "green", "黄灯": "amber", "红灯": "red"}
COND_STATUS_MAP = {"未开始": "pending", "进行中": "active", "已完成": "done", "阻塞": "blocked"}
TASK_STATUS_MAP = {"待处理": "pending", "进行中": "active", "阻塞": "blocked", "已完成": "done"}

# 旧阶段名 → 新阶段名
STAGE_MAP = {
    "验证中":   "验证中",
    "试运行":   "试运行(MVP)",
    "正式交付": "正式上线(PROD)",
    "规模化":   "正式上线(PROD)",
    # 新名直传
    "需求拆解":      "需求拆解",
    "试运行(MVP)":   "试运行(MVP)",
    "正式上线(PROD)":"正式上线(PROD)",
}

def norm_stage(v: str, default: str) -> str:
    return STAGE_MAP.get(v, v) if v else default


def build_client() -> lark.Client:
    return (lark.Client.builder()
            .app_id(os.getenv("FEISHU_APP_ID", ""))
            .app_secret(os.getenv("FEISHU_APP_SECRET", ""))
            .log_level(lark.LogLevel.ERROR).build())


def list_records(cli: lark.Client, app_token: str, table_id: str) -> list[dict]:
    records, page_token = [], None
    while True:
        b = (lark.bitable.v1.ListAppTableRecordRequest.builder()
             .app_token(app_token).table_id(table_id).page_size(500))
        if page_token:
            b.page_token(page_token)
        resp = cli.bitable.v1.app_table_record.list(b.build())
        if not resp.success():
            raise RuntimeError(f"List failed {table_id}: {resp.code} {resp.msg}")
        for r in (resp.data.items or []):
            records.append({"record_id": r.record_id, **r.fields})
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return records


def ts_to_date(v) -> str:
    """飞书 DateTime 字段返回毫秒时间戳，转成 YYYY-MM-DD"""
    if not v:
        return ""
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def str_val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(item.get("text", item.get("name", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(v)


def parse_projects(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        op_status = str_val(r.get("项目运营状态")) or "进行中"
        out.append({
            "id":              str_val(r.get("项目ID")),
            "name":            str_val(r.get("项目名称")),
            "captain":         str_val(r.get("Captain")),
            "sponsor":         str_val(r.get("业务侧需求人")),
            "stage":           norm_stage(str_val(r.get("当前载具阶段")), "验证中"),
            "targetStage":     norm_stage(str_val(r.get("目标载具阶段")), "试运行(MVP)"),
            "status":          STATUS_MAP.get(str_val(r.get("当前阶段状态")), "amber"),
            "operationStatus": op_status,
            "currentFocus":    str_val(r.get("当前在做")),
            "blocker":         str_val(r.get("当前卡点")),
            "latestFeedback":  str_val(r.get("最新反馈")),
            "feedbackFrom":    str_val(r.get("反馈来源")),
            "nextCheckpoint":  str_val(r.get("下个检查点")),
            "upgradeGap":      int(r.get("升级差距数") or 0),
            "canUpgrade":      str_val(r.get("是否可升级")),
            "githubProject":   str_val(r.get("GitHub Project")),
            "githubRepo":      str_val(r.get("GitHub 仓库")),
            "wau":             int(r.get("WAU") or 0),
            "weeklyRuns":      int(r.get("周任务量") or 0),
            "hoursSaved":      int(r.get("节省人小时") or 0),
            "deliveryScore":   int(r.get("交付分") or 0),
            "qualityScore":    int(r.get("质量分") or 0),
            "opsScore":        int(r.get("运维分") or 0),
            "adoptionScore":   int(r.get("采用分") or 0),
        })
    return out


def parse_conditions(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "id":         str_val(r.get("条件ID")) or r.get("record_id", ""),
            "projectId":  str_val(r.get("关联项目ID")),
            "name":       str_val(r.get("升级条件名称")),
            "category":   str_val(r.get("条件分类")),
            "fromStage":  norm_stage(str_val(r.get("当前载具阶段")), "验证中"),
            "toStage":    norm_stage(str_val(r.get("目标载具阶段")), "试运行(MVP)"),
            "status":     COND_STATUS_MAP.get(str_val(r.get("当前状态")), "pending"),
            "owner":      str_val(r.get("Owner")),
            "criteria":   str_val(r.get("验收标准")),
            "issue":      str_val(r.get("当前问题")),
            "dueDate":    ts_to_date(r.get("目标完成日期")),
        })
    return out


def parse_tasks(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "id":          str_val(r.get("任务ID")),
            "projectId":   str_val(r.get("关联项目ID")),
            "conditionId": str_val(r.get("关联条件ID")),
            "title":       str_val(r.get("任务标题")),
            "type":        str_val(r.get("类型")),
            "status":      TASK_STATUS_MAP.get(str_val(r.get("当前状态")), "pending"),
            "assignee":    str_val(r.get("负责人")),
            "url":         str_val(r.get("GitHub 链接")),
        })
    return out


def main():
    setup = json.loads(SETUP_FILE.read_text())
    app_token = setup["app_token"]
    tables = setup["tables"]
    cli = build_client()

    print("拉取项目主表...")
    proj_rows = list_records(cli, app_token, tables["项目主表"])
    print(f"  {len(proj_rows)} 条")

    print("拉取升级条件表...")
    cond_rows = list_records(cli, app_token, tables["升级条件表"])
    print(f"  {len(cond_rows)} 条")

    print("拉取任务表...")
    task_rows = list_records(cli, app_token, tables["任务表"])
    print(f"  {len(task_rows)} 条")

    data = {
        "projects":   parse_projects(proj_rows),
        "conditions": parse_conditions(cond_rows),
        "tasks":      parse_tasks(task_rows),
    }

    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n写入 {OUT_FILE}")


if __name__ == "__main__":
    main()
