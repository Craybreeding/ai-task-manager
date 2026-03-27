#!/usr/bin/env python3
"""
auto_sync_projects.py — 从 GitHub 自动同步项目到 data.json

检测逻辑:
  - 有 release tag → 正式上线(PROD)
  - README 含部署 URL (*.com, vercel.app 等) → 试运行(MVP)
  - 最近 7 天有 push + open issues → 验证中
  - 超过 14 天没 push → operationStatus=待启动
  - archived → operationStatus=已废弃

用法:
  python scripts/auto_sync_projects.py                    # 预览 (dry-run)
  python scripts/auto_sync_projects.py --write            # 写入 data.json
  python scripts/auto_sync_projects.py --write --with-issues  # 同时同步 issues 为 tasks
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "public" / "data.json"

ORG = "goodidea-ggn"

# 手动覆盖: 只覆盖显示名称，captain 从 GitHub contributors 自动检测
MANUAL_OVERRIDES: dict[str, dict] = {
    "consumer-insight-v2": {"name": "Consumer Insight v2"},
    "consumer-insights": {"name": "Consumer Insights"},
}

# GitHub login → 显示名映射（不需要映射的就不写，原样显示）
DISPLAY_NAMES: dict[str, str] = {}

# 项目 emoji 映射
EMOJI_MAP = {
    "yuntu-datapicker": "\U0001f4ca",
    "draft-audit": "\U0001f4dd",
    "xingtu-selector": "\u2b50",
    "tech-assistant": "\U0001f916",
    "strategy-chat": "\U0001f4ac",  # 改名: strategy_chat -> strategy-chat
    "strategy_chat": "\U0001f4ac",
    "ggn-workspace-frontend": "\U0001f5a5",
    "ggn-workspace-agent": "\U0001f9e0",
    "ggn-workspace": "\U0001f3e0",
    "consumer-insight-v2": "\U0001f50d",
    "consumer-insights": "\U0001f4a1",
    "design-agent": "\U0001f3a8",
    "web-pilot": "\U0001f310",
    "openclaw-skillhub": "\U0001f4e6",
}

# 排除的 repo（不算项目）
EXCLUDE_REPOS = {".github", "test", "sandbox"}

DEPLOY_URL_PATTERN = re.compile(
    r"https?://[\w.-]+\.(com|app|dev|io|site|pages|vercel\.app|netlify\.app|railway\.app)",
    re.IGNORECASE,
)


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, check=True
    )
    return result.stdout


def fetch_repos() -> list[dict]:
    raw = run_gh([
        "repo", "list", ORG, "--limit", "100",
        "--json", "name,description,isArchived,pushedAt,url",
    ])
    return json.loads(raw)


def fetch_releases(repo_name: str) -> list[dict]:
    try:
        raw = run_gh([
            "release", "list", "--repo", f"{ORG}/{repo_name}",
            "--json", "tagName,publishedAt", "--limit", "5",
        ])
        return json.loads(raw)
    except subprocess.CalledProcessError:
        return []


def fetch_readme(repo_name: str) -> str:
    try:
        raw = run_gh(["repo", "view", f"{ORG}/{repo_name}", "--json", "readme"])
        data = json.loads(raw)
        return data.get("readme", "") or ""
    except subprocess.CalledProcessError:
        return ""


def fetch_issues(repo_name: str) -> list[dict]:
    try:
        raw = run_gh([
            "issue", "list", "--repo", f"{ORG}/{repo_name}",
            "--state", "all",
            "--json", "number,title,state,assignees,url,labels",
            "--limit", "200",
        ])
        return json.loads(raw)
    except subprocess.CalledProcessError:
        return []


def fetch_recent_commits(repo_name: str, limit: int = 5) -> list[str]:
    """最近 N 条 commit message"""
    try:
        raw = run_gh([
            "api", f"repos/{ORG}/{repo_name}/commits",
            "--jq", f'.[:{limit}] | .[].commit.message',
        ])
        return [line.strip() for line in raw.strip().split("\n") if line.strip()]
    except subprocess.CalledProcessError:
        return []


def llm_refine_stages(uncertain_repos: list[dict]) -> dict[str, dict]:
    """
    批量调用 LLM 精修不确定项目的 stage / currentFocus。
    输入: [{id, name, readme_snippet, commits, heuristic_stage}]
    输出: {repo_id: {stage, currentFocus, confidence}}
    """
    if not uncertain_repos:
        return {}

    # 尝试找 API key: 环境变量 > 硬编码 moonshot key
    api_key = os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        api_key = "sk-Rxy3KtPy16zcpZ1CxQbgZsncjVA9fx64JSOcZ8Cld7CuUWRn"
    if not api_key:
        print("  ⚠ No Moonshot API key found, skipping LLM refinement")
        return {}

    # 构建 prompt — 一次调用批量判断
    repo_descriptions = []
    for r in uncertain_repos:
        readme_short = r["readme"][:500] if r["readme"] else "(no README)"
        commits_str = "\n    ".join(r["commits"][:5]) if r["commits"] else "(no commits)"
        repo_descriptions.append(
            f"- **{r['id']}** ({r['name']})\n"
            f"  README snippet: {readme_short}\n"
            f"  Recent commits:\n    {commits_str}\n"
            f"  Heuristic guess: {r['heuristic_stage']}\n"
            f"  Last push: {r['pushed_days']} days ago"
        )

    prompt = f"""你是一个项目管理专家。请根据以下 GitHub 仓库信息，判断每个项目的开发阶段。

阶段定义:
- 需求拆解: 刚开始，还在规划/设计，没有可运行的产品
- 验证中: 有代码在开发，核心功能在搭建中，可能有 demo
- 试运行(MVP): 有可用产品，已部署或正在内测，有用户在试用
- 正式上线(PROD): 稳定运行，有正式用户在用

项目列表:
{chr(10).join(repo_descriptions)}

请返回 JSON 数组，每个元素:
{{"id": "repo-id", "stage": "阶段", "currentFocus": "一句话描述当前在做什么", "confidence": 0.0-1.0}}

只返回 JSON，不要其他文字。"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.moonshot.cn/v1/chat/completions",
            data=json.dumps({
                "model": "moonshot-v1-8k",
                "temperature": 0.3,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            text = body["choices"][0]["message"]["content"]
            # 提取 JSON
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                results = json.loads(match.group())
                return {r["id"]: r for r in results}
    except Exception as e:
        print(f"  ⚠ LLM refinement failed: {e}")

    return {}


def days_since(iso_date: str) -> int:
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def detect_stage(repo: dict, releases: list, readme: str) -> tuple[str, bool]:
    """启发式判断项目阶段。返回 (stage, is_certain)"""
    if releases:
        return "正式上线(PROD)", True
    if repo.get("isArchived"):
        return "需求拆解", True
    if DEPLOY_URL_PATTERN.search(readme):
        return "试运行(MVP)", False  # URL 不一定代表在线
    pushed_days = days_since(repo["pushedAt"])
    if pushed_days <= 14:
        return "验证中", False  # 不确定，可能是 MVP
    return "需求拆解", False


def detect_op_status(repo: dict) -> str:
    if repo.get("isArchived"):
        return "已废弃"
    pushed_days = days_since(repo["pushedAt"])
    if pushed_days <= 14:
        return "进行中"
    if pushed_days <= 60:
        return "已暂停"
    return "待启动"


def detect_status(issues: list) -> str:
    """red/yellow/green"""
    open_issues = [i for i in issues if i["state"] == "OPEN"]
    blocked = [i for i in open_issues
               if any(l.get("name", "").lower() in ("blocked", "bug", "critical")
                      for l in i.get("labels", []))]
    if blocked:
        return "red"
    if len(open_issues) > 10:
        return "yellow"
    return "green"


def detect_captain(issues: list, repo_name: str) -> str:
    override = MANUAL_OVERRIDES.get(repo_name, {})
    if override.get("captain"):
        return override["captain"]
    # 从 issues assignees 推断最频繁的贡献者
    counts: dict[str, int] = {}
    for issue in issues:
        for a in issue.get("assignees", []):
            login = a.get("login", "")
            if login:
                counts[login] = counts.get(login, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return "待确认"


def fetch_contributors(repo_name: str) -> list[str]:
    """获取 repo 贡献者列表（按贡献量排序）"""
    try:
        raw = run_gh(["api", f"repos/{ORG}/{repo_name}/contributors", "--jq", ".[].login"])
        return [l.strip() for l in raw.strip().split("\n") if l.strip()]
    except subprocess.CalledProcessError:
        return []


def llm_match_tasks_to_conditions(
    project_id: str, conditions: list[dict], tasks: list[dict]
) -> dict[str, str]:
    """
    用 LLM 智能匹配 tasks → conditions。
    返回 {task_id: condition_id}
    """
    if not conditions or not tasks:
        return {}

    api_key = os.environ.get("MOONSHOT_API_KEY", "sk-Rxy3KtPy16zcpZ1CxQbgZsncjVA9fx64JSOcZ8Cld7CuUWRn")

    cond_list = "\n".join(f"  - {c['id']}: {c['name']}" for c in conditions)
    task_list = "\n".join(f"  - {t['id']}: {t['title']}" for t in tasks[:50])  # 限 50 条

    prompt = f"""请将以下 GitHub issues (tasks) 匹配到最合适的升级条件 (conditions)。

项目: {project_id}

升级条件:
{cond_list}

任务列表:
{task_list}

规则:
- 一个 task 只能匹配一个 condition
- 如果 task 和任何 condition 都不相关，不要匹配（跳过）
- 根据 task 标题的语义判断它属于哪个 condition

返回 JSON 对象，key=task_id, value=condition_id。只返回匹配的，不匹配的不用写。
只返回 JSON，不要其他文字。"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.moonshot.cn/v1/chat/completions",
            data=json.dumps({
                "model": "moonshot-v1-8k",
                "temperature": 0.3,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            text = body["choices"][0]["message"]["content"]
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
    except Exception as e:
        print(f"    ⚠ Task-condition matching failed for {project_id}: {e}")

    return {}


def issues_to_tasks(issues: list, project_id: str, task_cond_map: dict[str, str] | None = None) -> list[dict]:
    """把 GitHub issues 转成 data.json 的 tasks 格式"""
    if task_cond_map is None:
        task_cond_map = {}
    tasks = []
    for issue in issues:
        assignees = [a.get("login", "") for a in issue.get("assignees", [])]
        # 显示名映射
        display_assignees = [DISPLAY_NAMES.get(a, a) for a in assignees]
        state = issue.get("state", "OPEN")
        status = "done" if state == "CLOSED" else "active"

        labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
        if "blocked" in labels:
            status = "blocked"
        elif state == "OPEN" and not assignees:
            status = "pending"

        task_id = f"{project_id}-issue-{issue['number']}"
        tasks.append({
            "id": task_id,
            "projectId": project_id,
            "conditionId": task_cond_map.get(task_id, ""),
            "title": issue.get("title", ""),
            "type": "feature",
            "status": status,
            "assignee": ", ".join(display_assignees) or "待确认",
            "url": issue.get("url", ""),
        })
    return tasks


def sync_projects(with_issues: bool = False, use_llm: bool = False) -> dict:
    """主同步逻辑，返回完整 data.json 结构"""
    # 加载现有 data
    existing = {}
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text())

    existing_projects = {p["id"]: p for p in existing.get("projects", [])}
    existing_conditions = existing.get("conditions", [])

    repos = fetch_repos()
    print(f"Found {len(repos)} repos in {ORG}")

    # Pass 1: 规则兜底 + 收集不确定的 repo
    projects = []
    all_tasks = []
    uncertain: list[dict] = []  # 需要 LLM 精修的

    for repo in repos:
        name = repo["name"]
        if name in EXCLUDE_REPOS:
            continue

        project_id = name.replace("_", "-")
        print(f"  Processing {name}...", end=" ")

        releases = fetch_releases(name)
        readme = fetch_readme(name)
        issues = fetch_issues(name) if with_issues else []

        stage, is_certain = detect_stage(repo, releases, readme)
        op_status = detect_op_status(repo)
        status = detect_status(issues) if issues else "green"

        # Captain: contributors API > issue assignees > 待确认
        contributors = fetch_contributors(name) if with_issues else []
        if contributors:
            captain = DISPLAY_NAMES.get(contributors[0], contributors[0])
        else:
            captain = detect_captain(issues, name)

        # 收集不确定项目给 LLM
        if use_llm and not is_certain:
            commits = fetch_recent_commits(name)
            uncertain.append({
                "id": project_id,
                "name": name,
                "readme": readme,
                "commits": commits,
                "heuristic_stage": stage,
                "pushed_days": days_since(repo["pushedAt"]),
            })

        override = MANUAL_OVERRIDES.get(name, {})
        display_name = override.get("name", name)

        prev = existing_projects.get(project_id, {})

        project = {
            "id": project_id,
            "name": display_name,
            "stage": prev.get("stage") or stage,
            "targetStage": prev.get("targetStage") or _next_stage(stage),
            "operationStatus": op_status,
            "status": status,
            "sponsor": override.get("sponsor") or prev.get("sponsor") or "待确认",
            "captain": captain,
            "blocker": prev.get("blocker", "待确认"),
            "currentFocus": prev.get("currentFocus", "待确认"),
            "nextCheckpoint": prev.get("nextCheckpoint", "待确认"),
            "latestFeedback": prev.get("latestFeedback", ""),
            "feedbackFrom": prev.get("feedbackFrom", ""),
            "wau": prev.get("wau", 0),
            "weeklyRuns": prev.get("weeklyRuns", 0),
            "hoursSaved": prev.get("hoursSaved", 0),
        }
        projects.append(project)
        cert = "✓" if is_certain else "?"
        print(f"→ {stage} [{cert}] | {op_status} | captain={captain}")

        if with_issues and issues:
            # 先创建不带 conditionId 的 tasks
            raw_tasks = issues_to_tasks(issues, project_id)
            # LLM 匹配 tasks → conditions
            proj_conditions = [c for c in existing_conditions if c["projectId"] == project_id]
            if proj_conditions and use_llm:
                print(f"    🔗 Matching {len(raw_tasks)} tasks to {len(proj_conditions)} conditions...")
                task_cond_map = llm_match_tasks_to_conditions(project_id, proj_conditions, raw_tasks)
                if task_cond_map:
                    # 重新创建带 conditionId 的 tasks
                    raw_tasks = issues_to_tasks(issues, project_id, task_cond_map)
                    matched = sum(1 for t in raw_tasks if t.get("conditionId"))
                    print(f"    ✅ Matched {matched}/{len(raw_tasks)} tasks")
            all_tasks.extend(raw_tasks)

    # Pass 2: LLM 精修不确定的项目
    if uncertain and use_llm:
        print(f"\n  🤖 LLM refining {len(uncertain)} uncertain projects...")
        llm_results = llm_refine_stages(uncertain)
        if llm_results:
            proj_map = {p["id"]: p for p in projects}
            for repo_id, refinement in llm_results.items():
                if repo_id in proj_map:
                    p = proj_map[repo_id]
                    new_stage = refinement.get("stage", "")
                    confidence = refinement.get("confidence", 0)
                    if new_stage and confidence >= 0.6:
                        old = p["stage"]
                        p["stage"] = new_stage
                        p["targetStage"] = _next_stage(new_stage)
                        if refinement.get("currentFocus") and p["currentFocus"] == "待确认":
                            p["currentFocus"] = refinement["currentFocus"]
                        print(f"    {repo_id}: {old} → {new_stage} (confidence={confidence})")
                    else:
                        print(f"    {repo_id}: kept {p['stage']} (low confidence={confidence})")
            print(f"  ✅ LLM refinement done")

    # 按 operationStatus 排序: 进行中 > 待启动 > 已暂停 > 已废弃
    op_order = {"进行中": 0, "待启动": 1, "已暂停": 2, "已废弃": 3}
    projects.sort(key=lambda p: (op_order.get(p["operationStatus"], 9), p["name"]))

    # 如果没有同步 issues，保留现有 tasks
    if not with_issues:
        all_tasks = existing.get("tasks", [])

    return {
        "projects": projects,
        "conditions": existing_conditions,
        "tasks": all_tasks,
    }


def _next_stage(stage: str) -> str:
    stages = ["需求拆解", "验证中", "试运行(MVP)", "正式上线(PROD)"]
    try:
        idx = stages.index(stage)
        return stages[min(idx + 1, len(stages) - 1)]
    except ValueError:
        return "验证中"


def main():
    parser = argparse.ArgumentParser(description="Auto-sync GitHub repos → data.json")
    parser.add_argument("--write", action="store_true", help="写入 data.json（默认 dry-run）")
    parser.add_argument("--with-issues", action="store_true", help="同时同步 issues 为 tasks")
    parser.add_argument("--llm", action="store_true", help="用 LLM 精修不确定的阶段判断")
    args = parser.parse_args()

    data = sync_projects(with_issues=args.with_issues, use_llm=args.llm)

    print(f"\n{'='*50}")
    print(f"Projects: {len(data['projects'])}")
    for p in data["projects"]:
        emoji = EMOJI_MAP.get(p["id"], "\U0001f4e6")
        print(f"  {emoji} {p['name']:30s} {p['stage']:16s} {p['operationStatus']:6s} captain={p['captain']}")
    print(f"Tasks: {len(data['tasks'])}")
    print(f"Conditions: {len(data['conditions'])}")

    if args.write:
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"\n✅ Written to {DATA_FILE}")
    else:
        print(f"\n🔍 Dry-run. Use --write to save.")


if __name__ == "__main__":
    main()
