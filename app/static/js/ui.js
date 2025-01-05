
// Cookie操作のユーティリティ関数
const CookieUtil = {
    setCookie: function(name, value, days = 30) {
        const d = new Date();
        d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
        const expires = "expires=" + d.toUTCString();
        document.cookie = name + "=" + value + ";" + expires + ";path=/";
        //console.log('setCookie', name + "=" + value + ";" + expires + ";path=/" )
    },
    
    getCookie: function(name, value) {
        const cookieName = name + "=";
        const cookies = document.cookie.split(';');
        for(let i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim();
            if (cookie.indexOf(cookieName) === 0) {
                ret = cookie.substring(cookieName.length, cookie.length);
                //console.log('getCookie', cookie, ret )
                return ret;
            }
        }
        return value;
    }
};

class UIController {
    constructor() {
        this.values = {}
        this.event_from_ui = {}
        this.event_to_ui = {}
        this.speechControl = document.getElementById('speechControl');
        this.bufsize = document.getElementById('bufsize');
        this.llmStatusDiv = document.getElementById('llmStatus');
        this.transcriptArea = document.getElementById('transcriptArea');
        this.summaryArea = document.getElementById('summaryArea');
        
        this.isRecording = false;
        this.fragment = [];
        this.lastSummaryUpdate = Date.now();
        this.lastText = '';

        // ウィンドウリサイズ時のテキストエリア調整を削除
        // window.addEventListener('resize', () => this.adjustTextAreaHeights());
        // 初期化時にも高さを調整（DOMの読み込み完了後）を削除
        // setTimeout(() => this.adjustTextAreaHeights(), 0);

        this.values['recogStat'] = 'stop';
        const recogStat = document.getElementById('recogStat');
        recogStat.onclick = () => {
            console.log('onclick')
            const isStop = this.values['recogStat'] !== 'start'
            const key = isStop ? 'recogStart' : 'recogStop';
            if( key in this.event_from_ui ) {
                console.log('onclick',key)
                this.event_from_ui[key]().then( ()=>{} )
            }
        };
        this.event_to_ui['recogStat'] = async (value) => {
            if( value==='start' ) {
                recogStat.textContent = '音声認識: 実行中';
                recogStat.classList.add('active');
            } else {
                recogStat.classList.remove('active');
                if( value=='stop' ) {
                    recogStat.textContent = '音声認識: 停止中';
                } else if( value=='not' ) {
                    recogStat.textContent = '音声認識: 非対応';
                } else {
                    recogStat.textContent = '音声認識: エラー';
                }
            }
        }
    // lang
        const recogLang = CookieUtil.getCookie('recogLang','English');
        this.values['recogLang'] = recogLang;
        const elem = document.getElementById('recogLang');
        if (elem) {
            // 初期値
            elem.value = recogLang;
            // uiからの通知
            elem.addEventListener('change', (event) => {
                this.updateFromUI('recogLang', event.target.value );
            });
            // uiへの通知
            this.event_to_ui['recogLang'] = async (value) => {
                elem.value = value;
            }
        }
        // echo
        const ids = [ "echoCancellation","noiseSuppression","autoGainControl" ]
        for( const key of ids ) {
            const elem = document.getElementById(key);
            const svalue = CookieUtil.getCookie(key,'false');
            const value = svalue==='true';
            //console.log('get',key,value);
            this.values[key] = value;
            if (elem) {
                //初期値
                elem.checked = value;
                // uiからの通知
                elem.addEventListener('change', (event) => {
                    this.updateFromUI(key,event.target.checked);
                });
                // uiへの通知
                this.event_to_ui[key] = async (value) => {
                    elem.checked = value;
                }
            }
        }
        // モード選択に応じた設定
        const llmMode = CookieUtil.getCookie('llmMode','off');
        this.values['llmMode'] = llmMode;
        // 初期値
        document.querySelectorAll('input[name="llmMode"]').forEach( (radio)=>{
            radio.checked = radio.value===llmMode;
        })
        // uiからの通知
        document.querySelectorAll('input[name="llmMode"]').forEach((radio) => {
            radio.addEventListener('change', async (event) => {
                this.updateFromUI('llmMode', event.target.value );
            });
        });
        // uiへの通知
        this.event_to_ui['llmMode'] = async (value) => {
            document.querySelectorAll('input[name="llmMode"]').forEach( (radio)=>{
                radio.checked = radio.value===value;
            })
        }

        this.event_to_ui['llmStatus'] = async (value) => {
            if( value ) {
                this.llmStatusDiv.textContent = 'LLM: 処理中';
                this.llmStatusDiv.classList.add('processing');
            } else {
                this.llmStatusDiv.textContent = 'LLM: 待機中';
                this.llmStatusDiv.classList.remove('processing');
            }
        }
        this.event_to_ui['bufsize'] = async (value) => {
            if( value ) {
                this.bufsize.textContent = value;
            }
        }
    }

    uiHandler( key, func ) {
        this.event_from_ui[key] = func;
        if( key in this.values) {
            func(this.values[key]).then( ()=>{} )
        }
    }

    updateFromUI( key, value ) {
        if( !key in this.values || this.values[key] !== value ) {
            CookieUtil.setCookie(key, value);
            this.values[key] = value;
            if( key in this.event_from_ui ) {
                this.event_from_ui[key](value).then( ()=>{} );
            }
        }
    }

    updateToUI( key, value ) {
        if( !key in this.values || this.values[key] !== value ) {
            CookieUtil.setCookie(key, value);
            this.values[key] = value;
            if( key in this.event_to_ui ) {
                this.event_to_ui[key](value).then( ()=>{} );
            }
        }
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

    updateSummaryUI(summary) {
        this.summaryArea.value = summary;
        this.summaryArea.scrollTop = this.summaryArea.scrollHeight;
    }

    updateStatusForError(err) {
        console.log('error',err)
    }
}

// UIコントローラーのインスタンスを作成してグローバルに公開
window.uiController = new UIController();
