from fastapi import FastAPI, Depends, HTTPException, status
from agente_grafo import ejecutar_grafo
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
import os
from dotenv import load_dotenv

app = FastAPI()

class SolicitudCorreo(BaseModel):
    remitente:str
    asunto:str
    cuerpo_correo:str

load_dotenv()

API_KEY_NAME = "X-API-Key"
API_KEY_SECRET = os.getenv("API_KEY")


api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def validar_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave de API inválida o ausente",
        )
    return api_key


@app.post("/procesar")
def procesar(data: SolicitudCorreo, token_valido: str = Depends(validar_api_key)) :
    try:
        consulta = data.cuerpo_correo

        resumen = ejecutar_grafo(consulta)

    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno"
        )

    return {
        "status": "completado",
        "enviar_a": data.remitente,
        "texto_resumido":resumen
    }