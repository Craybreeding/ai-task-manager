#!/usr/bin/env python3
"""Seed the AI Captain Feishu Bitable with initial demo records."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import lark_oapi as lark


ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"


def to_ts_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def client() -> lark.Client:
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


def batch_create(cli: lark.Client, app_token: str, table_id: str, rows: list[dict]) -> None:
    records = [lark.bitable.v1.AppTableRecord.builder().fields(row).build() for row in rows]
    request = (
        lark.bitable.v1.BatchCreateAppTableRecordRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .request_body(
            lark.bitable.v1.BatchCreateAppTableRecordRequestBody.builder().records(records).build()
        )
        .build()
    )
    response = cli.bitable.v1.app_table_record.batch_create(request)
    if not response.success():
        raise RuntimeError(f"Seed failed for {table_id}: {response.code} {response.msg}")


def load_setup() -> dict:
    return json.loads(SETUP_FILE.read_text())


def seed_projects() -> list[dict]:
    return [
        {
            "项目ID": "captain-hireflow",
            "项目名称": "AI 招聘助手",
            "Captain": "马田野",
            "Sponsor": "妃姐-stephy",
            "所属业务线": "招聘",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "当前阶段状态": "黄灯",
            "目标DDL": to_ts_ms("2026-04-12"),
            "当前主线": "补齐候选人识别能力，准备从试跑升级到正式交付。",
            "当前在做": "补齐候选人识别标注集，重跑 eval，并确认正式交付前的值班与回滚方案。",
            "当前卡点": "候选人识别 0 分，导致项目不能进入稳定运营；回滚预案也还没锁定。",
            "最新反馈": "希望每个 AI 项目都能明确 captain、eval、deadline、每周进展和员工试用情况。",
            "反馈来源": "妃姐-stephy",
            "下个检查点": "周五前完成候选人识别复测，周报同步是否可进正式交付。",
            "升级差距数": 3,
            "是否可升级": "待评估",
            "WAU": 12,
            "周任务量": 184,
            "节省人小时": 22,
            "交付分": 72,
            "质量分": 61,
            "运维分": 68,
            "采用分": 40,
            "GitHub 仓库": "github.com/goodidea/ai-hireflow",
            "GitHub Project": "github.com/goodidea/ai-hireflow/projects/1",
            "Notion 文档": "",
            "最后更新时间": to_ts_ms("2026-03-24"),
        },
        {
            "项目ID": "captain-prospect",
            "项目名称": "销售线索 Copilot",
            "Captain": "郭鹏天",
            "Sponsor": "Peggy",
            "所属业务线": "销售",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "当前阶段状态": "绿灯",
            "目标DDL": to_ts_ms("2026-04-28"),
            "当前主线": "把试点反馈转成上线门槛和 eval 规则。",
            "当前在做": "把试点销售反馈收集成可量化 eval，并补齐上线 SLO。",
            "当前卡点": "正式上线后的可用性目标还没定义，导致运维接管标准不清晰。",
            "最新反馈": "排序建议有价值，但希望更快看到哪些线索建议被真实采纳。",
            "反馈来源": "Peggy",
            "下个检查点": "下周二前补完 SLO 和试点团队反馈样本。",
            "升级差距数": 2,
            "是否可升级": "待评估",
            "WAU": 6,
            "周任务量": 96,
            "节省人小时": 9,
            "交付分": 79,
            "质量分": 74,
            "运维分": 53,
            "采用分": 32,
            "GitHub 仓库": "github.com/goodidea/lead-copilot",
            "GitHub Project": "github.com/goodidea/lead-copilot/projects/1",
            "Notion 文档": "",
            "最后更新时间": to_ts_ms("2026-03-24"),
        },
        {
            "项目ID": "captain-content",
            "项目名称": "内容复盘机器人",
            "Captain": "刘喆",
            "Sponsor": "火火",
            "所属业务线": "内容",
            "当前载具阶段": "汽车",
            "目标载具阶段": "高铁",
            "当前阶段状态": "绿灯",
            "目标DDL": to_ts_ms("2026-03-18"),
            "当前主线": "从单团队稳定运行升级到多团队可复制。",
            "当前在做": "复制到第二业务线，同时给成本波动建立告警阈值。",
            "当前卡点": "没有功能阻塞，但新增团队接入后 token 成本可能放大。",
            "最新反馈": "复盘质量认可，下一阶段要把模板标准化成可复制打法。",
            "反馈来源": "火火",
            "下个检查点": "下周完成第二业务线模板适配和成本预警配置。",
            "升级差距数": 2,
            "是否可升级": "待评估",
            "WAU": 24,
            "周任务量": 312,
            "节省人小时": 37,
            "交付分": 88,
            "质量分": 84,
            "运维分": 82,
            "采用分": 76,
            "GitHub 仓库": "github.com/goodidea/content-review-bot",
            "GitHub Project": "github.com/goodidea/content-review-bot/projects/1",
            "Notion 文档": "",
            "最后更新时间": to_ts_ms("2026-03-24"),
        },
    ]


def seed_upgrade_conditions() -> list[dict]:
    return [
        {
            "条件ID": "hireflow-up-1",
            "关联项目ID": "captain-hireflow",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "升级条件名称": "候选人识别准确率达标",
            "条件分类": "质量",
            "当前状态": "阻塞",
            "Owner": "马田野",
            "验收标准": "候选人识别相关 Eval >= 80",
            "当前问题": "当前候选人识别得分为 0。",
            "预计完成时间": to_ts_ms("2026-03-28"),
            "升级证据": "补标数据集 + 新一轮 Eval 结果",
        },
        {
            "条件ID": "hireflow-up-2",
            "关联项目ID": "captain-hireflow",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "升级条件名称": "回滚预案确认",
            "条件分类": "运维",
            "当前状态": "阻塞",
            "Owner": "马田野",
            "验收标准": "上线失败时有明确回滚路径",
            "当前问题": "回滚方案仍未锁定。",
            "预计完成时间": to_ts_ms("2026-03-28"),
            "升级证据": "回滚 SOP 文档",
        },
        {
            "条件ID": "prospect-up-1",
            "关联项目ID": "captain-prospect",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "升级条件名称": "上线 SLO 定义完成",
            "条件分类": "运维",
            "当前状态": "进行中",
            "Owner": "张世锋",
            "验收标准": "明确延迟和可用性目标",
            "当前问题": "指标口径还未冻结。",
            "预计完成时间": to_ts_ms("2026-04-01"),
            "升级证据": "SLO 文档",
        },
        {
            "条件ID": "prospect-up-2",
            "关联项目ID": "captain-prospect",
            "当前载具阶段": "自行车",
            "目标载具阶段": "汽车",
            "升级条件名称": "业务采纳反馈闭环",
            "条件分类": "采用",
            "当前状态": "进行中",
            "Owner": "Peggy",
            "验收标准": "至少一轮试点反馈闭环完成",
            "当前问题": "反馈回收样本偏少。",
            "预计完成时间": to_ts_ms("2026-04-01"),
            "升级证据": "试点问卷和复盘",
        },
        {
            "条件ID": "content-up-1",
            "关联项目ID": "captain-content",
            "当前载具阶段": "汽车",
            "目标载具阶段": "高铁",
            "升级条件名称": "第二业务线复制完成",
            "条件分类": "采用",
            "当前状态": "进行中",
            "Owner": "郭鹏天",
            "验收标准": "第二团队可独立运行模板",
            "当前问题": "模板适配尚未完成。",
            "预计完成时间": to_ts_ms("2026-03-31"),
            "升级证据": "第二业务线运行记录",
        },
        {
            "条件ID": "content-up-2",
            "关联项目ID": "captain-content",
            "当前载具阶段": "汽车",
            "目标载具阶段": "高铁",
            "升级条件名称": "成本异常预警接入",
            "条件分类": "成本",
            "当前状态": "进行中",
            "Owner": "马田野",
            "验收标准": "单周成本异常自动提醒",
            "当前问题": "尚未配置阈值。",
            "预计完成时间": to_ts_ms("2026-03-31"),
            "升级证据": "成本告警规则",
        },
    ]


def seed_weekly_updates() -> list[dict]:
    return [
        {
            "周更新ID": "2026-W13-hireflow",
            "关联项目ID": "captain-hireflow",
            "周期": "2026-W13",
            "当前在做": "补齐候选人识别标注集，重跑 eval。",
            "当前卡点": "候选人识别 0 分，回滚预案未锁定。",
            "最新反馈": "希望 captain / eval / deadline / 周进展更清楚。",
            "反馈来源": "妃姐-stephy",
            "本周推进变化": "状态识别、时间抽取等已达标，但关键升级条件仍未过。",
            "下个检查点": "周五前确认是否可从自行车升到汽车。",
            "当前判断": "仍处于自行车阶段，不满足正式交付条件。",
            "是否需要升级介入": True,
        },
        {
            "周更新ID": "2026-W13-prospect",
            "关联项目ID": "captain-prospect",
            "周期": "2026-W13",
            "当前在做": "把试点反馈转成 Eval 和 SLO。",
            "当前卡点": "上线后的可用性目标未定义。",
            "最新反馈": "希望看到建议被真实采纳的反馈闭环。",
            "反馈来源": "Peggy",
            "本周推进变化": "研发推进正常，本周 +11%。",
            "下个检查点": "下周二确认 SLO 和反馈样本。",
            "当前判断": "处于自行车后段，可冲刺汽车。",
            "是否需要升级介入": False,
        },
        {
            "周更新ID": "2026-W13-content",
            "关联项目ID": "captain-content",
            "周期": "2026-W13",
            "当前在做": "复制到第二业务线，补成本预警。",
            "当前卡点": "扩张后 token 成本可能放大。",
            "最新反馈": "下一阶段要把模板标准化成可复制打法。",
            "反馈来源": "火火",
            "本周推进变化": "交付已稳定，开始准备汽车升高铁。",
            "下个检查点": "下周完成第二业务线模板适配。",
            "当前判断": "已是汽车阶段，正在冲刺高铁。",
            "是否需要升级介入": False,
        },
    ]


def main() -> int:
    setup = load_setup()
    cli = client()
    app_token = setup["app_token"]
    tables = setup["tables"]

    batch_create(cli, app_token, tables["项目主表"], seed_projects())
    batch_create(cli, app_token, tables["升级条件表"], seed_upgrade_conditions())
    batch_create(cli, app_token, tables["周更新表"], seed_weekly_updates())

    print("Seeded 项目主表 / 升级条件表 / 周更新表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
