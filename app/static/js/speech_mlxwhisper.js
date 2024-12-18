function getAllSupportedMimeTypes(...mediaTypes) {
    if (!mediaTypes.length) mediaTypes.push('video', 'audio')
    const CONTAINERS = ['webm', 'ogg', 'mp3', 'mp4', 'x-matroska', '3gpp', '3gpp2', '3gp2', 'quicktime', 'mpeg', 'aac', 'flac', 'x-flac', 'wave', 'wav', 'x-wav', 'x-pn-wav', 'not-supported']
    const CODECS = ['vp9', 'vp9.0', 'vp8', 'vp8.0', 'avc1', 'av1', 'h265', 'h.265', 'h264', 'h.264', 'opus', 'vorbis', 'pcm', 'aac', 'mpeg', 'mp4a', 'rtx', 'red', 'ulpfec', 'g722', 'pcmu', 'pcma', 'cn', 'telephone-event', 'not-supported']
    
    return [...new Set(
      CONTAINERS.flatMap(ext =>
          mediaTypes.flatMap(mediaType => [
            `${mediaType}/${ext}`,
          ]),
      ),
    ), ...new Set(
      CONTAINERS.flatMap(ext =>
        CODECS.flatMap(codec =>
          mediaTypes.flatMap(mediaType => [
            // NOTE: 'codecs:' will always be true (false positive)
            `${mediaType}/${ext};codecs=${codec}`,
          ]),
        ),
      ),
    ), ...new Set(
      CONTAINERS.flatMap(ext =>
        CODECS.flatMap(codec1 =>
        CODECS.flatMap(codec2 =>
          mediaTypes.flatMap(mediaType => [
            `${mediaType}/${ext};codecs="${codec1}, ${codec2}"`,
          ]),
        ),
        ),
      ),
    )].filter(variation => MediaRecorder.isTypeSupported(variation))
  }
  
  // To get all mime types, use: getAllSupportedMimeTypes()
  
  console.log('Video mime types:')
  console.log(getAllSupportedMimeTypes('video'))
  
  console.log('Audio mime types:')
  console.log(getAllSupportedMimeTypes('audio'))
  /*
    'webm;codecs=opus', 'audio/webm;codecs=pcm',
    'audio/webm;codecs="opus, opus"', 'audio/webm;codecs="opus, pcm"', 'audio/webm;codecs="pcm, opus"', 'audio/webm;codecs="pcm, pcm"',
    'audio/mp4;codecs=opus',
    'audio/mp4;codecs="opus, opus"']
   */
  /*
    audio/mp4", "audio/mp4;codecs=avc1", "audio/mp4;codecs=mp4a", "audio/mp4;codecs=\"avc1, avc1\"", "audio/mp4;codecs=\"avc1, mp4a\"", "audio/mp4;codecs=\"mp4a, avc1\"", "audio/mp4;codecs=\"mp4a, mp4a\""
  */

function calculateXORChecksum(data) {
    let checksum = 0;
    for (let i = 0; i < data.length; i++) {
        checksum ^= data[i]; // 各バイトをXOR演算
    }
    return checksum;
}
// Blobをbase64に変換
async function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64data = reader.result.split(',')[1];
            resolve(base64data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}
class WhisperController {
    constructor() {
        this.mediaRecorder = null;
        this.media_seq = 0;
        this.audioContext = null;
        this.audioChunks = [];
        this.stream = null;
        this.socket = null;
        this.recog_lang = 'en';
        this.fragment = [];
        this.isListening = false; // 音声認識がアクティブかどうかを追跡

        // DOM要素の取得
        this.status = document.getElementById('speechStatus');

        // 音声録音の設定
        this.constraints = {
            audio: {
                echoCancellation: false,
                noiseSuppression: true,
                autoGainControl: false,
                channelCount: 1,
                sampleRate: 16000
            }
        };
        this.setupUiHandler();
    }

    setupUiHandler() {
        document.getElementById('languageSelect').addEventListener('change', (event) => {
            const newLang = event.target.value;
            this.recog_lang = newLang;
            // 言語変更をサーバーに通知
            if (this.socket && this.socket.connected) {
                const selectedMode = document.querySelector('input[name="mode"]:checked').value;
                this.socket.emit('configure', {'mode':selectedMode, 'lang':this.recog_lang}) ;
            }
        });
        this.recog_lang = document.getElementById('languageSelect').value;

        document.getElementById('startButton').onclick = () => {
            window.uiController.handleStartButtonClick((shouldStart) => {
                if (shouldStart) {
                    this.startRecording();
                } else {
                    this.stopRecording();
                }
            });
        };

        // モード選択に応じた設定
        document.querySelectorAll('input[name="mode"]').forEach((radio) => {
            radio.addEventListener('change', async (event) => {
                const mode = event.target.value;
                let upd = false
                if (mode === 'conversation') {
                    upd = !this.constraints.audio.echoCancellation
                    this.constraints.audio.echoCancellation = true;
                } else {
                    upd = this.constraints.audio.echoCancellation
                    this.constraints.audio.echoCancellation = false;
                }
                // モード変更をサーバーに通知
                if (this.socket && this.socket.connected) {
                    this.socket.emit('configure', {'mode':mode, 'lang':this.recog_lang});
                }
                // // 音声認識がアクティブな場合のみストリームを再取得
                // if (this.isListening && this.stream) {
                //     this.stream.getTracks().forEach(track => track.stop());
                //     this.stream = await navigator.mediaDevices.getUserMedia(this.constraints);
                // }
            });
        });
    }

    // WebSocket接続を初期化
    initializeWebSocket() {
        this.socket = io(window.location.origin, {
            path: '/socket.io',
            transports: ['websocket'],
        });

        const selectedMode = document.querySelector('input[name="mode"]:checked').value;
        this.socket.on('connect', () => {
            console.log('socketio connected');
            this.socket.emit('configure', {'mode':selectedMode, 'lang':this.recog_lang});
            window.uiController.updateUIForRecordingStart();
        });

        this.socket.on('transcription', (data) => {
            console.log('socketio recv transcription');
            const results = []
            if (data.text) {
                for (const result_text of data.text) {
                    results.push({ text: result_text, isFinal: true, confidence: 1.0 });
                }
            }
            if (data.tmp) {
                for (const result_text of data.tmp) {
                    results.push({ text: result_text, isFinal: false, confidence: 0.5});
                }
            }
            window.uiController.updateTranscriptUI(results);
        });
        this.socket.on('audio_error', (data) => {
            const msg = data.error
            console.log('socketio recv audio',msg);
            this.stopRecording()
        });
        this.socket.on('audio_stream', (data) => {
            console.log('socketio recv audio');
            this.playAudio(data.audio);
        });
        this.socket.on('audio_stream', (data) => {
            console.log('socketio recv audio');
            this.playAudio(data.audio);
        });
        this.socket.on('result_text', (data) => {
            console.log('socketio recv audio');
            const text = data.text;
            const audio = data.audio;
            if( audio ) {
                this.playAudio(audio);
            }
            if( text ) {
                window.uiController.updateSummaryUI(text);
            }
        });
        this.socket.on('connect_error', (error) => {
            console.log('socketio connect error',error);
            window.uiController.updateStatusForError(error);
            window.uiController.updateUIForRecordingEnd();
        });

        this.socket.on('disconnect', () => {
            console.log('socketio disconnect');
            window.uiController.updateUIForRecordingEnd();
        });
    }
    async playAudio(audioData) {
        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (!this.audioContext) {
                return;
            }
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }
            const audioBuffer = await this.audioContext.decodeAudioData(audioData);
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.start();
        } catch (error) {
            console.error('Error decoding or playing audio:', error);
        }
    }
    async startRecording() {
        try {
            this.isListening = true; // 音声認識をアクティブに設定
            // WebSocket接続を初期化
            this.initializeWebSocket();
            
            // マイクへのアクセスを要求
            this.stream = await navigator.mediaDevices.getUserMedia(this.constraints);
            // MediaRecorderの設定
            const options = {mimeType: 'audio/webm;codecs=opus'};
            options.mimeType = 'audio/webm';
            //options.mimeType = 'audio/webm;codecs=pcm'
            options.mimeType = 'audio/mp4;codecs=opus'
            this.mediaRecorder = new MediaRecorder(this.stream);

            this.mediaRecorder.ondataavailable = async (event) => {
                if (this.isListening && event.data.size > 0) {
                    try {
                        // WebSocketを通じてサーバーに音声データを送信
                        if (this.socket && this.socket.connected) {
                            const seq = this.media_seq++;
                            const type = event.data.type;
                            const send = 1;
                            console.log('send mode',send)
                            if( send==1 ) {
                                // ダイレクト
                                this.socket.emit('audio_bin', event.data )
                            } else if( send==3 ) {
                                const audio_bin = await event.data.arrayBuffer()
                                const u8 = new Uint8Array(audio_bin)
                                const b64 = btoa(String.fromCharCode.apply(null,u8))
                                this.socket.emit('audio_b64', b64 )
                            } else if( send==4 ) {
                                const b64 = await blobToBase64(event.data)
                                this.socket.emit('audio_b64', b64 )
                            } else if( send==5 ) {
                                const formData = new FormData();
                                formData.append('sid', this.socket.id )
                                formData.append('audio_chunk', event.data, `chunk_${seq}.webm`);
                                fetch('/audio_post', { method: 'POST', body: formData })
                                  .then(response => response.json())
                                  .then(data => console.log('サーバーからの応答:', data))
                                  .catch(error => console.error('エラー:', error));
                            } else if( send==6 ) {
                                this.socket.emit('audio_data', {
                                    'seq':seq,
                                    'type': type,
                                    'base64': blobToBase64(event.data),
                                } );
                            }
                        }
                    } catch (error) {
                        console.error('音声データの送信エラー:', error);
                    }
                }
            };

            // 1秒ごとにデータを取得するように設定
            this.mediaRecorder.start(1000);

            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
        } catch (error) {
            this.handleError(error);
        }
    }

    async stopRecording() {
        try {
            console.log('call stop')
            this.isListening = false; // 音声認識を非アクティブに設定
            if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                // MediaRecorderを停止する前に最後のデータを送信
                this.mediaRecorder.stop();
                // 最後のデータが送信されるのを待つ
                await new Promise(resolve => {
                    this.mediaRecorder.addEventListener('stop', resolve, { once: true });
                });
            }
            // 音声ストリームを停止
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
            }
            // WebSocket切断
            if (this.socket) {
                await new Promise(resolve => setTimeout(resolve, 500));
                this.socket.disconnect();
            }
        } catch (error) {
            this.handleError(error);
        }
    }

    handleError(error) {
        console.error('エラーが発生しました:', error);
        window.uiController.updateStatusForError(error);
        window.uiController.updateUIForRecordingEnd();
    }

}

// WhisperControllerのインスタンスを作成してグローバルに公開
window.whisperController = new WhisperController();
