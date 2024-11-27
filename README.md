# MeetingMinutesSummarizer

このリポジトリは、簡単な議事録システムのサンプルコードです。Google Chromeの音声認識機能を使用して会話をテキスト化し、LLMを使って議事録を生成します。FlaskとOpenAI APIを利用しています。

## 必要な依存関係

このプロジェクトを実行するには、以下の依存関係が必要です：

- Python 3.x
- 必要なパッケージは `requirements.txt` に記載されています。

## 簡単な使い方

1. リポジトリをクローンします：

   ```bash
   git clone https://github.com/route250/MeetingMinutesSummarizer.git
   cd MeetingMinutesSummarizer
   ```

2. 依存関係をインストールします：

   ```bash
   pip install -r requirements.txt
   ```

3. HTTPS用の自己署名証明書を作成します：
   （マイクを使うにはhttpsサイトでなければならないので）

   ```bash
   ./make_cert.sh
   ```

   ディレクトリ `.certs` に証明書が作成されていることを確認してください。以下のファイルが生成されます：

   ```text
   -rw-rw-r-- 1 neko neko   34 11月 27 11:13 SAN.txt   # 使わない
   -rw-rw-r-- 1 neko neko 1147 11月 27 11:13 server.crt # 証明書
   -rw-rw-r-- 1 neko neko  968 11月 27 11:13 server.csr # 使わない
   -rw------- 1 neko neko 1708 11月 27 11:13 server.key # キー
   ```

4. OpenAIのAPIキーを `setting.env` に設定してください。以下のように記述します：

   ```text:setting.env
   OPENAI_API_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```

5. アプリケーションを実行します：

   ```bash
   python app.py
   ```

6. ブラウザ（推奨：Chrome）で `https://localhost:5000` にアクセス

   マイクを使うにはhttpsサイトでなければならないので、httpsで開いて下さい。

7. 自己署名証明書のため、警告が表示されますが、強行突破してください。

8. マイクの使用許可を求められたら、必ず許可してください。

9. ページが開いたら、音声認識開始ボタンをクリックするだけです。他の操作は必要ありません。

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
