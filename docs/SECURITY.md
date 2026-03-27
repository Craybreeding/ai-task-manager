# SECURITY.md

## 1. 数据安全 (Data Security)
- **密钥管理**: API 密钥存储在环境变量或密钥管理器中。
- **权限管理 (ACL)**:
  - 飞书 Bitable 设置为 Captain (ou_f191c7a1be499f8d7f517335697c269f) 管理员权限。
  - GitHub 权限通过个人访问令牌 (PAT) 授权。

## 2. 系统安全 (System Security)
- **执行安全**: 使用 ACP (Claude Code) 时，限制文件读写权限到指定目录。
- **Ingestion 安全**: 对传入的飞书消息和 GitHub Event 进行基本格式校验，防止注入攻击。

## 3. 合规性 (Compliance)
- 不采集非业务相关的私人数据。
- 日志保留期策略：保留 30 天核心日志供溯源。
