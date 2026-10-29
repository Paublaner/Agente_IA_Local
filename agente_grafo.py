
import herramientas
import locale
import datetime
from langchain_ollama import ChatOllama
from langgraph.graph import MessagesState, StateGraph, END, START
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

#buscar_web Busca en internet como hace google

#leer_texto Sacar el texto de una pagina concreta

#guardar_informe Guarda el resultado final en un archivo

#buscar_en_pagina Busca un dato concreto en toda la pagina (RAG)

try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except locale.Error:
    locale.setlocale(locale.LC_TIME, "spanish")

hoy = datetime.datetime.now()
fecha_formateada = hoy.strftime("%d de %B de %Y")
dia_semana = hoy.strftime("%A")

instrucciones = f"""
ROL:
Eres un agente de investigación. Respondes siempre en español.

HERRAMIENTAS:
- buscar_web(consulta): busca en internet y devuelve 5 resultados con título, enlace y resumen.
- leer_texto(url): descarga una página y devuelve solo su PRINCIPIO (8000 caracteres). Sirve para hacerse una idea general.
- buscar_en_pagina(url, pregunta): busca dentro de la página ENTERA y devuelve solo los fragmentos relacionados con la pregunta. Si responde "no aparece en la pagina", esa página no tiene el dato.
- guardar_informe(titulo, contenido): guarda un informe en Markdown en la carpeta "informes".
- resumir_documento(nombre): resume documentos largos de la carpeta de documentos.
- leer_documento: lee el documento y devuelve el texto dentro de el.

CÓMO TRABAJAR:
1. Usa buscar_web con una consulta clara para encontrar fuentes sobre la pregunta del usuario.
2. Lee las 2 o 3 páginas más útiles de los resultados:
   - Si buscas un DATO CONCRETO (una fecha, una cifra, quién hizo algo, una cita...), usa buscar_en_pagina con una pregunta corta y precisa.
   - Si necesitas una idea GENERAL del tema, usa leer_texto.
   - Si leer_texto no trae lo que buscas (la página es larga y el dato estará más abajo), prueba buscar_en_pagina en esa misma página.
3. Escribe un informe en Markdown con lo que has aprendido, incluyendo los enlaces de las fuentes.
4. LLAMA a la herramienta guardar_informe con ese informe. Escribir el informe en tu respuesta NO lo guarda: solo se guarda si llamas a la herramienta.
5. Cuando esté guardado, responde al usuario con un resumen corto de lo que has encontrado Y QUE ESTE TODO ORDENADO.

FIDELIDAD A LAS FUENTES:
- Usa solo información que aparezca en lo que devuelven las herramientas. No inventes datos (alucinaciones).
- Si la fuente trae una lista, una cita o una frase textual, cópiala PALABRA POR PALABRA y COMPLETA, entre comillas. No la resumas, no cambies palabras por sinónimos y no te saltes elementos.
- No añadas explicaciones ni opiniones tuyas. Si de verdad aportan algo, ponlas aparte con el título "Comentario (no viene de la fuente)".
- Indica de qué enlace sale cada dato.
- Si no encuentras algo, dilo claramente en vez de rellenarlo.

ACCIONES:
- Nunca digas que has hecho algo (guardar un archivo, leer una página...) si no has llamado a la herramienta y ella te ha respondido.
- Solo puedes decir que el informe está guardado si guardar_informe te ha devuelto "Se ha creado el archivo..." con la ruta. Copia esa ruta tal cual.
- Si una herramienta devuelve un error, díselo al usuario.

DATOS DE HOY
- Fecha: {fecha_formateada}
- Día de la semana: {dia_semana}
"""

llm = ChatOllama(
    model="qwen3",
    temperature=0,
    num_ctx= 16384
)

funciones ={
     "buscar_web":herramientas.buscar_web,
     "buscar_en_pagina": herramientas.buscar_en_pagina,
     "leer_texto": herramientas.leer_texto,
     "guardar_informe": herramientas.guardar_informe,
     "resumir_documento": herramientas.resumir_documento,
     "leer_documento": herramientas.leer_documento
}

llm_with_tools = llm.bind_tools(list(funciones.values()))

def node_modelo (state: MessagesState):
    messages = state["messages"]
    lista_nueva = [("system", instrucciones)] + messages
    resultado= llm_with_tools.invoke(lista_nueva)
    return {"messages": [resultado]}


def node_herramientas(state: MessagesState):
    resultado = []
    ultimo = state["messages"][-1]

    for llamada in ultimo.tool_calls:
        if llamada["name"] in funciones:
            result = funciones[llamada["name"]].invoke(llamada)
            resultado.append(result)

    return {"messages": resultado}

def decidir(state: MessagesState):
    ultimo = state["messages"][-1]
    if ultimo.tool_calls:
        return "herramienta"
    return END

conexion = sqlite3.connect("memoria.db", check_same_thread=False)

memory = SqliteSaver(conexion)


workflow = StateGraph(MessagesState)

workflow.add_node("node_modelo", node_modelo)
workflow.add_node("node_herramientas", node_herramientas)

workflow.add_edge(START, "node_modelo")

workflow.add_conditional_edges("node_modelo", 
                                decidir,{
        "herramienta": "node_herramientas",
        END: END
    })

workflow.add_edge("node_herramientas", "node_modelo")

app = workflow.compile() #Para la API: sin memoria, cada correo empieza de cero

app_memoria = workflow.compile(checkpointer=memory) #Para el chat de Streamlit: recuerda la conversacion (cada chat tiene su thread_id)

def ejecutar_grafo (pregunta: str, hilo: str):
    """
    Con memoria (para el chat de Streamlit).
    En vez de devolver solo el final, va devolviendo (yield) cada paso según ocurre:
    ("herramienta", llamada) cuando el modelo pide una herramienta y ("respuesta", texto) al
 terminar.
    """
    config = {"configurable": {"thread_id": hilo}, "recursion_limit": 40}

    for paso in app_memoria.stream({"messages": [pregunta]}, config, stream_mode="updates"):
        for nodo, cambios in paso.items():
            if nodo != "node_modelo":
                continue
            for mensaje in cambios["messages"]:
                for llamada in mensaje.tool_calls:
                    yield ("herramienta", llamada)
                if not mensaje.tool_calls:
                    yield ("respuesta", mensaje.content)

