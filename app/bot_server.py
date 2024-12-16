
import asyncio
import time
from queue import Queue, Empty
from io import BytesIO
from threading import Thread
import wave
import tempfile
import numpy as np
from text_to_voice import TtsEngine
from rec_util import audio_to_wave_bytes

SAMPLE_RATE=16000

class VoiceRes:
    def __init__(self, cmd:int, text:str, voice:bytes ):
        self.cmd = cmd
        self.text = text
        self.voice = voice

class Bot:
    def __init__(self,mode:str='off'):
        config={ 'voicevox_speaker': 8 }
        self.tts:TtsEngine = TtsEngine(config=config)
        self.queue:Queue = Queue()
        self.th = None
        self.run = False
        self.global_messages:list[dict] = []
        self.mode = mode

    def set_mode(self,mode):
        self.mode = mode

    def start(self):
        self.run=True
        if self.th is None:
            self.th = Thread( target=self._th_loop, daemon=True)
            self.th.start()

    def stop(self):
        self.run=False
        if self.th:
            self.th.join(1.0)
            self.th = None

    def _th_loop(self):
        try:
            last_time:float = 0
            while self.run:
                # off,summary,translation,conversation
                if self.mode == 'summary':
                    pass
                elif self.mode == 'translation':
                    pass
                elif self.mode == 'conversation':
                    if (time.time()-last_time)>25.0:
                        text = 'やっほー!'
                        b,m = self.aaa(text)
                        self.queue.put( VoiceRes(1,text,b))
                        last_time = time.time()
                else:
                    pass

                time.sleep(1.0)
        except:
            pass

    def aaa(self,text):
        audio_data,model = self.tts._text_to_audio_by_voicevox(text,sampling_rate=SAMPLE_RATE)
        if audio_data is not None:
            return audio_to_wave_bytes(audio_data, sampling_rate=SAMPLE_RATE, ch=1), model
        return b'',model

    async def put(self,message:list[str]):
        pass

    async def get(self, *, timeout:float=0.0) ->tuple[int,str,bytes]:
        breaktime = time.time()+(timeout if timeout>0 else 90.0)
        while time.time()<breaktime:
            try:
                a = self.queue.get_nowait()
                if isinstance(a,VoiceRes):
                    return a.cmd, a.text, a.voice
            except Empty:
                pass
            await asyncio.sleep(0.2)
        return 0,'',b''