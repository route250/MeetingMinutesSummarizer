class WhisperController {
    constructor() {
        this.mediaRecorder = null;
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
                if (mode === 'conversation') {
                    this.constraints.audio.echoCancellation = true;
                } else {
                    this.constraints.audio.echoCancellation = false;
                }
                // モード変更をサーバーに通知
                if (this.socket && this.socket.connected) {
                    this.socket.emit('configure', {'mode':selectedMode, 'lang':this.recog_lang});
                }
                // 音声認識がアクティブな場合のみストリームを再取得
                if (this.isListening && this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = await navigator.mediaDevices.getUserMedia(this.constraints);
                }
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
        this.socket.on('audio_stream', (data) => {
            console.log('socketio recv audio');
            this.playAudio(data.audio);
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
            this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: 'audio/webm' });

            this.mediaRecorder.ondataavailable = async (event) => {
                if (this.isListening && event.data.size > 0) {
                    try {
                        // WebSocketを通じてサーバーに音声データを送信
                        if (this.socket && this.socket.connected) {
                            // Blobデータをそのまま送信
                            const audio_bin = await event.data.arrayBuffer()
                            const u8 = new Uint8Array(audio_bin)
                            const b64 = btoa(String.fromCharCode.apply(null,u8))
                            //console.log('Blob size:', event.data.size, 'type:', event.data.type, 'sz',audio_bin.byteLength );
                            this.socket.emit('audio_data', { 'size':event.data.size, 'base64':b64} );
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
            this.isListening = false; // 音声認識を非アクティブに設定
            if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                // MediaRecorderを停止する前に最後のデータを送信
                this.mediaRecorder.stop();
                // 最後のデータが送信されるのを待つ
                await new Promise(resolve => {
                    this.mediaRecorder.addEventListener('stop', resolve, { once: true });
                });
                
                // 音声ストリームを停止
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                }
                
                // WebSocket切断
                if (this.socket) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    this.socket.disconnect();
                }
                
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
