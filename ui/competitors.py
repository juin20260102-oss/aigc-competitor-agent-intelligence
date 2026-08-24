"""
UI 模块：竞品清单配置与深度档案库 (Competitor Suite - SaaS 旗舰版)
"""

import os
import glob
import json
import asyncio
import streamlit as st
from datetime import datetime

DATA_DIR = "data"
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
COMPETITORS_CONFIG_PATH = os.path.join(DATA_DIR, "competitors.json")

DEFAULT_COMPETITOR_DATA = [
  {"url": "https://ai.699pic.com", "name": "摄图AI", "category": "图像/设计", "enabled": True},
  {"url": "https://www.konggeai.com", "name": "空格AI", "category": "电商商拍/模特", "enabled": True},
  {"url": "https://www.keevx.com", "name": "Keevx", "category": "AI视频量产/本地化", "enabled": True},
  {"url": "https://rhtv.runninghub.cn", "name": "RunningHub", "category": "多模型聚合/工作流", "enabled": True},
  {"url": "https://www.oiioii.tv/home", "name": "Oiioii", "category": "动画智能体/Agent", "enabled": True},
  {"url": "https://www.piccopilot.com", "name": "PicCopilot", "category": "电商营销设计", "enabled": True},
  {"url": "https://www.gaoding.com", "name": "稿定设计", "category": "综合设计平台", "enabled": True},
  {"url": "https://marketing.k-fashionshop.com", "name": "K-Fashion", "category": "服装电商营销", "enabled": True},
  {"url": "https://www.skildart.cn", "name": "Skildart", "category": "创意艺术设计", "enabled": True},
  {"url": "https://m.gaoding.com", "name": "稿定移动端", "category": "移动端创作", "enabled": True},
  {"url": "https://hailuoai.com", "name": "海螺AI", "category": "大模型视频/生图", "enabled": True},
  {"url": "https://klingai.com", "name": "快手可灵", "category": "前沿视频大模型", "enabled": True},
  {"url": "https://www.liblib.tv", "name": "哩布哩布AI", "category": "开源模型社区/生图", "enabled": True},
  {"url": "https://hs.quantv.com", "name": "QuanTV", "category": "AI视频工具", "enabled": True},
  {"url": "https://www.yiketu.com", "name": "一刻图", "category": "智能修图/抠图", "enabled": True},
  {"url": "https://jihegeo.com", "name": "几何AIGC", "category": "3D/生成设计", "enabled": True}
]


def load_competitors_config() -> list[dict]:
    """读取 data/competitors.json 监控清单，如为空或不存在则自动基于默认清单初始化"""
    if os.path.exists(COMPETITORS_CONFIG_PATH):
        try:
            with open(COMPETITORS_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass
    save_competitors_config(DEFAULT_COMPETITOR_DATA)
    return DEFAULT_COMPETITOR_DATA


def save_competitors_config(items: list[dict]):
    """保存监控清单到 data/competitors.json"""
    with open(COMPETITORS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def load_all_competitor_profiles():
    """读取所有已建档的竞品快照"""
    files = glob.glob(os.path.join(SNAPSHOT_DIR, "*_latest.json"))
    profiles = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8-sig") as fp:
                data = json.load(fp)
                url = data.get("url", "")
                captured_at = data.get("captured_at", "")
                profile = data.get("profile", "")
                shot_path = data.get("screenshot_path", "")
                history = data.get("update_history", [])

                rating = "未定"
                if "S级" in profile or "S 级" in profile or "评级：S" in profile or "评级: S" in profile:
                    rating = "S"
                elif "A级" in profile or "A 级" in profile or "评级：A" in profile or "评级: A" in profile:
                    rating = "A"
                elif "B级" in profile or "B 级" in profile or "评级：B" in profile or "评级: B" in profile:
                    rating = "B"
                elif "C级" in profile or "C 级" in profile or "评级：C" in profile or "评级: C" in profile:
                    rating = "C"

                profiles.append({
                    "file": f,
                    "url": url,
                    "rating": rating,
                    "captured_at": captured_at[:16].replace("T", " ") if captured_at else "近期",
                    "profile": profile,
                    "shot_path": shot_path,
                    "history": history,
                    "content_len": len(data.get("content", ""))
                })
        except Exception:
            pass

    return sorted(profiles, key=lambda x: (x["rating"], x["url"]))


def render_competitors():
    st.markdown('<div class="hero-title">🌐 竞品监控清单与深度档案中心</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">在此管理每日监控的目标站点清单（增删改查）、查看各站点的商业基准画像与版本演进履历</div>', unsafe_allow_html=True)

    tab_list, tab_profiles = st.tabs([
        "📋 监控站点清单管理 (增/删/改/启停)",
        "🏷️ 竞品深度画像与历史档案库"
    ])

    # ══════════════════════════════════════════════════════════════════
    # 选项卡 1：监控站点清单编辑器 (增删改查)
    # ══════════════════════════════════════════════════════════════════
    with tab_list:
        st.markdown("### 📋 当前监控站点清单配置")
        st.caption("Agent 每次执行监控时，将全量并发抓取下方处于「启用」状态的所有竞品网站。")

        config_items = load_competitors_config()

        # 1. 快捷添加与批量编辑按钮栏
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        with col_btn1:
            show_single_add = st.button("➕ 添加单个竞品", use_container_width=True, type="primary")
        with col_btn2:
            show_bulk_edit = st.button("📝 批量粘贴/编辑清单", use_container_width=True)

        # 2. 单个添加表单抽屉
        if show_single_add:
            st.markdown("""
<div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px; padding: 1.2rem; margin: 1rem 0;">
    <div style="font-weight: 700; color: #1E40AF; font-size: 1rem; margin-bottom: 0.5rem;">➕ 添加新竞品站点到监控清单</div>
</div>
""", unsafe_allow_html=True)
            with st.form("add_single_competitor_form"):
                new_url = st.text_input("竞品官网 URL (必填)：", placeholder="https://www.example.com")
                c_name, c_cat = st.columns(2)
                with c_name:
                    new_name = st.text_input("竞品简称/别名 (选填)：", placeholder="如：Midjourney")
                with c_cat:
                    new_cat = st.text_input("业务分类 (选填)：", placeholder="如：AI生图/视频")
                
                submitted = st.form_submit_button("💾 确认添加并保存", type="primary")
                if submitted:
                    if not new_url or not new_url.startswith("http"):
                        st.error("请输入合法的网址（以 http:// 或 https:// 开头）")
                    else:
                        existing_urls = [it["url"].lower().rstrip("/") for it in config_items]
                        if new_url.lower().rstrip("/") in existing_urls:
                            st.warning(f"⚠️ 该网址 `{new_url}` 已存在于监控清单中！")
                        else:
                            config_items.append({
                                "url": new_url.strip(),
                                "name": new_name.strip() or new_url.replace("https://", "").split("/")[0],
                                "category": new_cat.strip() or "AIGC工具",
                                "enabled": True
                            })
                            save_competitors_config(config_items)
                            st.success(f"🎉 成功添加竞品：{new_url}")
                            st.rerun()

        # 3. 批量多行文本编辑抽屉
        if show_bulk_edit:
            st.markdown("""
<div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 12px; padding: 1.2rem; margin: 1rem 0;">
    <div style="font-weight: 700; color: #0F172A; font-size: 1rem; margin-bottom: 0.5rem;">📝 批量网址多行文本编辑器</div>
    <div style="font-size: 0.85rem; color: #64748B;">直接在下方文本框中粘贴或编辑网址列表（每行一个 URL），点击保存将自动同步监控清单：</div>
</div>
""", unsafe_allow_html=True)
            current_urls_text = "\n".join([it["url"] for it in config_items])
            
            with st.form("bulk_urls_form"):
                bulk_text = st.text_area("竞品网址清单 (每行一个)：", value=current_urls_text, height=220)
                bulk_submit = st.form_submit_button("💾 保存并更新全部清单", type="primary")
                
                if bulk_submit:
                    lines = [line.strip() for line in bulk_text.splitlines() if line.strip() and line.strip().startswith("http")]
                    new_items = []
                    for u in lines:
                        matched = next((it for it in config_items if it["url"].lower().rstrip("/") == u.lower().rstrip("/")), None)
                        if matched:
                            new_items.append(matched)
                        else:
                            domain = u.replace("https://", "").replace("http://", "").split("/")[0]
                            new_items.append({
                                "url": u,
                                "name": domain,
                                "category": "AIGC工具",
                                "enabled": True
                            })
                    save_competitors_config(new_items)
                    st.success(f"🎉 批量更新成功！当前有效监控站点数：{len(new_items)} 个")
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # 4. 可视化清单表格与逐项控制
        st.write(f"当前清单共包含 **{len(config_items)}** 个竞品站点：")
        
        has_changed = False
        items_to_delete = []

        for idx, item in enumerate(config_items):
            c_check, c_name, c_url, c_cat, c_del = st.columns([1, 2, 4, 2, 1])
            
            with c_check:
                new_state = st.checkbox(
                    "启用",
                    value=item.get("enabled", True),
                    key=f"chk_{idx}",
                    help="勾选表示加入每日定时监控，取消则跳过"
                )
                if new_state != item.get("enabled", True):
                    item["enabled"] = new_state
                    has_changed = True

            with c_name:
                st.markdown(f"**{item.get('name', '未命名')}**")

            with c_url:
                st.markdown(f"[`{item['url']}`]({item['url']})")

            with c_cat:
                st.caption(f"🏷️ {item.get('category', 'AIGC')}")

            with c_del:
                if st.button("🗑️", key=f"del_{idx}", help=f"删除 {item['url']}"):
                    items_to_delete.append(idx)

        # 处理删除与变更
        if items_to_delete:
            for d_idx in sorted(items_to_delete, reverse=True):
                del config_items[d_idx]
            save_competitors_config(config_items)
            st.success("✅ 已删除选中的竞品站点！")
            st.rerun()

        if has_changed:
            save_competitors_config(config_items)
            st.toast("✅ 清单状态已自动保存", icon="💾")

    # ══════════════════════════════════════════════════════════════════
    # 选项卡 2：竞品深度画像与历史档案库
    # ══════════════════════════════════════════════════════════════════
    with tab_profiles:
        st.markdown("### 🏷️ 已建档竞品商业基准深度画像")
        st.caption("查看各竞品的定位、3-5项核心功能矩阵、差异化壁垒、商业模式细节及历次版本更新履历。")

        profiles = load_all_competitor_profiles()

        col_search, col_filter = st.columns([3, 2])
        with col_search:
            kw = st.text_input("🔍 搜索竞品域名、功能关键字：", placeholder="如：电商, 模特, 视频, 定价...", key="search_profiles")
        with col_filter:
            rating_filter = st.selectbox("⭐ 按竞争力评级筛选：", ["全部评级", "S 级 (核心标杆)", "A 级 (主力竞品)", "B 级 (参考竞品)", "C 级 (常规观察)"], key="filter_profiles")

        filtered = profiles
        if kw:
            filtered = [p for p in filtered if kw.lower() in p["url"].lower() or kw in p["profile"]]
        if rating_filter != "全部评级":
            target_r = rating_filter[0]
            filtered = [p for p in filtered if p["rating"] == target_r]

        st.caption(f"当前共匹配呈现 **{len(filtered)}** 份独立竞品商业档案：")

        for idx, item in enumerate(filtered):
            badge_html = {
                "S": '<span class="badge-s">S 级 核心标杆</span>',
                "A": '<span class="badge-a">A 级 主力竞品</span>',
                "B": '<span class="badge-b">B 级 参考竞品</span>',
                "C": '<span class="badge-b">C 级 常规观察</span>'
            }.get(item["rating"], '<span class="badge-b">未评级</span>')

            with st.expander(f"📌 {item['url']}  ｜  评级：{item['rating']} 级  ｜  🕒 档案建档：{item['captured_at']}", expanded=(idx == 0)):
                col_text, col_media = st.columns([3, 2])
                
                with col_text:
                    st.markdown(f"### 🏷️ 深度画像分析 {badge_html}", unsafe_allow_html=True)
                    if item["profile"]:
                        st.markdown(item["profile"])
                    else:
                        st.info("💡 尚未生成基准深度画像，可在控制台运行一次监控更新。")

                    if item["history"]:
                        st.markdown("---")
                        st.markdown("#### 📜 历史版本迭代履历：")
                        for h in item["history"]:
                            st.caption(f"🕒 **{h.get('time', '未知时间')}**")
                            st.markdown(f"> {h.get('summary', '无明显变化')}")

                with col_media:
                    st.markdown("### 📸 页面视觉存证截图")
                    domain = item["url"].replace("https://", "").replace("http://", "").split("/")[0]
                    shot_file = item["shot_path"]
                    if not shot_file or not os.path.exists(shot_file):
                        shot_file = os.path.join(SCREENSHOT_DIR, f"{domain}_latest.png")
                    
                    if shot_file and os.path.exists(shot_file):
                        st.image(shot_file, caption=f"高清渲染截屏 · {domain}", use_container_width=True)
                    else:
                        st.caption("暂无本地存证截图")

                    st.markdown(f"""
<div style="margin-top: 1rem; padding: 0.8rem; background: #F1F5F9; border-radius: 8px; border: 1px solid #E2E8F0;">
    <div style="font-size: 0.8rem; color: #475569;">🔗 竞品在线直达：</div>
    <div style="font-weight: 600; margin-top: 2px;"><a href="{item['url']}" target="_blank" style="color: #2563EB; text-decoration: none;">访问 {domain} 官方主页 ↗</a></div>
</div>
""", unsafe_allow_html=True)