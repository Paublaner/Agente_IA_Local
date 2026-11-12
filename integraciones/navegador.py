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
ELEMENTOS = []

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
    global ELEMENTOS
    ELEMENTOS = []
    selector = 'a, button, input, select, textarea, [role="button"]'
    pagina = obtener_pagina()
    elementos = pagina.locator(selector)
    lineas = []

    for el in elementos.all():

        if el.is_visible():
            etiqueta = el.evaluate('el => el.tagName')
            nombre = nombre_elemento(el)

            ELEMENTOS.append(el)

            numero = len(ELEMENTOS)

            lineas.append(f"[{numero}]  {etiqueta}  {nombre}")

    return "\n".join(lineas)
            
def clicar(numero: int):
    if numero < 1 or numero > len(ELEMENTOS):
        return f"Ha habido un error: no existe el elemento {numero}. Usa listar_elementos para ver los números disponibles."

    el = ELEMENTOS[numero - 1]
    nombre = nombre_elemento(el)

    try:
        el.click(timeout=ESPERA_MAXIMA)
        pagina = obtener_pagina()
        pagina.wait_for_load_state(timeout=ESPERA_MAXIMA)

    except PlaywrightTimeoutError:
        return f'Ha habido un error: no se ha podido clicar en [{numero}] "{nombre}" en {ESPERA_MAXIMA // 1000} segundos (puede estar tapado o desactivado). Usa listar_elementos para ver la página actual.'
    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f'Ha habido un error al clicar en [{numero}] "{nombre}": {primera_linea}'

    return f'He clicado en [{numero}] "{nombre}". Ahora estás en {pagina.url}\n\nElementos de la página actual:\n{listar_elementos()}'


if __name__ == "__main__":
    # Prueba 1: la página de login
    leer_pagina("https://the-internet.herokuapp.com/login")
    print(listar_elementos())
    print("Guardados en ELEMENTOS:", len(ELEMENTOS))

    print("\n==========\n")

    # Prueba 2: otra página, para comprobar que ELEMENTOS se vacía
    leer_pagina("https://the-internet.herokuapp.com/checkboxes")
    print(listar_elementos())
    print("Guardados en ELEMENTOS:", len(ELEMENTOS))

    print("\n==========\n")

    # Prueba 3: clicar en "Form Authentication" desde la página principal
    leer_pagina("https://the-internet.herokuapp.com")
    listar_elementos()

    # Buscamos su número en la lista, como haría el modelo leyendo los [N]
    numero_form = None
    for i, el in enumerate(ELEMENTOS):
        if nombre_elemento(el) == "Form Authentication":
            numero_form = i + 1

    print(clicar(numero_form))

    print("\n==========\n")

    # Prueba 4: números que no existen (no deben clicar nada)
    print(clicar(50))
    print(clicar(0))
    print(clicar(-1))

