
import os
from pathlib import Path
import re
import html
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
import base64
from bs4 import BeautifulSoup


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Solo para probar en local con TU cuenta (conectar_gmail). La app usa auth_gmail.py
CREDENCIALES = Path(__file__).resolve().parents[1] / "credenciales"
TOKEN = CREDENCIALES / "token.json"
CLIENTE = CREDENCIALES / "credentials.json"

INVISIBLES = re.compile("[­͏​-‏⁠﻿]")


def limpiar_texto(texto):
    texto = html.unescape(texto)          # &amp; -> &   y   &#39; -> '
    texto = INVISIBLES.sub("", texto)     # borra los caracteres invisibles
    return " ".join(texto.split())        # deja un solo espacio entre palabras

def conectar_gmail():
    credenciales = None

    if os.path.exists(TOKEN):
        credenciales = Credentials.from_authorized_user_file(TOKEN, SCOPES)

    if not credenciales or not credenciales.valid:
        if credenciales and credenciales.expired and credenciales.refresh_token:
            credenciales.refresh(Request())
        else:
            flujo = InstalledAppFlow.from_client_secrets_file(CLIENTE, SCOPES)
            credenciales = flujo.run_local_server(port=0)
        
        with open(TOKEN, "w") as archivo:
            archivo.write(credenciales.to_json())

    return build("gmail", "v1", credentials=credenciales)


def listar_correos(credenciales, busqueda: str, maximo: int = 10):
    maximo = min(maximo, 20)

    try:

        if credenciales is None:
            return "Ha habido un error: el usuario no ha conectado su Gmail…"

        servicio = build("gmail", "v1", credentials=credenciales)
        respuesta = servicio.users().messages().list(userId="me", q=busqueda, maxResults=maximo).execute()
        correos = respuesta.get("messages", [])
        fichas = []

        if correos == []:
            return "No se han encontrado correos con esa búsqueda"

        for correo in correos:
            dic = servicio.users().messages().get(userId="me",id=correo["id"],format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
            fragmento = limpiar_texto(dic["snippet"])

            remitente = "(desconocido)"
            asunto = "(sin asunto)"
            fecha = "(sin fecha)"

            for cabecera in dic["payload"]["headers"]:
                if cabecera["name"] == "From":
                    remitente = cabecera["value"]
                elif cabecera["name"] == "Subject":
                    asunto = cabecera["value"]
                elif cabecera["name"] == "Date":
                    fecha = cabecera["value"]

            ficha = (
                f"ID: {correo['id']}\n"
                f"De: {remitente}\n"
                f"Asunto: {asunto}\n"
                f"Fecha: {fecha}\n"
                f"Fragmento: {fragmento}"
            )

            fichas.append(ficha)

        return "\n---\n".join(fichas)

    except RefreshError:
        return "Ha habido un error: Vuelve a conectar Gmail"
    except Exception as e:
        return f"Ha habido un error al buscar correos: {e}"


def sacar_texto(parte: dict) -> str:
    if parte.get("mimeType") == "text/plain" and parte.get("body", {}).get("data"):
        data = parte.get("body", {}).get("data")
        resultado = base64.urlsafe_b64decode(data).decode("utf-8")
        return resultado

    if parte.get("mimeType") == "text/html" and parte.get("body", {}).get("data"):
        data = parte.get("body", {}).get("data")
        resultadoHtml = base64.urlsafe_b64decode(data).decode("utf-8")
        soup= BeautifulSoup(resultadoHtml, "html.parser")

        for etiqueta in soup(["script", "style"]):
            etiqueta.decompose()

        texto = soup.get_text(separator=" ")
        return limpiar_texto(texto)
    
    for subparte in parte.get("parts", []):
        result = sacar_texto(subparte)

        if result != "":
            return result

    return ""
        

def leer_correo(credenciales, id_correo: str) -> str:
    try:

        if credenciales is None:
            return "Ha habido un error: el usuario no ha conectado su Gmail…"

        servicio = build("gmail", "v1", credentials=credenciales)

        dic = servicio.users().messages().get(userId="me",id=id_correo,format="full").execute()

        remitente = "(desconocido)"
        asunto = "(sin asunto)"
        fecha = "(sin fecha)"

        for cabecera in dic["payload"]["headers"]:
            if cabecera["name"] == "From":
                remitente = cabecera["value"]
            elif cabecera["name"] == "Subject":
                asunto = cabecera["value"]
            elif cabecera["name"] == "Date":
                fecha = cabecera["value"]

        cuerpo = sacar_texto(dic["payload"])

        if cuerpo == "":
            cuerpo = "(sin cuerpo   )"

        limite = 8000
        if len(cuerpo) > limite:
            total = len(cuerpo)
            cuerpo = cuerpo[:limite] + f"\n\n[AVISO: correo recortado. Se muestran {limite} de {total} caracteres; el resto no se ha leído.]"


        ficha = (
            f"De: {remitente}\n"
            f"Asunto: {asunto}\n"
            f"Fecha: {fecha}\n"
            f"Cuerpo:\n {cuerpo}\n"
        )

        return ficha

    except RefreshError:
        return "Ha habido un error: Vuelve a conectar Gmail"
    except Exception as e:
        return f"Ha habido un error al leer el correo: {e}"


    
            

