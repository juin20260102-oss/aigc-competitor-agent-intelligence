# GitHub Actions + R2 部署

此部署方式不运行常驻服务器。GitHub Actions 每天启动一次临时 Ubuntu Runner，恢复 R2 中的运行基线，执行 Agent，然后把新的运行产物写回同一个私有 R2 桶。

## Cloudflare R2

创建一个 Standard 存储类别的私有桶，例如 `aigc-competitor-agent-runtime`。不要为该桶配置公共访问或自定义公开域名。

GitHub Actions 使用 Cloudflare API Token 调用 R2 REST API。Token 需要在目标账户拥有至少 `Workers R2 Storage Write` 权限；只验证 Token 有效并不代表它拥有 R2 权限。

## GitHub Secrets 与 Variables

在仓库 **Settings → Secrets and variables → Actions** 设置：

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账户 ID |
| Secret | `CLOUDFLARE_API_TOKEN` | 具备 R2 读写权限的 Cloudflare API Token |
| Secret | `R2_BUCKET` | 私有 R2 桶名 |
| Secret | `DASHSCOPE_API_KEY` | 模型 API Key |
| Secret | `WECOM_WEBHOOK` | 可选的企业微信机器人地址 |
| Variable | `OPENAI_BASE_URL` | 已允许的 OpenAI 兼容模型端点 |
| Variable | `MODEL_NAME` | 模型名称 |
| Variable | `AGENT_SCHEDULE_ENABLED` | 设置为 `true` 后才启用每日定时运行 |

不要把以上 Secret 写入仓库、Workflow 文件或 `.env.example`。

## 运行与成本控制

工作流文件为 `.github/workflows/daily-monitor.yml`。默认在北京时间 09:30 触发，同时可从 Actions 页面手动执行。

它设置了 30 分钟 GitHub Job 上限、900 秒 Agent 上限、最多 20 次逻辑模型调用和 120,000 Token。R2 同步采用“先上传对象、最后上传哈希清单”的顺序；恢复时逐文件校验 SHA-256，失败时拒绝使用损坏的基线。

运行产物不会提交回 Git。R2 桶保持私有；请在 Cloudflare 用量页面设置提醒，并定期检查存储量。默认本地仅保留最近 30 次完整证据运行，但远端对象不会被同步脚本自动删除。

## 首次验证

配置完 Secrets 后，在 GitHub 的 **Actions → Daily competitor monitor → Run workflow** 手动运行一次。确认日志中的“恢复基线”“运行日报”“上传运行文件”均成功，再等待定时任务。

定时任务默认关闭。只有在首次手动验证成功后，才将 `AGENT_SCHEDULE_ENABLED` 设置为 `true`；这样可避免凭据未配置时每天产生失败任务。
