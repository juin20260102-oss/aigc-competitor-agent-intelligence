# 运行与恢复手册

## 日常运行

先复制 `.env.example` 为 `.env`，填入允许的模型端点与 API Key。日常可从 Streamlit 工作台启动，也可以执行：

```powershell
python step3_agent.py
```

程序会取得运行锁；若已有实例在执行，第二个实例会退出而不会并发写入快照或证据。

## 运行产物

每次完整运行会创建 `runtime/runs/<run_id>/`。目录中包含抓取原文、规范化正文、截图（如抓取成功）、结构化分析、`events.jsonl`、`run_summary.json` 和 `manifest.json`。清单列出文件 SHA-256，可用于人工审计。

若运行超时或异常，已获得的产物会以失败清单固化；不会覆盖先前成功运行。通过 `runtime/data/latest_run.json` 可定位最近一次成功完成的运行。

## 恢复与迁移

旧的 `data/snapshots/*_latest.json` 可迁移为不可变证据：

```powershell
python migrate_legacy_evidence.py
python migrate_legacy_evidence.py --apply
```

第一条为预检，第二条仅复制并校验哈希，源文件不删除、不修改，也不会更新 `latest_run.json`。

## 预算与保留

建议先以默认预算运行。遇到成本或时长压力时，优先降低 `MAX_MODEL_CALLS`、`MAX_TOTAL_TOKENS` 或启用较少站点；避免简单提高并发。

证据保留默认关闭。只有在确认磁盘空间和审计周期后，才设置 `EVIDENCE_RETENTION_DAYS` 或 `EVIDENCE_MAX_RUNS` 为正数。该策略仅清理已有 `manifest.json` 的完成运行，未完成运行会保留以便排查。

## 发布检查

发布前在 Windows 环境执行：

```powershell
python -m pip install -r requirements.lock
python -m pip check
python -m ruff check .
python -m unittest discover -s tests -v
python -m compileall -q .
```

CI 使用相同的离线测试流程，不会执行真实抓取、调用模型或推送企业微信。
