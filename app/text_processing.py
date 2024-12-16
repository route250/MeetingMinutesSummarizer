from flask import request, jsonify
from openai import OpenAI

def summarize_text(text: str) -> str:
    """音声認識テキストを要約する"""
    prompt = """
以下の音声認識テキストを簡潔に要約してください。
重要なポイントを箇条書きで記載し、できるだけ簡潔にまとめてください。

# 要約
- 重要なポイントを箇条書きで記載

音声認識テキスト：
"""
    system_role = "あなたは音声テキストの要約の専門家です。重要なポイントを簡潔にまとめます。"
    # OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_role},
            {"role": "user", "content": prompt + text}
        ]
    )
    
    return response.choices[0].message.content or ""

def translate_text(text: str) -> str:
    """テキストを日本語に翻訳する"""
    prompt = """
以下のテキストを自然な日本語に翻訳してください。
文脈を考慮し、分かりやすい日本語になるよう心がけてください。

原文：
"""
    system_role = "あなたは優秀な翻訳者です。自然で分かりやすい日本語訳を提供します。"
    # OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_role},
            {"role": "user", "content": prompt + text}
        ]
    )
    
    return response.choices[0].message.content or ""

