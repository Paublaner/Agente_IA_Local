import sounddevice as sd
from pathlib import Path
from piper import PiperVoice

# La voz está en voz/voces/, en la misma carpeta que este archivo
RUTA_VOZ = Path(__file__).resolve().parent / "voces" / "es_ES-davefx-medium.onnx"

piper = PiperVoice.load(str(RUTA_VOZ))
print("Voz cargada")


def hablar(texto: str):
    audios = piper.synthesize(texto)

    for audio in audios:
        sd.play(audio.audio_float_array, audio.sample_rate)
        sd.wait()


if __name__ == "__main__": 
    hablar("Ivan es un polludo que me come mucho la polla pero le amo porque es mi amorcin")
