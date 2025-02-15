import asyncio
from asyncio.subprocess import Process as SubProcess
import traceback
import time
import math
import re,json
from typing import NamedTuple
from io import BytesIO
from io import BufferedReader
import subprocess
from subprocess import Popen
from multiprocessing import Process, Value, Array, Manager, Queue
from queue import Empty
#from multiprocessing.connection import Connection
import threading
from threading import Thread
import numpy as np
from numpy.typing import NDArray

from typing import Optional
import os
from logging import getLogger, Logger, StreamHandler, FileHandler, Formatter,  DEBUG as LV_DEBUG, INFO as LV_INFO, WARN as LV_WARN

try:
    import mlx.core as mx
    import mlx_whisper
    USE_MLX_WHISPER:bool = True
except:
    USE_MLX_WHISPER:bool = False

# tiny base small medium large
WHISPER_MODEL_TINY_EN = "mlx-community/whisper-tiny.en-mlx-q4"
WHISPER_MODEL_LARGE_EN = "mlx-community/whisper-small.en-mlx-q4"

WM = {
    'en': 'small.en',
    'ja': 'kotoba',

    'kotoba': ("kaiinui/kotoba-whisper-v1.1-mlx",'ja'),
    'tiny.ja': ("mlx-community/whisper-tiny-mlx-q4",'ja'),
    'base.ja': ("mlx-community/whisper-base-mlx-q4",'ja'),
    'small.ja': ("mlx-community/whisper-small-mlx-q4",'ja'),
    'medium.ja': ("mlx-community/whisper-medium-mlx-q4",'ja'),
    'large.ja': ("mlx-community/whisper-large-v3-turbo-q4",'ja'),

    'tiny.en': (WHISPER_MODEL_TINY_EN,'en'),
    'base.en': ("mlx-community/whisper-base.en-mlx-q4",'en'),
    'small.en': ("mlx-community/whisper-small.en-mlx-q4",'en'),
    #'medium.en': ("mlx-community/whisper-medium.en-mlx-q4",'en'),

    'tiny': ("mlx-community/whisper-tiny-mlx-q4",''),
    'base': ("mlx-community/whisper-base-mlx-q4",''),
    'small': ("mlx-community/whisper-small-mlx-q4",''),
    'medium': ("mlx-community/whisper-medium-mlx-q4",''),
    'large': ("mlx-community/whisper-large-v3-turbo-q4",''),
}

def lang_to_model(lang:str|None)->tuple[str,str]:
    if lang is not None and lang.strip()!='' and lang!='off':
        ret = lang.lower()
        if ret.startswith('en-'):
            ret='en'
        elif ret.startswith('ja-'):
            ret='ja'
        while isinstance(ret,str):
            ret = WM.get(ret)
        if isinstance(ret,tuple):
            return ret
    return WHISPER_MODEL_TINY_EN,'off'

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
    def __init__(self, id:int, seek:int, start:float, end:float, text:str, avg_logprob:float, compression_ratio:float, no_speech_prob:float, audio:NDArray[np.float32]):
        self.tid:int =id
        self.seek: int = seek
        self.start:float = start
        self.end:float = end
        self.text:str = text.strip() if text else ''
        self.isFixed:bool = False
        self.avg_logprob = avg_logprob
        self.compression_ratio:float = compression_ratio
        self.no_speech_prob:float = no_speech_prob
        self.audio:NDArray[np.float32] = audio
    def json(self):
        return {'seek': self.seek, 'start':self.start, 'end':self.end, 'isFixed':self.isFixed, 'text': self.text,
                 'prob':self.avg_logprob, 'comp':self.compression_ratio, 'no_speech':self.no_speech_prob }
    @staticmethod
    def is_recog_success_dict( seg:dict|None ) ->bool:
        try:
            if isinstance(seg,dict):
                return Seg.is_recog_success( seg.get('text'), seg.get('avg_logprob'), seg.get('compression_ratio'), seg.get('no_speech_prob') )
        except Exception as ex:
            print(f"ERROR:is_recog_success_dict {str(ex)}")
        return False
    @staticmethod
    def is_recog_success( text:str|None, avg_logprob:float|None, compression_ratio:float|None, no_speech_prob:float|None ) ->bool:
        if not isinstance(text,str) or len(text.strip())==0:
            return False
        if not isinstance(avg_logprob,float) or not isinstance(compression_ratio,float) or not isinstance(no_speech_prob,float):
            return False
        if avg_logprob<-0.5:
            return False # 認識の信頼性が低い
        if compression_ratio<0.5 or 2.0<compression_ratio:
            return False # 
        if no_speech_prob>0.2:
            return False
        if avg_logprob>-0.7:
            return True
        if 0.8<compression_ratio and compression_ratio<1.4:
            return True
        if 0.1>no_speech_prob:
            return True
        return False
        
class TextSeg(NamedTuple):
    seq:int
    start:float
    end:float
    text:str
    audio:NDArray[np.float32]

def transcribe(audio:np.ndarray, *, model:str=WHISPER_MODEL_TINY_EN, lang:str='', prompt:str|None=None,logger:Logger|None=None) -> list[Seg]:

    if not USE_MLX_WHISPER:
        return []
    xlang = lang if lang!='' else None
    t0 = time.time()
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=model,
        language=xlang,
        prompt=prompt,
        #hallucination_silence_threshold=0.5,
        no_speech_threshold=0.2,
        fp16=False,
        verbose=None)
    if logger is not None:
        t0 = time.time()-t0
        logger.info(f"[transcribe] elaps time {t0:.3f}/{len(audio)/SAMPLE_RATE:.3f}sec")
    segs = result.get("segments") if isinstance(result,dict) else None
    ret = []
    if isinstance(segs,list):
        for seg in segs:
            id=seg.get('id')
            seek=seg.get('seek')
            start = seg.get('start')
            end = seg.get('end')
            text = seg.get('text')
            avg_logprob=seg.get('avg_logprob')
            compression_ratio=seg.get('compression_ratio')
            no_speech_prob=seg.get('no_speech_prob')
            if Seg.is_recog_success(text,avg_logprob,compression_ratio,no_speech_prob):
                s = max(0,int((start-0.1)*SAMPLE_RATE))
                e = max(int((end+0.1)*SAMPLE_RATE),len(audio))
                b = audio[s:e].copy()
                ret.append(Seg(id,seek,start,end,text,avg_logprob,compression_ratio,no_speech_prob,b))
    else:
        print(f"ERROR:result={result}")
    return ret

async def async_ffmpeg() ->SubProcess:
    cmd = "ffmpeg"
    cmdline = [
            "-err_detect", "ignore_err","-ignore_unknown", "-flags", "low_delay",
            "-i", "-",
            "-loglevel", "error",
            "-threads", "0",
            "-f", "s16le",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE),
            "-"
    ]
    bufsz = 512
    ffmpeg_process = await asyncio.create_subprocess_exec(cmd, *cmdline,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE )
    return ffmpeg_process

def popen_ffmpeg() ->Popen:
    cmdline = [
            "ffmpeg",
            "-err_detect", "ignore_err","-ignore_unknown", "-flags", "low_delay",
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
    ffmpeg_process = Popen(cmdline,bufsize=bufsz,pipesize=bufsz, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return ffmpeg_process

async def check_audio(audio:bytes,size:int) ->str:
    try:
        proc:SubProcess = await async_ffmpeg()
        if proc is None:
            return "can not start ffmpeg"
        else:
            try:
                ok=False
                err='can not convert audio'
                if proc.stdin:
                    proc.stdin.write(audio)
                    proc.stdin.close()
                    if proc.stdout:
                        output = await proc.stdout.read()
                        if isinstance(output,bytes) and len(output)>0:
                            aa = np.frombuffer(output,dtype=np.int16)
                            if isinstance(aa,np.ndarray) and len(aa)>0:
                                err = ''
                                ok = True
                            else:
                                err = f"invalid audio length {len(aa)}!={size}"
                    if proc.stderr:
                        lines = await proc.stderr.read()
                        if len(lines)>0:
                            err = lines.decode().strip()
                            if "File ended prematurely at pos" in err:
                                err=""
                if err:
                    return err
                if ok:
                    return ''
                return 'Can not convert audio'
            finally:
                try:
                    proc.kill()
                except Exception as ex:
                    pass
    except Exception as ex:
        traceback.print_exc()
        return f"Exception:{str(ex)}"

class MlxWhisperProcess:
    def __init__(self, *, logfile:str|None=None):
        self._transcribe_closed:bool = False
        self._whisper_process = None
        self._share_bufsz = Array('i',4)
        self._share_id = Value('i',0)
        self._transcribe_queue:Queue[tuple[list[TextSeg],list[str]]] = Queue()
        self._audio_queue:Queue = Queue()
        self._logfile:str|None = logfile
        self._language = 'off'

    def set_language(self, lang: str):
        """言語設定を更新する"""
        self._language = lang
        if self._whisper_process and self._whisper_process.is_alive():
            # 言語設定を更新するためにキューに特別なメッセージを送信
            print(f"request lang={lang}")
            self._audio_queue.put(('set_language', lang))
        else:
            print(f"set lang={lang}")

    def append_audio(self, seq:int, typ:str, data: bytes) ->float:
        if isinstance(data,bytes) and len(data)>0 and self._whisper_process and self._whisper_process.is_alive():
            #print(f"[AUdio]{seq},{typ}")
            self._audio_queue.put(data)
            self._share_bufsz[0] += len(data)
            time.sleep(0.01)
        try:
            b = self._share_bufsz[0] - self._share_bufsz[1]
            if b<=0:
                return 0
            elif b<1049:
                return 0.001
            elif b<1048576:
                return round( b/1048576, 3 )
            return round( b/1048576, 1 )
        except:
            return 0.0

    def close_audio(self):
        if self._whisper_process and self._whisper_process.is_alive():
            self._audio_queue.put(b'')
            time.sleep(0.01)

    async def read(self,*,timeout:float=3.0) ->tuple[list[str],list[str]]|None:
        while not self._transcribe_closed:
            try:
                data = self._transcribe_queue.get_nowait()
                if data is not None:
                    if isinstance(data,tuple):
                        a,b = data
                        aa = [ x.text for x in a]
                        return (aa,b)
                    else:
                        self._transcribe_closed = True
            except Empty:
                pass
            await asyncio.sleep(0.2)
        return None

    def start(self):
        # start whisper
        if self._whisper_process is None or not self._whisper_process.is_alive():
            print(f"[Whisper]start process")
            self._share_bufsz[0] = 0
            self._share_bufsz[1] = 0
            self._share_bufsz[2] = 0
            self._share_bufsz[3] = 0
            try:
                while True:
                    self._audio_queue.get_nowait()
            except:
                pass
            self._whisper_process = Process(target=self._th_transcribe, name='mlxwhisper', args=(self._share_id, self._share_bufsz,self._audio_queue,self._transcribe_queue, self._language, self._logfile))
            self._whisper_process.start()

    @staticmethod
    def segment_split( previous:list[Seg], current:list[Seg], secs ) ->int:
        """確定した位置を決定する
            return: currentで確定したインデックス(インデックス位置を含む)
        """
        if not isinstance(previous,list) or not isinstance(current,list):
            return -1
        pre_size = len(previous)
        cur_size = len(current)
        regex = r'[a-zA-Z][.!?][ ]*$'
        #---step.1
        tail_blank_sec = secs-(current[-1].end) if cur_size>0 else 0
        if tail_blank_sec>1.2:
            return cur_size-1 # テキストの最後と音声の最後が1.2秒あれば、全部確定

        if cur_size <=1:
            return -1 # セグメントが1以下の場合は、確定しない
        elif cur_size==2:
            if re.search(regex,current[0].text):
                if re.search(regex,current[1].text):
                    if (secs-current[1].end)>0.4:
                        return 0 # セグメントが2個の場合、時間感覚が0.4秒以上あれば確定する
            return -1
        else:
            return cur_size-3 # セグメントが3個以上あったら、最後の二つ以外は確定

    def _th_transcribe(self,share_id, share_bufsz, audio_queue:Queue, stdout:Queue, lang:str, logfile:str|None=None):
        run:bool = True
        acnt:int = 0
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
            ffmpeg_process = popen_ffmpeg()

            #--------------------
            #--------------------
            ffmpeg_closed:bool=False
            def to_stderr():
                try:
                    # copy input audio
                    while run and ffmpeg_process and ffmpeg_process.stderr:
                        time.sleep(0.01)
                        b = ffmpeg_process.stderr.read()
                        if b: # and not ffmpeg_closed:
                            print(f"[FFMPEG]{b.decode()}")
                            logger.info(f"[FFMPEG] {b.decode()}")
                        else:
                            break
                except Exception as ex:
                    traceback.print_exc()
            
            err_thread = Thread( target=to_stderr, name='ffmpeg_stderr', daemon=True )
            err_thread.start()
        
            #--------------------
            #--------------------
            model,lang = lang_to_model(lang)
            print(f"[Whisper] Language {model} {lang}")
            bmodel = model
            blang = lang
            def to_ffmpeg():
                logger.info("[CP]start")
                try:
                    seq:int = 0
                    # copy input audio
                    while run and ffmpeg_process and ffmpeg_process.stdin:
                        time.sleep(0.01)
                        if not audio_queue.empty():
                            data = audio_queue.get()
                            if isinstance(data, tuple) and data[0] == 'set_language':
                                # 言語設定の更新
                                nonlocal bmodel
                                nonlocal blang
                                bmodel,blang = lang_to_model(data[1])
                                logger.info(f"[CP] Language changed to {bmodel} {blang}")
                                print(f"[CP] Language changed to {bmodel} {blang}")
                            elif isinstance(data,bytes) and len(data)>0 :
                                if seq==0:
                                    print(f"[CP]write data")
                                share_bufsz[1] += len(data)
                                ffmpeg_process.stdin.write( data )
                                fname = f'tmp/dump/webm{seq:06d}.webm'
                                os.makedirs('tmp/dump',exist_ok=True)
                                with open( fname, 'wb') as f:
                                    f.write(data)
                                seq+=1
                            else:
                                logger.info("[CP]close")
                                print(f"[CP]close")
                                nonlocal ffmpeg_closed
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
            minimum_buf_size = int( seg_sec * SAMPLE_RATE )
            buffer:NDArray[np.float32] = np.zeros( SAMPLE_RATE*30, dtype=np.float32)
            buffer_len:int = 0
            prev_segments:list[Seg] = []
            blanktime = SAMPLE_RATE *0.8
            read_unit=int(SAMPLE_RATE*0.2)
            #
            while run and ffmpeg_process and ffmpeg_process.stdout:
                time.sleep(0.01)
                if model!=bmodel or lang!=blang:
                    model = bmodel
                    lang = blang
                    logger.info(f"[Whisper] Language {model} {lang}")
                    print(f"[Whisper] Language {model} {lang}")
                # get audio segment
                if acnt==0:
                    print(f"[Whisper]wait audio")

                read_frames=0
                read_buf_sec = 0.0
                while not ffmpeg_closed and not ffmpeg_process.stdout.closed:
                    frames=min(read_unit,len(buffer)-buffer_len)
                    if frames==0:
                        break
                    read_buf_sec=time.time()
                    buf:bytes = ffmpeg_process.stdout.read(frames*2)
                    read_buf_sec=time.time()-read_buf_sec
                    # convert bytes to np.ndarray
                    audio_seg = np.frombuffer(buf,dtype=np.int16).astype(np.float32) / 32768.0
                    audio_len=len(audio_seg)
                    read_frames+=audio_len
                    # add to buffer
                    buffer[buffer_len:buffer_len+audio_len] = audio_seg
                    buffer_len+=audio_len
                    if read_frames>=minimum_buf_size and read_buf_sec>0.1:
                        break

                if acnt==0:
                    print(f"[Whisper]started audio")
                acnt+=1

                # transcrib
                if buffer_len>0:
                    prompt = ' '.join( [s.text for s in prev_segments] ) if len(prev_segments)>0 else None
                    trans_sec = time.time()
                    segments = transcribe(buffer[:buffer_len], model=model,lang=lang, prompt=prompt, logger=logger)
                    trans_sec = time.time() - trans_sec
                    buf_sec = buffer_len/SAMPLE_RATE
                    rate = trans_sec/buf_sec
                    if rate>1.0:
                        print(f"elaps {trans_sec:.1f}/{buf_sec:.1f} = {rate:.2f} lang:{lang}")
                else:
                    segments = []

                out1:list[TextSeg] = []
                out2:list[str] = []
                if segments and len(segments)>0:
                    fixed_pos = MlxWhisperProcess.segment_split(prev_segments,segments,buffer_len/SAMPLE_RATE)
                    logstr = '\n'.join( [f"  {x.json()}" for x in segments])
                    logger.debug( f"# transcribe results split:{fixed_pos}\n{logstr}")

                    if fixed_pos>=0:
                        # 確定したテキストがあれば
                        for seg in segments[:fixed_pos+1]:
                            seg.isFixed = True
                            logger.info( f"[Text] fix {seg.text}")
                            seq = share_id.value
                            share_id.value += 1
                            ts = TextSeg(seq,0.0,1.0,seg.text,seg.audio)
                            out1.append(ts)
                        # 最後の確定セグメントの終了位置（サンプル数）を計算
                        last_end_sample = int(segments[fixed_pos].end * SAMPLE_RATE)               
                        # バッファをシフト
                        remaining_samples = buffer_len - last_end_sample
                        if remaining_samples > 0:
                            np.copyto(buffer[0:remaining_samples], buffer[last_end_sample:buffer_len])
                            buffer_len = remaining_samples
                        else:
                            buffer_len = 0
                        segments = segments[fixed_pos+1:]
                    for seg in segments:
                        logger.info( f"[Text] tmp {seg.text}")
                        out2.append(seg.text)
                else:
                    logger.debug( f"# transcribe result: []")
                    # no result
                    for seg in prev_segments:
                        if not seg.isFixed:
                            seq = share_id.value
                            share_id.value += 1
                            ts = TextSeg(seq,0.0,1.0,seg.text,seg.audio)
                            out1.append(ts)
                    if buffer_len>minimum_buf_size:
                        x = buffer_len - minimum_buf_size
                        np.copyto( buffer[0:minimum_buf_size], buffer[x:buffer_len] )
                        buffer_len = minimum_buf_size
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
        self._transcribe_closed = True
        try:
            if self._whisper_process and self._whisper_process.is_alive():
                self._whisper_process.terminate()
                for i in range(10):
                    time.sleep(0.2)
                    if self._whisper_process is None or not self._whisper_process.is_alive():
                        return
                self._whisper_process.kill()
        except Exception as ex:
            print(f"[Whisp]stop {str(ex)}")
        finally:
            self._whisper_process = None
