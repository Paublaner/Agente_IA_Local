
from agente import herramientas
import locale
import datetime
from langchain_ollama import ChatOllama
from langgraph.graph import MessagesState, StateGraph, END, START
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt, Command
from pathlib import Path
from mcp_local.conexion_mcp import cargar_herramientas_mcp
import asyncio
from langgraph.runtime import Runtime
from agente.instrucciones import instrucciones
from agente.base_datos import conexion_memoria, conexion
from langchain_core.messages import ToolMessage

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
     "iniciar_sesion_manual": herramientas.iniciar_sesion_manual,
     "buscar_en_documentos": herramientas.buscar_en_documentos
}

funciones_gmail = [
    "listar_correos",
    "leer_correo"
]


funciones_a_revisar = [
    "clicar",
    "escribir",
    "COMPOSIO_MULTI_EXECUTE_TOOL"
]

herramientas_mcp = cargar_herramientas_mcp()
nombres_mcp = {herramienta.name for herramienta in herramientas_mcp}

for herramienta in herramientas_mcp:
        funciones[herramienta.name] = herramienta

llm_with_tools = llm.bind_tools(list(funciones.values()))

def node_modelo (state: MessagesState):
    messages = state["messages"]
    fuentes = herramientas.documentos_indexados()

    if fuentes == []:
        texto_fuentes = "DOCUMENTOS INDEXADOS DEL USUARIO: (ninguno)"

    else:
        texto_fuentes = f"DOCUMENTOS INDEXADOS DEL USUARIO: {', '.join(fuentes)}"

    lista_nueva = [("system", instrucciones + texto_fuentes)] + messages
    resultado= llm_with_tools.invoke(lista_nueva)
    return {"messages": [resultado]}


def node_herramientas(state: MessagesState,  runtime: Runtime):
    resultado = []
    ultimo = state["messages"][-1]
    credenciales = runtime.context["credenciales_gmail"]

    for llamada in ultimo.tool_calls:

        if llamada["name"] in funciones_a_revisar:
            respuesta_humana = interrupt({"Funcion nombre": llamada["name"], "Argumentos": llamada["args"]})

            if not respuesta_humana:
                tool_msg = ToolMessage(
                    content="el usuario ha rechazado la peticion, no lo reintentes, pregunta al usuario qué quiere cambiar",
                    tool_call_id=llamada["id"],
                    name=llamada["name"] 
                )

                resultado.append(tool_msg)

                continue

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

RAIZ = Path(__file__).resolve().parents[1] 

memory = PostgresSaver(conexion_memoria)

memory.setup()

conexion.execute("""
    CREATE TABLE IF NOT EXISTS conversaciones (
        hilo   TEXT PRIMARY KEY,
        titulo TEXT NOT NULL,
        creada TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
""")


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


def conversacion(hilo: str):

    config = {"configurable": {"thread_id": hilo}}

    estado = app_memoria.get_state(config)

    return estado.values.get("messages", [])


def guardar_conversacion(hilo, titulo):
    conexion.execute(
    "INSERT INTO conversaciones (hilo, titulo) VALUES (%s, %s) ON CONFLICT (hilo) DO NOTHING",
    (hilo, titulo)
    )



def listar_conversaciones():
    cursor = conexion.execute("SELECT hilo, titulo FROM conversaciones ORDER BY creada DESC")
    conversaciones = cursor.fetchall()

    lista_tuplas = []

    for fila in conversaciones:
        tupla = (fila["hilo"], fila["titulo"])
        lista_tuplas.append(tupla)

    return lista_tuplas


def eliminar_conversacion(hilo):
    conexion.execute("DELETE FROM conversaciones WHERE hilo = %s",
                     (hilo,))
    memory.delete_thread(thread_id=hilo)



def ejecutar_grafo (credenciales , pregunta: str, hilo: str, aprobacion = None):
    """
    Con memoria (para el chat de Streamlit).
    En vez de devolver solo el final, va devolviendo (yield) cada paso según ocurre:
    ("herramienta", llamada) cuando el modelo pide una herramienta y ("respuesta", texto) al
 terminar.
    """
    config = {"configurable": {"thread_id": hilo}, "recursion_limit": 40}

    if aprobacion is None:
        mensajes = {"messages": [pregunta]}

    else:
        mensajes = Command(resume= aprobacion)

    

    for paso in app_memoria.stream(mensajes ,config, stream_mode="updates",  context={"credenciales_gmail": credenciales}):
        print(paso)
        for nodo, cambios in paso.items():
            if nodo != "node_modelo":
                continue
            for mensaje in cambios["messages"]:
                for llamada in mensaje.tool_calls:
                    yield ("herramienta", llamada)
                if not mensaje.tool_calls:
                    yield ("respuesta", mensaje.content)

