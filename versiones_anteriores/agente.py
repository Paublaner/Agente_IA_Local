import ollama
import herramientas
import locale
import datetime

#buscar_web Busca en internet como hace google

#leer_texto Sacar el texto de una pagina concreta

#guardar_informe Guarda el resultado final en un archivo

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
- leer_texto(url): descarga una página y devuelve su texto.
- guardar_informe(titulo, contenido): guarda un informe en Markdown en la carpeta "informes".

CÓMO TRABAJAR:
1. Usa buscar_web con una consulta clara para encontrar fuentes sobre la pregunta del usuario.
2. Usa leer_texto en las 2 o 3 páginas más útiles de los resultados.
3. Escribe un informe en Markdown con lo que has aprendido, incluyendo los enlaces de las fuentes.
4. Guarda el informe con guardar_informe.
5. Cuando esté guardado, responde al usuario con un resumen corto de lo que has encontrado Y QUE ESTE TODO ORDENADO.

No inventes datos (alucinaciones); basa tu respuesta estrictamente en lo que devuelvan las herramientas.

DATOS DE HOY
- Fecha: {fecha_formateada}
- Día de la semana: {dia_semana}
"""

historial = []

funciones ={
     "buscar_web":herramientas.buscar_web,
     "leer_texto":herramientas.leer_texto,
     "guardar_informe":herramientas.guardar_informe
}

historial.append({"role":"system", "content":instrucciones})


while True :

    resultado = input("¿Que quieres descubrir hoy?:   ")

    historial.append({"role":"user", "content":resultado})

    response = ollama.chat(
        model= "qwen3",
        messages = historial,
        tools=list(funciones.values())
    )

    historial.append(response.message)


    if response.message.tool_calls is not None:
        while response.message.tool_calls is not None:
            for pedidos in response.message.tool_calls:
                if pedidos.function.name in funciones:
                    resultado_funcion = funciones[pedidos.function.name](**pedidos.function.arguments)
                    historial.append({"role":"tool", "content":resultado_funcion, "tool_name": pedidos.function.name})

            response = ollama.chat(
                model= "qwen3",
                messages = historial,
                tools=list(funciones.values())
            )

            historial.append(response.message)

    resultado_limpio = response.message.content.replace("*", "")

    print(resultado_limpio)


