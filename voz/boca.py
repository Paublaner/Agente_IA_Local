import io
import re
import wave
import asyncio
import edge_tts
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


def limpiar_para_voz(texto: str) -> str:
    """Quita lo que se ve bien en pantalla pero suena mal leído (Markdown, enlaces, emojis)."""
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)       # [nombre](url) -> nombre
    texto = re.sub(r"https?://\S+", "", texto)                   # URLs sueltas
    texto = re.sub(r"[*_#`>|]", "", texto)                       # negritas, títulos, código, tablas
    texto = re.sub(r"^\s*[-•]\s+", "", texto, flags=re.MULTILINE)  # viñetas de listas
    texto = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", texto)  # emojis
    texto = " ".join(texto.split())
    return re.sub(r"\s+([.,;:!?])", r"\1", texto)                # "lenguaje ." -> "lenguaje."


def sintetizar_wav(texto: str) -> bytes:
    """Como hablar(), pero en vez de sonar por TU altavoz devuelve un archivo WAV en memoria.
    En la web el sonido tiene que salir por el navegador de quien usa la página, no por el PC
    donde corre el servidor; por eso se le manda el archivo y el navegador lo reproduce."""
    memoria = io.BytesIO()                  # un "archivo" que vive en la RAM, sin tocar el disco
    with wave.open(memoria, "wb") as wav:
        piper.synthesize_wav(limpiar_para_voz(texto), wav)   # Piper escribe todos los trozos seguidos
    return memoria.getvalue()


