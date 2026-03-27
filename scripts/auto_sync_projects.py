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

# 手动覆盖: 支持 name/stage/captain/sponsor/currentFocus/blocker 等字段
# stage 覆盖会强制生效，忽略自动检测和历史值
MANUAL_OVERRIDES: dict[str, dict] = {
    "consumer-insight-v2": {"name": "Consumer Insight v2"},
    "consumer-insights": {"name": "Consumer Insights"},
    "ai-captain-dashboard": {
        "name": "AI Captain Dashboard",
        "stage": "试运行(MVP)",
        "captain": "ggn",
        "sponsor": "ggn",
        "currentFocus": "项目驾驶舱看板，自动从GitHub同步项目状态",
    },
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
    "ai-captain-dashboard": "\U0001f680",
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


def fetch_milestones(repo_name: str) -> list[dict]:
    """读取 GitHub Milestones（含 open + closed）"""
    try:
        raw = run_gh([
            "api", f"repos/{ORG}/{repo_name}/milestones",
            "--method", "GET",
            "-f", "state=all",
            "-f", "per_page=50",
        ])
        return json.loads(raw)
    except subprocess.CalledProcessError:
        return []


def fetch_issues(repo_name: str) -> list[dict]:
    try:
        raw = run_gh([
            "issue", "list", "--repo", f"{ORG}/{repo_name}",
            "--state", "all",
            "--json", "number,title,state,assignees,url,labels,milestone",
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


# Milestone description 里用标签标注 category 和 criteria
# 格式: "category: 功能完善\ncriteria: xxx\nfromStage: 验证中\ntoStage: 试运行(MVP)"
MILESTONE_CATEGORIES = {"功能完善", "质量保障", "运维稳定", "用户验证", "文档规范"}


def milestones_to_conditions(milestones: list[dict], project_id: str, stage: str, target_stage: str) -> list[dict]:
    """把 GitHub Milestones 转成 data.json 的 conditions 格式"""
    conditions = []
    for ms in milestones:
        ms_number = ms.get("number", 0)
        title = ms.get("title", "")
        desc = ms.get("description") or ""
        state = ms.get("state", "open")
        due = ms.get("due_on", "") or ""

        # 从 description 解析结构化字段
        meta = {}
        for line in desc.split("\n"):
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip().lower()] = val.strip()

        category = meta.get("category", "功能完善")
        if category not in MILESTONE_CATEGORIES:
            category = "功能完善"
        criteria = meta.get("criteria", desc.split("\n")[0] if desc else "")
        from_stage = meta.get("fromstage", stage)
        to_stage = meta.get("tostage", target_stage)

        # milestone state → condition status
        if state == "closed":
            cond_status = "done"
        else:
            open_count = ms.get("open_issues", 0)
            closed_count = ms.get("closed_issues", 0)
            if closed_count > 0 and open_count > 0:
                cond_status = "active"
            else:
                cond_status = "pending"

        conditions.append({
            "id": f"ms-{project_id}-{ms_number}",
            "projectId": project_id,
            "name": title,
            "category": category,
            "fromStage": from_stage,
            "toStage": to_stage,
            "status": cond_status,
            "owner": "",  # 从 issues assignees 推断
            "criteria": criteria,
            "issue": "",
            "dueDate": due[:10] if due else "",
        })
    return conditions


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


def llm_generate_conditions(
    project: dict, readme: str, issues: list, existing_tasks: list
) -> tuple[list[dict], list[dict]]:
    """
    用 LLM 为缺少升级路径的项目自动生成 conditions (线) 和 tasks (点)。
    分析项目的 README、issues、当前阶段，生成从 stage → targetStage 的升级条件。
    返回 (conditions, tasks)
    """
    project_id = project["id"]
    stage = project["stage"]
    target = project["targetStage"]
    name = project["name"]
    captain = project.get("captain", "待确认")

    api_key = os.environ.get("MOONSHOT_API_KEY", "sk-Rxy3KtPy16zcpZ1CxQbgZsncjVA9fx64JSOcZ8Cld7CuUWRn")

    readme_short = readme[:800] if readme else "(no README)"
    issues_str = "\n".join(
        f"  - #{i.get('number','')}: {i.get('title','')} [{i.get('state','OPEN')}]"
        for i in issues[:20]
    ) or "(no issues)"

    existing_task_str = "\n".join(
        f"  - {t['title']} [{t['status']}]" for t in existing_tasks[:20]
    ) or "(no existing tasks)"

    prompt = f"""你是一个 AI 项目管理专家。请为以下项目生成从 "{stage}" 升级到 "{target}" 的升级路径。

项目: {name} (id: {project_id})
负责人: {captain}
当前阶段: {stage}
目标阶段: {target}

README:
{readme_short}

GitHub Issues:
{issues_str}

已有任务:
{existing_task_str}

请生成 3-6 个升级条件 (conditions)，每个条件下 1-3 个具体任务 (tasks)。

条件类别 (category) 只能是以下之一: 功能完善, 质量保障, 运维稳定, 用户验证, 文档规范

返回格式 (严格 JSON):
{{
  "conditions": [
    {{
      "name": "条件名称（简短）",
      "category": "功能完善",
      "criteria": "具体达标标准，一句话",
      "status": "pending",
      "tasks": [
        {{
          "title": "具体任务描述",
          "type": "feature/bug/ops/doc"
        }}
      ]
    }}
  ]
}}

规则:
- 根据项目实际情况生成，不要泛泛而谈
- 如果有 GitHub issues，优先把相关 issue 归入对应条件
- 条件应该是从当前阶段到目标阶段的关键里程碑
- 每个条件有清晰的验收标准 (criteria)
- 只返回 JSON，不要其他文字"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.moonshot.cn/v1/chat/completions",
            data=json.dumps({
                "model": "moonshot-v1-32k",
                "temperature": 0.4,
                "max_tokens": 4096,
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
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                print(f"    ⚠ LLM returned no JSON for {project_id}")
                return [], []
            result = json.loads(match.group())

        conditions = []
        tasks = []
        for idx, cond in enumerate(result.get("conditions", []), 1):
            cond_id = f"cond-{project_id}-{idx}"
            conditions.append({
                "id": cond_id,
                "projectId": project_id,
                "name": cond["name"],
                "category": cond.get("category", "功能完善"),
                "fromStage": stage,
                "toStage": target,
                "status": cond.get("status", "pending"),
                "owner": captain,
                "criteria": cond.get("criteria", ""),
                "issue": "",
                "dueDate": "",
            })
            for tidx, task in enumerate(cond.get("tasks", []), 1):
                tasks.append({
                    "id": f"task-{project_id}-{idx}-{tidx}",
                    "projectId": project_id,
                    "conditionId": cond_id,
                    "title": task["title"],
                    "type": task.get("type", "feature"),
                    "status": "pending",
                    "assignee": captain,
                    "url": "",
                })
        return conditions, tasks

    except Exception as e:
        print(f"    ⚠ Condition generation failed for {project_id}: {e}")
        return [], []


def bootstrap_github_project(repo_name: str, stage: str, target_stage: str, captain: str = "") -> bool:
    """
    用 LLM 分析项目，然后直接在 GitHub 上创建 Milestones + Issues。
    之后正常 sync 就能自动读到这些数据。这是 GitHub-first 的做法。
    """
    print(f"\n🚀 Bootstrapping {repo_name} ({stage} → {target_stage})")

    # 1. 收集项目信息
    readme = fetch_readme(repo_name)
    issues = fetch_issues(repo_name)
    commits = fetch_recent_commits(repo_name, 10)
    existing_milestones = fetch_milestones(repo_name)

    if existing_milestones:
        print(f"  ⚠ Already has {len(existing_milestones)} milestones, skipping bootstrap")
        return False

    readme_short = readme[:1200] if readme else "(no README)"
    issues_str = "\n".join(
        f"  - #{i.get('number','')}: {i.get('title','')} [{i.get('state','OPEN')}]"
        for i in issues[:20]
    ) or "(no issues)"
    commits_str = "\n".join(f"  - {c}" for c in commits[:10]) or "(no commits)"

    # 2. 调 LLM 生成 milestones + issues
    api_key = os.environ.get("MOONSHOT_API_KEY", "sk-Rxy3KtPy16zcpZ1CxQbgZsncjVA9fx64JSOcZ8Cld7CuUWRn")

    prompt = f"""你是一个 AI 项目管理专家。请为以下项目规划从 "{stage}" 升级到 "{target_stage}" 的路线图。

项目: {repo_name}
当前阶段: {stage}
目标阶段: {target_stage}

README:
{readme_short}

最近 commits:
{commits_str}

现有 GitHub Issues:
{issues_str}

请生成 3-5 个 GitHub Milestones（升级里程碑），每个 Milestone 下 2-4 个具体 Issue（任务）。

要求:
- Milestone 名称简短有力（如 "核心功能闭环"、"监控告警上线"、"用户反馈收集"）
- 每个 Milestone 的 description 必须包含：
  category: <功能完善|质量保障|运维稳定|用户验证|文档规范>
  criteria: <一句话验收标准>
- Issue 标题要具体、可执行（如 "接入 Sentry 错误监控" 而不是 "添加监控"）
- Issue 必须有 labels 数组（从 feature/bug/ops/doc 中选）
- 根据项目实际内容生成，不要泛泛而谈
- 如果已有 open issues，把它们归到合适的 milestone（通过 existing_issue_number 字段）

返回格式 (严格 JSON):
{{
  "milestones": [
    {{
      "title": "里程碑名称",
      "description": "category: 功能完善\\ncriteria: 验收标准描述",
      "issues": [
        {{
          "title": "具体任务描述",
          "body": "任务详情和背景",
          "labels": ["feature"],
          "existing_issue_number": null
        }}
      ]
    }}
  ]
}}

只返回 JSON。"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.moonshot.cn/v1/chat/completions",
            data=json.dumps({
                "model": "moonshot-v1-32k",
                "temperature": 0.4,
                "max_tokens": 4096,
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
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                print(f"  ⚠ LLM returned no JSON")
                return False
            result = json.loads(match.group())
    except Exception as e:
        print(f"  ⚠ LLM call failed: {e}")
        return False

    # 3. 创建 GitHub Milestones + Issues
    repo_full = f"{ORG}/{repo_name}"
    created_ms = 0
    created_issues = 0

    for ms_data in result.get("milestones", []):
        ms_title = ms_data["title"]
        ms_desc = ms_data.get("description", "")

        # 创建 Milestone
        try:
            ms_json = run_gh([
                "api", f"repos/{repo_full}/milestones",
                "--method", "POST",
                "-f", f"title={ms_title}",
                "-f", f"description={ms_desc}",
                "-f", "state=open",
            ])
            ms_result = json.loads(ms_json)
            ms_number = ms_result["number"]
            created_ms += 1
            print(f"  ✅ Milestone #{ms_number}: {ms_title}")
        except Exception as e:
            print(f"  ⚠ Failed to create milestone '{ms_title}': {e}")
            continue

        # 创建 Issues 并关联到 Milestone (用 milestone 名称，不是 number)
        for issue_data in ms_data.get("issues", []):
            existing_num = issue_data.get("existing_issue_number")

            if existing_num:
                # 更新已有 issue 的 milestone
                try:
                    run_gh([
                        "api", f"repos/{repo_full}/issues/{existing_num}",
                        "--method", "PATCH",
                        "-f", f"milestone={ms_number}",
                    ])
                    print(f"    🔗 Linked existing #{existing_num} → Milestone #{ms_number}")
                except Exception as e:
                    print(f"    ⚠ Failed to link #{existing_num}: {e}")
            else:
                title = issue_data["title"]
                body = issue_data.get("body", "")
                labels = issue_data.get("labels", ["feature"])

                # gh issue create --milestone 接受名称，不是 number
                try:
                    gh_args = [
                        "issue", "create",
                        "--repo", repo_full,
                        "--title", title,
                        "--body", body,
                        "--milestone", ms_title,
                    ]
                    for label in labels:
                        gh_args.extend(["--label", label])
                    run_gh(gh_args)
                    created_issues += 1
                    print(f"    ✅ Issue: {title}")
                except subprocess.CalledProcessError:
                    # label 可能不存在，不带 label 重试
                    try:
                        run_gh([
                            "issue", "create",
                            "--repo", repo_full,
                            "--title", title,
                            "--body", body,
                            "--milestone", ms_title,
                        ])
                        created_issues += 1
                        print(f"    ✅ Issue: {title} (no labels)")
                    except Exception as e2:
                        print(f"    ⚠ Failed to create issue '{title}': {e2}")

    print(f"\n  📊 Created {created_ms} milestones, {created_issues} issues for {repo_name}")
    return created_ms > 0


def issues_to_tasks(issues: list, project_id: str, task_cond_map: dict[str, str] | None = None) -> list[dict]:
    """把 GitHub issues 转成 data.json 的 tasks 格式。
    自动从 issue.milestone 关联到 condition (ms-{projectId}-{milestone_number})。
    """
    if task_cond_map is None:
        task_cond_map = {}
    tasks = []
    for issue in issues:
        assignees = [a.get("login", "") for a in issue.get("assignees", [])]
        display_assignees = [DISPLAY_NAMES.get(a, a) for a in assignees]
        state = issue.get("state", "OPEN")
        status = "done" if state == "CLOSED" else "active"

        labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
        if "blocked" in labels:
            status = "blocked"
        elif state == "OPEN" and not assignees:
            status = "pending"

        # 从 issue.milestone 自动关联 conditionId
        task_id = f"{project_id}-issue-{issue['number']}"
        milestone = issue.get("milestone") or {}
        ms_number = milestone.get("number") if isinstance(milestone, dict) else None
        if ms_number:
            cond_id = f"ms-{project_id}-{ms_number}"
        else:
            cond_id = task_cond_map.get(task_id, "")

        # 从 labels 推断 type
        task_type = "feature"
        for label in labels:
            if label in ("bug", "fix"):
                task_type = "bug"
                break
            elif label in ("ops", "infra", "devops"):
                task_type = "ops"
                break
            elif label in ("doc", "docs", "documentation"):
                task_type = "doc"
                break

        tasks.append({
            "id": task_id,
            "projectId": project_id,
            "conditionId": cond_id,
            "title": issue.get("title", ""),
            "type": task_type,
            "status": status,
            "assignee": ", ".join(display_assignees) or "待确认",
            "url": issue.get("url", ""),
        })
    return tasks


def sync_projects(with_issues: bool = False, use_llm: bool = False, gen_conditions: bool = False) -> dict:
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
        milestones = fetch_milestones(name) if with_issues else []

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

        # override 里的 stage 强制生效，否则保留历史值或用自动检测
        final_stage = override.get("stage") or prev.get("stage") or stage
        final_captain = override.get("captain") or captain

        project = {
            "id": project_id,
            "name": display_name,
            "stage": final_stage,
            "targetStage": override.get("targetStage") or (
                _next_stage(final_stage) if "stage" in override else prev.get("targetStage") or _next_stage(final_stage)
            ),
            "operationStatus": op_status,
            "status": status,
            "sponsor": override.get("sponsor") or prev.get("sponsor") or "待确认",
            "captain": final_captain,
            "blocker": override.get("blocker") or prev.get("blocker", "待确认"),
            "currentFocus": override.get("currentFocus") or prev.get("currentFocus", "待确认"),
            "nextCheckpoint": override.get("nextCheckpoint") or prev.get("nextCheckpoint", "待确认"),
            "latestFeedback": prev.get("latestFeedback", ""),
            "feedbackFrom": prev.get("feedbackFrom", ""),
            "wau": prev.get("wau", 0),
            "weeklyRuns": prev.get("weeklyRuns", 0),
            "hoursSaved": prev.get("hoursSaved", 0),
        }
        projects.append(project)
        cert = "✓" if is_certain else "?"
        print(f"→ {stage} [{cert}] | {op_status} | captain={captain}")

        if with_issues:
            # Milestones → Conditions (GitHub 是唯一数据源)
            if milestones:
                ms_conditions = milestones_to_conditions(milestones, project_id, final_stage, project["targetStage"])
                # 替换该项目的旧条件
                existing_conditions = [c for c in existing_conditions if c["projectId"] != project_id]
                existing_conditions.extend(ms_conditions)
                if ms_conditions:
                    print(f"    📌 {len(ms_conditions)} milestones → conditions")

            # Issues → Tasks (milestone 关联自动通过 issue.milestone 字段)
            if issues:
                raw_tasks = issues_to_tasks(issues, project_id)
                # 如果没有 milestone 关联，用 LLM 匹配到 existing conditions
                unlinked = [t for t in raw_tasks if not t.get("conditionId")]
                proj_conditions = [c for c in existing_conditions if c["projectId"] == project_id]
                if unlinked and proj_conditions and use_llm:
                    print(f"    🔗 Matching {len(unlinked)}/{len(raw_tasks)} unlinked tasks to {len(proj_conditions)} conditions...")
                    task_cond_map = llm_match_tasks_to_conditions(project_id, proj_conditions, unlinked)
                    if task_cond_map:
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

    # Pass 3: 为缺少条件的活跃项目自动生成升级路径
    if gen_conditions:
        proj_map = {p["id"]: p for p in projects}
        projects_with_conditions = {c["projectId"] for c in existing_conditions}
        active_without = [
            p for p in projects
            if p["operationStatus"] == "进行中"
            and p["id"] not in projects_with_conditions
            and p["stage"] != "正式上线(PROD)"  # PROD 不需要升级条件
        ]
        if active_without:
            print(f"\n  🧠 Generating conditions for {len(active_without)} projects...")
            for p in active_without:
                print(f"    📋 {p['name']} ({p['stage']} → {p['targetStage']})...")
                readme = fetch_readme(p["id"].replace("-", "_"))
                if not readme:
                    readme = fetch_readme(p["id"])
                issues = fetch_issues(p["id"].replace("-", "_")) if with_issues else []
                if not issues:
                    issues = fetch_issues(p["id"])
                proj_tasks = [t for t in all_tasks if t["projectId"] == p["id"]]
                new_conds, new_tasks = llm_generate_conditions(p, readme, issues, proj_tasks)
                if new_conds:
                    existing_conditions.extend(new_conds)
                    all_tasks.extend(new_tasks)
                    print(f"    ✅ Generated {len(new_conds)} conditions, {len(new_tasks)} tasks")
                else:
                    print(f"    ⚠ No conditions generated")
            print(f"  ✅ Condition generation done")

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
    parser.add_argument("--gen-conditions", action="store_true", help="用 LLM 为缺少条件的项目自动生成升级路径（仅写 data.json）")
    parser.add_argument("--bootstrap", nargs="*", metavar="REPO",
                        help="用 LLM 分析项目并在 GitHub 上创建 Milestones + Issues。"
                             "不指定 repo 则处理所有缺 milestone 的活跃项目")
    args = parser.parse_args()

    # --bootstrap 模式: LLM → GitHub Milestones + Issues
    if args.bootstrap is not None:
        # 先加载现有数据获取 stage 信息
        existing = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}
        proj_map = {p["id"]: p for p in existing.get("projects", [])}

        if args.bootstrap:
            # 指定了具体 repo
            target_repos = args.bootstrap
        else:
            # 自动检测: 所有活跃、非 PROD、无 milestone 的项目
            repos = fetch_repos()
            target_repos = []
            for repo in repos:
                name = repo["name"]
                if name in EXCLUDE_REPOS:
                    continue
                pid = name.replace("_", "-")
                p = proj_map.get(pid, {})
                if p.get("operationStatus") != "进行中":
                    continue
                if p.get("stage") == "正式上线(PROD)":
                    continue
                ms = fetch_milestones(name)
                if not ms:
                    target_repos.append(name)
            print(f"Found {len(target_repos)} projects without milestones")

        for repo_name in target_repos:
            pid = repo_name.replace("_", "-")
            p = proj_map.get(pid, {})
            stage = p.get("stage", "验证中")
            target = p.get("targetStage", _next_stage(stage))
            captain = p.get("captain", "")
            bootstrap_github_project(repo_name, stage, target, captain)

        print("\n✅ Bootstrap done. Run --write --with-issues to sync into dashboard.")
        return

    data = sync_projects(with_issues=args.with_issues, use_llm=args.llm, gen_conditions=args.gen_conditions)

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
