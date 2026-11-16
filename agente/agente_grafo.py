
from agente import herramientas
import locale
import datetime
from langchain_ollama import ChatOllama
from langgraph.graph import MessagesState, StateGraph, END, START
import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from mcp_local.conexion_mcp import cargar_herramientas_mcp
import asyncio
from langgraph.runtime import Runtime
from agente.instrucciones import instrucciones

try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except locale.Error:
    locale.setlocale(locale.LC_TIME, "spanish")

hoy = datetime.datetime.now()
fecha_formateada = hoy.strftime("%d de %B de %Y")
dia_semana = hoy.strftime("%A")

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
     "leer_documento": herramientas.leer_documento,
     "listar_correos": herramientas.listar_correos,
     "leer_correo": herramientas.leer_correo,
     "leer_pagina": herramientas.leer_pagina,
     "listar_elementos": herramientas.listar_elementos,
     "clicar": herramientas.clicar,
     "escribir": herramientas.escribir,
     "iniciar_sesion_manual": herramientas.iniciar_sesion_manual
}

funciones_gmail = [
    "listar_correos",
    "leer_correo"
]

herramientas_mcp = cargar_herramientas_mcp()
nombres_mcp = {herramienta.name for herramienta in herramientas_mcp}

for herramienta in herramientas_mcp:
        funciones[herramienta.name] = herramienta

llm_with_tools = llm.bind_tools(list(funciones.values()))

def node_modelo (state: MessagesState):
    messages = state["messages"]
    lista_nueva = [("system", instrucciones)] + messages
    resultado= llm_with_tools.invoke(lista_nueva)
    return {"messages": [resultado]}


def node_herramientas(state: MessagesState,  runtime: Runtime):
    resultado = []
    ultimo = state["messages"][-1]
    credenciales = runtime.context["credenciales_gmail"]

    for llamada in ultimo.tool_calls:

        if llamada["name"] in funciones_gmail:
            llamada_args = llamada["args"]
            llamada_args_credenciales = {**llamada_args, "credenciales": credenciales}
            llamada = {**llamada, "args":llamada_args_credenciales}
            result = funciones[llamada["name"]].invoke(llamada)
            resultado.append(result)

        elif llamada["name"] in nombres_mcp:
            result = asyncio.run(funciones[llamada["name"]].ainvoke(llamada))
            resultado.append(result)

        elif llamada["name"] in funciones:
            result = funciones[llamada["name"]].invoke(llamada)
            resultado.append(result)

    return {"messages": resultado}

def decidir(state: MessagesState):
    ultimo = state["messages"][-1]
    if ultimo.tool_calls:
        return "herramienta"
    return END

RAIZ = Path(__file__).resolve().parents[1]  # carpeta del proyecto (agente_grafo.py está en agente/)
conexion = sqlite3.connect(RAIZ / "datos" / "memoria.db", check_same_thread=False)

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

def ejecutar_grafo (credenciales, pregunta: str, hilo: str):
    """
    Con memoria (para el chat de Streamlit).
    En vez de devolver solo el final, va devolviendo (yield) cada paso según ocurre:
    ("herramienta", llamada) cuando el modelo pide una herramienta y ("respuesta", texto) al
 terminar.
    """
    config = {"configurable": {"thread_id": hilo}, "recursion_limit": 40}

    for paso in app_memoria.stream({"messages": [pregunta]}, config, stream_mode="updates",  context={"credenciales_gmail": credenciales}):
        for nodo, cambios in paso.items():
            if nodo != "node_modelo":
                continue
            for mensaje in cambios["messages"]:
                for llamada in mensaje.tool_calls:
                    yield ("herramienta", llamada)
                if not mensaje.tool_calls:
                    yield ("respuesta", mensaje.content)

