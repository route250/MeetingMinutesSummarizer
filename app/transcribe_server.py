import sys, os, json
import time
import base64
from io import BytesIO
import atexit
import asyncio
from asyncio import Task
from typing import cast
import threading
from dotenv import load_dotenv
from openai import OpenAI

from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_socketio import SocketIO, emit

from whisper_transcribe import check_audio, MlxWhisperProcess
from text_processing import summarize_text,translate_text
from bot_server import Bot, VoiceRes

# Flask-SocketIOのrequestオブジェクトの型を拡張
class SocketIORequest:
    sid: str

def calculate_xor_checksum(data: bytes) -> int:
    checksum = 0
    for byte in data:
        checksum ^= byte  # 各バイトをXOR演算
    return checksum

def create_app():
    global_status:bool = True
    app = Flask(__name__)
    #app.config['SECRET_KEY'] = 'secret!'
    socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, async_mode='threading')

    # 各接続ごとに専用のwhisper_procを管理
    client_sessions: dict[str, "ClientSession"] = {}

    # 非同期ループを共有
    global_event_loop = asyncio.new_event_loop()
    # 別スレッドでイベントループを実行
    async def background_task():
        """サーバ全体で動作するバックグラウンドタスク"""
        while global_status:
            await asyncio.sleep(5)
    global_event_loop.create_task(background_task())
    asyncio.set_event_loop(global_event_loop)
    global_thread = threading.Thread(target=global_event_loop.run_forever, daemon=True)
    global_thread.start()

    class ClientSession:

        def __init__(self,clientid):
            self.client_id = clientid
            self.whisper_proc = MlxWhisperProcess( logfile=f'tmp/client_{clientid}.log')
            self.vot_proc = Bot()
            self._run=False
            self._t1:Task|None = None
            self._t2:Task|None = None
            self.mode = 'off'  # デフォルトモード
            self.lang = 'off'  # デフォルト言語
            self._accept_audio:str|None = None

        async def start(self):
            self._run=True
            loop = asyncio.get_event_loop()
            if self._t1 is None:
                self._t1 = loop.create_task( self._task_stt() )
            if self._t2 is None:
                self._t2 = loop.create_task( self._task_vod() )

        def send_ev(self,msg,data):
            socketio.emit('ev', {'msg': msg, 'data': data}, to=self.client_id)

        async def update_configure(self, data ):
            mode = data.get('llmMode', 'off') if data else 'off'
            lang = data.get('recogLang', 'en') if data else 'en'
            print(f"Mode: {mode}, Lang: {lang}")
            self.mode = mode
            self.lang = lang
            # 必要に応じてwhisper_procやvot_procの設定も更新
            if self.whisper_proc:
                self.whisper_proc.set_language(lang)
            if self.vot_proc:
                self.vot_proc.set_mode(mode)

        def append_audio(self,seq:int,typ:str,audio:bytes) ->str:
            if self._accept_audio is None or self._accept_audio!='':
                self._accept_audio = check_audio(audio, 16000)
            if self._accept_audio is not None and self._accept_audio!='':
                return self._accept_audio
            if self.whisper_proc:
                self.whisper_proc.append_audio(seq,typ,audio)
            return ''

        async def _task_stt(self):
            print(f"[SESSION]{self.client_id}:stt start")
            self.whisper_proc.start()
            """whisper_procからの結果を読み取ってクライアントに送信するタスク"""
            try:
                while self._run and self.client_id in client_sessions:  # クライアントが接続中の間だけ実行
                    try:
                        fixed_text = ''
                        result = await self.whisper_proc.read()
                        if result:
                            fixed_text, temp_text = result
                            # 確定したテキストを送信
                            if fixed_text or temp_text:
                                print(f"Sending fixed text to {self.client_id}: {fixed_text} {temp_text}")
                                self.send_ev( 'transcription', {'text': ' '.join(fixed_text), 'tmp': ' '.join(temp_text)} )
                            if fixed_text is not None and fixed_text!='':
                                await self.vot_proc.put(fixed_text,temp_text)
                    except Exception as ex:
                        print(f"Error in read_transcription loop for client {self.client_id}: {str(ex)}")
                    await asyncio.sleep(0.1)  # 短い待機時間を入れてCPU使用率を抑える
            except Exception as ex:
                print(f"Error in read_transcription for client {self.client_id}: {str(ex)}")
            finally:
                self._run = False
                self.whisper_proc.stop()
                print(f"[SESSION]{self.client_id}:end")

        async def _task_vod(self):
            print(f"[SESSION]{self.client_id}:vod start")
            self.vot_proc.start()
            """whisper_procからの結果を読み取ってクライアントに送信するタスク"""
            try:
                while self._run and self.client_id in client_sessions:  # クライアントが接続中の間だけ実行
                    try:
                        cmd, restext, voice = await self.vot_proc.get(timeout=0.2)
                        if restext != '' or len(voice)>0:
                            if cmd==VoiceRes.CMD_APPEND:
                                socketio.emit('audio_stream', {'text': restext, 'audio': voice}, to=self.client_id)
                            elif cmd==VoiceRes.CMD_ALL:
                                socketio.emit('result_text', {'text': restext, 'audio': voice}, to=self.client_id)
                    except Exception as ex:
                        print(f"Error in read_transcription loop for client {self.client_id}: {str(ex)}")
                    await asyncio.sleep(0.1)  # 短い待機時間を入れてCPU使用率を抑える
            except Exception as ex:
                print(f"Error in read_transcription for client {self.client_id}: {str(ex)}")
            finally:
                self.vot_proc.stop()
                self._run = False
                print(f"[SESSION]{self.client_id}:end")

        def stop(self):
            self._run=False
            self.whisper_proc.stop()
            self.vot_proc.stop()
            if self._t1 is not None:
                self._t1.cancel()
                self._t1 = None
            if self._t2 is not None:
                self._t2.cancel()
                self._t2 = None

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
        print(f"static {path}")
        return send_from_directory('static', path)

    @socketio.on('connect')
    def handle_connect():
        """クライアント接続時にwhisper_procを生成して起動"""
        try:
            # requestをSocketIORequest型としてキャスト
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            print(f'Client connected: {client_id}')
            if client_id not in client_sessions:
                session:ClientSession = ClientSession(client_id)
                client_sessions[client_id] = session
                # 非同期タスクを作成
                global_event_loop.create_task(session.start())
        except Exception as ex:
            print(f"Error in handle_connect: {str(ex)}")
            emit('error', {'error': str(ex)})
    @socketio.on('ev')
    def handle_message(raw_message):
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            session = client_sessions.get(client_id)
            if session:
                cmd_dict:dict = raw_message
                print(f"[API]message {raw_message}")
                cmd = cmd_dict.get('msg')
                data = cmd_dict.get('data')
                if cmd == 'configure':
                    # 非同期タスクを作成
                    global_event_loop.create_task(session.update_configure(data))
                    return
                elif cmd == 'aaa':
                    pass
                    return
            print(f"[API] invalid cmd {raw_message}")
        except Exception as ex:
            print(f"[API]message {raw_message} {str(str)}")

    @socketio.on('audio_bin')
    def handle_audio_bin(data):
        """WebSocketで受信した音声データを該当クライアントのwhisper_procに送信"""
        msg = 'invalid data'
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            session = client_sessions.get(client_id)
            if session is not None:
                if isinstance(data,bytes):
                    seq = 0
                    typ = ''
                    msg = session.append_audio(seq,typ,data)
        except Exception as e:
            msg = f"Error handling audio data for client {client_id}: {str(e)}"
        if msg:
            print(f"{msg}")
            if client_id:
                socketio.send( json.dumps({'msg':'audioError', 'data': {'error': msg}}), to=client_id )

    @socketio.on('audio_b64')
    def handle_audio_b64(data):
        """WebSocketで受信した音声データを該当クライアントのwhisper_procに送信"""
        msg = 'invalid data'
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            session = client_sessions.get(client_id)
            if session is not None:
                if isinstance(data,str):
                    seq = 0
                    typ = ''
                    buf:bytes = base64.b64decode(data)
                    msg = session.append_audio(seq,typ,buf)
        except Exception as e:
            msg = f"Error handling audio data for client {client_id}: {str(e)}"
        if msg:
            print(f"{msg}")
            emit('audio_error', {'error': msg})

    @socketio.on('audio_dict')
    def handle_audio_dict(data):
        """WebSocketで受信した音声データを該当クライアントのwhisper_procに送信"""
        msg = 'invalid data'
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            session = client_sessions.get(client_id)
            if session is not None:
                if isinstance(data,dict):
                    seq = data.get('seq',-1)
                    typ = data.get('type','')
                    b64 = data.get('base64','')
                    buf:bytes = base64.b64decode(b64)
                    msg = session.append_audio(seq,typ,buf)
        except Exception as e:
            msg = f"Error handling audio data for client {client_id}: {str(e)}"
        if msg:
            print(f"{msg}")
            emit('audio_error', {'error': msg})

    # 音声チャンクの保存
    @app.route('/audio_post', methods=['POST'])
    def upload_audio_chunk():
        msg = 'invalid data'
        try:
            client_id = request.form.get('sid')
            audio_chunk = request.files.get('audio_chunk')
            if client_id is not None and audio_chunk is not None:
                session = client_sessions.get(client_id)
                if session is not None:
                    buf = audio_chunk.read()
                    seq = 0
                    typ = ''
                    msg = session.append_audio(seq,typ,buf)
                    if msg=='':
                        return jsonify({'message': 'Chunk saved'}), 200
        except Exception as e:
            msg = f"Error handling audio data for client {client_id}: {str(e)}"
        if msg:
            print(f"{msg}")
        return jsonify({'error': msg}), 400

    @socketio.on('disconnect')
    def handle_disconnect():
        """クライアント切断時にwhisper_procを停止"""
        try:
            socket_request = cast(SocketIORequest, request)
            client_id = socket_request.sid
            print(f'Client disconnected: {client_id}')
            session = client_sessions.pop(client_id)
            if session:
                session.stop()
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

    #defining function to run on shutdown
    def close_running_threads():
        global_status = False
        print("Threads complete, ready to finish")

    #Register the function to be called on exit
    atexit.register(close_running_threads)

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
