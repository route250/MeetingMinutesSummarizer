from io import BytesIO
import numpy as np
import mlx.core as mx
import mlx_whisper
from typing import Union

WHISPER_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"

def transcribe(audio:str|np.ndarray|mx.array) -> str:
    """
    audio: Union[str, np.ndarray, mx.array]
        The path to the audio file to open, or the audio waveform
    Returns:
        str: Transcribed text
    """
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=WHISPER_MODEL_NAME, language='ja', fp16=True, verbose=True)
    if isinstance(result, dict):
        return str(result.get("text", ""))
    elif isinstance(result, list):
        return " ".join(str(item) for item in result)
    else:
        return str(result)

def test():
    transcribe('aa')
if __name__ == "__main__":
    test()