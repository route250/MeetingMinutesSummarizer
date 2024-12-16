import sys,os
import asyncio
import subprocess
from io import BufferedReader
import os,re
import tempfile
from logging import getLogger, Logger, StreamHandler, FileHandler, Formatter,  DEBUG as LV_DEBUG, INFO as LV_INFO, WARN as LV_WARN

import mlx_whisper

sys.path.append('app')
from whisper_transcribe import WHISPER_MODEL_NAME, MlxWhisperProcess, transcribe, Seg

async def write_to_tp(tp:MlxWhisperProcess, file_path,chunk,size_limit):
    """
    非同期タスクでファイルを読み込み、tp.write にデータを送信する。
    """
    sz=0
    with open(file_path, "rb") as f:
        while sz<=size_limit:
            data = f.read(chunk)
            if not data:
                break
            tp.append_audio(data)
            sz+=len(data)
            await asyncio.sleep(0)  # 他のタスクに制御を渡す
        tp.close_audio()

async def read_from_tp(tp:MlxWhisperProcess):
    """
    非同期タスクで tp.read を監視して結果を出力する。
    """
    res = []
    while True:
        result = await tp.read()
        if result is None:
            break
        print(f"result: {result}")
        a,b = result
        for c in a:
            res.append(c)
    return res

def text_split(text) ->list[str]:
    # 区切り文字（. ! ?）で分割しつつ、区切り文字も結果に含める
    pattern = r"([a-zA-Z][.!?]) "  # キャプチャグループで区切り文字を記録
    # 分割
    result = re.split(pattern, text)
    # 空要素を取り除きながら、隣接する文字列と区切り文字を結合する
    final_result = ["".join(result[i:i+2]) for i in range(0, len(result)-1, 2)]
    return final_result

async def main():
    logger = getLogger( __name__ )
    logger.setLevel(LV_DEBUG)
    log_file = 'tmp/test.log'
    if os.path.exists(log_file):
        os.remove(log_file)
    fh = FileHandler(log_file)
    fh.setLevel(LV_DEBUG)
    formatter = Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # ログ出力のテスト
    logger.debug("Starting main function")
    logger.info("Processing file: output.webm")

    file_path = "tests/testData/output.webm"
    size_limit = 1280*1024
    chunk = 8192

    # 非同期タスクを作成
    tp = MlxWhisperProcess( logfile=log_file)
    tp.start()
    logger.debug("Created and started MlxWhisperProcess")

    write_task = asyncio.create_task(write_to_tp(tp, file_path, chunk, size_limit))
    read_task = asyncio.create_task(read_from_tp(tp))
    logger.debug("Created async tasks")

    # タスクが完了するまで待機
    await write_task
    logger.debug("Write task completed")
    result = await read_task
    logger.debug("Read task completed")
    result_text = ' '.join(result)
    tp.stop()
    logger.info("MlxWhisperProcess stopped")
    result_text = '\n'.join( text_split( result_text ) )
    with open('tmp/result.txt','w') as f:
        f.write(result_text)

    # 正解データを作成
    with tempfile.NamedTemporaryFile(mode="w+b", delete=True) as temp_file:
        logger.info(f"Created temporary file: {temp_file.name}")
        with open(file_path, "rb") as f:
            data = f.read(size_limit)
        temp_file.write(data)
        temp_file.flush()

        result = mlx_whisper.transcribe(
            temp_file.name, path_or_hf_repo=WHISPER_MODEL_NAME,
            language='en',
            #hallucination_silence_threshold=0.5,
            #no_speech_threshold=0.2,
            fp16=False,
            verbose=None)
        actual_text = result.get('text')
        actual_text = '\n'.join( text_split( actual_text ) )
        with open('tmp/actual.txt','w') as f:
            f.write(actual_text)

    logger.info("Transcription completed")
    print("--actual----------------")
    print(actual_text)
    print("--result----------------")
    print( result_text )
    print("------------------")
    logger.debug("Program finished")

if __name__ == "__main__":
    asyncio.run(main())
