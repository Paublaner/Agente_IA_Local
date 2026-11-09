from mcp.server.fastmcp import FastMCP
from datetime import datetime


mcp = FastMCP("mcp_prueba")


@mcp.tool()
def fecha_hora() ->str:
    """
    Devuelve la fecha y la hora en la que estamos actualmente
    """
    ahora = datetime.now()
    formateado = ahora.strftime("%d/%m/%Y %H:%M")
    return formateado

if __name__ == "__main__":
    mcp.run(transport="stdio")
