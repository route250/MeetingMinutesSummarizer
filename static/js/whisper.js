let mediaRecorder;
let audioChunks = [];
let stream;
let socket;

const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const status = document.getElementById('status');
const transcription = document.getElementById('transcription');

// WebSocket接続を初期化
function initializeWebSocket() {
    // Socket.IOクライアントを初期化
    socket = io(window.location.origin, {
        path: '/socket.io',
        transports: ['websocket']
    });

    socket.on('connect', () => {
        console.log('WebSocket接続が確立されました');
    });

    socket.on('transcription', (data) => {
        if (data.text) {
            transcription.textContent += data.text + '\n';
            transcription.scrollTop = transcription.scrollHeight;
        }
    });

    socket.on('connect_error', (error) => {
        console.error('接続エラー:', error);
        status.textContent = 'サーバーへの接続に失敗しました';
    });

    socket.on('disconnect', () => {
        console.log('WebSocket接続が切断されました');
    });
}

// Blobをbase64に変換
async function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64data = reader.result.split(',')[1];
            resolve(base64data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

// 音声録音の設定
const constraints = {
    audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 16000
    }
};

startButton.addEventListener('click', async () => {
    try {
        // WebSocket接続を初期化
        initializeWebSocket();
        
        // マイクへのアクセスを要求
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        
        // MediaRecorderの設定
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        mediaRecorder.ondataavailable = async (event) => {
            if (event.data.size > 0) {
                try {
                    // WebSocketを通じてサーバーに音声データを送信
                    if (socket && socket.connected) {
                        // BlobデータをBase64に変換
                        const base64data = await blobToBase64(event.data);
                        socket.emit('audio_data', base64data);
                    }
                } catch (error) {
                    console.error('音声データの送信エラー:', error);
                }
            }
        };

        // 1秒ごとにデータを取得するように設定
        mediaRecorder.start(1000);
        
        startButton.disabled = true;
        stopButton.disabled = false;
        status.textContent = '録音中...';
        document.body.classList.add('recording');
        
    } catch (error) {
        status.textContent = 'エラー: ' + error.message;
        console.error('Error:', error);
    }
});

stopButton.addEventListener('click', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        stream.getTracks().forEach(track => track.stop());
        
        if (socket && socket.connected) {
            socket.disconnect();
        }
        
        startButton.disabled = false;
        stopButton.disabled = true;
        status.textContent = '録音終了';
        document.body.classList.remove('recording');
    }
});
