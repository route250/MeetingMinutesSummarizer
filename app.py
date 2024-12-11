from flask import Flask, request, jsonify
from openai import OpenAI
import os
from dotenv import load_dotenv

# setting.envファイルが存在する場合、環境変数として読み込む
if os.path.exists('setting.env'):
    load_dotenv('setting.env')

app = Flask(__name__)

# OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
client = OpenAI()

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        data = request.get_json()
        text = data.get('text', '')
        mode = data.get('mode', 'summary')  # デフォルトは要約モード
        
        if mode == 'off':
            return jsonify({"response": ""})
            
        if mode == 'summary':
            # 要約生成用のプロンプト
            prompt = """
以下の音声認識テキストを簡潔に要約してください。
重要なポイントを箇条書きで記載し、できるだけ簡潔にまとめてください。

# 要約
- 重要なポイントを箇条書きで記載

音声認識テキスト：
"""
            system_role = "あなたは音声テキストの要約の専門家です。重要なポイントを簡潔にまとめます。"
            
        else:  # translation mode
            # 翻訳用のプロンプト
            prompt = """
以下のテキストを自然な日本語に翻訳してください。
文脈を考慮し、分かりやすい日本語になるよう心がけてください。

原文：
"""
            system_role = "あなたは優秀な翻訳者です。自然で分かりやすい日本語訳を提供します。"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", #モデルは gpt-4o-miniを使って下さいよ！
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt + text}
            ]
        )
        
        answer = response.choices[0].message.content
        return jsonify({"response": answer})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = 5007
    ssl_key='.certs/server.key'
    ssl_cert='.certs/server.crt'
    if os.path.exists(ssl_key) and os.path.exists(ssl_cert):
        ssl_context=(ssl_cert,ssl_key)
    else:
        ssl_context=None
    app.run(host='0.0.0.0', port=port, ssl_context=ssl_context, debug=True)
