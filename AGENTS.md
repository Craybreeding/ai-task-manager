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
