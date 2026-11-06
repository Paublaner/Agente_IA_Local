import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

raiz = Path(__file__).resolve().parent

cliente = MultiServerMCPClient({
    "prueba": {
        "transport": "stdio",
        "command": str(raiz / ".venv" / "Scripts" / "python.exe"),
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