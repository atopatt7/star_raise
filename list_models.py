"""
list_models.py — 列出你的 Gemini API 帳號下所有可用模型
用途：當 generate_assets.py 出現 404 模型不存在時，先跑這個確認正確名稱。

用法：
  python list_models.py
"""

import os
import sys

try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("請先執行：pip install google-genai")

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    API_KEY = input("請輸入 Gemini API Key：").strip()

print("\n各 API 版本下的圖片相關模型：\n")

for api_ver in ["v1alpha", "v1beta", "v1"]:
    try:
        client = genai.Client(
            api_key=API_KEY,
            http_options=types.HttpOptions(api_version=api_ver),
        )
        all_models = list(client.models.list())
        image_models = [
            m.name for m in all_models
            if any(kw in m.name.lower() for kw in ["image", "imagen", "flash", "vision"])
        ]
        print(f"  [{api_ver}]  共 {len(all_models)} 個模型，圖片相關 {len(image_models)} 個：")
        for name in sorted(image_models):
            print(f"    • {name}")
        if not image_models:
            print("    （無）")
    except Exception as e:
        print(f"  [{api_ver}]  錯誤：{e}")
    print()

print("─" * 50)
print("請將正確的模型名稱（短名，斜線後的部分）")
print("填入 generate_assets.py 的 CANDIDATE_MODELS 清單第一位。")
