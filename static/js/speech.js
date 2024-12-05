class SpeechRecognitionHandler {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        this.final_map = {};
        this.interm_map = {};
        this.onsound = false;
        this.onspeech = false;
        this.noResultTimer = null;        // 10秒タイマー
        this.noUpdateTimer = null;        // 2秒タイマー
        this.lastResultTime = null;       // 最後に結果を受け取った時間
        this.initializeSpeechRecognition();
    }

    initializeSpeechRecognition() {
        if ('webkitSpeechRecognition' in window) {
            this.recognition = new webkitSpeechRecognition();
            this.setupRecognitionConfig();
            this.setupRecognitionEvents();
            this.setupButtonHandler();
            this.setupLanguageHandler();
        } else {
            window.uiController.showBrowserSupportError();
        }
    }

    setupRecognitionConfig() {
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = document.getElementById('languageSelect').value;
    }

    setupLanguageHandler() {
        document.getElementById('languageSelect').addEventListener('change', (event) => {
            const newLang = event.target.value;
            if (this.isListening) {
                // 音声認識中の場合は一旦停止して再開
                this.recognition.stop();
                this.recognition.lang = newLang;
                this.recognition.start();
            } else {
                // 停止中の場合は設定のみ変更
                this.recognition.lang = newLang;
            }
        });
    }

    setupRecognitionEvents() {
        this.recognition.onstart = () => {
            console.log('# on_start')
            this.final_map = {};
            this.interm_map = {};
            this.onsound = false;
            this.onspeech = false;
            this.lastResultTime = Date.now();
            this.startNoResultTimer();
            window.uiController.updateUIForRecordingStart();
        };

        this.recognition.onend = () => {
            console.log('# on_end')
            this.clearTimers();
            let results = [];
            const idxs = Object.keys(this.interm_map).sort();
            if( idxs.length>0 ) {
                for( const idx of idxs ) {
                    const text = this.interm_map[idx].text;
                    const confidence = this.interm_map[idx].confidence;
                    results.push({text: text, isFinal: true, confidence: confidence });
                }
            }
            this.final_map = {};
            this.interm_map = {};
            this.onsound = false;
            this.onspeech = false;
            if (this.isListening) {
                // 意図的な停止でない場合は再開する
                console.log('# resume')
                this.recognition.start();
            }
            if( results.length>0) {
                window.uiController.updateTranscriptUI(results);
            }
            window.uiController.updateTranscriptUI([])
            if (!this.isListening) {
                window.uiController.updateUIForRecordingEnd();
            }
        };

        this.recognition.onresult = (event) => {
            this.lastResultTime = Date.now();
            this.resetTimers();
            this.handleRecognitionResult(event);
        };

        this.recognition.onnomatch = (event) => {
            console.log('## on_nomatch')
        };

        this.recognition.onsoundstart = (event) => {
            this.onsound = true;
            this.handleRecognitionStatus();
        };
        this.recognition.onsoundend = (event) => {
            this.onsound = false;
            this.handleRecognitionStatus();
        };
        this.recognition.onspeechstart = (event) => {
            this.onspeech = true;
            this.handleRecognitionStatus();
        };
        this.recognition.onspeechend = (event) => {
            this.onspeech = false;
            this.handleRecognitionStatus();
        };

        this.recognition.onerror = (event) => {
            // no-speech エラーは無視（一時的な無音を検出しただけなので）
            if (event.error == 'no-speech') {
                console.log('## on_error no-speech')
            } else {
                console.error('音声認識エラー:', event.error);
                window.uiController.updateStatusForError(event.error);
            }
        };
    }

    setupButtonHandler() {
        document.getElementById('startButton').onclick = () => {
            window.uiController.handleStartButtonClick((shouldStart) => {
                if (shouldStart) {
                    this.startRecognition();
                } else {
                    this.stopRecognition();
                }
            });
        };
    }

    startRecognition() {
        this.isListening = true;
        this.recognition.start();
    }

    stopRecognition() {
        this.isListening = false;
        this.clearTimers();
        this.recognition.stop();
    }

    handleRecognitionResult(event) {
        let results = [];

        // 新しい結果のみを処理
        for (let i = event.resultIndex; i < event.results.length; i++) {
            if( !this.final_map[i] ) {
                const result = event.results[i];
                let content = result[0].transcript.trim();
                let confidence = result[0].confidence;
                if( content ) {
                    this.interm_map[i] = { 'text': content, 'confidence': confidence }
                } else if( i in this.interm_map ) {
                    content = this.interm_map[i].text
                    confidence = this.interm_map[i].confidence
                }
                results.push({
                    text: content,
                    isFinal: result.isFinal,
                    confidence: confidence
                });
                if( result.isFinal ) {
                    this.final_map[i] = true;
                    delete this.interm_map[i]
                }
            }
        }

        window.uiController.updateTranscriptUI(results);
    }

    handleRecognitionStatus() {
        window.uiController.updateUIForRecognitonState( this.onspeech ? 2 : this.onsound ? 1: 0 );
    }

    // タイマー関連の新しいメソッド
    startNoResultTimer() {
        // 10秒間結果が来ないタイマー
        this.noResultTimer = setTimeout(() => {
            console.log('10秒間結果なし - 再起動');
            if (this.isListening) {
                this.recognition.stop();
            }
        }, 10000);

        // 2秒間更新がないタイマー
        this.startNoUpdateTimer();
    }

    startNoUpdateTimer() {
        this.noUpdateTimer = setTimeout(() => {
            if (this.isListening && Object.keys(this.interm_map).length > 0) {
                console.log('2秒間更新なし - 中間結果を確定');
                const results = [];
                const idxs = Object.keys(this.interm_map).sort();
                for (const idx of idxs) {
                    const text = this.interm_map[idx].text;
                    const confidence = this.interm_map[idx].confidence;
                    results.push({text: text, isFinal: true, confidence: confidence});
                    this.final_map[idx] = true;
                }
                this.interm_map = {};
                window.uiController.updateTranscriptUI(results);
                
                // 認識を再起動
                this.recognition.stop();
            }
        }, 2000);
    }

    resetTimers() {
        this.clearTimers();
        this.startNoResultTimer();
    }

    clearTimers() {
        if (this.noResultTimer) {
            clearTimeout(this.noResultTimer);
            this.noResultTimer = null;
        }
        if (this.noUpdateTimer) {
            clearTimeout(this.noUpdateTimer);
            this.noUpdateTimer = null;
        }
    }
}

// アプリケーション初期化
document.addEventListener('DOMContentLoaded', () => {
    new SpeechRecognitionHandler();
});
