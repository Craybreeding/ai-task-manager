# QUALITY_SCORE.md

## 1. 核心质量指标 (Core Metrics)
- **交付成功**: 
  - 是否按时 (DDL Status)。
  - Checklist 是否齐备 (Checklist Completion Rate)。
  - 上线 7 天是否稳定 (Post-Delivery Stability Index)。

- **业务成功**: 
  - 活跃用户 (Active Users)。
  - 节省人时 (Time Saved per Task)。
  - 转化率提升 (Conversion Uplift)。

- **AI 成功**: 
  - 准确率 (Accuracy Score)。
  - 误报率 (False Positives)。
  - 幻觉率 (Hallucination Rate)。
  - 人工干预度 (Manual Correction Rate)。

## 2. 自动化采集逻辑 (Automation)
- 通过 `metrics_collector.py` 采集。
- 数据存入 Bitable 的 `EvalMetric` 表。
- 展示在 React Captain Dashboard 的 `Quality Wall` 页面。
