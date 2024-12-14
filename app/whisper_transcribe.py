import asyncio
import traceback
import time
import re,json
from typing import NamedTuple
from io import BytesIO
from io import BufferedReader
import subprocess
from multiprocessing import Process, Queue
from queue import Empty
from multiprocessing.connection import Connection
import threading
from threading import Thread
import numpy as np
from numpy.typing import NDArray
import mlx.core as mx
import mlx_whisper
from typing import Optional
import scipy.io.wavfile
import os
from logging import getLogger, Logger, StreamHandler, FileHandler, Formatter,  DEBUG as LV_DEBUG, INFO as LV_INFO, WARN as LV_WARN

WHISPER_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
#WHISPER_MODEL_NAME = "mlx-community/whisper-tiny.en-mlx-q4"
#WHISPER_MODEL_NAME = "mlx-community/whisper-base.en-mlx-q4"
WHISPER_MODEL_NAME = "mlx-community/whisper-small.en-mlx-q4"
SAMPLE_RATE=16000
_pcm_counter = 0

"""
mlx_whisper Transcribe Output Format

The transcribe method in mlx_whisper returns a Python dictionary with the following structure:

Return Type:
- **dict**: The result of the transcription process.

Top-Level Keys:
- **text** (`str`): A string containing the full transcription of the audio.
- **segments** (`list` of `dict`): A list of segments, where each segment represents a portion of the audio transcription.
- **language** (`str`): The detected language of the transcription (e.g., "en" for English).

Segment Structure:
Each segment in the `segments` list is a dictionary with the following keys:
- **id** (`int`): The unique identifier for the segment.
- **seek** (`int`): The seek position in the audio where this segment starts (in frames).
- **start** (`float`): The start time of the segment (in seconds).
- **end** (`float`): The end time of the segment (in seconds).
- **text** (`str`): The transcription text for this segment.
- **tokens** (`list` of `int`): The tokenized representation of the text.
- **temperature** (`float`): The temperature used during decoding.
- **avg_logprob** (`float`): The average log probability of the tokens in this segment.
- **compression_ratio** (`float`): The compression ratio of the text in this segment.
- **no_speech_prob** (`float`): The probability that no speech is present in this segment.

Example Output:
1. Single segment transcription:
```python
{
    "text": "A few hours of downtime yesterday.",
    "segments": [
        {
            "id": 0,
            "seek": 0,
            "start": 0.0,
            "end": 1.7,
            "text": "A few hours of downtime yesterday.",
            "tokens": [50365, 316, 1326, 2496, 295, 49648, 5186, 13, 50450],
            "temperature": 0.0,
            "avg_logprob": -0.286,
            "compression_ratio": 1.141,
            "no_speech_prob": 2.195e-10
        }
    ],
    "language": "en"
}
"""

class Seg:
    """transcribeの結果にisFixedフラグを追加したクラス"""
    def __init__(self, id:int, seek:int, start:float, end:float, text:str, avg_logprob:float, compression_ratio:float, no_speech_prob:float):
        self.tid:int =id
        self.seek: int = seek
        self.start:float = start
        self.end:float = end
        self.text:str = text.strip() if text else ''
        self.isFixed:bool = False
        self.avg_logprob = avg_logprob
        self.compression_ratio:float = compression_ratio
        self.no_speech_prob:float = no_speech_prob
    def json(self):
        return {'seek': self.seek, 'start':self.start, 'end':self.end, 'isFixed':self.isFixed, 'text': self.text,
                 'prob':self.avg_logprob, 'comp':self.compression_ratio, 'no_speech':self.no_speech_prob }

def transcribe(audio:np.ndarray, *, prompt:str|None=None,logger:Logger|None=None) -> list[Seg]:
    t0 = time.time()
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=WHISPER_MODEL_NAME,
        language='en',
        prompt=prompt,
        #hallucination_silence_threshold=0.5,
        no_speech_threshold=0.2,
        fp16=False,
        verbose=None)
    if logger is not None:
        t0 = time.time()-t0
        logger.info(f"[transcribe] elaps time {t0:.3f}/{len(audio)/SAMPLE_RATE:.3f}sec")
    segs = result.get("segments") if isinstance(result,dict) else None
    if isinstance(segs,list):
        return [
            Seg( id=seg.get('id'), seek=seg.get('seek'),
                 start = seg.get('start'), end = seg.get('end'), text = seg.get('text'),
                 avg_logprob=seg.get('avg_logprob'), compression_ratio=seg.get('compression_ratio'),no_speech_prob=seg.get('no_speech_prob'))
            for seg in segs if seg.get('text') and seg.get('no_speech_prob',0.0)<0.2
        ]
    return []

class MlxWhisperProcess:
    def __init__(self, *, logfile:str|None=None):
        self._transcribe_closed:bool = False
        self._whisper_process = None
        self._transcribe_queue:Queue = Queue()
        self._audio_queue:Queue = Queue()
        self._logfile:str|None = logfile

    def append_audio(self, data: bytes):
        if len(data)>0 and self._whisper_process and self._whisper_process.is_alive():
            self._audio_queue.put(data)

    def close_audio(self):
        if self._whisper_process and self._whisper_process.is_alive():
            self._audio_queue.put(b'')

    async def read(self) ->tuple[list[str],list[str]]|None:
        while not self._transcribe_closed:
            try:
                data = self._transcribe_queue.get_nowait()
                if data is not None:
                    if isinstance(data,tuple):
                        return data
                    else:
                        self._transcribe_closed = True
            except Empty:
                pass
            await asyncio.sleep(0.2)
        return None

    def start(self):
        # start whisper
        self._whisper_process = Process(target=self._th_transcribe, name='mlxwhisper', args=(self._audio_queue,self._transcribe_queue, self._logfile))
        self._whisper_process.start()

    @staticmethod
    def segment_split( previous:list[Seg], current:list[Seg], secs ) ->int:
        if not isinstance(previous,list) or not isinstance(current,list):
            return -1
        pre_size = len(previous)
        cur_size = len(current)
        regex = r'[a-zA-Z][.!?][ ]*$'
        if cur_size <=1:
            return -1
        elif cur_size==2:
            if re.search(regex,current[0].text):
                if re.search(regex,current[1].text):
                    if (secs-current[1].end)>0.4:
                        return 0
            return -1
        else:
            return cur_size-3

    def _th_transcribe(self, audio_queue:Queue, stdout:Queue, logfile:str|None=None):
        run:bool = True
        try:
            logger = getLogger( __name__ )
            if logfile is not None:
                logger.setLevel(LV_DEBUG)
                fh = FileHandler(logfile)
                fh.setLevel(LV_DEBUG)
                formatter = Formatter('%(asctime)s - %(levelname)s - %(message)s')
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            logger.info(f"[Whisper] Start")
            #--------------------
            # start ffmpeg
            #--------------------
            cmdline = [
            "ffmpeg",
            "-i", "-",
            "-loglevel", "error",
            "-threads", "0",
            "-f", "s16le",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE),
            "-"
            ]
            bufsz = 8192
            ffmpeg_process = subprocess.Popen(cmdline, bufsize=bufsz, pipesize=bufsz, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

            #--------------------
            #--------------------
            ffmpeg_closed:bool=False
            def to_stderr():
                try:
                    # copy input audio
                    while run and ffmpeg_process and ffmpeg_process.stderr:
                        b = ffmpeg_process.stderr.readline()
                        if b and not ffmpeg_closed:
                            logger.info(f"[FFMPEG] {b.decode()}")
                        else:
                            break
                except Exception as ex:
                    pass
            
            err_thread = Thread( target=to_stderr, name='ffmpeg_stderr', daemon=True )
            err_thread.start()
        
            #--------------------
            #--------------------
            def to_ffmpeg():
                logger.info("[CP]start")
                try:
                    # copy input audio
                    while run and ffmpeg_process and ffmpeg_process.stdin:
                        if not audio_queue.empty():
                            data = audio_queue.get()
                            if len(data)>0:
                                ffmpeg_process.stdin.write( data )
                            else:
                                logger.info("[CP]close")
                                print(f"[cp]close")
                                ffmpeg_closed = True
                                ffmpeg_process.stdin.close()
                                break
                except Exception as ex:
                    logger.info(f"[CP] {str(ex)}")
                finally:
                    logger.info("[CP]end")
            
            copy_thread = Thread( target=to_ffmpeg, name='ffmpeg_stdin', daemon=True )
            copy_thread.start()

            #--------------------
            #--------------------
            def is_split(text:str) ->bool:
                if text and re.search( r'[a-zA-Z][.!?]$',text):
                    return True
                return False
            #--------------------
            #--------------------
            seg_sec = 1.0
            seg_size = int( seg_sec * SAMPLE_RATE )
            read_size = int(seg_size*2)
            buffer:NDArray[np.float32] = np.zeros( SAMPLE_RATE*30, dtype=np.float32)
            buffer_len:int = 0
            prev_segments:list[Seg] = []
            blanktime = SAMPLE_RATE *0.8
            #
            while run and ffmpeg_process and ffmpeg_process.stdout:
                # get audio segment
                buf:bytes = ffmpeg_process.stdout.read(read_size)
                if len(buf)>0:
                    # convert bytes to np.ndarray
                    audio_seg = np.frombuffer(buf,dtype=np.int16).astype(np.float32) / 32768.0
                    sz=len(audio_seg)
                    # add to buffer
                    buffer[buffer_len:buffer_len+sz] = audio_seg
                    buffer_len+=sz
                    # transcrib
                    prompt = ' '.join( [s.text for s in prev_segments] ) if len(prev_segments)>0 else None
                    segments = transcribe(buffer[:buffer_len], prompt=prompt, logger=logger)
                else:
                    segments = []

                out1 = []
                out2 = []
                if segments:
                    split = MlxWhisperProcess.segment_split(prev_segments,segments,buffer_len*SAMPLE_RATE)
                    logstr = '\n'.join( [f"  {x.json()}" for x in segments])
                    logger.debug( f"# transcribe results split:{split}\n{logstr}")

                    if split>=0:
                        for seg in segments[:split+1]:
                            seg.isFixed = True
                            logger.info( f"[Text] fix {seg.text}")
                            out1.append(seg.text)
                        # 最後の確定セグメントの終了位置（サンプル数）を計算
                        last_end_sample = int(segments[split].end * SAMPLE_RATE)               
                        # バッファをシフト
                        remaining_samples = buffer_len - last_end_sample
                        if remaining_samples > 0:
                            np.copyto(buffer[0:remaining_samples], buffer[last_end_sample:buffer_len])
                            buffer_len = remaining_samples
                        else:
                            buffer_len = 0
                        segments = segments[split+1:]
                    for seg in segments:
                        logger.info( f"[Text] tmp {seg.text}")
                        out2.append(seg.text)
                else:
                    logger.debug( f"# transcribe result: []")
                    # no result
                    for seg in prev_segments:
                        if not seg.isFixed:
                            out1.append(seg.text)
                    if buffer_len>(2*seg_size):
                        x = buffer_len - seg_size
                        np.copyto( buffer[0:seg_size], buffer[x:buffer_len] )
                        buffer_len = seg_size
                if out1 or out2:
                    stdout.put( (out1,out2) )
                # 次の比較用に現在のセグメントを保存
                prev_segments = segments
                if len(buf)==0:
                    print("endwh")
                    break

        except Exception as ex:
            traceback.print_exc()
            logger.info(f"[Whisper] {str(ex)}")
        finally:
            stdout.put( "None" )
            run = False
            try:
                copy_thread.join(0.2)
            except:
                pass
            try:
                if ffmpeg_process is not None:
                    ffmpeg_process.terminate()
            except:
                pass
            logger.info(f"[Whisper] End")

    def stop(self):
        try:
            if self._whisper_process and self._whisper_process.is_alive():
                self._whisper_process.terminate()
                for i in range(10):
                    time.sleep(0.2)
                    if not self._whisper_process.is_alive():
                        return
                self._whisper_process.kill()
        finally:
            self._whisper_process = None