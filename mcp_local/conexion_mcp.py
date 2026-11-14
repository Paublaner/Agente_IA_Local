import sys
import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient
from dotenv import load_dotenv
import os


raiz = Path(__file__).resolve().parent  # carpeta mcp_local/

load_dotenv(raiz.parent /".env")

key = os.getenv("COMPOSIO_API_KEY")
url = os.getenv("COMPOSIO_MCP_URL")

PERMITIDAS_COMPOSIO = {
    "COMPOSIO_SEARCH_TOOLS",        # 1. buscar qué herramienta hace lo que quieres (ej. "publicar en linkedin")
    "COMPOSIO_GET_TOOL_SCHEMAS",    # 2. ver qué parámetros necesita esa herramienta
    "COMPOSIO_MULTI_EXECUTE_TOOL",  # 3. ejecutarla
    "COMPOSIO_MANAGE_CONNECTIONS",  # conectar una cuenta (LinkedIn...) si aún no lo está
}

cliente = MultiServerMCPClient({
    "prueba": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(raiz / "servidor_mcp.py")],
    },

    "composio": {
        "transport": "streamable_http",
        "url": url,
        "headers": {
            "x-consumer-api-key": key
        }
    }
})

def cargar_herramientas_mcp():

    herramientas = []
    try:
        tools = asyncio.run(cliente.get_tools(server_name="composio"))

        for tool in tools:
            if tool.name in PERMITIDAS_COMPOSIO:
                herramientas.append(tool)
    
    except Exception as e:
        print(f"Se ha lanzado el siguiente error {e}")

    return herramientas

def probar_herramienta(nombre, argumentos):
    """Llama a una herramienta MCP a mano (sin IA) y devuelve su respuesta en texto."""
    for herramienta in cargar_herramientas_mcp():
        if herramienta.name == nombre:
            return asyncio.run(herramienta.ainvoke(argumentos))
    return f"No hay ninguna herramienta llamada {nombre}"


if __name__ == "__main__":
    # Uso (desde la raíz del proyecto):
    #   python -m mcp_local.conexion_mcp                     -> lista las herramientas
    #   python -m mcp_local.conexion_mcp buscar              -> paso 1: qué herramienta de LinkedIn lee tu perfil
    #   python -m mcp_local.conexion_mcp conexiones          -> ver si LinkedIn está conectado a esta API key
    #   python -m mcp_local.conexion_mcp conectar            -> conectar LinkedIn (te da un enlace para autorizar)
    #   python -m mcp_local.conexion_mcp ejecutar NOMBRE     -> paso 2: ejecuta esa herramienta (solo lectura)
    modo = sys.argv[1] if len(sys.argv) > 1 else ""

    if modo == "buscar":
        # Paso 1: preguntarle a Composio QUÉ herramienta hace lo que queremos.
        # Fíjate en la respuesta: el nombre exacto (tool_slug, tipo LINKEDIN_...) y sus parámetros.
        respuesta = probar_herramienta("COMPOSIO_SEARCH_TOOLS", {
            "queries": [{"use_case": "get my own linkedin profile information"}],
            "session": {"generate_id": True},
        })
        print(str(respuesta)[:4000])

    elif modo == "conexiones":
        # Ver qué cuentas de LinkedIn tiene conectadas ESTA API key (no cambia nada).
        respuesta = probar_herramienta("COMPOSIO_MANAGE_CONNECTIONS", {
            "toolkits": [{"name": "linkedin", "action": "list"}],
        })
        print(str(respuesta)[:4000])

    elif modo == "conectar":
        # Crear la conexión con LinkedIn: devuelve un ENLACE que tienes que abrir
        # en tu navegador para darle permiso a Composio (como con Gmail).
        respuesta = probar_herramienta("COMPOSIO_MANAGE_CONNECTIONS", {
            "toolkits": [{"name": "linkedin", "action": "add"}],
        })
        print(str(respuesta)[:4000])

    elif modo == "ejecutar":
        # Paso 2: ejecutar la herramienta que ha salido en el paso 1.
        # Pon solo herramientas de LEER: nada de crear, publicar ni borrar.
        nombre = sys.argv[2] if len(sys.argv) > 2 else "LINKEDIN_GET_MY_INFO"
        respuesta = probar_herramienta("COMPOSIO_MULTI_EXECUTE_TOOL", {
            "tools": [{"tool_slug": nombre, "arguments": {}}],
            "thought": "Prueba manual: leer la información de mi perfil de LinkedIn",
        })
        print(str(respuesta)[:4000])

    else:
        for herramienta in cargar_herramientas_mcp():
            print(herramienta.name)
