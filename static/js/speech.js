class SpeechRecognitionHandler {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        this.lastResultIndex = 0;  // 追加: 最後に処理した結果のインデックスを追跡
        this.finalTranscript = ''; // 追加: 最終的なテキストを保持
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
            this.lastResultIndex = 0;  // 認識開始時にインデックスをリセット
            window.uiController.updateUIForRecordingStart();
        };

        this.recognition.onend = () => {
            if (this.isListening) {
                // 意図的な停止でない場合は再開する
                window.uiController.updateTranscriptUI('\n','')
                this.recognition.start();
            } else {
                window.uiController.updateUIForRecordingEnd();
            }
        };

        this.recognition.onresult = (event) => {
            this.handleRecognitionResult(event);
        };

        this.recognition.onerror = (event) => {
            // no-speech エラーは無視（一時的な無音を検出しただけなので）
            if (event.error !== 'no-speech') {
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
        let finalTranscript = '';
        let interimTranscript = '';
        // for( let i=0; i<event.results.length;i++) {
        //     console.log( '##'+i+':'+event.results[i][0].transcript)
        // }

        // 新しい結果のみを処理
        for (let i = this.lastResultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += ' ' + transcript; // 追加: finalTranscriptに追加
                this.lastResultIndex = i + 1;  // 最後に処理した結果のインデックスを更新
            } else {
                interimTranscript += transcript;
            }
        }

        window.uiController.updateTranscriptUI(finalTranscript, interimTranscript);
    }
}

// アプリケーション初期化
document.addEventListener('DOMContentLoaded', () => {
    new SpeechRecognitionHandler();
});
