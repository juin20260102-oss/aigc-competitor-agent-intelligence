"""
UI 模块：全局系统与安全配置中心 (Settings & Security)
"""

import os
import re
import httpx
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

ENV_FILE = ".env"


def mask_key(key: str) -> str:
    """对 API Key 进行安全掩码脱敏处理，防止明文泄露"""
    if not key:
        return "未配置"
    clean = key.strip()
    if len(clean) <= 8:
        return "••••••••"
    return f"{clean[:4]}{'•' * (len(clean) - 8)}{clean[-4:]}"


def load_env_dict():
    """读取 .env 文件键值对"""
    load_dotenv(override=True)
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY", ""),
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "MODEL_NAME": os.getenv("MODEL_NAME", "qwen3.7-flash"),
        "WECOM_WEBHOOK": os.getenv("WECOM_WEBHOOK", "")
    }


def save_env_dict(data: dict):
    """安全保存键值对到 .env 文件"""
    content = f"""# AIGC 竞品监控 Agent 配置文件
OPENAI_API_KEY={data.get('OPENAI_API_KEY', '')}
DASHSCOPE_API_KEY={data.get('OPENAI_API_KEY', '')}
OPENAI_BASE_URL={data.get('OPENAI_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')}
MODEL_NAME={data.get('MODEL_NAME', 'qwen3.7-flash')}
WECOM_WEBHOOK={data.get('WECOM_WEBHOOK', '')}
"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    load_dotenv(override=True)


def test_wecom_webhook(webhook: str) -> tuple[bool, str]:
    """测试企业微信 Webhook 是否有效"""
    if not webhook:
        return False, "Webhook 链接为空"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### 🔔 AIGC 竞品监控 Agent 测试消息\n\n这是一条来自 **可视化控制台** 的测试推送，恭喜配置成功！\n\n🕒 发送时间：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        }
    }
    try:
        resp = httpx.post(webhook, json=payload, timeout=10.0)
        res = resp.json()
        if res.get("errcode") == 0:
            return True, "推送测试成功！请查看企业微信群。"
        return False, f"推送失败：{res.get('errmsg')}"
    except Exception as e:
        return False, f"网络请求异常：{e}"


def render_settings():
    st.markdown('<div class="hero-title">⚙️ 全局系统与安全中心</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">大语言模型凭证密保管理、模型路由策略与企业微信群推送配置</div>', unsafe_allow_html=True)

    env_data = load_env_dict()
    current_raw_key = env_data["OPENAI_API_KEY"]
    masked_key_str = mask_key(current_raw_key)

    # 1. 密钥安全脱敏提示卡
    st.markdown(f"""
<div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: space-between;">
    <div>
        <div style="color: #166534; font-weight: 700; font-size: 0.95rem;">🔒 API Key 动态脱敏保护已激活</div>
        <div style="color: #15803D; font-size: 0.85rem; margin-top: 2px;">当前生效密钥：<code style="background: rgba(22,101,52,0.1); padding: 2px 8px; border-radius: 4px; font-weight: 600; color: #166534;">{masked_key_str}</code> （密保掩码显示，绝不明文暴露）</div>
    </div>
    <div style="background: #22C55E; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 700;">安全就绪</div>
</div>
""", unsafe_allow_html=True)

    # 2. 配置表单
    with st.form("settings_security_form"):
        st.markdown("### 🤖 1. 模型路由与算法策略")
        
        c1, c2 = st.columns([1, 1])
        with c1:
            models = ["qwen3.7-flash", "qwen-plus", "qwen-max", "deepseek-chat", "deepseek-reasoner", "自定义"]
            current_model = env_data["MODEL_NAME"]
            model_index = models.index(current_model) if current_model in models else len(models) - 1
            
            selected_model = st.selectbox("默认分析大模型：", models, index=model_index, help="推荐 qwen3.7-flash，具备极高的响应速度与提示词缓存价格优惠")
        
        with c2:
            if selected_model == "自定义":
                custom_model_name = st.text_input("输入自定义模型标识：", value=current_model)
                final_model = custom_model_name
            else:
                final_model = selected_model
                st.caption(f"当前生效模型：`{final_model}`")

        st.markdown("---")
        st.markdown("### 🔑 2. 接口地址与密保凭证")

        col_base, col_key = st.columns([1, 1])
        with col_base:
            base_url = st.text_input("OpenAI 兼容 Base URL：", value=env_data["OPENAI_BASE_URL"], help="如阿里云百炼兼容端点：https://dashscope.aliyuncs.com/compatible-mode/v1")

        with col_key:
            new_key_input = st.text_input(
                "更新 API Key (密码输入框)：",
                value="",
                type="password",
                placeholder="留空则保持当前已保存密钥不变",
                help="为了安全，此处默认留空不显示原密钥。如需更换，直接输入新 Key 保存即可。"
            )

        st.markdown("---")
        st.markdown("### 🔔 3. 企业微信群机器人推送")
        wecom_webhook = st.text_input("Webhook 推送链接 (可选)：", value=env_data["WECOM_WEBHOOK"], placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...", help="配置后，每日监控发现实质性变化将自动推送 Markdown 日报至群聊")

        st.markdown("<br>", unsafe_allow_html=True)
        saved = st.form_submit_button("💾 保存全部配置", type="primary", use_container_width=True)

        if saved:
            # 安全逻辑：若用户输入了新 key 则使用新 key；若留空则保留原密钥
            target_key = new_key_input.strip() if new_key_input.strip() else current_raw_key
            
            new_config = {
                "OPENAI_API_KEY": target_key,
                "OPENAI_BASE_URL": base_url.strip(),
                "MODEL_NAME": final_model.strip(),
                "WECOM_WEBHOOK": wecom_webhook.strip()
            }
            save_env_dict(new_config)
            st.success("✅ 配置已安全保存并生效！")
            st.rerun()

    # 3. 独立连通性测试区
    st.markdown("---")
    st.markdown("### 🧪 通知渠道连通性验证")
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.write("点击右侧按钮向已保存的企业微信群发送一条测试卡片：")
    with col_t2:
        if st.button("🔔 发送测试推送", use_container_width=True):
            if not env_data["WECOM_WEBHOOK"]:
                st.warning("⚠️ 请先在上方配置企业微信 Webhook 地址并保存")
            else:
                ok, msg = test_wecom_webhook(env_data["WECOM_WEBHOOK"])
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
