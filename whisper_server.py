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

# Flask-SocketIOのrequestオブジェクトの型を拡張
class SocketIORequest:
    sid: str

def xxxx():
    app = Flask(__name__)
    #app.config['SECRET_KEY'] = 'secret!'
    socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60)

    # 各接続ごとに専用のwhisper_procを管理
    client_procs:dict[str,MlxWhisperProcess] = {}

    @app.route('/')
    def whisper_page():
        return send_from_directory('static', 'whisper.html')

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
        except Exception as ex:
            emit('error', {'error': str(ex)})

    @socketio.on('audio_data')
    def handle_audio_data(blob:bytes):
        """WebSocketで受信した音声データを該当クライアントのwhisper_procに送信"""
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            whisper_proc = client_procs.get(client_id)
            if whisper_proc is not None:
                whisper_proc.write(blob)
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
            print(f"Error handling audio data for client {client_id}: {str(e)}")
            emit('error', {'error': str(e)})
        #emit('status', {'message': 'Whisper process stopped for client'})

    return app,socketio

def main():
    try:
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
