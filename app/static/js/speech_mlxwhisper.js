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
//   console.log('Video mime types:')
//   console.log(getAllSupportedMimeTypes('video'))
//   console.log('Audio mime types:')
//   console.log(getAllSupportedMimeTypes('audio'))
  /*
    'webm;codecs=opus', 'audio/webm;codecs=pcm',
    'audio/webm;codecs="opus, opus"', 'audio/webm;codecs="opus, pcm"', 'audio/webm;codecs="pcm, opus"', 'audio/webm;codecs="pcm, pcm"',
    'audio/mp4;codecs=opus',
    'audio/mp4;codecs="opus, opus"']
   */
  /*
    audio/mp4", "audio/mp4;codecs=avc1", "audio/mp4;codecs=mp4a", "audio/mp4;codecs=\"avc1, avc1\"", "audio/mp4;codecs=\"avc1, mp4a\"", "audio/mp4;codecs=\"mp4a, avc1\"", "audio/mp4;codecs=\"mp4a, mp4a\""
  */

// Cookie操作のユーティリティ関数
const CookieUtil = {
    setCookie: function(name, value, days = 30) {
        const d = new Date();
        d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
        const expires = "expires=" + d.toUTCString();
        document.cookie = name + "=" + value + ";" + expires + ";path=/";
    },
    
    getCookie: function(name) {
        const cookieName = name + "=";
        const cookies = document.cookie.split(';');
        for(let i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim();
            if (cookie.indexOf(cookieName) === 0) {
                return cookie.substring(cookieName.length, cookie.length);
            }
        }
        return "";
    }
};

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
        this.socket = null;
        this.values = {};
        this.mediaRecorder = null;
        this.media_seq = 0;
        this.audioContext = null;
        this.audioChunks = [];
        this.stream = null;
        this.recog_lang = 'en';
        this.fragment = [];
        this.isListening = false; // 音声認識がアクティブかどうかを追跡

        // DOM要素の取得
        this.speechControl = document.getElementById('speechControl');

        // 音声録音の設定
        this.constraints = {
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
                channelCount: 1,
                sampleRate: 16000
            }
        };

        // 保存された設定の読み込み
        this.loadSavedSettings();
        this.setupUiHandler();
    }

    loadSavedSettings() {
        // 言語設定の読み込み
        const savedLang = CookieUtil.getCookie('recogLang');
        if (savedLang) {
            this.values['recogLang'] = savedLang;
            const elem = document.getElementById('recogLang');
            if (elem) {
                elem.value = savedLang;
            }
        }
        for( const key in this.constraints.audio ) {
            const elem = document.getElementById(key);
            const value = CookieUtil.getCookie(key);
            if (elem && value ) {
                this.constraints.audio[key] = value;
                elem.checked = savedLang;
            }
        }
        // モード設定の読み込み
        const llmMode = CookieUtil.getCookie('llmMode');
        if (llmMode) {
            this.values['llmMode'] = llmMode;
            const elem = document.querySelector(`input[name="llmMode"][value="${llmMode}"]`);
            if (elem) {
                elem.value = llmMode;
                // エコーキャンセレーションの設定を更新
                this.constraints.audio.echoCancellation = llmMode === 'conversation';
            }
        }
    }

    setupUiHandler() {
        document.getElementById('recogLang').addEventListener('change', (event) => {
            const newLang = event.target.value;
            this.recog_lang = newLang;
            // 言語設定をCookieに保存
            CookieUtil.setCookie('recogLang', newLang);
            // 言語変更をサーバーに通知
            this.values['recogLang'] = newLang
            this.sendValues().then(()=>{});
        });

        // audio trackの設定を変更する
        for( const key in this.constraints.audio ) {
            const elem = document.getElementById(key);
            if(elem) {
                elem.addEventListener('change', (event) => {
                    const value = event.target.checked;
                    CookieUtil.setCookie(key, value);
                    if( this.constraints.audio[key] != value) {
                        this.constraints.audio[key] = value;
                        this.applyConstraints()
                    }
                });
            }
        }

        this.speechControl.onclick = () => {
            window.uiController.handleStartButtonClick((shouldStart) => {
                if (shouldStart) {
                    this.startRecording();
                } else {
                    this.stopRecording();
                }
            });
        };

        // モード選択に応じた設定
        document.querySelectorAll('input[name="llmMode"]').forEach((radio) => {
            radio.addEventListener('change', async (event) => {
                const llmMode = event.target.value;
                // モード設定をCookieに保存
                CookieUtil.setCookie('llmMode', llmMode);
                this.values['llmMode'] = llmMode
                this.sendValues().then(()=>{});
                    
                let upd = false
                if (llmMode === 'conversation') {
                    upd = !this.constraints.audio.echoCancellation
                    this.constraints.audio.echoCancellation = true;
                } else {
                    upd = this.constraints.audio.echoCancellation
                    this.constraints.audio.echoCancellation = false;
                }
                // audio trackの設定を変更する
                if (upd) {
                    this.applyConstraints();
                }
            });
        });
    }

    // WebSocket接続を初期化
    async initializeWebSocket() {
        // 接続中（CONNECTING）の場合に待機
        if( !this.socket) {
            console.log('connect','start',this.socket?.readyState)
            this.socket = io(window.location.origin, { path: '/socket.io', transports: ['websocket'], });
            // イベントリスナーを設定
            this.socket.on('connect', this.onConnect.bind(this));
            this.socket.on('connect_error', this.onConnectError.bind(this));
            this.socket.on('disconnect', this.onDisconnect.bind(this));
            this.socket.on('ev', this.onEv.bind(this));
            //this.socket.on('audio_error', this.onAudioError.bind(this));
            this.socket.on('audio_stream', this.onAudioStream.bind(this));
            this.socket.on('result_text', this.onResultText.bind(this));
            // 初期データ送信        
            await this.sendValues();    
        }
    }

    onConnect() {
        console.log('socketio connected');
        const llmMode = document.querySelector('input[name="llmMode"]:checked').value;
    }
    onConnectError(error) {
        console.log('socketio connect error',error);
        window.uiController.updateStatusForError(error);
        this.socket = null;
    }
    onDisconnect() {
        console.log('socketio disconnect');
        window.uiController.updateUIForRecordingEnd();
        this.socket = null;
    }
    onEv(event) {
        const cmd = event['msg']
        const data = event['data']
        if( cmd == 'transcription' ) {
            this.onTranscription(data)
        }else if( cmd=='resultText' ) {
            
        }else if( cmd=='audioError' ) {
            const msg = data.error
            console.log('socketio recv audio err',msg);
            this.stopRecording() 
        }
    }
    onTranscription(data) {
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
    }
    onResultText(data) {
        console.log('socketio recv text');
        const text = data.text;
        const audio = data.audio;
        if( audio ) {
            this.playAudio(audio);
        }
        if( text ) {
            window.uiController.updateSummaryUI(text);
        }
    }

    onAudioStream(data) {
        console.log('socketio recv audio');
        this.playAudio(data.audio);
    }
    async dicsonnect() {
        // WebSocket切断
        if (this.socket && ( this.socket.readyState == WebSocket.OPEN || this.socket.readyState==WebSocket.CONNECTING ) ) {
            this.socket.disconnect();
        }
    }
    // audio trackの設定を変更する
    applyConstraints() {
        if (this.isListening && this.stream) {
            const this_const = JSON.stringify(this.constraints);
            let upd = false;
            const tracks = this.stream.getTracks();
            tracks.forEach((track) => {
                const appliedConstraints = track.getConstraints();
                // 制約を比較
                if (this_const !== JSON.stringify(appliedConstraints)) {
                    upd = true;
                }
            });
            if( upd ) {
                this.stopRecording();
                this.startRecording();    
            }
        }
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

    async asend_ev(msg,data) {
        await this.initializeWebSocket()
        this.socket.emit('ev', { msg: msg, data: data});
    }

    send_ev(msg,data) {
        asend_ev(msg,data).then( ()=> {} );
    }

    async sendValues() {
        await this.asend_ev('configure',this.values);
    }

    async startRecording() {
        try {
            this.isListening = true; // 音声認識をアクティブに設定
            // WebSocket接続を初期化
            await this.initializeWebSocket();
            
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
                            //console.log('send mode',send)
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
            window.uiController.updateUIForRecordingStart();
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
            window.uiController.updateUIForRecordingEnd();
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
