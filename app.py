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
        
        # 議事録生成用のプロンプトを作成
        prompt = """
以下の会議の音声認識テキストから、重要なポイントを抽出して議事録を作成してください。
フォーマットは以下の通りです：

# 議事録
## 主要な議題と決定事項
- 重要なポイントを箇条書きで記載

## 詳細な議論内容
- 議論の流れや重要な発言を要約して記載

音声認識テキスト：
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", #モデルは gpt-4o-miniを使って下さいよ！
            messages=[
                {"role": "system", "content": "あなたは会議の議事録作成の専門家です。"},
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
