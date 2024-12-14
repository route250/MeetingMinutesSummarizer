import sys, os
import time
import asyncio
from typing import cast
import threading
from dotenv import load_dotenv
from openai import OpenAI

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

from whisper_transcribe import MlxWhisperProcess
from text_processing import summarize_text,translate_text

# Flask-SocketIOのrequestオブジェクトの型を拡張
class SocketIORequest:
    sid: str

def create_app():
    app = Flask(__name__)
    #app.config['SECRET_KEY'] = 'secret!'
    socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, async_mode='threading')

    # 各接続ごとに専用のwhisper_procを管理
    client_procs: dict[str, MlxWhisperProcess] = {}
    # 各クライアントのスレッドを管理
    client_threads: dict[str, threading.Thread] = {}

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
    def handle_audio_data(blob: bytes):
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

    @app.route('/process_audio', methods=['POST'])
    def process_audio_route():
        try:
            data = request.get_json()
            text = data.get('text', '')
            mode = data.get('mode', 'summary')  # デフォルトは要約モード
            
            if mode == 'off':
                return jsonify({"response": ""})
                
            if mode == 'summary':
                answer = summarize_text(text)
            else:  # translation mode
                answer = translate_text(text)
            
            return jsonify({"response": answer})
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app, socketio

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
        ssl_context = None
        app, socketio = create_app()
        socketio.run(app, host='0.0.0.0', port=port, ssl_context=ssl_context, debug=True)
    except Exception as ex:
        print(f"{ex}")

if __name__ == '__main__':
    main()
