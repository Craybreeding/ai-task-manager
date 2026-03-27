# AI Captain — Agent 协作规范

> 请把下面的「GitHub 工作规范」贴到你负责的项目 `CLAUDE.md` 底部。
> Agent (Claude Code / Codex) 会自动遵循，看板刷新就能拉到最新状态。

---

## GitHub 工作规范

- 开始做一个功能/修 bug 前，先创建 GitHub Issue
- Issue 标题要清晰描述任务（例：「修复 PDF 导出截断问题」）
- 用 label 标注类型：bug / feature / ops / blocked
- 如果任务被卡住，加 `blocked` label 并在 comment 说明原因
- 完成后通过 PR 关联 Issue（PR 描述里写 `Closes #123`）
- PR merge 后 Issue 自动关闭
