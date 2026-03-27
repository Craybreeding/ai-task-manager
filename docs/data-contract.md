# AI Captain 数据契约

## 1. 分层原则

不要让 React 页面直接消费 GitHub 或飞书的原始字段。

统一约定三层：

1. `source records`
   来自 GitHub Projects、GitHub Actions、飞书 Bitable、健康检查脚本。
2. `unified snapshot`
   后端整理后的单项目快照，供前端直接消费。
3. `ui view model`
   前端按页面需要做轻量转换，但不再理解源平台细节。

## 2. 现有 `github_sync.py` 输出

当前脚本已具备的字段：

- `github_id`
- `title`
- `status`
- `assignees`
- `html_url`
- `updated_at`

这批字段适合落到统一模型中的 `work_items`。

对应关系：

| github_sync.py | unified snapshot |
|---|---|
| `github_id` | `work_items[].external_id` |
| `title` | `work_items[].title` |
| `status` | `work_items[].status` |
| `assignees` | `work_items[].owners` |
| `html_url` | `work_items[].source_url` |
| `updated_at` | `work_items[].updated_at` |

## 3. 飞书项目主表需要补齐的字段

GitHub 不会天然提供这些项目经营字段，必须从飞书主表补：

- `project_id`
- `project_name`
- `captain`
- `sponsor`
- `stage`
- `target_launch_date`
- `success_score`
- `quality_score`
- `ops_score`
- `weekly_progress`
- `business_impact`

## 4. 推荐的统一接口

前端只接一个聚合接口：

```json
{
  "generated_at": "2026-03-24T13:00:00+08:00",
  "projects": [
    {
      "id": "captain-hireflow",
      "name": "AI 招聘助手",
      "captain": "马田野",
      "sponsor": "妃姐-stephy",
      "stage": "operate",
      "status": "amber",
      "target_launch_date": "2026-04-12",
      "success_score": 72,
      "quality_score": 61,
      "ops_score": 68,
      "weekly_progress": "已接近正式交付...",
      "business_impact": "本周覆盖 59 份简历...",
      "work_items": [],
      "milestones": [],
      "eval_metrics": [],
      "ops_signals": []
    }
  ]
}
```

## 5. 聚合逻辑建议

### 项目层

来自飞书 `项目主表`。

### 任务层

来自 GitHub Project + 飞书手工录入任务。

### 质量层

来自 Eval 表和测试结果。

### 运维层

来自健康检查脚本、部署状态和异常记录。

## 6. 前端当前状态

当前 React 原型使用本地 mock data，字段结构已经贴近统一快照。

因此后续真正接数据时，只需要：

1. 把聚合脚本产出 JSON。
2. 用 `fetch('/api/projects/snapshot')` 替换 mock data。
3. 保持 `Project` 类型不变或只做增量扩展。
