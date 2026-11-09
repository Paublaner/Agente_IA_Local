import sounddevice as sd
from faster_whisper import WhisperModel
import numpy as np
modelo = WhisperModel("small", device="cpu", compute_type="int8")

FRECUENCIA = 16000

def escuchar(segundos = 5):
    print("Empieza a hablar: ")
    muestras = segundos * FRECUENCIA

    #channels 1 mono 2 estereo
    audio = sd.rec(muestras, samplerate=FRECUENCIA, channels=1, dtype="float32")

    sd.wait()
    print("Ha terminado")
    return audio

def transcribir(audio:np.array):
    aplanado = audio.flatten()
    texto = []
    segmentos, _ = modelo.transcribe(aplanado, language="es")

    for segmento in segmentos:
        texto.append(segmento.text)

    return " ".join(texto).strip()


if __name__ == "__main__":
    audio = escuchar()
    print(transcribir(audio))