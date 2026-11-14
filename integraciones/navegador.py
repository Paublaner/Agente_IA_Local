from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from integraciones import gmail
import atexit
from pathlib import Path
import queue
import threading

ENCARGOS = queue.Queue()
LIMITE = 8000
ESPERA_MAXIMA = 15000
NAVEGADOR = None
PLAYWRIGHT = None
PAGINA = None
ELEMENTOS = []
DATA = str(Path(__file__).resolve().parent.parent / "datos" / "user_data_dir")
ESPERA_LOGIN = 120000
HILO = None

def encargado():
    while True:
        encargo = ENCARGOS.get()
        funcion = encargo[0]
        args = encargo[1]
        respuesta = encargo[2]

        try:
            resultado = funcion(*args)
        except Exception as e:
            primera_linea = str(e).splitlines()[0] if str(e) else type(e).__name__
            resultado = f"Ha habido un error inesperado en el navegador ({funcion.__name__}): {primera_linea}"

        respuesta.put(resultado)
            
def en_hilo_navegador(funcion, *argumentos):
    global HILO

    if HILO is None:
        HILO = threading.Thread(target=encargado, daemon=True)
        HILO.start()

    respuesta = queue.Queue()

    ENCARGOS.put((funcion, argumentos, respuesta))

    return respuesta.get()


    
def obtener_pagina():

    global PLAYWRIGHT, NAVEGADOR, PAGINA

    if PAGINA is None:

        PLAYWRIGHT = sync_playwright().start()
        
        NAVEGADOR = PLAYWRIGHT.chromium.launch_persistent_context(DATA, args= ["--disable-blink-features=AutomationControlled"], headless=False,channel="chrome")

        paginas = NAVEGADOR.pages

        PAGINA = paginas[0]

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

def cerrar_navegador():

    global PLAYWRIGHT, NAVEGADOR, PAGINA

    if NAVEGADOR is None:
        return

    NAVEGADOR.close()
    PLAYWRIGHT.stop()

    NAVEGADOR = None
    PLAYWRIGHT = None
    PAGINA = None


@atexit.register
def al_salir():
    if HILO is None:
        cerrar_navegador()
        return

    en_hilo_navegador(cerrar_navegador)



def nombre_elemento(el):
    texto = el.inner_text().strip()
    atributo_aria_label = el.get_attribute("aria-label")
    atributo_place_holder = el.get_attribute("placeholder")
    atributo_name = el.get_attribute("name")

    return texto or atributo_aria_label or atributo_place_holder or atributo_name


def listar_elementos():
    global ELEMENTOS
    ELEMENTOS = []
    selector = 'a, button, input, select, textarea, [role="button"], [contenteditable="true"], [role="textbox"]'
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


def escribir(numero: int, texto: str):
    if numero < 1 or numero > len(ELEMENTOS):
        return f"Ha habido un error: no existe el elemento {numero}. Usa listar_elementos para ver los números disponibles."

    el = ELEMENTOS[numero - 1]
    nombre = nombre_elemento(el)

    try:
        el.fill(texto, timeout=ESPERA_MAXIMA)


    except PlaywrightTimeoutError:
        return f'Ha habido un error: no se ha podido introducir texto en [{numero}] "{nombre}" en {ESPERA_MAXIMA // 1000} segundos (puede estar tapado o desactivado).'

    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f'Ha habido un error al introducir el texto en [{numero}] "{nombre}": {primera_linea}'

    return f'Se ha introducido el texto en [{numero}] "{nombre}"'


def iniciar_sesion_manual(url: str):

    try:
        pagina = obtener_pagina()
        pagina.goto(url, timeout=ESPERA_MAXIMA)
        pagina.wait_for_selector("input[type=password]", state="visible", timeout=ESPERA_LOGIN)
        pagina.wait_for_selector("input[type=password]", state="hidden", timeout=ESPERA_LOGIN)
        pagina.wait_for_load_state(timeout=ESPERA_MAXIMA)
        siguiente_url = pagina.url

    except PlaywrightTimeoutError:
        return f'Ha habido un error al iniciar sesion en la URL: {url} se ha acabado el tiempo'
    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f"Ha habido un error al iniciar sesion en la URL: {url} con el siguiente error de codigo: {primera_linea}"

    return f"Se ha iniciado sesion correctamente y se ha pasado a la siguiente URL: {siguiente_url}"

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

    print("\n==========\n")

    # Prueba 5: login completo (escribir usuario y contraseña y clicar en Login)
    leer_pagina("https://the-internet.herokuapp.com/login")
    listar_elementos()

    numero_usuario = None
    numero_password = None
    numero_login = None
    numero_enlace = None
    for i, el in enumerate(ELEMENTOS):
        nombre = nombre_elemento(el)
        if nombre == "username":
            numero_usuario = i + 1
        elif nombre == "password":
            numero_password = i + 1
        elif nombre == "Login":
            numero_login = i + 1
        elif nombre == "Elemental Selenium":
            numero_enlace = i + 1

    print(escribir(numero_usuario, "tomsmith"))
    print(escribir(numero_password, "SuperSecretPassword!"))

    # Prueba 6: escribir en un enlace (debe dar error, no romper)
    print(escribir(numero_enlace, "hola"))

    # Prueba 7: número que no existe
    print(escribir(99, "hola"))

    # Si el login ha ido bien, la URL debe acabar en /secure
    print(clicar(numero_login))

    print("\n==========\n")

    # Prueba 8: login MANUAL. Primero cerramos la sesión de la prueba 5
    # para que vuelva a salir el formulario.
    leer_pagina("https://the-internet.herokuapp.com/logout")
    print("Inicia sesión A MANO en la ventana del navegador (tomsmith / SuperSecretPassword!)...")
    print(iniciar_sesion_manual("https://the-internet.herokuapp.com/login"))
    # Si ha ido bien, la URL del mensaje debe acabar en /secure

