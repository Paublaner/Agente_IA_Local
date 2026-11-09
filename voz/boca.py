import sounddevice as sd
from pathlib import Path
from piper import PiperVoice

# La voz está en voz/voces/, en la misma carpeta que este archivo
RUTA_VOZ = Path(__file__).resolve().parent / "voces" / "es_ES-davefx-medium.onnx"

voz = PiperVoice.load(str(RUTA_VOZ))
print("Voz cargada")


def hablar(texto: str):
    pass