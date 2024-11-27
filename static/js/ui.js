class UIController {
    constructor() {
        this.startButton = document.getElementById('startButton');
        this.statusDiv = document.getElementById('status');
        this.speechStatusDiv = document.getElementById('speechStatus');
        this.llmStatusDiv = document.getElementById('llmStatus');
        this.transcriptArea = document.getElementById('transcriptArea');
        this.summaryArea = document.getElementById('summaryArea');
        
        this.isRecording = false;
        this.lastTranscript = '';
        this.lastSummaryUpdate = Date.now();
        this.hasNewContent = false;

        // 15秒ごとに議事録更新をチェック
        setInterval(() => this.checkForSummaryUpdate(), 15000);
    }

    updateUIForRecordingStart() {
        this.isRecording = true;
        this.statusDiv.textContent = '録音中';
        this.statusDiv.classList.add('recording');
        this.speechStatusDiv.textContent = '音声認識: 実行中';
        this.speechStatusDiv.classList.add('active');
        this.startButton.textContent = '停止';
    }

    updateUIForRecordingEnd() {
        this.isRecording = false;
        this.statusDiv.textContent = '待機中';
        this.statusDiv.classList.remove('recording');
        this.speechStatusDiv.textContent = '音声認識: 停止中';
        this.speechStatusDiv.classList.remove('active');
        this.startButton.textContent = '音声認識開始';
    }

    updateTranscriptUI(finalTranscript, interimTranscript) {
        if (finalTranscript) {
            // 最後の改行を除去して、新しい行を追加
            const newTranscript = finalTranscript.trim();
            if (newTranscript) {
                if( this.lastTranscript ) {
                    this.lastTranscript += ' '+newTranscript
                } else {
                    this.lastTranscript = newTranscript
                }
                this.hasNewContent = true;
            } else if( finalTranscript=='\n' && this.lastTranscript && !this.lastTranscript.endsWith('\n') ){
                this.lastTranscript += '\n'
            }
        }
        // 暫定認識結果を一時的に表示
        const displayText = this.lastTranscript + (interimTranscript ? ' '+interimTranscript : '');
        this.transcriptArea.value = displayText;
        // テキストエリアを最下部にスクロール
        this.transcriptArea.scrollTop = this.transcriptArea.scrollHeight;
    }

    async checkForSummaryUpdate() {
        if (!this.hasNewContent) return;

        const currentTime = Date.now();
        if (currentTime - this.lastSummaryUpdate >= 15000) {
            this.lastSummaryUpdate = currentTime;
            this.hasNewContent = false;
            
            try {
                this.llmStatusDiv.textContent = 'LLM: 処理中';
                this.llmStatusDiv.classList.add('processing');

                const response = await fetch('/process_audio', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 
                        text: this.transcriptArea.value,
                        type: 'summary'
                    })
                });

                const data = await response.json();
                if (data.error) {
                    console.error('議事録生成エラー:', data.error);
                    this.llmStatusDiv.textContent = 'LLM: エラー';
                } else {
                    this.updateSummaryUI(data.response);
                    this.llmStatusDiv.textContent = 'LLM: 待機中';
                }
            } catch (error) {
                console.error('議事録生成中にエラーが発生:', error);
                this.llmStatusDiv.textContent = 'LLM: エラー';
            } finally {
                this.llmStatusDiv.classList.remove('processing');
            }
        }
    }

    updateSummaryUI(summary) {
        this.summaryArea.value = summary;
        this.summaryArea.scrollTop = this.summaryArea.scrollHeight;
    }

    updateStatusForError(error) {
        this.statusDiv.textContent = `エラー: ${error}`;
        this.speechStatusDiv.textContent = '音声認識: エラー';
        this.llmStatusDiv.textContent = 'LLM: 停止';
    }

    showBrowserSupportError() {
        this.startButton.style.display = 'none';
        this.statusDiv.textContent = 'ブラウザ非対応';
        this.speechStatusDiv.textContent = '音声認識: 非対応';
        this.llmStatusDiv.textContent = 'LLM: 停止';
    }

    handleStartButtonClick(callback) {
        if (this.isRecording) {
            callback(false); // 停止
        } else {
            callback(true);  // 開始
        }
    }
}

// UIコントローラーのインスタンスを作成してグローバルに公開
window.uiController = new UIController();
