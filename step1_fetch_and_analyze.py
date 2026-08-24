"""
第一步：跑通最小闭环
流程：输入一个竞品网址 → 抓取页面内容 → 大模型分析总结 → 打印结果

跑之前先做两件事：
1. pip install crawl4ai openai python-dotenv
2. crawl4ai-setup  （crawl4ai 需要这一步初始化浏览器）
3. 把 .env.example 复制成 .env，填入你的 OPENAI_API_KEY 和模型配置
"""

import sys
import os
import asyncio
import base64
from openai import OpenAI
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 加载 .env 文件里的环境变量（你的 API Key 存在那里）
load_dotenv()


def get_llm_client() -> tuple[OpenAI, str]:
    """获取 OpenAI 兼容客户端与模型配置"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("MODEL_NAME", "qwen3.7-flash")

    if not api_key:
        raise ValueError("未检测到 API Key，请在 .env 文件中配置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY")

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


# ── 第一部分：抓取网页与截图 ────────────────────────────────────

async def fetch_page(url: str) -> tuple[str, str | None]:
    """
    用 crawl4ai 抓取指定网址，同时捕获渲染截图。
    返回 (markdown文本, 截图本地路径)
    """
    print(f"正在抓取：{url}")
    screenshot_dir = os.path.join("data", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    screenshot_path = os.path.join(screenshot_dir, f"{domain}_latest.png")
    
    try:
        run_config = CrawlerRunConfig(screenshot=True)
        async with AsyncWebCrawler() as crawler:
            result = await asyncio.wait_for(crawler.arun(url=url, config=run_config), timeout=25.0)
    except asyncio.TimeoutError:
        raise RuntimeError(f"抓取超时 (25s)，目标网站 {url} 响应过慢或连接受阻")
    
    if not result.success:
        raise RuntimeError(f"抓取失败：{result.error_message}")
    
    saved_screenshot = None
    if getattr(result, "screenshot", None):
        try:
            img_data = base64.b64decode(result.screenshot)
            with open(screenshot_path, "wb") as f:
                f.write(img_data)
            saved_screenshot = screenshot_path
            print(f"网页截图已保存：{screenshot_path}")
        except Exception as e:
            print(f"截图保存失败：{e}")

    md_text = result.markdown.raw_markdown if hasattr(result.markdown, "raw_markdown") else str(result.markdown)
    print(f"抓取成功，内容长度：{len(md_text)} 字符")
    return md_text, saved_screenshot


# ── 第二部分：让大模型分析内容（防幻觉与严格证据归因） ────────────

def analyze_with_llm(page_content: str, url: str, screenshot_path: str | None = None) -> str:
    """
    把抓取到的页面内容发给大模型，提取关键信息并强制附带证据。
    """
    client, model = get_llm_client()

    prompt = f"""你是一名严谨的 AIGC 领域资深产品分析师。下面是从竞品网站真实抓取的页面内容。

网址：{url}

页面内容：
{page_content[:8000]}  

【防幻觉与证据溯源原则】：
1. 严禁凭空臆测任何功能、参数或商业模式；页面未提及的信息请直接标注“页面未披露”，严禁脑补。
2. 每一句结论、核心功能或亮点后，必须紧跟【依据：页面原文“...”】或相关链接（摘录页面中真实出现的标语、按钮名称、价格数字或宣传语，字数 10~30 字）。

请从产品运营视角分析这个产品，按以下结构输出：

## 1. 产品定位
- （一句话说清楚这个产品是做什么的，目标用户是谁）【依据：页面原文“...”】

## 2. 核心功能
- （列出 3-5 个最主要的功能点，每个功能点必须附带真实原文依据）【依据：页面原文“...”】

## 3. 差异化亮点
- （相比同类产品，这个产品有什么特别之处，严禁空泛词汇）【依据：页面原文“...”】

## 4. 商业化与运营细节
- （UI 设计风格、定价策略、收费模式、获客引导等；若页面无价格则标注“定价未公开”）【依据：页面原文“...”】

请简洁严谨，确保每条结论均有据可查。"""

    print(f"正在调用大模型 ({model}) 进行防幻觉证据归因分析...")

    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    analysis_text = response.choices[0].message.content
    if screenshot_path:
        analysis_text += f"\n\n> 📸 网页截图存证路径：`{screenshot_path}`"
    return analysis_text


# ── 第三部分：保存结果 ───────────────────────────────────────────

def save_result(url: str, analysis: str):
    """
    把分析结果保存成文本文件，统一存放在 reports/single/ 目录下。
    """
    output_dir = os.path.join("reports", "single")
    os.makedirs(output_dir, exist_ok=True)
    
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    filename = os.path.join(output_dir, f"result_{domain}.txt")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"来源：{url}\n")
        f.write("=" * 50 + "\n\n")
        f.write(analysis)
    
    print(f"结果已保存到：{filename}")


# ── 主函数 ───────────────────────────────────────────────────────

async def main():
    target_url = "https://www.midjourney.com"

    # 第一步：抓取与截图
    page_content, screenshot_path = await fetch_page(target_url)

    # 第二步：证据归因分析
    analysis = analyze_with_llm(page_content, target_url, screenshot_path)

    # 第三步：打印 + 保存
    print("\n" + "=" * 50)
    print("分析结果：")
    print("=" * 50)
    print(analysis)

    save_result(target_url, analysis)


if __name__ == "__main__":
    asyncio.run(main())

