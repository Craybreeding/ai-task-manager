#!/usr/bin/env python3
"""
ai_match_tasks.py
用 Kimi API 自动把 GitHub 任务匹配到升级条件，写回飞书。

用法:
    python3 scripts/ai_match_tasks.py              # 匹配所有未关联任务
    python3 scripts/ai_match_tasks.py --dry-run    # 只打印，不写飞书
    python3 scripts/ai_match_tasks.py --force      # 重新匹配所有任务（含已关联的）
"""
from __future__ import annotations
import argparse, json, os, re, time
from pathlib import Path
import httpx
import lark_oapi as lark

ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "state" / "feishu_ai_captain_setup.json"

KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"
KIMI_MODEL = "moonshot-v1-32k"


# ── Feishu helpers ────────────────────────────────────────

def build_feishu_client() -> lark.Client:
    return (lark.Client.builder()
            .app_id(os.getenv("FEISHU_APP_ID", ""))
            .app_secret(os.getenv("FEISHU_APP_SECRET", ""))
            .log_level(lark.LogLevel.ERROR).build())


def list_records(cli, app_token, table_id) -> list[dict]:
    records, page_token = [], None
    while True:
        b = (lark.bitable.v1.ListAppTableRecordRequest.builder()
             .app_token(app_token).table_id(table_id).page_size(500))
        if page_token:
            b.page_token(page_token)
        resp = cli.bitable.v1.app_table_record.list(b.build())
        if not resp.success():
            raise RuntimeError(f"List failed: {resp.code} {resp.msg}")
        for r in (resp.data.items or []):
            records.append({"_record_id": r.record_id, **r.fields})
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return records


def update_record(cli, app_token, table_id, record_id, fields):
    req = (lark.bitable.v1.UpdateAppTableRecordRequest.builder()
           .app_token(app_token).table_id(table_id).record_id(record_id)
           .request_body(lark.bitable.v1.AppTableRecord.builder().fields(fields).build())
           .build())
    resp = cli.bitable.v1.app_table_record.update(req)
    if not resp.success():
        raise RuntimeError(f"Update failed: {resp.code} {resp.msg}")


def str_val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in v
        )
    return str(v)


# ── Kimi matching ─────────────────────────────────────────

SYSTEM_PROMPT = """你是一个 AI 项目管理助手。
你的任务是：给定一个项目的「升级条件列表」和「GitHub 任务列表」，
判断每条任务最直接推进了哪个升级条件。

规则：
1. 每条任务只能匹配一个条件（或 null）
2. 如果任务和任何条件都没有明显关联（如纯基础设施、无关 bugfix），返回 null
3. 用条件的 id 字段作为返回值
4. 只返回 JSON，不要任何解释

返回格式：
[
  {"task_id": "gh-xxx", "condition_id": "proj-c01"},
  {"task_id": "gh-yyy", "condition_id": null},
  ...
]"""


def match_tasks_to_conditions(
    project_name: str,
    conditions: list[dict],
    tasks: list[dict],
) -> list[dict]:
    """调用 Kimi API，返回 [{task_id, condition_id}] 列表"""
    if not conditions or not tasks:
        return []

    cond_text = "\n".join(
        f"- id={c['id']}  名称={c['name']}  分类={c.get('category','')}  验收={c.get('criteria','')}"
        for c in conditions
    )
    task_text = "\n".join(
        f"- task_id={t['id']}  标题={t['title']}  负责人={t.get('assignee','')}"
        for t in tasks
    )

    user_msg = f"""项目：{project_name}

升级条件：
{cond_text}

GitHub 任务（{len(tasks)} 条）：
{task_text}

请输出每条任务对应的升级条件 id（或 null）。"""

    api_key = os.getenv("MOONSHOT_API_KEY", "")
    resp = httpx.post(
        KIMI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": KIMI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.1,
            "max_tokens": 8192,
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()

    # 解析 JSON（容错：可能被 markdown 包裹）
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            text = m.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 解析失败: {e}\n  原文: {text[:200]}")
        return []


# ── 主流程 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="重新匹配已有关联的任务")
    args = parser.parse_args()

    setup = json.loads(SETUP_FILE.read_text())
    app_token = setup["app_token"]
    tables = setup["tables"]
    cli = build_feishu_client()

    print("读取飞书数据...")
    projects   = list_records(cli, app_token, tables["项目主表"])
    conditions = list_records(cli, app_token, tables["升级条件表"])
    tasks      = list_records(cli, app_token, tables["任务表"])

    # 按项目分组
    cond_by_proj: dict[str, list[dict]] = {}
    for c in conditions:
        pid = str_val(c.get("关联项目ID"))
        cond_by_proj.setdefault(pid, []).append({
            "id":       str_val(c.get("条件ID")),
            "name":     str_val(c.get("升级条件名称")),
            "category": str_val(c.get("条件分类")),
            "criteria": str_val(c.get("验收标准")),
        })

    task_by_proj: dict[str, list[dict]] = {}
    for t in tasks:
        pid = str_val(t.get("关联项目ID"))
        existing_cond = str_val(t.get("关联条件ID"))
        if existing_cond and not args.force:
            continue  # 已关联，跳过
        task_by_proj.setdefault(pid, []).append({
            "_record_id": t["_record_id"],
            "id":         str_val(t.get("任务ID")),
            "title":      str_val(t.get("任务标题")),
            "assignee":   str_val(t.get("负责人")),
        })

    total_updated = 0
    for proj in projects:
        pid  = str_val(proj.get("项目ID"))
        name = str_val(proj.get("项目名称"))
        conds = cond_by_proj.get(pid, [])
        proj_tasks = task_by_proj.get(pid, [])

        if not conds or not proj_tasks:
            print(f"\n{name}: 跳过（条件={len(conds)} 任务={len(proj_tasks)}）")
            continue

        print(f"\n{name}: {len(proj_tasks)} 条任务 × {len(conds)} 个条件 → Kimi 匹配中...")

        matches = match_tasks_to_conditions(name, conds, proj_tasks)
        if not matches:
            print(f"  ⚠ 未返回匹配结果")
            continue

        # 建 task_id → record_id 映射
        task_id_to_record = {t["id"]: t["_record_id"] for t in proj_tasks}

        matched, skipped = 0, 0
        for m in matches:
            task_id = m.get("task_id", "")
            cond_id = m.get("condition_id")
            record_id = task_id_to_record.get(task_id)

            if not record_id:
                continue
            if not cond_id:
                skipped += 1
                continue

            if args.dry_run:
                print(f"  [dry] {task_id} → {cond_id}")
            else:
                try:
                    update_record(cli, app_token, tables["任务表"], record_id, {"关联条件ID": cond_id})
                    matched += 1
                except Exception as e:
                    print(f"  ✗ 更新失败 {task_id}: {e}")

            time.sleep(0.05)  # 避免 rate limit

        print(f"  ✓ 匹配={matched} 无关联={skipped}")
        total_updated += matched

    print(f"\n完成，共更新 {total_updated} 条任务关联。")
    if args.dry_run:
        print("（dry-run 模式，未写入飞书）")


if __name__ == "__main__":
    main()
