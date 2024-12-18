
import asyncio
import time
from queue import Queue, Empty
from io import BytesIO
from threading import Thread
import wave
import tempfile
import numpy as np
from openai import OpenAI
from text_to_voice import TtsEngine
from rec_util import audio_to_wave_bytes

SAMPLE_RATE=16000

class VoiceRes:

    CMD_ALL:int = 1
    CMD_APPEND:int = 2

    def __init__(self, cmd:int, text:str, voice:bytes ):
        self.cmd = cmd
        self.text = text
        self.voice = voice

class Bot:
    MODE_SUMMARY:str = 'summary'
    MODE_TRANSLATION:str = 'translation'
    MODE_CONVERSATION:str = 'conversation'
    def __init__(self,mode:str='off'):
        config={ 'voicevox_speaker': 8 }
        self.tts:TtsEngine = TtsEngine(config=config)
        self.queue:Queue = Queue()
        self.th = None
        self.run = False
        self.global_messages:list[dict] = []
        self.mode = mode
        self._orig_texts:list[str] = []
        self._temp_texts:list[str] = []
        self._user_messages:list[str] = []
        self._execute_interval:float = 15
        self._last_execute_time:float = 0

    def set_mode(self,mode):
        if self.mode != Bot.MODE_CONVERSATION:
            if mode == Bot.MODE_CONVERSATION:
                pass
            else:
                pass
        else:
            pass
        self.mode = mode

    def start(self):
        self.run=True
        if self.th is None:
            self.th = Thread( target=self._th_loop, daemon=True)
            self.th.start()

    async def put(self,message:list[str],temp:list[str]|None=None):
        if self.mode==Bot.MODE_CONVERSATION:
            self._user_messages.extend(message)
        else:
            self._orig_texts.extend(message)
            if isinstance(temp,list) and len(temp)>0:
                self._temp_texts=[m for m in temp]
            else:
                self._temp_texts=[]

    def stop(self):
        self.run=False
        if self.th:
            self.th.join(1.0)
            self.th = None

    def _th_loop(self):
        try:
            last_time:float = 0
            last_num = 0
            while self.run:
                # off,summary,translation,conversation
                if self.mode == Bot.MODE_SUMMARY:
                    if (time.time()-last_time)>15.0 and len(self._orig_texts)!=last_num:
                        self.summarize_text()
                        last_num = len(self._orig_texts)
                        last_time = time.time()
                elif self.mode == Bot.MODE_TRANSLATION:
                    if (time.time()-last_time)>10.0 and len(self._orig_texts)!=last_num:
                        self.translate_text()
                        last_num = len(self._orig_texts)
                        last_time = time.time()
                elif self.mode == Bot.MODE_CONVERSATION:
                    if (time.time()-last_time)>25.0 and len(self._orig_texts)!=last_num:
                        text = 'やっほー!'
                        b,m = self.aaa(text)
                        self.queue.put( VoiceRes(VoiceRes.CMD_APPEND,text,b))
                        last_num = len(self._orig_texts)
                        last_time = time.time()
                else:
                    pass

                time.sleep(1.0)
        except:
            pass

    def translate_text(self):
        """テキストを日本語に翻訳する"""
        prompt = """
以下のテキストを自然な日本語に翻訳してください。
文脈を考慮し、分かりやすい日本語になるよう心がけてください。

原文：
"""
        system_role = "あなたは優秀な翻訳者です。自然で分かりやすい日本語訳を提供します。"
        # OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
        client = OpenAI()
        text = '\n'.join(self._orig_texts)
        if len(self._temp_texts)>0:
            text = text + '\n'+'\n'.join(self._temp_texts)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt + text}
            ]
        )
        restext = response.choices[0].message.content or ""
        res = VoiceRes(VoiceRes.CMD_ALL,text=restext,voice=b'')
        self.queue.put(res)

    def summarize_text(self):
        """音声認識テキストを要約する"""
        prompt = """
以下の音声認識テキストを簡潔に要約してください。
重要なポイントを箇条書きで記載し、できるだけ簡潔にまとめてください。

# 参加者
- 会話から人物を推定して列挙

# 結論
- 議題1：大まかな内容
- 議題2：大まかな内容

# 内容
- 議題1
    - 重要なポイントや決議事項や発言者を箇条書きで記載
- 議題2
    - 重要なポイントや決議事項や発言者を箇条書きで記載

音声認識テキスト：
"""
        system_role = "あなたは音声テキストの要約の専門家です。重要なポイントを簡潔にまとめます。"
        # OpenAI クライアントの初期化（環境変数から自動的にAPI keyを取得）
        client = OpenAI()
        text = '\n'.join(self._orig_texts)
        if len(self._temp_texts)>0:
            text = text + '\n'+'\n'.join(self._temp_texts)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt + text}
            ]
        )
        
        restext = response.choices[0].message.content or ""
        res = VoiceRes(VoiceRes.CMD_ALL,text=restext,voice=b'')
        self.queue.put(res)

    def aaa(self,text):
        audio_data,model = self.tts._text_to_audio_by_voicevox(text,sampling_rate=SAMPLE_RATE)
        if audio_data is not None:
            return audio_to_wave_bytes(audio_data, sampling_rate=SAMPLE_RATE, ch=1), model
        return b'',model

    async def get(self, *, timeout:float=0.0) ->tuple[int,str,bytes]:
        breaktime = time.time()+(timeout if timeout>0 else 3.0)
        while time.time()<breaktime:
            try:
                a = self.queue.get_nowait()
                if isinstance(a,VoiceRes):
                    return a.cmd, a.text, a.voice
            except Empty:
                pass
            await asyncio.sleep(0.2)
        return 0,'',b''