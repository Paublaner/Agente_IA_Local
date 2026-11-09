import uuid
from pathlib import Path
import streamlit as st
from agente.agente_grafo import ejecutar_grafo, memory
from integraciones import auth_gmail
from faster_whisper import decode_audio
from voz.oido import transcribir   # el mismo oído que usa voz/conversacion.py

st.set_page_config(page_title="Agente de investigación", page_icon="🔎", layout="centered")

# Si venimos de aceptar en Google (?code=...), terminar el inicio de sesión antes de pintar nada
auth_gmail.completar_conexion()

carpeta_documentos = Path(__file__).resolve().parent / "datos" / "documentos"
carpeta_documentos.mkdir(exist_ok=True)

# Cómo se enseña cada herramienta mientras el agente trabaja: icono, texto y qué argumento mostrar
etiquetas = {
    "buscar_web":        ("🌐", "Buscando en internet", "consulta"),
    "leer_texto":        ("📄", "Leyendo la página", "url"),
    "buscar_en_pagina":  ("🔍", "Buscando en la página", "pregunta"),
    "leer_documento":    ("📂", "Leyendo el documento", "nombre"),
    "resumir_documento": ("📚", "Resumiendo el documento (puede tardar)", "nombre"),
    "guardar_informe":   ("💾", "Guardando el informe", "titulo"),
    "listar_correos":    ("📧", "Buscando en tu Gmail", "busqueda"),
    "leer_correo":       ("📖", "Leyendo el correo", "id_correo"),
    "fecha_hora":        ("🕒", "Mirando la hora", None),
}

sugerencias = [
    "¿Qué es LangGraph y para qué sirve?",
    "Investiga las últimas noticias sobre inteligencia artificial",
    "¿Cuáles son los principios del Zen de Python?",
]

# Streamlit vuelve a ejecutar el archivo entero cada vez que haces algo en la página.
# Lo que tiene que durar entre mensajes se guarda en st.session_state
if "hilo" not in st.session_state:
    st.session_state.hilo = str(uuid.uuid4())   # thread_id de la memoria: un hilo por conversación
    st.session_state.mensajes = []              # Lo que se pinta en pantalla: (rol, texto, pasos)


def texto_paso(llamada):
    icono, texto, argumento = etiquetas.get(llamada["name"], ("🔧", llamada["name"], None))
    valor = llamada["args"].get(argumento, "") if argumento else ""
    return f"{icono} {texto}: *{valor}*" if valor else f"{icono} {texto}"


# ---------- Barra lateral ----------
with st.sidebar:
    st.markdown("## 🔎 Agente IA")
    st.caption("Investigación en local con Ollama · qwen3")

    if st.button("✨ Nueva conversación", type="primary", width="stretch"):
        st.session_state.hilo = str(uuid.uuid4())
        st.session_state.mensajes = []
        st.rerun()

    # ---------- Gmail del usuario ----------
    st.divider()
    st.markdown("#### 📧 Tu Gmail")

    if "aviso_gmail" in st.session_state:
        st.warning(st.session_state.pop("aviso_gmail"))

    if auth_gmail.credenciales_actuales() is None:
        st.caption("Conecta tu cuenta para que el agente pueda leer tus correos (solo lectura).")
        # Se abre en otra pestaña: al volver de Google, sigue en esa pestaña nueva
        st.link_button("Conectar Gmail", auth_gmail.enlace_conexion(), width="stretch")
    else:
        st.success(f"Conectado como **{st.session_state.email_gmail}**")
        if st.button("Cerrar sesión", width="stretch"):
            auth_gmail.desconectar()
            memory.delete_thread(st.session_state.hilo)  # borra de memoria.db lo que haya leído de tus correos
            st.session_state.hilo = str(uuid.uuid4())
            st.session_state.mensajes = []
            st.rerun()

    st.divider()
    st.markdown("#### 📂 Tus documentos")

    subido = st.file_uploader("Sube un documento", type=["pdf", "docx", "txt", "md"],
                              label_visibility="collapsed")
    if subido is not None:
        # Path(...).name se queda solo con el nombre del archivo, sin carpetas (igual que is_relative_to en herramientas.py)
        ruta = carpeta_documentos / Path(subido.name).name
        ruta.write_bytes(subido.getvalue())

    disponibles = sorted(archivo.name for archivo in carpeta_documentos.iterdir()
                         if archivo.is_file() and archivo.name != ".gitkeep")
    if disponibles == []:
        st.caption("Todavía no hay documentos.")
    else:
        for nombre in disponibles:
            st.markdown(f"📄 `{nombre}`")
        st.caption("Pídele: *Resúmeme el documento ...*")


# ---------- Conversación ----------
if st.session_state.mensajes == []:
    # Pantalla de bienvenida con preguntas de ejemplo
    st.markdown("<h1 style='text-align: center; margin-top: 2rem;'>¿Qué quieres investigar?</h1>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; opacity: 0.7;'>Busco en internet, leo las páginas "
                "y te respondo con las fuentes. También resumo tus documentos.</p>",
                unsafe_allow_html=True)
    st.write("")

    columnas = st.columns(len(sugerencias))
    for columna, sugerencia in zip(columnas, sugerencias):
        if columna.button(sugerencia, width="stretch"):
            st.session_state.pendiente = sugerencia
            st.rerun()

# Pintar la conversación que ya había
for rol, texto, pasos in st.session_state.mensajes:
    with st.chat_message(rol, avatar="🔎" if rol == "assistant" else "🧑"):
        if pasos:
            with st.expander(f"Ha usado {len(pasos)} herramienta(s)"):
                for paso in pasos:
                    st.markdown(paso)
        st.markdown(texto)

# accept_audio=True añade un botón de micrófono dentro de la caja del chat.
# El navegador graba y Streamlit nos da el audio ya a 16 kHz (lo que quiere Whisper)
entrada = st.chat_input("Escribe o pulsa el micrófono para hablar...", accept_audio=True)

pregunta = None
if entrada is not None:
    pregunta = entrada.text.strip()
    if entrada.audio is not None:
        with st.spinner("Escuchando lo que has dicho..."):
            # decode_audio convierte el archivo de audio en los números que espera transcribir()
            dicho = transcribir(decode_audio(entrada.audio))
        if dicho == "":
            st.toast("No he entendido el audio. Prueba a hablar más cerca del micrófono.", icon="🎤")
        pregunta = f"{pregunta} {dicho}".strip()   # por si ha escrito algo y además ha hablado

# Si ha pulsado una sugerencia, se usa como si la hubiera escrito
if "pendiente" in st.session_state:
    pregunta = st.session_state.pop("pendiente")

if pregunta:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(pregunta)

    with st.chat_message("assistant", avatar="🔎"):
        respuesta = ""
        pasos = []

        with st.status("Pensando...", expanded=True) as estado:
            try:
                for tipo, dato in ejecutar_grafo(auth_gmail.credenciales_actuales(),pregunta, st.session_state.hilo):
                    if tipo == "herramienta":
                        paso = texto_paso(dato)
                        pasos.append(paso)
                        st.markdown(paso)
                        estado.update(label=paso.split(":")[0])
                    else:
                        respuesta = dato

                estado.update(label=f"Listo · {len(pasos)} herramienta(s)", state="complete", expanded=False)

            except Exception as e:
                estado.update(label="Ha fallado", state="error")
                respuesta = f"Ha habido un error: {e}"

        st.markdown(respuesta)

    st.session_state.mensajes.append(("user", pregunta, []))
    st.session_state.mensajes.append(("assistant", respuesta, pasos))
    st.rerun()   # Para quitar la pantalla de bienvenida y pintarlo todo desde el historial
