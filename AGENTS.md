# AI Captain Agents

## 1. Main Agent (The Orchestrator)
- **Role**: Coordinates data flow between GitHub, Feishu, and the dashboard.
- **Responsibilities**: 
  - Runs ingestion workers.
  - Generates weekly digests.
  - Sends real-time alerts.

## 2. Ingestion Workers (Python/OpenClaw)
- **github_sync.py**: Syncs GitHub Issues/Projects to Bitable.
- **feishu_event_sync.py**: Processes Feishu group chat commands and updates Bitable.
- **metrics_collector.py**: Collects quality and performance metrics.

## 3. Deployment & Quality Agents (Claude Code)
- **Role**: Handles implementation, deployment tasks, and automated testing.
- **Tools**: `gh`, `uv`, `playwright`.

## 4. 协作规范（所有 Agent 必须遵循）

每个项目的 `CLAUDE.md` 应包含以下规范，确保看板能自动同步：

```
## GitHub 工作规范
- 开始做一个功能/修 bug 前，先创建 GitHub Issue
- Issue 标题要清晰描述任务（例：「修复 PDF 导出截断问题」）
- 用 label 标注类型：bug / feature / ops / blocked
- 如果任务被卡住，加 blocked label 并在 comment 说明原因
- 完成后通过 PR 关联 Issue（PR 描述里写 Closes #123）
- PR merge 后 Issue 自动关闭
```

详细说明见 `docs/GITHUB_WORKFLOW.md`。
