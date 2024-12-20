class UIController {
    constructor() {
        this.speechControl = document.getElementById('speechControl');
        this.llmStatusDiv = document.getElementById('llmStatus');
        this.transcriptArea = document.getElementById('transcriptArea');
        this.summaryArea = document.getElementById('summaryArea');
        this.modeRadios = document.getElementsByName('mode');
        
        this.isRecording = false;
        this.fragment = [];
        this.lastSummaryUpdate = Date.now();
        this.lastText = '';

        // 15秒ごとに議事録更新をチェック
        setInterval(() => this.checkForSummaryUpdate(), 15000);

        // ウィンドウリサイズ時のテキストエリア調整を削除
        // window.addEventListener('resize', () => this.adjustTextAreaHeights());
        // 初期化時にも高さを調整（DOMの読み込み完了後）を削除
        // setTimeout(() => this.adjustTextAreaHeights(), 0);
    }

    /*
    adjustTextAreaHeights() {
        const headerHeight = document.querySelector('.header').offsetHeight;
        const controlsHeight = document.querySelector('.recognition-controls').offsetHeight;
        const summaryControlsHeight = document.querySelector('.summary-controls').offsetHeight;
        const windowHeight = window.innerHeight;
        const bodyPadding = 20; // body padding
        const containerGap = 10; // container gap
        const textAreaPadding = 15; // textarea padding
        const borderWidth = 4; // border width (2px * 2)
        
        // 利用可能な高さを計算（余白や境界線を考慮）
        const availableHeight = windowHeight - headerHeight - Math.max(controlsHeight, summaryControlsHeight) 
            - (bodyPadding * 2) - containerGap - (textAreaPadding * 2) - borderWidth - 15; // 5pxの追加マージン
        
        // テキストエリアに高さを設定
        if (availableHeight > 0) {
            console.log( 'h:'+availableHeight )
            this.transcriptArea.style.height = `${availableHeight}px`;
            this.summaryArea.style.height = `${availableHeight}px`;
        }
    }
    */

    getCurrentMode() {
        for (const radio of this.modeRadios) {
            if (radio.checked) {
                return radio.value;
            }
        }
        return 'summary'; // デフォルトは要約モード
    }

    updateUIForRecordingStart() {
        this.isRecording = true;
        this.speechControl.textContent = '音声認識: 実行中';
        this.speechControl.classList.add('active');
    }

    updateUIForRecordingEnd() {
        this.isRecording = false;
        this.speechControl.textContent = '音声認識: 停止中';
        this.speechControl.classList.remove('active');
    }

    updateUIForRecognitonState(st) {
        if( this.isRecording ) {
            if( st==1 ) {
                this.speechControl.textContent = '音声認識: sound';
            } else if( st==2 ) {
                this.speechControl.textContent = '音声認識: speech';
            } else {
                this.speechControl.textContent = '音声認識: silent';
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
                const span = document.createElement('span');
                span.className = this.getConfidenceClass(result.confidence, result.isFinal);
                span.textContent = result.text + ' ';
                this.fragment.push(span);
            }
        }
        const fragment = document.createDocumentFragment();
        for (const result of this.fragment) {
            fragment.appendChild(result)
        }
        for (const result of results) {
            if (!result.isFinal) {
                const span = document.createElement('span');
                span.className = this.getConfidenceClass(result.confidence, result.isFinal);
                span.textContent = result.text + ' ';
                fragment.appendChild(span);
            }
        }
        // 既存の内容を置き換え
        this.transcriptArea.innerHTML = ''; // 必要に応じてリセット
        this.transcriptArea.appendChild(fragment);

        // 最下部にスクロール
        this.transcriptArea.scrollTop = this.transcriptArea.scrollHeight;
    }

    async checkForSummaryUpdate() {
        const currentText = this.transcriptArea.textContent.trim()
        if( this.lastText == currentText ) {
            return;
        }

        const currentMode = this.getCurrentMode();
        if (currentMode === 'off') {
            this.llmStatusDiv.textContent = 'LLM: OFF';
            return;
        }
        return;
        const currentTime = Date.now();
        if (currentTime - this.lastSummaryUpdate >= 15000) {
            this.lastSummaryUpdate = currentTime;
            this.lastText = currentText
            try {
                this.llmStatusDiv.textContent = 'LLM: 処理中';
                this.llmStatusDiv.classList.add('processing');

                const response = await fetch('/process_audio', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 
                        text: currentText,
                        mode: currentMode
                    })
                });

                const data = await response.json();
                if (data.error) {
                    console.error('処理エラー:', data.error);
                    this.llmStatusDiv.textContent = 'LLM: エラー';
                } else {
                    this.updateSummaryUI(data.response);
                    this.llmStatusDiv.textContent = 'LLM: 待機中';
                }
            } catch (error) {
                console.error('処理中にエラーが発生:', error);
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
        this.speechControl.textContent = '音声認識: エラー';
        this.speechControl.classList.remove('active');
        this.llmStatusDiv.textContent = 'LLM: 停止';
    }

    showBrowserSupportError() {
        this.speechControl.textContent = '音声認識: 非対応';
        this.speechControl.classList.remove('active');
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
