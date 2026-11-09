import uuid
from voz.oido import escuchar, transcribir
from agente.agente_grafo import ejecutar_grafo

print("Agente cargado")

if __name__ == "__main__":
    # Un hilo nuevo cada vez que se abre el programa: empieza la conversación de cero
    hilo = str(uuid.uuid4())

    audio = escuchar()
    texto = transcribir(audio)
    print(f"Tú: {texto}")

    if texto == "":
        print("No he oído nada. Vuelve a probar hablando más cerca del micrófono.")
    else:
        # Sin Gmail conectado en este programa: credenciales = None
        # (si preguntas por correos, gmail.py devuelve el aviso y el agente te lo explica)
        for tipo, dato in ejecutar_grafo(None, texto, hilo):
            if tipo == "herramienta":
                print(f"   🔧 {dato['name']}")
            elif tipo == "respuesta":
                print(f"Agente: {dato}")
