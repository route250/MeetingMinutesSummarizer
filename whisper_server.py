from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
import numpy as np
from numpy.typing import NDArray
from pydub import AudioSegment
import io
from whisper_transcribe import transcribe
import tempfile
from typing import cast, Union
import threading
from queue import Queue
import time
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60)

# 音声データのキューを作成
audio_queue = Queue()

def convert_audio_to_numpy(audio_data: Union[str, bytes]) -> NDArray[np.float32]:
    """
    音声データ（ファイルパスまたはバイナリデータ）をNumPy配列に変換
    """
    if isinstance(audio_data, str):
        # ファイルパスの場合
        audio = AudioSegment.from_file(audio_data, format="webm")
    else:
        # バイナリデータの場合
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="webm")
        except Exception as e:
            print(f"Error converting audio data: {e}")
            return np.array([], dtype=np.float32)
    
    # モノラルに変換
    if audio.channels > 1:
        audio = audio.set_channels(1)
    
    # サンプルレートを16kHzに変換
    if audio.frame_rate != 16000:
        audio = audio.set_frame_rate(16000)
    
    # サンプルを取得してNumPy配列に変換
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    
    # 正規化 (-1 to 1の範囲に)
    samples = samples / (1 << (8 * audio.sample_width - 1))
    
    return cast(NDArray[np.float32], samples)

def process_audio_queue():
    """音声データを処理するバックグラウンドタスク"""
    while True:
        if not audio_queue.empty():
            audio_data = audio_queue.get()
            try:
                # 音声データを変換
                audio_array = convert_audio_to_numpy(audio_data)
                
                if len(audio_array) > 0:
                    # whisper_transcribe.pyの関数を使用して文字起こし
                    result = transcribe(audio_array)
                    
                    if result.strip():
                        socketio.emit('transcription', {'text': result})
            except Exception as e:
                print(f"Error processing audio: {str(e)}")
        time.sleep(0.1)  # CPUの使用率を下げるために少し待機

# バックグラウンドタスクを開始
processing_thread = threading.Thread(target=process_audio_queue, daemon=True)
processing_thread.start()

@app.route('/')
def whisper_page():
    return send_from_directory('static', 'whisper.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('audio_data')
def handle_audio_data(data):
    """WebSocketで受信した音声データを処理キューに追加"""
    try:
        # Base64データをデコード
        audio_data = base64.b64decode(data)
        audio_queue.put(audio_data)
    except Exception as e:
        print(f"Error handling audio data: {str(e)}")

@app.route('/transcribe_audio', methods=['POST'])
def transcribe_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        
        # 一時ファイルとして保存
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
            audio_file.save(temp_file.name)
            temp_path = temp_file.name

        try:
            # pydubを使用して音声データを変換
            audio_array = convert_audio_to_numpy(temp_path)
            
            # whisper_transcribe.pyの関数を使用して文字起こし
            result = transcribe(audio_array)
            
            # 一時ファイルの削除
            os.unlink(temp_path)
            
            return jsonify({'text': result})
            
        except Exception as e:
            # エラーが発生した場合も一時ファイルを削除
            os.unlink(temp_path)
            raise e

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = 5008  # 既存のapp.pyと異なるポート番号を使用
    ssl_key='.certs/server.key'
    ssl_cert='.certs/server.crt'
    if os.path.exists(ssl_key) and os.path.exists(ssl_cert):
        ssl_context=(ssl_cert,ssl_key)
    else:
        ssl_context=None
    socketio.run(app, host='0.0.0.0', port=port, ssl_context=ssl_context, debug=True)
