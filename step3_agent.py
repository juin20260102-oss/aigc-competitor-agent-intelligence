# -*- coding: utf-8 -*-
"""
第三步：完整 Agent 工作流（自动清理弹窗 + 深度渲染与高清截屏 + 稳健高并发版）
"""

import sys
import os
import re
import asyncio
import json
import httpx
import base64
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import TypedDict
from openai import AsyncOpenAI
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv(override=True)

# ── 目录规范定义 ──────────────────────────────────────────────────
DATA_DIR = "data"
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
REPORT_DIR = "reports"
COMPETITORS_CONFIG_PATH = os.path.join(DATA_DIR, "competitors.json")

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ── 默认兜底竞品清单 ───────────────────────────────────────────────
DEFAULT_COMPETITOR_URLS = [
    "https://ai.699pic.com",
    "https://www.konggeai.com",
    "https://www.keevx.com",
    "https://rhtv.runninghub.cn",
    "https://www.oiioii.tv/home",
    "https://www.piccopilot.com",
    "https://www.gaoding.com",
    "https://marketing.k-fashionshop.com",
    "https://www.skildart.cn",
    "https://m.gaoding.com",
    "https://hailuoai.com",
    "https://klingai.com",
    "https://www.liblib.tv",
    "https://hs.quantv.com",
    "https://www.yiketu.com",
    "https://jihegeo.com",
]

# 通用弹窗与遮罩层自动清理 JavaScript 脚本
POPUP_DISMISS_JS = """
try {
    const closeBtns = document.querySelectorAll('[class*="close"], [class*="Close"], button[aria-label*="close"], button[aria-label*="Close"], .ant-modal-close, .el-dialog__headerbtn, .modal-close');
    closeBtns.forEach(btn => {
        if (btn && btn.offsetParent !== null) {
            try { btn.click(); } catch(e){}
        }
    });
    const masks = document.querySelectorAll('.ant-modal-mask, .ant-modal-wrap, .el-overlay, .modal-backdrop, [class*="modal-mask"], [class*="overlay"]');
    masks.forEach(m => {
        if (m) m.style.display = "none";
    });
} catch(e) {}
"""

def load_competitor_urls() -> list[str]:
    """从 data/competitors.json 加载所有处于启用状态的竞品网址"""
    if os.path.exists(COMPETITORS_CONFIG_PATH):
        try:
            with open(COMPETITORS_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                urls = [item["url"].strip() for item in data if item.get("enabled", True) and item.get("url")]
                if urls:
                    return list(dict.fromkeys(urls))
        except Exception:
            pass
    return DEFAULT_COMPETITOR_URLS

# 企业微信机器人 Webhook（可选，不填则跳过推送）
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")


# ── Token 统计追踪器 ──────────────────────────────────────────────

@dataclass
class TokenTracker:
    prompt_tokens: int = 0
    cached_prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage):
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", 0) or (prompt + completion)
        
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details:
            cached = getattr(details, "cached_tokens", 0) or 0
        if not cached:
            cached = getattr(usage, "cached_tokens", 0) or 0

        self.prompt_tokens += prompt
        self.cached_prompt_tokens += cached
        self.completion_tokens += completion
        self.total_tokens += total

    @property
    def uncached_prompt_tokens(self) -> int:
        return max(0, self.prompt_tokens - self.cached_prompt_tokens)

    def summary_markdown(self) -> str:
        return f"""### 📊 本次监控 Token 消耗统计
| 指标类别 | 消耗 Token 数量 | 说明 |
| :--- | :--- | :--- |
| **未命中缓存输入 (Uncached Input)** | `{self.uncached_prompt_tokens:,}` | 实际计费标准输入 Token |
| **命中缓存输入 (Prompt Cache Hit)** | `{self.cached_prompt_tokens:,}` | 享受缓存优惠/极低价 Token |
| **输出生成 (Completion Output)** | `{self.completion_tokens:,}` | 模型生成的分析与日报 Token |
| **总计消耗 (Total Tokens)** | **`{self.total_tokens:,}`** | 本次监控全流程总 Token |
"""


def get_async_llm_client() -> tuple[AsyncOpenAI, str]:
    """获取异步 OpenAI 兼容客户端与模型配置"""
    load_dotenv(override=True)
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("MODEL_NAME", "qwen3.7-flash")

    if not api_key:
        raise ValueError("未检测到 API Key，请在 .env 文件中配置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return client, model


# ── 工具函数 ─────────────────────────────────────────────────────

def get_site_key(url: str) -> str:
    """根据 URL 生成安全的文件名标识，保留子域名与路径特征"""
    clean = re.sub(r"^https?://", "", url).rstrip("/")
    clean = re.sub(r"[^\w\-.]", "_", clean)
    return clean

def get_snapshot_path(site_key: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{site_key}_latest.json")

def load_last_snapshot(site_key: str) -> dict | None:
    path = get_snapshot_path(site_key)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_snapshot(site_key: str, url: str, content: str, profile: str | None = None, screenshot_path: str | None = None, update_record: dict | None = None):
    """保存快照与竞品完整档案"""
    existing = load_last_snapshot(site_key) or {}
    history = existing.get("update_history", [])
    if update_record:
        history.append(update_record)

    snapshot = {
        "url": url,
        "content": content,
        "profile": profile or existing.get("profile"),
        "screenshot_path": screenshot_path or existing.get("screenshot_path"),
        "captured_at": datetime.now().isoformat(),
        "update_history": history
    }
    with open(get_snapshot_path(site_key), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def extract_latest_change(entry: str) -> str:
    """仅提取本次变化段，避免宏观总结把历史基准画像误当成今日动态。"""
    marker = "#### 【最新版本迭代与动态追踪】"
    if marker not in entry:
        return "未识别到结构化变化段，需人工复核。"
    return entry.split(marker, 1)[1].strip()[:1200]


# ── State：LangGraph 共享状态 ────────────────────────────────────

class AgentState(TypedDict):
    urls: list[str]                    # 要监控的网址列表
    crawled_contents: dict[str, str]   # 抓取结果：{url: 内容}
    crawled_screenshots: dict[str, str]# 网页截图：{url: 截图路径}
    crawl_errors: dict[str, str]       # 抓取失败或异常的记录：{url: 错误信息}
    comparisons: dict[str, str]        # 分析/对比结果：{url: 分析文本}
    first_time_urls: list[str]         # 属于首次收录的网址列表
    token_usage: dict                  # Token 统计数据
    daily_report: str                  # 最终汇总日报
    should_push: bool                  # 是否需要推送


# ══════════════════════════════════════════════════════════════════
# LangGraph 节点
# ══════════════════════════════════════════════════════════════════

# ── 节点 1：智能并发抓取、自动关弹窗与高清截图 ────────────────────

async def crawl_all_node(state: AgentState) -> dict:
    urls_to_crawl = state["urls"]
    print(f"\n[节点1] 开始并发抓取与截图 {len(urls_to_crawl)} 个网站（3 并发控制 + 自动清理弹窗）...")
    sem = asyncio.Semaphore(3)

    async with AsyncWebCrawler() as crawler:
        async def fetch_one(url: str) -> tuple[str, str | None, str | None, str | None]:
            async with sem:
                site_key = get_site_key(url)
                screenshot_path = os.path.join(SCREENSHOT_DIR, f"{site_key}_latest.png")
                try:
                    run_config = CrawlerRunConfig(
                        screenshot=True,
                        delay_before_return_html=2.5,
                        screenshot_wait_for=1.5,
                        js_code=POPUP_DISMISS_JS,
                        page_timeout=35000
                    )
                    result = await asyncio.wait_for(crawler.arun(url=url, config=run_config), timeout=40.0)
                    if result.success:
                        md_text = result.markdown.raw_markdown if hasattr(result.markdown, "raw_markdown") else str(result.markdown)
                        saved_screenshot = None
                        if getattr(result, "screenshot", None):
                            try:
                                img_data = base64.b64decode(result.screenshot)
                                with open(screenshot_path, "wb") as f:
                                    f.write(img_data)
                                saved_screenshot = screenshot_path
                            except Exception:
                                pass

                        if len(md_text.strip()) < 50:
                            err_msg = f"页面正文过短 ({len(md_text.strip())} 字符)，疑似触发反爬或客户端重度JS渲染未完成"
                            print(f"  [异常] {url}：{err_msg}")
                            return url, None, saved_screenshot, err_msg

                        print(f"  [成功] {url} ({len(md_text)} 字符, 截图: 已存)")
                        return url, md_text, saved_screenshot, None
                    else:
                        print(f"  [失败] {url}：{result.error_message}")
                        return url, None, None, result.error_message
                except asyncio.TimeoutError:
                    print(f"  [超时] {url}：抓取超时 (40s)")
                    return url, None, None, "抓取超时 (40s)"
                except Exception as e:
                    print(f"  [异常] {url}：{str(e)}")
                    return url, None, None, str(e)

        results = await asyncio.gather(*[fetch_one(url) for url in urls_to_crawl])

    crawled = {}
    screenshots = {}
    errors = {}
    for url, content, shot, error in results:
        if content:
            crawled[url] = content
            if shot:
                screenshots[url] = shot
        else:
            errors[url] = error or "未知异常"
            if shot:
                screenshots[url] = shot

    print(f"抓取完成：成功 {len(crawled)} 个，失败/异常 {len(errors)} 个，截图 {len(screenshots)} 张")
    return {"crawled_contents": crawled, "crawled_screenshots": screenshots, "crawl_errors": errors}


# ── 节点 2：并发双轨解析（基准画像持久化 + 增量版本追踪） ───────

async def compare_all_node(state: AgentState) -> dict:
    print(f"\n[节点2] 开始并发执行大模型双轨解析与对比（基准画像+增量追踪）...")
    client, model = get_async_llm_client()
    tracker = TokenTracker()

    comparisons = {}
    first_time_urls = []
    screenshots = state.get("crawled_screenshots", {})
    llm_sem = asyncio.Semaphore(4)

    async def process_one_site(url: str, content: str) -> tuple[str, str, bool, object]:
        site_key = get_site_key(url)
        last = load_last_snapshot(site_key)
        shot_path = screenshots.get(url)
        has_baseline_profile = last is not None and bool(last.get("profile"))

        if not has_baseline_profile:
            prompt = f"""你是一名严谨的 AIGC 领域资深产品分析师。这是该竞品网站的基准深度建档分析，请根据抓取的真实页面内容对其进行深度画像分析。

网址：{url}

页面内容：
{content[:7000]}

【防幻觉与证据溯源原则（极重要）】：
1. 严禁凭空推断或捏造功能；每条结论后必须紧跟【依据：页面原文“...”】（摘录页面真实存在的按钮名称、标语、价格或宣传语，字数 10~30 字）。
2. 涉及价格、算力额度、版本号或限制条件的，必须 100% 提取自原文；页面未提及的请直接标明“【依据：页面未披露】”，严禁脑补。

请按以下结构输出结构化分析：
#### 【产品基准深度画像】
- **产品定位**：（一句话说明产品定位及目标人群）【依据：页面原文“...”】
- **核心功能**：（列出 3-5 个核心功能特性，均附真实原文依据）【依据：页面原文“...”】
- **差异化亮点**：（与同类竞品相比的特色优势与壁垒，附依据）【依据：页面原文“...”】
- **商业/运营细节**：（UI风格、定价收费模式、引导策略等；无价格标“定价未公开”）【依据：页面原文“...”】
- **竞争力评级**：（S/A/B/C，并附 1-2 句简评）"""

            async with llm_sem:
                response = await client.chat.completions.create(
                    model=model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}]
                )
            profile_text = response.choices[0].message.content

            full_entry = f"""{profile_text}

#### 【最新版本迭代与动态追踪】
- **版本状态**：首次纳入监控建档，已建立基线档案。
- **存证截图**：`{shot_path}`"""

            save_snapshot(site_key, url, content, profile=profile_text, screenshot_path=shot_path)
            print(f"  [完成建档] {url}")
            return url, full_entry, True, response.usage

        else:
            prompt = f"""你是一名 AIGC 产品分析师，负责追踪竞品的产品动态。

网址：{url}
上次抓取时间：{last['captured_at'][:16]}
本次抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

【上次内容】
{last['content'][:3500]}

【本次内容】
{content[:3500]}

【防幻觉要求】：
1. 只列出两版内容中确实存在文本、功能或价格变动的部分，严禁虚构。
2. 发现的每一处新增或调整必须标注【依据：本次新增原文“...”】。若无明显改动请如实写“本次无明显变化”。

请对比两次内容，找出发生了哪些实质性变化。按以下结构输出：
#### 【最新版本迭代与动态追踪】
- **变化摘要**：（一句话总结本次更新情况，如“本次无明显变化”或“发现 X 处调整”）
- **新增内容**：（本次出现、上次没有的内容，没有写“无”）【依据：...】
- **删除/调整**：（上次有、本次下线或修改的内容，没有写“无”）【依据：...】
- **运营参考**：（对我们产品侧/运营侧的跟进建议，无变化写“暂无”）"""

            async with llm_sem:
                response = await client.chat.completions.create(
                    model=model,
                    max_tokens=800,
                    messages=[{"role": "user", "content": prompt}]
                )
            diff_text = response.choices[0].message.content

            full_entry = f"""{last['profile']}

{diff_text}
- **存证截图**：`{shot_path}`"""

            update_record = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "summary": diff_text[:200]
            }
            save_snapshot(site_key, url, content, profile=last["profile"], screenshot_path=shot_path, update_record=update_record)
            print(f"  [完成比对] {site_key}")
            return url, full_entry, False, response.usage

    site_inputs = list(state["crawled_contents"].items())
    tasks = [process_one_site(url, content) for url, content in site_inputs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for (source_url, _), result in zip(site_inputs, results):
        if isinstance(result, Exception):
            print(f"  [分析失败] {source_url}：{result}")
            comparisons[source_url] = "#### 【最新版本迭代与动态追踪】\n- **状态**：模型分析失败，已保留抓取结果，请人工复核或稍后重试。"
            continue
        url, entry, is_first, usage = result
        comparisons[url] = entry
        if is_first:
            first_time_urls.append(url)
        tracker.add(usage)

    return {
        "comparisons": comparisons,
        "first_time_urls": first_time_urls,
        "token_usage": asdict(tracker)
    }


# ── 节点 3：生成每日竞品汇总日报（LLM 宏观洞察 + 16 站点全景拼装 + 异常底部分离） ────

async def generate_report_node(state: AgentState) -> dict:
    print(f"\n[节点3] 汇总生成竞品日报（LLM 宏观提炼 + 全量竞品双轨拼装）...")
    client, model = get_async_llm_client()
    
    tracker = TokenTracker(**state.get("token_usage", {}))

    sites_brief = ""
    for url, result in state["comparisons"].items():
        sites_brief += f"\n- **站点**：{url}\n{extract_latest_change(result)}\n"

    macro_prompt = f"""你是 AIGC 竞品监控团队的核心资深分析师。以下是今日所有成功监控站点的核心摘要：

{sites_brief}

请只根据上方“本次变化段”输出以下两部分，不得把历史产品画像当成今日动态，也不得预测页面证据之外的行业趋势。首次纳入监控只表示建立基线，不代表竞品今日发布了新功能。若证据不足，请明确写“需人工复核”。格式严格遵循 Markdown：

## 🌟 今日重点提炼
（提炼 1-3 条有本次变化文本支持的重点；若没有足够证据则如实说明）

## 💡 产品与运营行动建议
（基于上述变化提出 2-4 条可验证的参考建议，并与事实结论区分）
"""

    response = await client.chat.completions.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": macro_prompt}]
    )
    tracker.add(response.usage)

    macro_content = response.choices[0].message.content.strip()

    summary_part = macro_content
    action_part = ""
    if "## 💡 产品与运营行动建议" in macro_content:
        parts = macro_content.split("## 💡 产品与运营行动建议")
        summary_part = parts[0].strip()
        action_part = "## 💡 产品与运营行动建议\n" + parts[1].strip()

    competitors_section = f"## 📊 竞品全景监测看板（基准画像 + 最新动态追踪 · 共 {len(state['comparisons'])} 个站点）\n\n"
    for i, (url, result) in enumerate(state["comparisons"].items(), 1):
        competitors_section += f"### 🔗 [{i}] {url}\n\n{result}\n\n---\n\n"

    error_section = ""
    if state["crawl_errors"]:
        error_section += "## ⚠️ 监控异常与抓取失败站点说明\n"
        error_section += "> 以下站点由于触发反爬拦截、页面超时或动态渲染未完成未能提取有效正文，已保留其历史档案，将在下次监控中自动重试：\n\n"
        error_section += "| 异常站点 | 失败原因 / 诊断说明 |\n"
        error_section += "| :--- | :--- |\n"
        for url, err in state["crawl_errors"].items():
            error_section += f"| `{url}` | {err} |\n"
        error_section += "\n---\n\n"

    today_str = datetime.now().strftime('%Y年%m月%d日')
    final_report = f"""# AIGC 竞品监控日报 · {today_str}

> 本报告由模型基于网页抓取结果生成，用于提高信息整理效率；引用、变化判断与行动建议均需人工复核。

{summary_part}

---

{competitors_section}
{action_part}

---

{error_section}{tracker.summary_markdown()}
"""

    print("日报生成完成！共包含 " + str(len(state['comparisons'])) + " 个完整竞品板块")
    print(tracker.summary_markdown())

    report_path = os.path.join(REPORT_DIR, f"daily_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"日报已保存至：{report_path}")

    has_substantive = bool(state["first_time_urls"]) or any(
        "无明显变化" not in r and "无实质性变化" not in r
        for r in state["comparisons"].values()
    )

    return {
        "daily_report": final_report,
        "token_usage": asdict(tracker),
        "should_push": has_substantive and bool(WECOM_WEBHOOK)
    }


# ── 节点 4：推送到企业微信 ──────────────────────────────────────

async def push_to_wecom_node(state: AgentState) -> dict:
    if not state.get("should_push"):
        print("[节点4] 本次跳过企业微信推送（未配置 Webhook 或无实质性变化）")
        return {}

    print(f"\n[节点4] 正在推送日报至企业微信...")
    webhook = WECOM_WEBHOOK
    date_str = datetime.now().strftime("%Y-%m-%d")

    content = f"### 🚀 AIGC 竞品监控日报（{date_str}）\n\n" + state["daily_report"][:4000]

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook, json=payload, timeout=10.0)
            res_json = resp.json()
            if res_json.get("errcode") == 0:
                print("企业微信推送成功！")
            else:
                print(f"企业微信推送失败：{res_json.get('errmsg')}")
    except Exception as e:
        print(f"企业微信推送异常：{e}")

    return {}


# ── 构建 LangGraph 工作流 ─────────────────────────────────────────

def build_competitor_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("crawl_all", crawl_all_node)
    workflow.add_node("compare_all", compare_all_node)
    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("push_to_wecom", push_to_wecom_node)

    workflow.set_entry_point("crawl_all")
    workflow.add_edge("crawl_all", "compare_all")
    workflow.add_edge("compare_all", "generate_report")
    workflow.add_edge("generate_report", "push_to_wecom")
    workflow.add_edge("push_to_wecom", END)

    return workflow.compile()


# ── 主入口 ───────────────────────────────────────────────────────

async def main():
    urls = load_competitor_urls()
    print("=" * 60)
    print(f"竞品监控 Agent 启动 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"当前生效监控清单：共 {len(urls)} 个竞品网站")
    print("=" * 60)

    agent = build_competitor_agent()

    initial_state: AgentState = {
        "urls": urls,
        "crawled_contents": {},
        "crawled_screenshots": {},
        "crawl_errors": {},
        "comparisons": {},
        "first_time_urls": [],
        "token_usage": {},
        "daily_report": "",
        "should_push": False
    }

    final_state = await agent.ainvoke(initial_state)

    print("\n" + "=" * 60)
    print("【完整竞品日报已保存至 reports 目录】")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
