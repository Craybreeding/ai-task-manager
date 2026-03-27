# GitHub 工作规范（AI Agent 协作版）

> 适用于所有 AI 项目仓库。请将本规范加入项目的 `CLAUDE.md` 或 `AGENTS.md`，确保 Agent（Claude Code / Codex / 其他）遵循。

---

## 核心规则

### 1. Issue 先行
- **开始做功能/修 bug 前，先创建 GitHub Issue**
- Issue 标题清晰描述任务，不要写"修 bug"这种模糊标题
- 好标题：`修复 PDF 导出截断问题`、`添加抖音双平台搜索支持`
- 坏标题：`fix bug`、`update code`、`改一下`

### 2. Label 标注类型
每个 Issue 必须打 label：

| Label | 用途 |
|-------|------|
| `bug` | 修复已有功能的问题 |
| `feature` | 新增功能 |
| `ops` | 运维/部署/基础设施 |
| `blocked` | 任务被卡住（必须在 comment 说明原因） |
| `doc` | 文档更新 |

### 3. 卡住时及时标注
- 加 `blocked` label
- 在 Issue comment 说明卡住原因和需要什么才能解除
- 解除后移除 `blocked` label

### 4. PR 关联 Issue
- PR 描述里写 `Closes #123`（或 `Fixes #123`）
- PR merge 后 Issue 自动关闭
- 一个 PR 可以关联多个 Issue：`Closes #1, Closes #2`

### 5. Commit Message 规范
```
feat(模块): 简要描述
fix(模块): 简要描述
ops(模块): 简要描述
```

---

## 复制粘贴模板

把以下内容直接粘贴到你项目的 `CLAUDE.md` 底部：

```markdown
## GitHub 工作规范
- 开始做一个功能/修 bug 前，先创建 GitHub Issue
- Issue 标题要清晰描述任务（例：「修复 PDF 导出截断问题」）
- 用 label 标注类型：bug / feature / ops / blocked
- 如果任务被卡住，加 blocked label 并在 comment 说明原因
- 完成后通过 PR 关联 Issue（PR 描述里写 Closes #123）
- PR merge 后 Issue 自动关闭
```

---

## 为什么这样做？

项目管理看板（AI Captain）会从 GitHub 自动拉取 Issue/PR 状态。
只要你按规范操作 GitHub，看板就能自动反映进度，不需要额外维护。

- Issue open → 看板显示"进行中"
- Issue 打 blocked label → 看板显示"阻塞"
- PR merge + Issue close → 看板显示"已完成"
