from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
import os
from pathlib import Path
import re
from langchain.tools import tool
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from pypdf import PdfReader
from docx import Document

@tool
def buscar_web(consulta: str) -> str:
    """
    Busca en internet y devuelve los 5 primeros resultados (título, enlace y resumen).

    Args:
        consulta: Lo que se quiere buscar, por ejemplo "últimas noticias inteligencia artificial"
    """

    try:
    
        results = DDGS().text(consulta, max_results = 5)
        resume = []

        if results == []:
            return "No se ha podido encontrar nada"

        for r in results:

            formato_resultado = (
                    f"Título: {r['title']}\n"
                    f"Enlace: {r['href']}\n"
                    f"Resumen: {r['body']}"
                )

            resume.append(formato_resultado)

    except Exception as e:
        return f"Ha habido un error en el bucle {e}"
    
    salto_entre_resultados = "\n\n" + "="*40 + "\n\n"
    return salto_entre_resultados.join(resume)


def descargar_pagina(url:str) -> str:
    """
    Descarga una página web y devuelve su texto.

    Args:
        url: La dirección completa de la página, por ejemplo "https://es.wikipedia.org/wiki/Python"
    """

    try:

        headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        }

        respuesta = requests.get(url, timeout= 10,headers=headers)

        respuesta.raise_for_status()

    except Exception as e:
        return f"Ha habido un error {e}"

    soup= BeautifulSoup(respuesta.text, "html.parser")

    for etiqueta in soup(['nav', 'script', 'style', 'footer', "header"]):
        etiqueta.decompose()

    texto = soup.get_text(separator=" ", strip=True)

    return texto

def extraer_texto_archivo(ruta: Path)-> str:

    extension = ruta.suffix.lower()
    paginas = []

    try:
        if extension == ".txt" or extension == ".md":
            with open(ruta, "r", encoding="utf-8") as archivo:
                contenido = archivo.read()
                return contenido 
        elif extension == ".pdf":
            reader = PdfReader(ruta)
            for pagina in reader.pages:
                texto = pagina.extract_text()
                if texto is None or not texto.strip():
                    continue

                paginas.append(texto)

        elif extension == ".docx":
            doc = Document(ruta)
            for parrafo in doc.paragraphs:
                paginas.append(parrafo.text)
        else:
            return "Los formatos que se aceptan son PDF, WORD, TXT y MD o MarkDown"

        salto_entre_resultados = "\n\n"
        return salto_entre_resultados.join(paginas)
        
    except Exception as e:
        return f"Ha habido un error al intentar leer el archivo. Error {e}"

@tool   
def leer_documento(nombre: str) -> str:
    """
    Lee un documento del usuario cuando sea un documento corto (PDF, Word .docx, TXT o MD) de la carpeta "documentos" y devuelve su
    texto.
    Úsala cuando el usuario quiera resumir, analizar o preguntar sobre uno de sus documentos los cuales sean cortos.

    Args:
        nombre: Nombre del archivo dentro de la carpeta "documentos", por ejemplo "informe.pdf"
    """
    proyecto = Path(__file__).resolve().parent
    carpeta = (proyecto / "documentos").resolve()

    # resolve() calcula a dónde apunta de verdad la ruta (quita los "..")
    ruta = (carpeta / nombre).resolve()

    # Seguridad: si la ruta se sale de "documentos" (por ejemplo "../../secreto.txt"), no se lee
    if not ruta.is_relative_to(carpeta):
        return "No está permitido leer archivos fuera de la carpeta documentos"

    # Si no existe o es una carpeta, decimos qué archivos sí hay para que el modelo pueda corregirse
    if not ruta.is_file():
        disponibles = [archivo.name for archivo in carpeta.iterdir() if archivo.is_file()]
        if disponibles == []:
            return "No existe ese archivo y la carpeta documentos está vacía"
        return f"No existe el archivo '{nombre}'. Archivos disponibles: {', '.join(disponibles)}"

    texto = extraer_texto_archivo(ruta)
    limite = 25000
    if len(texto) >= limite:
        aviso = f"El texto ha sido recortado a {limite} caracteres ya que ah excedido el limite de {limite} el documento tenia {len(texto)}"
        texto_recortado = texto[:limite]
        return aviso + "\n\n" + texto_recortado
    
    return texto
    

@tool
def leer_texto(url: str) -> str:
    """
    Descarga una página web y devuelve su texto (máximo 8000 caracteres).

    Args:
        url: La dirección completa de la página, por ejemplo "https://es.wikipedia.org/wiki/Python"
    """

    texto = descargar_pagina(url)

    return texto[:8000]

@tool
def guardar_informe(titulo: str, contenido:str) -> str:
    """
    Guarda el informe final en un archivo Markdown dentro de la carpeta "informes".

    Args:
        titulo: Título del informe, se usa como nombre del archivo
        contenido: Texto completo del informe en formato Markdown
    """

    titulo_limpio = re.sub(r'[<>:"/\\|?*]', '', titulo)

    titulo_correcto = "_".join(titulo_limpio.split())

    if titulo_correcto == "":
        titulo_correcto = "informe"

    titulo_personalizado = f"{titulo_correcto}.md"

    proyecto = Path(__file__).resolve().parent

    nombre_carpeta = "informes"

    try:
        ruta_carpeta = os.path.join(proyecto, nombre_carpeta)

        os.makedirs(ruta_carpeta, exist_ok=True)

        ruta_archivo = os.path.join(ruta_carpeta, titulo_personalizado)

        with open(ruta_archivo, "w", encoding="utf-8") as archivo:
            archivo.write(contenido)
    except Exception as e:
        return f"Ha habido un error {e}"

    return f"Se ha creado el archivo y su contenido correctamente en la ruta {ruta_archivo}"


@tool
def buscar_en_pagina(url:str, pregunta:str) -> str:
    """
    Saca la informacion en caso de que encuentre algo sobre la pregunta en la pagina, para encontrar un dato concreto en una pagina larga.

    Args:
        url: pagina de la cual queremos sacar la informacion
        pregunta: Pregunta del usuario para saber si encuentra algo parecido
    """
    resume = []

    embeddings = OllamaEmbeddings(
        model="bge-m3",
    )

    texto = descargar_pagina(url)

    if texto.startswith("Ha habido un error"):
        return "Ha habido un error al descargar la pagina"


    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,     # Número máximo de caracteres por fragmento
        chunk_overlap=100,   # Caracteres que coge del documento anterior para no perder contexto del anterior
        separators=["\n\n", "\n", " ", ""]
    )

    chunks = splitter.split_text(texto)


    vector = Chroma.from_texts( #Crea BBDD vectorial de numeros
        texts=chunks,
        embedding=embeddings
    )


    resultados = vector.similarity_search_with_score(
        query= pregunta,
        k=5,
    )

    vector.delete_collection()
    
    umbral = 1.0

    salto_entre_resultados = "\n\n" + "="*40 + "\n\n"

    for doc, score in resultados:
        if score < umbral:
            formato_resultado = (
                f"Doc: {doc.page_content}\n"
                f"Score: {score}"
            )

            resume.append(formato_resultado)

    if resume == []:
        return "Esta informacion no aparece en la pagina"

    return salto_entre_resultados.join(resume)

