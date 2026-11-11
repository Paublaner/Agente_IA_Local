from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from integraciones import gmail

LIMITE = 8000
ESPERA_MAXIMA = 15000
NAVEGADOR = None
PLAYWRIGHT = None
PAGINA = None


def obtener_pagina():

    global PLAYWRIGHT, NAVEGADOR, PAGINA

    if PAGINA is None:

        PLAYWRIGHT = sync_playwright().start()
        
        NAVEGADOR = PLAYWRIGHT.chromium.launch(headless=False)

        PAGINA = NAVEGADOR.new_page()

    return PAGINA
    


def leer_pagina(url: str):
    if not url.startswith(("http://", "https://")):
        return f"Ha habido un error: la URL '{url}' no es válida, tiene que empezar por http:// o https://"

    try:

        PAGINA = obtener_pagina()

        PAGINA.goto(url, timeout=ESPERA_MAXIMA)
        texto = PAGINA.inner_text("body")

    except PlaywrightTimeoutError:
        return f"Ha habido un error: la página {url} ha tardado más de {ESPERA_MAXIMA // 1000} segundos en cargar"
    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f"Ha habido un error al abrir la página {url}: {primera_linea}"

    texto_limpio = gmail.limpiar_texto(texto)

    if len(texto_limpio) > LIMITE:
        total = len(texto_limpio)
        cuerpo = texto_limpio[:LIMITE] + f"\n\n[AVISO: correo recortado. Se muestran {LIMITE} de {total} caracteres; el resto no se ha leído.]"
        return cuerpo

    return texto_limpio




if __name__ == "__main__":
    print(leer_pagina("wikipedia.org"))

