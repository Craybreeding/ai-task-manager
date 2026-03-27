#!/usr/bin/env python3
"""
update_conditions.py
1. 升级条件表加「目标完成日期」字段（DateTime）
2. 删除 strategy-chat 的5条通用条件，写入5条真实条件
3. 把所有条件的 toStage 旧值更新为新阶段名
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
import lark_oapi as lark

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"

setup = json.loads(SETUP_FILE.read_text())
APP_TOKEN = setup["app_token"]
TABLE_ID  = setup["tables"]["升级条件表"]

STAGE_MAP = {
    "试运行":   "试运行(MVP)",
    "正式交付": "正式上线(PROD)",
    "规模化":   "正式上线(PROD)",
}

STRATEGY_CHAT_CONDITIONS = [
    {
        "条件ID":       "strategy-chat-c01",
        "关联项目ID":   "strategy-chat",
        "升级条件名称": "End-to-end workflow 完整跑通",
        "条件分类":     "交付",
        "当前载具阶段": "验证中",
        "目标载具阶段": "试运行(MVP)",
        "当前状态":     "进行中",
        "Owner":        "待确认",
    },
    {
        "条件ID":       "strategy-chat-c02",
        "关联项目ID":   "strategy-chat",
        "升级条件名称": "核心稳定性达标（无 P0 bug 连续2周）",
        "条件分类":     "质量",
        "当前载具阶段": "验证中",
        "目标载具阶段": "试运行(MVP)",
        "当前状态":     "进行中",
        "Owner":        "待确认",
    },
    {
        "条件ID":       "strategy-chat-c03",
        "关联项目ID":   "strategy-chat",
        "升级条件名称": "有真实用户在日常使用",
        "条件分类":     "采用",
        "当前载具阶段": "验证中",
        "目标载具阶段": "试运行(MVP)",
        "当前状态":     "已完成",
        "Owner":        "待确认",
    },
    {
        "条件ID":       "strategy-chat-c04",
        "关联项目ID":   "strategy-chat",
        "升级条件名称": "文件上传/附件功能可用",
        "条件分类":     "交付",
        "当前载具阶段": "验证中",
        "目标载具阶段": "试运行(MVP)",
        "当前状态":     "进行中",
        "Owner":        "待确认",
    },
    {
        "条件ID":       "strategy-chat-c05",
        "关联项目ID":   "strategy-chat",
        "升级条件名称": "有飞书/周报反馈回路",
        "条件分类":     "质量",
        "当前载具阶段": "验证中",
        "目标载具阶段": "试运行(MVP)",
        "当前状态":     "未开始",
        "Owner":        "待确认",
    },
]


def build_client():
    return (lark.Client.builder()
            .app_id(os.getenv("FEISHU_APP_ID", ""))
            .app_secret(os.getenv("FEISHU_APP_SECRET", ""))
            .log_level(lark.LogLevel.ERROR).build())


def list_records(cli, fields_filter=None):
    records, page_token = [], None
    while True:
        b = (lark.bitable.v1.ListAppTableRecordRequest.builder()
             .app_token(APP_TOKEN).table_id(TABLE_ID).page_size(500))
        if page_token:
            b.page_token(page_token)
        resp = cli.bitable.v1.app_table_record.list(b.build())
        if not resp.success():
            raise RuntimeError(f"List failed: {resp.code} {resp.msg}")
        for r in (resp.data.items or []):
            records.append({"_id": r.record_id, **r.fields})
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return records


def delete_record(cli, record_id):
    req = (lark.bitable.v1.DeleteAppTableRecordRequest.builder()
           .app_token(APP_TOKEN).table_id(TABLE_ID).record_id(record_id)
           .build())
    resp = cli.bitable.v1.app_table_record.delete(req)
    if not resp.success():
        print(f"  ✗ 删除失败 {record_id}: {resp.code} {resp.msg}")


def update_record(cli, record_id, fields):
    req = (lark.bitable.v1.UpdateAppTableRecordRequest.builder()
           .app_token(APP_TOKEN).table_id(TABLE_ID).record_id(record_id)
           .request_body(lark.bitable.v1.AppTableRecord.builder().fields(fields).build())
           .build())
    resp = cli.bitable.v1.app_table_record.update(req)
    if not resp.success():
        print(f"  ✗ 更新失败 {record_id}: {resp.code} {resp.msg}")


def batch_create(cli, rows):
    records = [lark.bitable.v1.AppTableRecord.builder().fields(r).build() for r in rows]
    req = (lark.bitable.v1.BatchCreateAppTableRecordRequest.builder()
           .app_token(APP_TOKEN).table_id(TABLE_ID)
           .request_body(lark.bitable.v1.BatchCreateAppTableRecordRequestBody.builder()
                         .records(records).build())
           .build())
    resp = cli.bitable.v1.app_table_record.batch_create(req)
    if not resp.success():
        raise RuntimeError(f"BatchCreate failed: {resp.code} {resp.msg}")


def add_date_field(cli):
    """在升级条件表加「目标完成日期」DateTime 字段，已存在则跳过"""
    # 先列出现有字段
    req = (lark.bitable.v1.ListAppTableFieldRequest.builder()
           .app_token(APP_TOKEN).table_id(TABLE_ID).build())
    resp = cli.bitable.v1.app_table_field.list(req)
    if not resp.success():
        print(f"  ✗ 列字段失败: {resp.code} {resp.msg}")
        return
    existing = [f.field_name for f in (resp.data.items or [])]
    if "目标完成日期" in existing:
        print("  「目标完成日期」字段已存在，跳过")
        return

    req = (lark.bitable.v1.CreateAppTableFieldRequest.builder()
           .app_token(APP_TOKEN).table_id(TABLE_ID)
           .request_body(
               lark.bitable.v1.AppTableField.builder()
               .field_name("目标完成日期")
               .type(5)          # 5 = DateTime
               .property(lark.bitable.v1.AppTableFieldProperty.builder()
                         .date_formatter("yyyy/MM/dd").build())
               .build()
           ).build())
    resp = cli.bitable.v1.app_table_field.create(req)
    if resp.success():
        print("  ✓ 「目标完成日期」字段已创建")
    else:
        print(f"  ✗ 创建字段失败: {resp.code} {resp.msg}")


def str_val(v) -> str:
    if v is None: return ""
    if isinstance(v, list):
        return "".join(i.get("text","") if isinstance(i,dict) else str(i) for i in v)
    return str(v)


def main():
    cli = build_client()

    # 1. 加日期字段
    print("1. 添加「目标完成日期」字段...")
    add_date_field(cli)

    # 2. 替换 strategy-chat 条件
    print("\n2. 替换 strategy-chat 升级条件...")
    records = list_records(cli)
    sc_records = [r for r in records if str_val(r.get("关联项目ID")) == "strategy-chat"]
    print(f"  找到 {len(sc_records)} 条旧条件，删除中...")
    for r in sc_records:
        delete_record(cli, r["_id"])
        time.sleep(0.05)
    print(f"  批量写入5条新条件...")
    batch_create(cli, STRATEGY_CHAT_CONDITIONS)
    print("  ✓ strategy-chat 条件已更新")

    # 3. 更新其他项目的 toStage 旧值
    print("\n3. 更新其余条件的阶段名称...")
    records = list_records(cli)
    updated = 0
    for r in records:
        pid = str_val(r.get("关联项目ID"))
        if pid == "strategy-chat":
            continue
        to_stage = str_val(r.get("目标载具阶段"))
        new_stage = STAGE_MAP.get(to_stage)
        if new_stage:
            update_record(cli, r["_id"], {"目标载具阶段": new_stage})
            updated += 1
            time.sleep(0.05)
    print(f"  ✓ 更新了 {updated} 条阶段名称")

    print("\n完成！")


if __name__ == "__main__":
    main()
