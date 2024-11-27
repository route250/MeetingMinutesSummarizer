class UIController {
    constructor() {
        this.startButton = document.getElementById('startButton');
        this.statusDiv = document.getElementById('status');
        this.speechStatusDiv = document.getElementById('speechStatus');
        this.llmStatusDiv = document.getElementById('llmStatus');
        this.transcriptArea = document.getElementById('transcriptArea');
        this.summaryArea = document.getElementById('summaryArea');
        
        this.isRecording = false;
        this.lastResults = [];
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

    updateUIForRecognitonState(st) {
        if( this.isRecording ) {
            if( st==1 ) {
                this.speechStatusDiv.textContent = '音声認識: sound';
            } else if( st==2 ) {
                this.speechStatusDiv.textContent = '音声認識: speech';
            } else {
                this.speechStatusDiv.textContent = '音声認識: silent';
            }
        }
    }

    getConfidenceClass(confidence, isFinal) {
        if (!isFinal) return 'text-interim';
        if (confidence >= 0.8) return 'text-high-confidence';
        if (confidence >= 0.5) return 'text-medium-confidence';
        return 'text-low-confidence';
    }

    updateTranscriptUI(results) {
        // 確定テキストを更新
        for (const result of results) {
            if (result.isFinal) {
                this.lastResults.push(result);
                this.hasNewContent = true;
            }
        }

        // HTMLを生成
        let html = '';
        
        // 確定済みテキストを表示
        for (const result of this.lastResults) {
            const confidenceClass = this.getConfidenceClass(result.confidence, result.isFinal);
            html += `<span class="${confidenceClass}">${result.text}</span> `;
        }

        // 未確定テキストを表示（最新の未確定テキストのみ）
        const interimResults = results.filter(r => !r.isFinal);
        for( const result of interimResults ) {
            const confidenceClass = this.getConfidenceClass(result.confidence, result.isFinal);
            html += `<span class="${confidenceClass}">${result.text}</span>`;
        }

        this.transcriptArea.innerHTML = html;

        // 最下部にスクロール
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
                        text: this.transcriptArea.textContent,
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
