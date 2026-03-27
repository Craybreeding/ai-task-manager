# RELIABILITY.md

## 1. 系统可用性 (Availability)
- **Ingestion Workers**: 定期轮询机制，支持失败重试。
- **Bitable Store**: 飞书基础设施保障，多端同步。
- **React Dashboard**: 静态或轻量部署，保障展示层稳定。

## 2. 核心监控 (Monitoring)
- **MTTR (Mean Time to Recovery)**: 异常检测与报警。
- **SLA**: 核心同步任务的成功率。
- **Token 成本波动**: 异常消耗预警。

## 3. 运维恢复 (Recovery)
- 一旦检测到 API 失败或 5xx 错误，AI 自动尝试切换备用模型或重启服务。
- 定期触发健康检查脚本，确保各模块在线。
