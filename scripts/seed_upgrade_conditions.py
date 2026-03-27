#!/usr/bin/env python3
"""
为每个项目预填标准升级条件（验证中→试运行）
已有条件的项目跳过。
"""
from __future__ import annotations
import json, os
from pathlib import Path
import lark_oapi as lark

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"

# 验证中 → 试运行 的标准条件
STANDARD_CONDITIONS_V1 = [
    ("有1个可重复运行的完整场景",   "交付"),
    ("Captain 已明确，有人负责",     "交付"),
    ("有基础反馈来源（用户/业务方）","采用"),
    ("有周更新机制",                 "质量"),
    ("基础 Eval 指标已定义",         "质量"),
]

def build_client() -> lark.Client:
    return (lark.Client.builder()
            .app_id(os.getenv("FEISHU_APP_ID", ""))
            .app_secret(os.getenv("FEISHU_APP_SECRET", ""))
            .log_level(lark.LogLevel.ERROR).build())

def list_records(cli, app_token, table_id):
    records, page_token = [], None
    while True:
        b = (lark.bitable.v1.ListAppTableRecordRequest.builder()
             .app_token(app_token).table_id(table_id).page_size(500))
        if page_token:
            b.page_token(page_token)
        resp = cli.bitable.v1.app_table_record.list(b.build())
        if not resp.success():
            break
        for r in (resp.data.items or []):
            records.append({"record_id": r.record_id, **r.fields})
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return records

def batch_create(cli, app_token, table_id, rows):
    records = [lark.bitable.v1.AppTableRecord.builder().fields(r).build() for r in rows]
    req = (lark.bitable.v1.BatchCreateAppTableRecordRequest.builder()
           .app_token(app_token).table_id(table_id)
           .request_body(lark.bitable.v1.BatchCreateAppTableRecordRequestBody.builder().records(records).build())
           .build())
    resp = cli.bitable.v1.app_table_record.batch_create(req)
    if not resp.success():
        raise RuntimeError(f"BatchCreate failed: {resp.code} {resp.msg}")

def main():
    setup = json.loads(SETUP_FILE.read_text())
    app_token = setup["app_token"]
    tables = setup["tables"]
    cli = build_client()

    projects = list_records(cli, app_token, tables["项目主表"])
    existing_conds = list_records(cli, app_token, tables["升级条件表"])

    # 已有条件的项目ID
    covered = {str(c.get("关联项目ID", "")) for c in existing_conds}

    rows_to_create = []
    for p in projects:
        pid = str(p.get("项目ID", ""))
        if not pid or pid in covered:
            print(f"  跳过 {pid}（已有条件）")
            continue

        from_stage = str(p.get("当前载具阶段") or "验证中")
        to_stage   = str(p.get("目标载具阶段") or "试运行")

        for i, (name, category) in enumerate(STANDARD_CONDITIONS_V1, 1):
            rows_to_create.append({
                "条件ID":       f"{pid}-c{i:02d}",
                "关联项目ID":   pid,
                "当前载具阶段": from_stage,
                "目标载具阶段": to_stage,
                "升级条件名称": name,
                "条件分类":     category,
                "当前状态":     "未开始",
                "Owner":        "待确认",
            })
        print(f"  {pid}: 准备写入 {len(STANDARD_CONDITIONS_V1)} 条升级条件")

    if rows_to_create:
        batch_create(cli, app_token, tables["升级条件表"], rows_to_create)
        print(f"\n完成，共写入 {len(rows_to_create)} 条升级条件")
    else:
        print("无需写入")

if __name__ == "__main__":
    main()
