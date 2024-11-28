class SpeechRecognitionHandler {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        this.final_map = {};
        this.interm_map = {};
        this.onsound = false;
        this.onspeech = false;
        this.initializeSpeechRecognition();
    }

    initializeSpeechRecognition() {
        if ('webkitSpeechRecognition' in window) {
            this.recognition = new webkitSpeechRecognition();
            this.setupRecognitionConfig();
            this.setupRecognitionEvents();
            this.setupButtonHandler();
        } else {
            window.uiController.showBrowserSupportError();
        }
    }

    setupRecognitionConfig() {
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'ja-JP';
    }

    setupRecognitionEvents() {
        this.recognition.onstart = () => {
            console.log('# on_start')
            this.final_map = {};
            this.interm_map = {};
            this.onsound = false;
            this.onspeech = false;
            window.uiController.updateUIForRecordingStart();
        };

        this.recognition.onend = () => {
            console.log('# on_end')
            if (this.isListening) {
                // 意図的な停止でない場合は再開する
                window.uiController.updateTranscriptUI([])
                this.final_map = {};
                this.interm_map = {};
                this.onsound = false;
                this.onspeech = false;
                this.recognition.start();
            } else {
                window.uiController.updateUIForRecordingEnd();
            }
        };

        this.recognition.onresult = (event) => {
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
        this.recognition.onpeechstart = (event) => {
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
                }
            }
        }

        window.uiController.updateTranscriptUI(results);
    }

    handleRecognitionStatus() {
        window.uiController.updateUIForRecognitonState( this.onspeech ? 2 : this.onsound ? 1: 0 );
    }
}

// アプリケーション初期化
document.addEventListener('DOMContentLoaded', () => {
    new SpeechRecognitionHandler();
});
