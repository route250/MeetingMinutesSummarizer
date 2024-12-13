import asyncio
import time
import re,json
from typing import NamedTuple
from io import BytesIO
from io import BufferedReader
import subprocess
from multiprocessing import Process, Queue
import threading
import numpy as np
from numpy.typing import NDArray
import mlx.core as mx
import mlx_whisper
from typing import Optional
import scipy.io.wavfile
import os

WHISPER_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
WHISPER_MODEL_NAME = "mlx-community/whisper-tiny.en-mlx-q4"
SAMPLE_RATE=16000
_pcm_counter = 0

class Seg:
    def __init__(self, start:float, end:float, text:str):
        self.start:float = start
        self.end:float = end
        self.text:str = text
        self.isFixed:bool = False
    def json(self):
        return {'start':self.start, 'end':self.end, 'isFixed':self.isFixed, 'text': self.text }

def transcribe(audio:np.ndarray) -> list[Seg]:
    t0 = time.time()
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=WHISPER_MODEL_NAME,
        language='en',
        #hallucination_silence_threshold=0.5,
        #no_speech_threshold=0.9,
        fp16=False,
        verbose=True)
    t0 = time.time()-t0
    print(f"transcribe end {t0:.3f}/{len(audio)/SAMPLE_RATE:.3f}sec")
    segs = result.get("segments") if isinstance(result,dict) else None
    if isinstance(segs,list):
        return [
            Seg( start = seg.get('start'), end = seg.get('end'), text = seg.get('text'))
            for seg in segs if seg.get('text')
        ]
    return []

# {"text": " a few hours of down.", "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": 1.0, "text": " a few hours of down.", "tokens": [50365, 257, 1326, 2496, 295, 760, 13, 50415], "temperature": 0.0, "avg_logprob": -0.6053032875061035, "compression_ratio": 0.7142857142857143, "no_speech_prob": 4.431138789229294e-11}], "language": "en"}

# {"text": " A few hours of downtime yesterday.", "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": 2.0, "text": " A few hours of downtime yesterday.", "tokens": [50365, 316, 1326, 2496, 295, 49648, 5186, 13, 50465], "temperature": 0.0, "avg_logprob": -0.363482403755188, "compression_ratio": 0.8095238095238095, "no_speech_prob": 3.643757517934887e-11}], "language": "en"}

# {"text": " a few hours of downtime yesterday. We know you depend...",
#  "segments": [
#     {"id": 0, "seek": 0, "start": 0.0, "end": 1.7, "text": " a few hours of downtime yesterday.",
#      "tokens": [50365, 257, 1326, 2496, 295, 49648, 5186, 13, 50450], "temperature": 0.0, 
#      "avg_logprob": -0.6433430839987362, "compression_ratio": 0.9180327868852459, "no_speech_prob": 1.1374010067122242e-10},
#     {"id": 1, "seek": 0, "start": 2.2800000000000002, "end": 3.0, "text": " We know you depend...",
#      "tokens": [50479, 492, 458, 291, 5672, 485, 50515], "temperature": 0.0,
#      "avg_logprob": -0.6433430839987362, "compression_ratio": 0.9180327868852459, "no_speech_prob": 1.1374010067122242e-10}
#   ], 
# "language": "en"}
# {"text": " a few hours of downtime yesterday. We know you depend on us, and we're really...", "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": 1.7, "text": " a few hours of downtime yesterday.", "tokens": [50365, 257, 1326, 2496, 295, 49648, 5186, 13, 50450], "temperature": 0.0, "avg_logprob": -0.4948151508967082, "compression_ratio": 1.0526315789473684, "no_speech_prob": 1.1376903585880171e-10}, {"id": 1, "seek": 0, "start": 2.1, "end": 4.34, "text": " We know you depend on us, and we're really...", "tokens": [50470, 492, 458, 291, 5672, 322, 505, 11, 293, 321, 434, 534, 485, 50582], "temperature": 0.0, "avg_logprob": -0.4948151508967082, "compression_ratio": 1.0526315789473684, "no_speech_prob": 1.1376903585880171e-10}], "language": "en"}
# {"text": " A few hours of downtime yesterday. We know you depend on us, and we're really sorry for the interruption.", "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": 1.7, "text": " A few hours of downtime yesterday.", "tokens": [50365, 316, 1326, 2496, 295, 49648, 5186, 13, 50450], "temperature": 0.0, "avg_logprob": -0.286235052963783, "compression_ratio": 1.141304347826087, "no_speech_prob": 2.1951529483033028e-10}, {"id": 1, "seek": 0, "start": 2.2800000000000002, "end": 5.0200000000000005, "text": " We know you depend on us, and we're really sorry for the interruption.", "tokens": [50479, 492, 458, 291, 5672, 322, 505, 11, 293, 321, 434, 534, 2597, 337, 264, 728, 11266, 13, 50616], "temperature": 0.0, "avg_logprob": -0.286235052963783, "compression_ratio": 1.141304347826087, "no_speech_prob": 2.1951529483033028e-10}], "language": "en"}
# {"text": " A few hours of downtime yesterday. We know you depend on us, and we're really sorry for the interruption.",
#  "segments": [{"id": 0, "seek": 0, "start": 0.0, "end": 1.7, "text": " A few hours of downtime yesterday.", 
# "tokens": [50365, 316, 1326, 2496, 295, 49648, 5186, 13, 50450], "temperature": 0.0, "avg_logprob": -0.26152604201744345, 
# "compression_ratio": 1.141304347826087, "no_speech_prob": 1.4872600373472267e-10},
#  {"id": 1, "seek": 0, "start": 2.1, "end": 5.14, "text": " We know you depend on us, and we're really sorry for the interruption.", "tokens": [50470, 492, 458, 291, 5672, 322, 505, 11, 293, 321, 434, 534, 2597, 337, 264, 728, 11266, 13, 50622], "temperature": 0.0, "avg_logprob": -0.26152604201744345, "compression_ratio": 1.141304347826087, "no_speech_prob": 1.4872600373472267e-10}], "language": "en"}

def _th_transcribe( stdout:Queue, queue:Queue ):
    print("[Whis]start")
    try:
        seg_sec = 1.0
        seg_size = int( seg_sec * SAMPLE_RATE )
        read_size = int(seg_size*2)
        audio_buffer:NDArray[np.float32] = np.zeros( SAMPLE_RATE*30, dtype=np.float32)
        pos:int = 0
        offset:float = 0
        preseg:list[Seg] = []
        while True:
            # get audio segment
            buf:bytes = stdout.get()
            if len(buf)<read_size:
                break #EOF
            segment = np.frombuffer(buf,dtype=np.int16).astype(np.float32) / 32768.0
            if len(segment)!=seg_size:
                print("*")
            # add to buffer
            audio_buffer[pos:pos+seg_size] = segment
            pos+=seg_size
            # normalize audio
            #rate = 0.5/np.max(np.abs(audio_buffer[:pos]))
            #nrm_audio = audio_buffer[:pos] * rate
            # transcrib
            segs = transcribe(audio_buffer[:pos])

            fixs = []
            if segs:
                endtime:float = float(pos*SAMPLE_RATE)
                nn = min(len(segs),len(preseg))
                # 確定したセグメントのテキストを追加
                for idx in range(nn):
                    if segs[idx].text and segs[idx].text == preseg[idx].text:
                        if segs[idx].isFixed == False or preseg[idx].isFixed == False:
                            # 確定したテキストを送信
                            print( f"[Text] {segs[idx].text}")
                            fixs.append( segs[idx].json() )
                            segs[idx].isFixed = True
                            preseg[idx].isFixed = True
                cut = -1
                for idx in range(len(segs)):
                    if segs[idx].isFixed:
                        if segs[idx].text.endswith('.'):
                            cut = idx + 1
                        elif idx<len(segs)-1 and (segs[idx+1].start-segs[idx].end)>SAMPLE_RATE:
                            cut = idx + 1
                    else:
                        fixs.append( segs[idx].json() )
                        break
                if cut > 0:
                    # 最後の確定セグメントの終了位置（サンプル数）を計算
                    last_end_sample = int(segs[cut-1].end * SAMPLE_RATE)                    
                    # バッファをシフト
                    remaining_samples = pos - last_end_sample
                    if remaining_samples > 0:
                        np.copyto(audio_buffer[0:remaining_samples], 
                                audio_buffer[last_end_sample:last_end_sample+remaining_samples])
                        pos = remaining_samples
                    else:
                        pos = 0
                    segs = segs[cut:]
                if fixs:
                    queue.put( fixs )
            else:
                # no result
                if pos>(2*seg_size):
                    x = pos - seg_size
                    np.copyto( audio_buffer[0:seg_size], audio_buffer[x:pos] )
                    pos = seg_size
            # 次の比較用に現在のセグメントを保存
            preseg = segs

    finally:
        print("[Whis]end")

class MlxWhisperProcess:
    def __init__(self):
        self._ffmpeg_process = None
        self._copy_thread = None
        self._whisper_process = None
        self._transcribe_queue = Queue()
        self._transfer_queue = Queue()

    def copy(self):
        print("[CP]start")
        try:
            seg_sec = 1.0
            sr = 16000
            seg_size = int( seg_sec * sr )
            read_size = int(seg_size*2)
            while self._ffmpeg_process is not None and self._ffmpeg_process.stdout is not None:
                a = self._ffmpeg_process.stdout.read(read_size)
                if len(a)<read_size:
                    break
                self._transfer_queue.put(a)
        finally:
            print("[CP]end")

    def start(self):
        # start ffmpeg
        cmdline = [
        "ffmpeg",
        "-loglevel", "error",
        "-threads", "0",
        "-f", "webm",
        "-i", "pipe:0",
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(SAMPLE_RATE),
        "-"
        ]
        bufsz = SAMPLE_RATE*3
        self._ffmpeg_process = subprocess.Popen(cmdline, bufsize=bufsz, pipesize=bufsz, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        # transfer
        self._copy_thread = threading.Thread(target=self.copy,daemon=True)
        self._copy_thread.start()
        # start whisper
        self._whisper_process = Process(target=_th_transcribe, args=(self._transfer_queue,self._transcribe_queue))
        self._whisper_process.start()

    def write(self, data: bytes):
        if self._ffmpeg_process and self._ffmpeg_process.stdin:
            self._ffmpeg_process.stdin.write(data)
            #self._ffmpeg_process.stdin.flush()

    def stop(self):
        if self._ffmpeg_process:
            if self._ffmpeg_process.stdin:
                self._ffmpeg_process.stdin.close()
            self._ffmpeg_process.wait(0.2)
        if self._whisper_process:
            self._whisper_process.join(1.0)
        if self._ffmpeg_process:
            self._ffmpeg_process.terminate()
            self._ffmpeg_process = None
        if self._whisper_process:
            self._whisper_process.terminate()
            self._whisper_process = None

    async def read(self) -> Optional[str]:
        ret = self._transcribe_queue.get()
        return ret
