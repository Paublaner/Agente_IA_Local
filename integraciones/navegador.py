from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from integraciones import gmail
import atexit


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

        cerrar_navegador

    return PAGINA
    


def leer_pagina(url: str):
    if not url.startswith(("http://", "https://")):
        return f"Ha habido un error: la URL '{url}' no es válida, tiene que empezar por http:// o https://"

    try:

        pagina = obtener_pagina()

        pagina.goto(url, timeout=ESPERA_MAXIMA)
        texto = pagina.inner_text("body")

    except PlaywrightTimeoutError:
        return f"Ha habido un error: la página {url} ha tardado más de {ESPERA_MAXIMA // 1000} segundos en cargar"
    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f"Ha habido un error al abrir la página {url}: {primera_linea}"

    texto_limpio = gmail.limpiar_texto(texto)

    if len(texto_limpio) > LIMITE:
        total = len(texto_limpio)
        cuerpo = texto_limpio[:LIMITE] + f"\n\n[Se muestran {LIMITE} de {total} caracteres; el resto no se ha leído.]"
        return cuerpo

    return texto_limpio

@atexit.register
def cerrar_navegador():
    
    global PLAYWRIGHT, NAVEGADOR, PAGINA

    if NAVEGADOR is None:
        return 

    NAVEGADOR.close()
    PLAYWRIGHT.stop()

    NAVEGADOR = None
    PLAYWRIGHT = None
    PAGINA = None



def nombre_elemento(el):
    texto = el.inner_text().strip()
    atributo_aria_label = el.get_attribute("aria-label")
    atributo_place_holder = el.get_attribute("placeholder")
    atributo_name = el.get_attribute("name")

    return texto or atributo_aria_label or atributo_place_holder or atributo_name


def listar_elementos():
    selector = 'a, button, input, select, textarea, [role="button"]'
    pagina = obtener_pagina()
    elementos = pagina.locator(selector)

    for el in elementos.all():

        if el.is_visible():
            etiqueta = el.evaluate('el => el.tagName')
            nombre = nombre_elemento(el)
            print(f"{nombre},  {etiqueta}")
            


if __name__ == "__main__":
    print(leer_pagina("wikipedia.org"))

