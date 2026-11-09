import sys
import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

raiz = Path(__file__).resolve().parent  # carpeta mcp_local/

cliente = MultiServerMCPClient({
    "prueba": {
        "transport": "stdio",
        # El mismo Python que está ejecutando la app (el del .venv). Funciona en Windows y en Linux
        "command": sys.executable,
        "args": [str(raiz / "servidor_mcp.py")],
    }
})

def cargar_herramientas_mcp():
    try:
        tools = asyncio.run(cliente.get_tools())
        return tools
    
    except Exception as e:
        print(f"Se ha lanzado el siguiente error {e}")
        return []

if __name__ == "__main__":
    for herramienta in cargar_herramientas_mcp():
        print(herramienta.name)