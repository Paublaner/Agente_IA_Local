
import herramientas
import locale
import datetime
from langchain_ollama import ChatOllama

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

historial = []
contador = 0
historial.append(("system", instrucciones))

funciones ={
     "buscar_web":herramientas.buscar_web,
     "leer_texto":herramientas.leer_texto,
     "guardar_informe":herramientas.guardar_informe,
     "buscar_en_pagina": herramientas.buscar_en_pagina
}

llm_with_tools = llm.bind_tools(list(funciones.values()))

while True:
    contador = 0

    resultado = input("¿Que quieres descubrir hoy?:   ")

    historial.append(("human", resultado))

    mensaje = llm_with_tools.invoke(historial)

    historial.append(mensaje)

    while mensaje.tool_calls and contador < 10:
        for llamada in mensaje.tool_calls:
            if llamada["name"] in funciones:
                result = funciones[llamada["name"]].invoke(llamada) #Porque lleva el id dentro y lo necesita para hacer varias llamadas
                historial.append(result)

        mensaje = llm_with_tools.invoke(historial)
        contador += 1
        historial.append(mensaje)

    if mensaje.tool_calls is []:
        print("Se han acabado las llamadas a las herramientas")

    print(mensaje.content)





            





