# PRODUCT_SENSE.md

## 1. 核心洞察 (Core Insights)
AI 项目不是简单的软件工程，它包含高度的不确定性和持续的运维成本。传统的任务管理（如 Jira, Trello）只能管「做什么」，管不了「做成什么样」和「上线后行不行」。

## 2. 差异化竞争 (The Differentiation)
- **从任务同步到全生命周期**: 涵盖 Intake, Build, Deliver, Operate, Scale。
- **驾驶舱视角**: 不看任务列表，看「项目健康红绿灯」。
- **AI Native**: AI 不仅是工具，更是管理对象。

## 4. 智能体全量产出定义 (The Agent Output Spectrum)
根据 Captain 火火的最高指令，一个成熟的智能体项目不仅是几行脚本，其产出必须由 AI Captain 进行全量覆盖与管理：

- **代码与测试**:
    - **产品代码与测试**: 业务逻辑源码 + 自动化测试用例。
    - **管理代码仓库本身的脚本**: 用于维护 Repo 结构、自动合入、自动化 Lint 的 `meta-scripts`。
- **工程与发布**:
    - **CI 配置和发布工具**: GitHub Actions, Dockerfile, `nixpacks.toml` 等自动化流水线。
    - **生产仪表板定义文件**: 包含 Bitable 视图配置、React 仪表盘前端代码。
- **知识与决策**:
    - **文档和设计历史**: `ARCHITECTURE.md`, `PRODUCT_SENSE.md`, `DESIGN.md`, 以及决策过程的沉淀。
    - **审阅评论和回复**: 沉淀在 GitHub PR 中的 Code Review 思考和交互历史。
- **质量与工具**:
    - **评估框架**: 针对 AI 能力的 `Eval Metrics` 采集逻辑与测试集。
    - **内部开发者工具**: 为该项目定制的辅助 CLI 或管理脚本。
