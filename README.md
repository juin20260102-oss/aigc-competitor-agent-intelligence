# AIGC 竞品监控 Agent & 可视化情报管理后台

基于 **LangGraph + Crawl4AI + 大语言模型 (Qwen / DeepSeek)** 构建的自动化竞品情报感知系统。支持 16+ 竞品网站并发抓取、网页高清截图存证、基准商业画像持久化、增量版本对比、防幻觉原文证据溯源以及可视化 Web GUI 控制台。

## 🌟 核心特性

- 🖥️ **现代可视化 Web GUI 控制台**：基于 Streamlit 构建，提供监控大盘、历史日报中心、竞品档案库、视觉存证画廊与全局配置。
- 🏷️ **双轨全景报告（画像+增量）**：永久持久化竞品基准画像，每日对比时同时呈现完整档案与最新版本动态。
- 🛡️ **严格防幻觉与证据链溯源**：每条结论均强制附带【依据：页面原文“...”】与本地渲染高清截图存证。
- ⚡ **高性能异步全并发架构**：单实例共享浏览器引擎 + AsyncOpenAI 16 站点全量并行处理，1 分钟内完成全流程。
- ⚠️ **异常站点底部分离**：反爬拦截或 JS 纯壳空页面独立置底表格说明，绝不污染主体分析报告。
- ⏰ **全自动定时调度**：原生支持 Windows 任务计划程序每天定时静默执行并可选推送到企业微信群。

---

## 📁 项目目录结构

```text
Agent_Daily_Report/
├── app.py                        # Streamlit 可视化 GUI 主入口应用
├── run_gui.bat                   # 🖥️ 双击一键启动可视化 Web 控制台
├── run_daily.bat                 # ⏰ 定时调度执行批处理脚本
├── setup_scheduler.ps1           # ⏰ Windows 任务计划一键注册脚本
│
├── ui/                           # GUI 模块组件目录
│   ├── dashboard.py              # 监控大盘与一键运行面板
│   ├── reports.py                # 每日情报中心与企业微信推送
│   ├── competitors.py            # 竞品档案库与清单管理
│   ├── gallery.py                # 视觉存证截图画廊
│   └── settings.py               # 全局模型与 API 配置
│
├── step1_fetch_and_analyze.py    # 单站抓取与深度画像测试脚本
├── step2_compare.py              # 单站增量对比与双轨报告测试脚本
├── step3_agent.py                # 完整 LangGraph 多竞品监控核心调度引擎
│
├── data/                         # 【数据层】
│   ├── snapshots/                # 各竞品历史基准画像与快照 (*_latest.json)
│   └── screenshots/              # 网页高清渲染截图 (*_latest.png)
│
├── reports/                      # 【报告层】
│   ├── daily_report_YYYYMMDD.md  # 每日综合竞品监控日报
│   └── single/                   # 单站测试报告
│
├── .env                          # 本地环境变量配置（含 API Key）
├── .env.example                  # 环境变量模板
└── requirements.txt              # 依赖清单
```

---

## 🚀 快速启动

### 方式 1：一键启动可视化 GUI 控制台（最推荐）

直接在项目文件夹中双击运行：
👉 **`run_gui.bat`**

或者在命令行运行：
```bash
streamlit run app.py
```
浏览器将自动弹出控制台界面（`http://localhost:8501`）。

---

### 方式 2：命令行静默运行 Agent

```bash
python step3_agent.py
```
