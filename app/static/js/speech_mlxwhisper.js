class WhisperController {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.socket = null;
        this.recog_lang = 'en';
        this.fragment = [];

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
            if (this.isListening && this.recognition !== null ) {
                // 音声認識中の場合は一旦停止して再開
                //this.recognition.stop();
                this.recog_lang = newLang;
                //this.recognition.start();
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
    }
    // WebSocket接続を初期化
    initializeWebSocket() {
        this.socket = io(window.location.origin, {
            path: '/socket.io',
            transports: ['websocket']
        });

        this.socket.on('connect', () => {
            console.log('WebSocket接続が確立されました');
            window.uiController.updateUIForRecordingStart();
        });

        this.socket.on('transcription', (data) => {
            console.log('text recv');
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

        this.socket.on('connect_error', (error) => {
            console.error('接続エラー:', error);
            window.uiController.updateStatusForError(error);
        });

        this.socket.on('disconnect', () => {
            console.log('WebSocket接続が切断されました');
            window.uiController.updateUIForRecordingEnd();
        });
    }

    async startRecording() {
        try {
            // WebSocket接続を初期化
            this.initializeWebSocket();
            
            // マイクへのアクセスを要求
            this.stream = await navigator.mediaDevices.getUserMedia(this.constraints);
            
            // MediaRecorderの設定
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0) {
                    try {
                        // WebSocketを通じてサーバーに音声データを送信
                        if (this.socket && this.socket.connected) {
                            // Blobデータをそのまま送信
                            this.socket.emit('audio_data', event.data);
                        }
                    } catch (error) {
                        console.error('音声データの送信エラー:', error);
                    }
                }
            };

            // 1秒ごとにデータを取得するように設定
            this.mediaRecorder.start(1000);
            
        } catch (error) {
            this.handleError(error);
        }
    }

    async stopRecording() {
        try {
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
                
                // WebSocket接続を適切に終了
                if (this.socket) {
                    // 切断前に少し待機して、最後のデータの送信を確実にする
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
    }

}

// WhisperControllerのインスタンスを作成してグローバルに公開
window.whisperController = new WhisperController();
