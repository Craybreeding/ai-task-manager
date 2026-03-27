# AI Captain - AI 项目全生命周期管理系统

> 核心理念：不仅是“任务管理”，而是覆盖从研发事实、执行状态、到上线运维与成功衡量的全生命周期管理系统。

## 1. 逻辑架构图 (Data Flow)

```text
GitHub (研发事实层)          Feishu (执行与协作层)
- Issues / Projects         - Bitable (Unified Store)
- Actions / CI Status       - 群消息 / 指令 / 表单
- Deploy Logs               - 周报输入 / 提醒
            │                     │
            ├─────────────────────┘
            ▼
      Ingestion Workers (Python / OpenClaw)
  - github_sync.py (代码与项目同步)
  - feishu_event_sync.py (指令与消息同步)
  - metrics_collector.py (指标与质量采集)
  - weekly_digest.py (周报生成逻辑)
            │
            ▼
    Unified Project Store (Bitable Core)
  - Projects (主表: Captain, Sponsor, Stage, 目标)
  - Work Items (任务明细: GitHub + Feishu + 手工)
  - Milestones (里程碑: 解决“到哪了”)
  - Eval Scores (AI 评分: 解决“行不行”)
  - Ops Health (运维状态: 解决“谁盯着”)
  - Outcome Metric (结果指标: 解决“值不值”)
            │
     ┌──────┴────────────────┐
     ▼                       ▼
React Captain UI (展示层)   Feishu Bots / Cards (触达层)
- Portfolio Overview        - 每日提醒 / DDL 预警
- Project Cockpit           - 交互式周报卡片
- Quality Wall (Eval)       - 异常实时告警
- Ops Console               - 状态快捷更新
```

## 2. 职责分层 (Responsibility)
- **GitHub**: 研发事实层。适合 PR、CI、代码质量、技术交付进度。
- **Feishu**: 执行层。适合负责人（Captain）、截止日期（Deadline）、团队同步、提醒。
- **React**: 展示层。专门看“项目到底行不行”，提供高阶决策视图。
- **Notion**: 知识层。沉淀 PRD、方案、复盘，不放高频变动的执行态任务。

## 3. 核心实体定义 (Entity Model)
- **Project**: 必须包含 Captain、Sponsor、当前阶段、上线 DDL。
- **WorkItem**: 颗粒度任务，支持多源同步。
- **Milestone**: 关键交付节点。
- **EvalMetric**: 针对 AI 项目的特殊指标（准确率、误报率、人工修正率）。
- **OpsHealth**: 在线状态、错误率、延迟、成本。
- **OutcomeMetric**: 业务结果指标（节省人时、转化率提升、ROI）。

## 4. 生命周期管理 (Lifecycle)
1. **Intake (立项)**: 明确 Captain/Sponsor，预设成功指标。
2. **Build (研发)**: 盯着 GitHub CI 和核心 Eval 表现。
3. **Deliver (交付)**: 强制 Checklist 检查，非代码写完就算完。
4. **Operate (运维)**: 关注可用性、回滚、值班响应。
5. **Scale (扩张)**: 评估复用率与接入 ROI。

## 5. 成功衡量体系 (Success Definition)
- **交付成功**: 按时、Checklist 齐备、上线 7 天稳定。
- **业务成功**: 活跃用户、人时节省、转化率。
- **AI 成功**: 准确率、误报率、幻觉率、人工干预度。
- **运维成功**: MTTR、SLA、Token 成本波动。
