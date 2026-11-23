import uuid
from pathlib import Path
import streamlit as st
from agente.agente_grafo import (ejecutar_grafo, conversacion, guardar_conversacion,
                                 listar_conversaciones, eliminar_conversacion)
from agente.herramientas import indexar_documento
from agente.base_datos import conexion
from integraciones import auth_gmail
from faster_whisper import decode_audio
from voz.oido import transcribir   # el mismo oído que usa voz/conversacion.py
from voz.boca import sintetizar_wav  # la misma voz de Piper que hablar(), pero para el navegador

st.set_page_config(page_title="Agente IA", page_icon=":material/travel_explore:", layout="centered")

# Estilos que el tema de .streamlit/config.toml no alcanza (burbujas, caja del chat, bienvenida...)
ruta_estilos = Path(__file__).resolve().parent / "estilos" / "interfaz.css"
st.html(f"<style>{ruta_estilos.read_text(encoding='utf-8')}</style>")

# Si venimos de aceptar en Google (?code=...), terminar el inicio de sesión antes de pintar nada
auth_gmail.completar_conexion()

carpeta_documentos = Path(__file__).resolve().parent / "datos" / "documentos"
carpeta_documentos.mkdir(exist_ok=True)

# Cómo se enseña cada herramienta mientras el agente trabaja: icono, texto y qué argumento mostrar.
# Los iconos son de Material Symbols (https://fonts.google.com/icons): Streamlit los pinta con :material/nombre:
etiquetas = {
    "buscar_web":            ("travel_explore", "Buscando en internet", "consulta"),
    "leer_texto":            ("article", "Leyendo la página", "url"),
    "buscar_en_pagina":      ("manage_search", "Buscando en la página", "pregunta"),
    "leer_documento":        ("description", "Leyendo el documento", "nombre"),
    "resumir_documento":     ("summarize", "Resumiendo el documento (puede tardar)", "nombre"),
    "buscar_en_documentos":  ("plagiarism", "Buscando en tus documentos", "pregunta"),
    "guardar_informe":       ("save", "Guardando el informe", "titulo"),
    "listar_correos":        ("mail", "Buscando en tu Gmail", "busqueda"),
    "leer_correo":           ("drafts", "Leyendo el correo", "id_correo"),
    "fecha_hora":            ("schedule", "Mirando la hora", None),
    "leer_pagina":           ("open_in_browser", "Abriendo en el navegador", "url"),
    "listar_elementos":      ("list", "Mirando los botones de la página", None),
    "clicar":                ("left_click", "Haciendo clic", "numero"),
    "escribir":              ("keyboard", "Escribiendo", "numero"),
    "iniciar_sesion_manual": ("login", "Esperando a que inicies sesión", "url"),
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
    icono, texto, argumento = etiquetas.get(llamada["name"], ("build", llamada["name"], None))
    valor = llamada["args"].get(argumento, "") if argumento else ""
    return f":material/{icono}: {texto}: *{valor}*" if valor else f":material/{icono}: {texto}"


def titulo_paso(llamada):
    # Solo el texto, para la etiqueta del recuadro "Pensando..." mientras trabaja
    return etiquetas.get(llamada["name"], ("build", llamada["name"], None))[1]


def cargar_mensajes(hilo):
    # Convierte los mensajes guardados en memoria.db en lo que pinta la interfaz:
    # una lista de tuplas (rol, texto, pasos), igual que st.session_state.mensajes
    resultado = []
    pasos = []   # los pasos de la pregunta actual, hasta que llegue su respuesta final

    for mensaje in conversacion(hilo):
        if mensaje.type == "human":
            resultado.append(("user", mensaje.content, []))

        elif mensaje.type == "ai" and mensaje.tool_calls:
            # El modelo pide herramientas: no se pinta, pero son los pasos del desplegable
            for llamada in mensaje.tool_calls:
                pasos.append(texto_paso(llamada))

        elif mensaje.type == "ai":
            # Sin tool_calls: es la respuesta final. Se lleva los pasos acumulados...
            resultado.append(("assistant", mensaje.content, pasos))
            # ...y se empieza una lista NUEVA para la siguiente pregunta.
            # (pasos.clear() vaciaría también la que acaba de entrar en la tupla)
            pasos = []

        # Los mensajes "tool" (lo que devuelve cada herramienta) no se pintan

    return resultado


def titulo_conversacion(pregunta, largo=40):
    # El título de la lista es el principio de la primera pregunta, cortado sin partir palabras
    texto = " ".join(pregunta.split())   # quita saltos de línea y espacios dobles
    if len(texto) <= largo:
        return texto
    return texto[:largo].rsplit(" ", 1)[0] + "…"


def empezar_conversacion_nueva():
    st.session_state.hilo = str(uuid.uuid4())
    st.session_state.mensajes = []


# ---------- Barra lateral ----------
with st.sidebar:
    st.markdown("## Agente IA")
    st.caption("En local con Ollama · qwen3")

    if st.button("Nueva conversación", icon=":material/edit_square:", type="primary", width="stretch"):
        empezar_conversacion_nueva()
        st.rerun()

    # ---------- Conversaciones anteriores ----------
    # La agenda (tabla "conversaciones" de memoria.db), de la más nueva a la más vieja.
    # La abierta se marca con el botón "secondary"; las demás son "tertiary" (sin borde).
    conversaciones = listar_conversaciones()
    if conversaciones:
        st.markdown("#### Conversaciones")
        with st.container(key="lista_conversaciones"):
            for hilo, titulo in conversaciones:
                abierta = hilo == st.session_state.hilo
                columna_titulo, columna_borrar = st.columns([6, 1], gap="small", vertical_alignment="center")

                if columna_titulo.button(titulo, key=f"abrir_{hilo}", width="stretch",
                                         type="secondary" if abierta else "tertiary"):
                    st.session_state.hilo = hilo
                    st.session_state.mensajes = cargar_mensajes(hilo)
                    st.rerun()

                if columna_borrar.button("", icon=":material/delete:", key=f"borrar_{hilo}",
                                         type="tertiary", help="Borrar esta conversación"):
                    eliminar_conversacion(hilo)   # la quita de la lista y borra sus mensajes de memoria.db
                    if abierta:
                        empezar_conversacion_nueva()
                    st.rerun()

    # Si hablas por el micro, siempre te contesta con voz. Esto es para que también lo haga al escribir
    st.divider()
    voz_siempre = st.toggle("Leer en voz alta también las respuestas escritas", value=False)

    # ---------- Gmail del usuario ----------
    st.divider()
    st.markdown("#### Tu Gmail")

    if "aviso_gmail" in st.session_state:
        st.warning(st.session_state.pop("aviso_gmail"))

    if auth_gmail.credenciales_actuales() is None:
        st.caption("Conecta tu cuenta para que el agente pueda leer tus correos (solo lectura).")
        # Se abre en otra pestaña: al volver de Google, sigue en esa pestaña nueva
        st.link_button("Conectar Gmail", auth_gmail.enlace_conexion(), icon=":material/mail:", width="stretch")
    else:
        st.success(f"Conectado como **{st.session_state.email_gmail}**")
        if st.button("Cerrar sesión", width="stretch"):
            auth_gmail.desconectar()
            # Borra esta conversación (de la lista y sus mensajes de memoria.db): puede tener tus correos
            eliminar_conversacion(st.session_state.hilo)
            empezar_conversacion_nueva()
            st.rerun()

    st.divider()
    st.markdown("#### Tus documentos")

    subido = st.file_uploader("Sube un documento", type=["pdf", "docx", "txt", "md"],
                              label_visibility="collapsed")
    if subido is not None:
        # Path(...).name se queda solo con el nombre del archivo, sin carpetas (igual que is_relative_to en herramientas.py)
        ruta = carpeta_documentos / Path(subido.name).name
        ruta.write_bytes(subido.getvalue())

    disponibles = sorted(archivo.name for archivo in carpeta_documentos.iterdir()
                         if archivo.is_file() and archivo.name != ".gitkeep")
    # Qué archivos tienen ya sus trozos en Postgres (la "fuente" que guarda indexar_documento)
    filas = conexion.execute("SELECT DISTINCT cmetadata ->> 'fuente' AS fuente FROM langchain_pg_embedding").fetchall()
    indexados = {fila["fuente"] for fila in filas}

    if disponibles == []:
        st.caption("Todavía no hay documentos.")
    else:
        for nombre in disponibles:
            columna_nombre, columna_boton = st.columns([6, 1], gap="small", vertical_alignment="center")
            ya_indexado = nombre in indexados
            icono_estado = ":material/check_circle:" if ya_indexado else ":material/description:"
            columna_nombre.markdown(f"{icono_estado} `{nombre}`")

            # Indexar = trocear + embeddings + guardar en Postgres. Si ya estaba, se reemplaza (no se duplica).
            pulsado = columna_boton.button("", key=f"indexar_{nombre}", type="tertiary",
                                           icon=":material/sync:" if ya_indexado else ":material/upload:",
                                           help="Volver a indexar" if ya_indexado else "Indexar para poder preguntarle")
            if pulsado:
                try:
                    with st.spinner(f"Indexando {nombre}…"):
                        indexar_documento(nombre)
                    st.toast(f"{nombre} indexado", icon=":material/check_circle:")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se ha podido indexar {nombre}: {e}")

        st.caption("Pulsa :material/upload: para indexar un documento. Luego pregúntale: "
                   "*¿Qué dice el documento sobre ...?* o *Resúmeme el documento ...*")


# ---------- Conversación ----------
if st.session_state.mensajes == []:
    # Pantalla de bienvenida con preguntas de ejemplo
    # El aspecto (centrado, letra, animación) está en .bienvenida, en estilos/interfaz.css
    st.html("<div class='bienvenida'><h1>¿Qué quieres investigar?</h1>"
            "<p>Busco en internet, leo las páginas y te respondo con las fuentes. "
            "También resumo tus documentos y leo tus correos.</p></div>")

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

# La voz de la última respuesta. Se saca con pop para que suene UNA vez:
# en la siguiente recarga de la página ya no está y no se repite
if "audio_respuesta" in st.session_state:
    st.audio(st.session_state.pop("audio_respuesta"), format="audio/wav", autoplay=True)

# accept_audio=True añade un botón de micrófono dentro de la caja del chat.
# El navegador graba y Streamlit nos da el audio ya a 16 kHz (lo que quiere Whisper)
entrada = st.chat_input("Escribe o pulsa el micrófono para hablar...", accept_audio=True)

pregunta = None
por_voz = False   # ¿ha hablado? Si es así, se le contesta hablando
if entrada is not None:
    pregunta = entrada.text.strip()
    if entrada.audio is not None:
        with st.spinner("Escuchando lo que has dicho..."):
            # decode_audio convierte el archivo de audio en los números que espera transcribir()
            dicho = transcribir(decode_audio(entrada.audio))
        if dicho == "":
            st.toast("No he entendido el audio. Prueba a hablar más cerca del micrófono.", icon="🎤")
        else:
            por_voz = True
        pregunta = f"{pregunta} {dicho}".strip()   # por si ha escrito algo y además ha hablado

# Si ha pulsado una sugerencia, se usa como si la hubiera escrito
if "pendiente" in st.session_state:
    pregunta = st.session_state.pop("pendiente")

if pregunta:
    # Primera pregunta de esta conversación: se apunta en la agenda para que salga en la barra lateral
    if st.session_state.mensajes == []:
        guardar_conversacion(st.session_state.hilo, titulo_conversacion(pregunta))

    with st.chat_message("user", avatar="🧑"):
        st.markdown(pregunta)

    with st.chat_message("assistant", avatar="🔎"):
        respuesta = ""
        pasos = []

        with st.status("Pensando...", expanded=True) as estado:
            try:
                for tipo, dato in ejecutar_grafo(auth_gmail.credenciales_actuales(), pregunta=pregunta,
                                                 hilo=st.session_state.hilo, aprobacion=None):
                    if tipo == "herramienta":
                        paso = texto_paso(dato)
                        pasos.append(paso)
                        st.markdown(paso)
                        estado.update(label=titulo_paso(dato))
                    else:
                        respuesta = dato

                estado.update(label=f"Listo · {len(pasos)} herramienta(s)", state="complete", expanded=False)

            except Exception as e:
                estado.update(label="Ha fallado", state="error")
                respuesta = f"Ha habido un error: {e}"

        st.markdown(respuesta)

        if (por_voz or voz_siempre) and respuesta:
            with st.spinner("Preparando la voz..."):
                try:
                    st.session_state.audio_respuesta = sintetizar_wav(respuesta)
                except Exception as e:
                    st.toast(f"No he podido generar la voz: {e}", icon="🔇")

    st.session_state.mensajes.append(("user", pregunta, []))
    st.session_state.mensajes.append(("assistant", respuesta, pasos))
    st.rerun()   # Para quitar la pantalla de bienvenida y pintarlo todo desde el historial
