class SpeechRecognitionHandler {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        this.final_map = {};
        this.pertials = []
        this.lastLength = -1;
        this.lastCount = -1;
        this.lastIndex = -1;
        this.fixidx=0;
        this.noUpdateTimer = null;        // 2秒タイマー
        this.lastResultTime = null;       // 最後に結果を受け取った時間
        this.lastTextTime = null;
        this.setupUiHandler();
    }

    setupUiHandler() {
        if ('webkitSpeechRecognition' in window) {
            document.getElementById('languageSelect').addEventListener('change', (event) => {
                const newLang = event.target.value;
                if (this.isListening && this.recognition !== null ) {
                    // 音声認識中の場合は一旦停止して再開
                    this.recognition.stop();
                    this.recognition.lang = newLang;
                    this.recognition.start();
                }
            });    
            document.getElementById('startButton').onclick = () => {
                window.uiController.handleStartButtonClick((shouldStart) => {
                    if (shouldStart) {
                        this.startRecognition();
                    } else {
                        this.stopRecognition();
                    }
                });
            };
        } else {
            window.uiController.showBrowserSupportError();
        }
    }

    startRecognition() {
        if ('webkitSpeechRecognition' in window) {
            this.isListening = true;
            this.recognition = new webkitSpeechRecognition();
            this.setupRecognitionConfig(this.recognition);
            this.recognition.start();
        } else {
            window.uiController.showBrowserSupportError();
        }
    }
    purgeRecognitionConfig(recognition){
        try {
            recognition.onstart = () =>{const a=0;}
            recognition.onend = () =>{const a=0;}
            recognition.onresult = (event) =>{const a=0;}
            recognition.onsoundstart = (event) =>{const a=0;}
            recognition.onsoundend = (event) =>{const a=0;}
            recognition.onspeechstart = (event) =>{const a=0;}
            recognition.onspeechend = (event) =>{const a=0;}
            recognition.onerror = (event) =>{const a=0;}
        } catch(error) {
            console.error('処理中にエラーが発生:', error);
        }
    }
    setupRecognitionConfig(recognition) {
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = document.getElementById('languageSelect').value;

        recognition.onstart = () => {
            console.log('# on_start')
            this.final_map = {};
            this.i1 = 0;
            this.lastLength = -1;
            this.lastCount = -1;
            this.lastIndex = -1;
            this.lastResultTime = Date.now();
            this.startNoUpdateTimer();
            window.uiController.updateUIForRecordingStart();
        };

        recognition.onend = () => {
            console.log('# on_end')
            this.stopNoUpdateTimer();
            this.flush_interm('<|END|>');
            if (this.isListening) {
                // 意図的な停止でない場合は再開する
                console.log('# resume')
                this.recognition = null;
                this.startRecognition();
            } else {
                window.uiController.updateUIForRecordingEnd();
            }
        };

        recognition.onresult = (event) => {
            this.lastResultTime = Date.now();
            this.startNoUpdateTimer();
            this.handleRecognitionResult(event);
        };

        recognition.onerror = (event) => {
            // no-speech エラーは無視（一時的な無音を検出しただけなので）
            this.stopNoUpdateTimer();
            this.purgeRecognitionConfig(this.recognition)
            if (event.error == 'no-speech') {
                console.log('## on_error no-speech')
            } else if(event.error==='aborted') {
                console.log('## on_error aborted')
            } else {
                console.error('音声認識エラー:', event.error);
                window.uiController.updateStatusForError(event.error);
            }
            this.flush_interm('<ERR>')
            this.startRecognition()
        };
    }

    stopRecognition() {
        this.isListening = false;
        this.stopNoUpdateTimer();
        this.recognition.abort();
        this.recognition = null;
    }

    handleRecognitionResult(event) {
        const evres = event.results;
        // for( let i=0; i<event.results.length; i++ ) {
        //     let a = i<this.fixidx ? '*' : ' '
        //     let b = i<event.resultIndex ? '-' : ' '
        //     let c = evres[i].isFinal ? 'F' : '?'
        //     console.log( '['+i+']'+a+b+c+ ' ')
        // }
        let count = 0;
        for( let i=0; i<evres.length; i++ ) {
            if( evres[i][0].transcript!='') {
                count = i;
            }
        }

        let results = [];
        let i=this.fixidx;
        for( ; i<evres.length; i++ ) {
            const r = evres[i];
            if(!(r.isFinal)) break;
            results.push({ text: r[0].transcript, isFinal: true, confidence: r[0].confidence });
        }
        this.fixidx = i
        if( count<this.lastCount ) {
            console.log("# ERROR? "+this.lastCount+"->"+count + " " + this.lastIndex + '->'+ event.resultIndex +' '+this.lastLength+"->"+evres.length)
            //this.stopNoUpdateTimer();
            //this.purgeRecognitionConfig(this.recognition)
            //this.flush_interm(' ...... ')
            //this.startRecognition();
            //return
            if( this.pertials && this.pertials.length>0 ) {
                console.log('#Flush pertials ')
                for( const x in this.pertials ) {
                    results.push(x)
                }
                this.pertials = []
                results.push({ text: '...', isFinal: true, confidence: 1 });
            }
        }
        this.lastLength = evres.length;
        this.lastCount = count;
        this.lastIndex = event.resultIndex;
        const pertials = []
        for( ; i<evres.length; i++ ) {
            const r = evres[i];
            if( r[0].transcript != '' ) {
                pertials.push({ text: r[0].transcript, isFinal: true, confidence: r[0].confidence });
                results.push({ text: r[0].transcript, isFinal: false, confidence: r[0].confidence });
            }
        }
        this.pertials = pertials

        if (results.length > 0) {
            window.uiController.updateTranscriptUI(results);
            this.lastTextTime = Date.now()
        }
    }

    put_newline() {
        if ( typeof this.lastTextTime === 'number' && (Date.now() - this.lastTextTime) > 800) {
            console.log('### newline');
            window.uiController.updateTranscriptUI(['\\n\n']);
            this.lastTextTime = null;
        }
    }

    flush_interm(mark) {
        this.final_map = {};
        this.fixidx = 0
        if( this.pertials && this.pertials.length>0 ) {
            console.log('#Flush pertials '+mark)
            const results = this.pertials;
            results.push( {text:mark, isFinal: true, confidence: 1.0 })
            window.uiController.updateTranscriptUI(results);
            this.lastTextTime = Date.now()
            this.lineline=false
            this.pertials = []
        }
        window.uiController.updateTranscriptUI([]);
    }

    // タイマー関連の新しいメソッド
    stopNoUpdateTimer() {
        if (this.noUpdateTimer) {
            clearTimeout(this.noUpdateTimer);
            this.noUpdateTimer = null;
        }
    }
    startNoUpdateTimer() {
        this.stopNoUpdateTimer()
        this.noUpdateTimer = setTimeout(() => {
            if (this.isListening ) {
                console.log('#NoUpdateTimer restart recognition');
                this.purgeRecognitionConfig(this.recognition)
                this.recognition.abort();
                // 認識を再起動
                this.flush_interm('......')
                this.startRecognition()
            }
        }, 3000);
    }
}

// アプリケーション初期化
document.addEventListener('DOMContentLoaded', () => {
    new SpeechRecognitionHandler();
});
