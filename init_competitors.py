import json
import os

COMPETITORS_CONFIG_PATH = os.path.join("data", "competitors.json")

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

with open(COMPETITORS_CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(DEFAULT_COMPETITOR_DATA, f, ensure_ascii=False, indent=2)

print("Saved competitors.json without BOM, count:", len(DEFAULT_COMPETITOR_DATA))
