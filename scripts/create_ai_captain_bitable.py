#!/usr/bin/env python3
"""Create the AI Captain Feishu Bitable workspace and seed tables."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import lark_oapi as lark


TEXT = 1
NUMBER = 2
SINGLE_SELECT = 3
MULTI_SELECT = 4
DATETIME = 5
CHECKBOX = 7

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"


def build_client() -> lark.Client:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET are required in environment.")
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


def field(
    name: str,
    type_code: int,
    ui_type: str,
    *,
    options: list[str] | None = None,
    multiple: bool = False,
    date_formatter: str | None = None,
    formatter: str | None = None,
) -> lark.bitable.v1.AppTableCreateHeader:
    property_builder = lark.bitable.v1.AppTableFieldProperty.builder()
    has_property = False
    if options:
        option_objs = [
            lark.bitable.v1.AppTableFieldPropertyOption.builder().name(opt).color(idx).build()
            for idx, opt in enumerate(options)
        ]
        property_builder.options(option_objs)
        has_property = True
    if multiple:
        property_builder.multiple(True)
        has_property = True
    if date_formatter:
        property_builder.date_formatter(date_formatter).auto_fill(False)
        has_property = True
    if formatter:
        property_builder.formatter(formatter)
        has_property = True

    builder = lark.bitable.v1.AppTableCreateHeader.builder().field_name(name).type(type_code).ui_type(ui_type)
    if has_property:
        builder.property(property_builder.build())
    return builder.build()


def table_schema() -> list[tuple[str, list[lark.bitable.v1.AppTableCreateHeader]]]:
    return [
        (
            "项目主表",
            [
                field("项目ID", TEXT, "Text"),
                field("项目名称", TEXT, "Text"),
                field("Captain", TEXT, "Text"),
                field("业务侧需求人", TEXT, "Text"),
                field("所属业务线", SINGLE_SELECT, "SingleSelect", options=["招聘", "销售", "内容", "运营", "其他"]),
                field("当前载具阶段", SINGLE_SELECT, "SingleSelect", options=["验证中", "试运行", "正式交付", "规模化"]),
                field("目标载具阶段", SINGLE_SELECT, "SingleSelect", options=["验证中", "试运行", "正式交付", "规模化"]),
                field("当前阶段状态", SINGLE_SELECT, "SingleSelect", options=["绿灯", "黄灯", "红灯"]),
                field("目标DDL", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("当前主线", TEXT, "Text"),
                field("当前在做", TEXT, "Text"),
                field("当前卡点", TEXT, "Text"),
                field("最新反馈", TEXT, "Text"),
                field("反馈来源", TEXT, "Text"),
                field("下个检查点", TEXT, "Text"),
                field("升级差距数", NUMBER, "Number", formatter="0"),
                field("是否可升级", SINGLE_SELECT, "SingleSelect", options=["可升级", "不可升级", "待评估"]),
                field("WAU", NUMBER, "Number", formatter="0"),
                field("周任务量", NUMBER, "Number", formatter="0"),
                field("节省人小时", NUMBER, "Number", formatter="0"),
                field("交付分", NUMBER, "Number", formatter="0"),
                field("质量分", NUMBER, "Number", formatter="0"),
                field("运维分", NUMBER, "Number", formatter="0"),
                field("采用分", NUMBER, "Number", formatter="0"),
                field("GitHub 仓库", TEXT, "Text"),
                field("GitHub Project", TEXT, "Text"),
                field("Notion 文档", TEXT, "Text"),
                field("最后更新时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
            ],
        ),
        (
            "升级条件表",
            [
                field("条件ID", TEXT, "Text"),
                field("关联项目ID", TEXT, "Text"),
                field("当前载具阶段", SINGLE_SELECT, "SingleSelect", options=["验证中", "试运行", "正式交付", "规模化"]),
                field("目标载具阶段", SINGLE_SELECT, "SingleSelect", options=["验证中", "试运行", "正式交付", "规模化"]),
                field("升级条件名称", TEXT, "Text"),
                field("条件分类", SINGLE_SELECT, "SingleSelect", options=["交付", "质量", "运维", "采用", "成本"]),
                field("当前状态", SINGLE_SELECT, "SingleSelect", options=["未开始", "进行中", "已完成", "阻塞"]),
                field("Owner", TEXT, "Text"),
                field("验收标准", TEXT, "Text"),
                field("当前问题", TEXT, "Text"),
                field("预计完成时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("升级证据", TEXT, "Text"),
            ],
        ),
        (
            "任务表",
            [
                field("任务ID", TEXT, "Text"),
                field("关联项目ID", TEXT, "Text"),
                field("关联条件ID", TEXT, "Text"),
                field("任务标题", TEXT, "Text"),
                field("类型", SINGLE_SELECT, "SingleSelect", options=["feature", "bug", "ops", "quality", "growth", "doc"]),
                field("来源", SINGLE_SELECT, "SingleSelect", options=["GitHub", "飞书", "手工", "Bot"]),
                field("当前状态", SINGLE_SELECT, "SingleSelect", options=["待处理", "进行中", "阻塞", "已完成"]),
                field("负责人", TEXT, "Text"),
                field("截止时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("是否关键路径", CHECKBOX, "Checkbox"),
                field("阻塞原因", TEXT, "Text"),
                field("GitHub 链接", TEXT, "Text"),
                field("更新时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
            ],
        ),
        (
            "周更新表",
            [
                field("周更新ID", TEXT, "Text"),
                field("关联项目ID", TEXT, "Text"),
                field("周期", TEXT, "Text"),
                field("当前在做", TEXT, "Text"),
                field("当前卡点", TEXT, "Text"),
                field("最新反馈", TEXT, "Text"),
                field("反馈来源", TEXT, "Text"),
                field("本周推进变化", TEXT, "Text"),
                field("下个检查点", TEXT, "Text"),
                field("当前判断", TEXT, "Text"),
                field("是否需要升级介入", CHECKBOX, "Checkbox"),
            ],
        ),
        (
            "Eval 表",
            [
                field("Eval记录ID", TEXT, "Text"),
                field("关联项目ID", TEXT, "Text"),
                field("关联条件ID", TEXT, "Text"),
                field("指标编码", TEXT, "Text"),
                field("指标名称", TEXT, "Text"),
                field("目标值", NUMBER, "Number", formatter="0"),
                field("当前值", NUMBER, "Number", formatter="0"),
                field("得分", NUMBER, "Number", formatter="0"),
                field("趋势", SINGLE_SELECT, "SingleSelect", options=["上升", "持平", "下降"]),
                field("样本量", NUMBER, "Number", formatter="0"),
                field("评估日期", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("是否阻塞升级", CHECKBOX, "Checkbox"),
            ],
        ),
        (
            "运维事件表",
            [
                field("事件ID", TEXT, "Text"),
                field("关联项目ID", TEXT, "Text"),
                field("事件时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("事件类型", SINGLE_SELECT, "SingleSelect", options=["错误", "延迟", "成本异常", "可用性", "数据质量"]),
                field("严重等级", SINGLE_SELECT, "SingleSelect", options=["P1", "P2", "P3"]),
                field("当前状态", SINGLE_SELECT, "SingleSelect", options=["已发现", "处理中", "已恢复", "已复盘"]),
                field("现象描述", TEXT, "Text"),
                field("值班人", TEXT, "Text"),
                field("恢复时间", DATETIME, "DateTime", date_formatter="yyyy/MM/dd"),
                field("Root Cause", TEXT, "Text"),
                field("是否影响升级", CHECKBOX, "Checkbox"),
            ],
        ),
    ]


def create_app(client: lark.Client, name: str, folder_token: str | None) -> str:
    body = {"name": name, "time_zone": "Asia/Shanghai"}
    if folder_token:
        body["folder_token"] = folder_token

    request = lark.bitable.v1.CreateAppRequest.builder().request_body(lark.bitable.v1.ReqApp(body)).build()
    response = client.bitable.v1.app.create(request)
    if not response.success():
        raise RuntimeError(f"Create app failed: {response.code} {response.msg}")

    app = getattr(response.data, "app", None)
    app_token = getattr(app, "app_token", None)
    if not app_token:
        raise RuntimeError("Create app succeeded but app_token missing in response.")
    return app_token


def create_table(
    client: lark.Client,
    app_token: str,
    name: str,
    headers: list[lark.bitable.v1.AppTableCreateHeader],
) -> str:
    table = (
        lark.bitable.v1.ReqTable.builder()
        .name(name)
        .default_view_name("默认视图")
        .fields(headers)
        .build()
    )
    body = lark.bitable.v1.CreateAppTableRequestBody.builder().table(table).build()
    request = (
        lark.bitable.v1.CreateAppTableRequest.builder()
        .app_token(app_token)
        .request_body(body)
        .build()
    )
    response = client.bitable.v1.app_table.create(request)
    if not response.success():
        raise RuntimeError(f"Create table {name} failed: {response.code} {response.msg}")
    return getattr(response.data, "table_id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create AI Captain Bitable workspace")
    parser.add_argument("--name", default="AI Captain 项目总台", help="Bitable name")
    parser.add_argument("--folder-token", default="", help="Optional Feishu folder token")
    parser.add_argument("--dry-run", action="store_true", help="Print planned schema only")
    args = parser.parse_args()

    schemas = table_schema()
    if args.dry_run:
        print(json.dumps({"name": args.name, "tables": [name for name, _ in schemas]}, ensure_ascii=False, indent=2))
        return 0

    client = build_client()
    app_token = create_app(client, args.name, args.folder_token or None)

    tables: dict[str, str] = {}
    for table_name, headers in schemas:
        table_id = create_table(client, app_token, table_name, headers)
        tables[table_name] = table_id
        print(f"created table: {table_name} -> {table_id}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "app_name": args.name,
                "app_token": app_token,
                "tables": tables,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"app_token={app_token}")
    print(f"saved={OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
