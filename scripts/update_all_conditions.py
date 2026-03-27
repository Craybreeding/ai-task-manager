#!/usr/bin/env python3
"""
update_all_conditions.py
删除 6 个项目的通用模板条件，替换为根据实际任务进度定制的真实升级路径。
(strategy-chat 已有真实条件，不动)
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

# ── 每个项目的真实升级路径（验证中 → 试运行MVP） ──────────────────

REAL_CONDITIONS = {
    "yuntu-datapicker": [
        # 3/4 tasks done: CI/CD, Langfuse, 三模块后处理 done; 本竞品投放 pending
        ("品牌心智/行业搜索/触点能效数据后处理完成", "交付", "已完成"),
        ("本竞品投放&达人矩阵取数流程跑通",         "交付", "未开始"),
        ("CI/CD + Langfuse 监控在线",               "质量", "已完成"),
        ("至少1个品牌完整跑通数据提取→报告流程",      "交付", "进行中"),
        ("业务侧数据准确性/时效性验收通过",          "采用", "未开始"),
    ],
    "draft-audit": [
        # 0/1 tasks done: Tech Assistant integration pending — very early stage
        ("Tech Assistant 接入草稿审核流程",           "交付", "未开始"),
        ("完整审核链路可运行（上传→AI审→出结果）",    "交付", "未开始"),
        ("Captain 明确且持续推进",                   "交付", "未开始"),
        ("至少10份真实草稿完成审核测试",              "质量", "未开始"),
        ("业务侧对审核质量给出反馈评估",              "采用", "未开始"),
    ],
    "xingtu-selector": [
        # 3/5 tasks done: CI/CD+Langfuse done, Tech Assistant done; MCN筛选+登录bug pending
        ("MCN 刊例筛选功能可用",                     "交付", "未开始"),
        ("星图登录流程稳定（无重复登录bug）",          "质量", "未开始"),
        ("CI/CD + Langfuse 监控在线",               "质量", "已完成"),
        ("Tech Assistant 集成可用",                  "交付", "已完成"),
        ("有业务侧实际使用选号并给出反馈",            "采用", "未开始"),
    ],
    "tech-assistant": [
        # 2/6 tasks done: 429+连接bug fixed; DeepWiki/RAG/monitoring pending
        ("Gemini 429限流 + 连接中断问题修复",         "质量", "已完成"),
        ("DeepWiki 集成研究并落地",                   "交付", "未开始"),
        ("RAG 定期评判机制上线",                      "交付", "未开始"),
        ("应用使用情况监控可查看",                     "质量", "未开始"),
        ("被至少2个产品日常调用",                      "采用", "进行中"),
    ],
    "ggn-workspace-frontend": [
        # 13/27 done: creative view done, VI logo+theme active, PPT pending
        ("VI Logo 上传 + 主色提取完整可用",            "交付", "进行中"),
        ("创意工坊基础功能上线",                       "交付", "已完成"),
        ("PPT 模板生成页面可用",                       "交付", "未开始"),
        ("明暗主题切换稳定无bug",                      "质量", "进行中"),
        ("有用户反馈并完成首轮UI迭代",                 "采用", "未开始"),
    ],
    "ggn-workspace-agent": [
        # 21/34 done: CI/CD+Langfuse done, creative API done, VI/PPT APIs active
        ("VI Logo + Product Image API 稳定可用",      "交付", "进行中"),
        ("PPT 模板生成 API 可用",                     "交付", "进行中"),
        ("创意工坊后端 API 上线",                      "交付", "已完成"),
        ("CI/CD + Langfuse 部署在线",                 "质量", "已完成"),
        ("前后端联调完成，端到端流程可用",              "采用", "进行中"),
    ],
}


def build_client():
    return (lark.Client.builder()
            .app_id(os.getenv("FEISHU_APP_ID", ""))
            .app_secret(os.getenv("FEISHU_APP_SECRET", ""))
            .log_level(lark.LogLevel.ERROR).build())


def list_records(cli):
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


def str_val(v) -> str:
    if v is None: return ""
    if isinstance(v, list):
        return "".join(i.get("text","") if isinstance(i,dict) else str(i) for i in v)
    return str(v)


def main():
    cli = build_client()
    all_records = list_records(cli)

    for project_id, conditions in REAL_CONDITIONS.items():
        print(f"\n── {project_id} ──")

        # 删除旧的模板条件
        old = [r for r in all_records if str_val(r.get("关联项目ID")) == project_id]
        print(f"  删除 {len(old)} 条旧条件...")
        for r in old:
            delete_record(cli, r["_id"])
            time.sleep(0.05)

        # 写入真实条件
        rows = []
        for i, (name, category, status) in enumerate(conditions, 1):
            rows.append({
                "条件ID":       f"{project_id}-c{i:02d}",
                "关联项目ID":   project_id,
                "升级条件名称": name,
                "条件分类":     category,
                "当前载具阶段": "验证中",
                "目标载具阶段": "试运行(MVP)",
                "当前状态":     status,
                "Owner":        "待确认",
            })

        batch_create(cli, rows)
        done_count = sum(1 for _, _, s in conditions if s == "已完成")
        active_count = sum(1 for _, _, s in conditions if s == "进行中")
        print(f"  ✓ 写入5条真实条件 ({done_count} done / {active_count} active / {5-done_count-active_count} pending)")

    print("\n全部完成！")


if __name__ == "__main__":
    main()
