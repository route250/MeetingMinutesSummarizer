from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from multiprocessing import Process, Pipe
import subprocess
import os
import numpy as np
from numpy.typing import NDArray
from pydub import AudioSegment
import io
from whisper_transcribe import MlxWhisperProcess
import tempfile
from typing import cast, Union, Any
import threading
from queue import Queue
import time
import asyncio
from dotenv import load_dotenv
from openai import OpenAI

# Flask-SocketIOのrequestオブジェクトの型を拡張
class SocketIORequest:
    sid: str

def xxxx():
    app = Flask(__name__)
    #app.config['SECRET_KEY'] = 'secret!'
    socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, async_mode='threading')

    # 各接続ごとに専用のwhisper_procを管理
    client_procs:dict[str,MlxWhisperProcess] = {}
    # 各クライアントのスレッドを管理
    client_threads:dict[str,threading.Thread] = {}

    def read_transcription(client_id: str, whisper_proc: MlxWhisperProcess):
        """whisper_procからの結果を読み取ってクライアントに送信するタスク"""
        try:
            while client_id in client_procs:  # クライアントが接続中の間だけ実行
                try:
                    # 非同期関数を同期的に実行
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(whisper_proc.read())
                    if result:
                        fixed_text, temp_text = result
                        # 確定したテキストを送信
                        if fixed_text or temp_text:
                            print(f"Sending fixed text to {client_id}: {fixed_text} {temp_text}")
                            socketio.emit('transcription', {'text': ' '.join(fixed_text), 'tmp': ' '.join(temp_text)}, to=client_id)
                    loop.close()
                except Exception as ex:
                    print(f"Error in read_transcription loop for client {client_id}: {str(ex)}")
                time.sleep(0.1)  # 短い待機時間を入れてCPU使用率を抑える
        except Exception as ex:
            print(f"Error in read_transcription for client {client_id}: {str(ex)}")
        finally:
            client_threads.pop(client_id, None)

    @app.route('/')
    def whisper_page():
        return send_from_directory('static', 'transcribe_mlxwhisper.html')

    @app.route('/transcribe_webrtc')
    def whisper_pagea():
        return send_from_directory('static', 'transcribe_webrtc.html')

    @app.route('/transcribe_mlxwhisper')
    def whisper_pageb():
        return send_from_directory('static', 'transcribe_mlxwhisper.html')

    @app.route('/static/<path:path>')
    def send_static(path):
        return send_from_directory('static', path)

    @socketio.on('connect')
    def handle_connect():
        """クライアント接続時にwhisper_procを生成して起動"""
        try:
            # requestをSocketIORequest型としてキャスト
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            print(f'Client connected: {client_id}')
            if client_id not in client_procs:
                whisper_proc = MlxWhisperProcess()
                whisper_proc.start()
                client_procs[client_id] = whisper_proc
                # 結果読み取りスレッドを開始
                thread = threading.Thread(
                    target=read_transcription,
                    args=(client_id, whisper_proc),
                    daemon=True
                )
                thread.start()
                client_threads[client_id] = thread
        except Exception as ex:
            print(f"Error in handle_connect: {str(ex)}")
            emit('error', {'error': str(ex)})

    @socketio.on('audio_data')
    def handle_audio_data(blob:bytes):
        """WebSocketで受信した音声データを該当クライアントのwhisper_procに送信"""
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            whisper_proc = client_procs.get(client_id)
            if whisper_proc is not None:
                whisper_proc.append_audio(blob)
        except Exception as e:
            print(f"Error handling audio data for client {client_id}: {str(e)}")
            emit('error', {'error': str(e)})

    @socketio.on('disconnect')
    def handle_disconnect():
        """クライアント切断時にwhisper_procを停止"""
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            print(f'Client disconnected: {client_id}')
            whisper_proc = client_procs.pop(client_id, None)
            if whisper_proc:
                whisper_proc.stop()
        except Exception as e:
            print(f"Error handling disconnect for client {client_id}: {str(e)}")
            emit('error', {'error': str(e)})

    # OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
    client = OpenAI()

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

    return app,socketio

def main():
    try:
        import tracemalloc
        tracemalloc.start()

        # setting.envファイルが存在する場合、環境変数として読み込む
        if os.path.exists('setting.env'):
            load_dotenv('setting.env')

        port = 5008  # 既存のapp.pyと異なるポート番号を使用
        # ssl_key='.certs/server.key'
        # ssl_cert='.certs/server.crt'
        # if os.path.exists(ssl_key) and os.path.exists(ssl_cert):
        #     ssl_context=(ssl_cert,ssl_key)
        # else:
        #     ssl_context=None
        ssl_context=None
        app,socketio = xxxx()
        socketio.run(app, host='0.0.0.0', port=port, ssl_context=ssl_context, debug=True)
    except Exception as ex:
        print(f"{ex}")

if __name__ == '__main__':
    main()
