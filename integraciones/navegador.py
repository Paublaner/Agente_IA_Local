from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from integraciones import gmail
import atexit
import os
import re
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
SCRIPT_PUNTERO = """
window.addEventListener('DOMContentLoaded', () => {
    const pointer = document.createElement('div');
    pointer.style.position = 'fixed';
    pointer.style.width = '24px';
    pointer.style.height = '24px';
    pointer.style.pointerEvents = 'none';
    pointer.style.zIndex = '999999';
    // Flecha como la de Windows: blanca con borde negro. La PUNTA está en (0,0),
    // la esquina de arriba a la izquierda, así que no hace falta centrarla con translate.
    pointer.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <polygon points="1,1 1,19 6,14 9.5,21.5 12.5,20 9,13 16,13"
                     fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>`;
    document.body.appendChild(pointer);

    document.addEventListener('mousemove', (e) => {
        pointer.style.left = `${e.clientX}px`;
        pointer.style.top = `${e.clientY}px`;
    });
});
"""



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
        
        # Solo para grabar vídeos de demo: si existe la variable de entorno GRABAR_NAVEGADOR,
        # la ventana se graba en esa carpeta (el vídeo se guarda al cerrar el navegador). Si no, nada cambia.
        grabacion = {}
        if os.environ.get("GRABAR_NAVEGADOR"):
            grabacion = {"record_video_dir": os.environ["GRABAR_NAVEGADOR"],
                         "record_video_size": {"width": 1280, "height": 720}}

        NAVEGADOR = PLAYWRIGHT.chromium.launch_persistent_context(DATA, args= ["--disable-blink-features=AutomationControlled"], headless=False,channel="chrome", **grabacion)

        paginas = NAVEGADOR.pages

        PAGINA = paginas[0]

        NAVEGADOR.add_init_script(SCRIPT_PUNTERO)

    return PAGINA
    


def leer_pagina(url: str):
    if not url.startswith(("http://", "https://")):
        return f"Ha habido un error: la URL '{url}' no es válida, tiene que empezar por http:// o https://"

    try:

        pagina = obtener_pagina()

        pagina.goto(url, timeout=ESPERA_MAXIMA)

        pagina.mouse.move(400, 300, steps=20)

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

    atributo_data_placeholder = el.get_attribute("data-placeholder") or el.get_attribute("aria-placeholder")

    placeholder_hijo = None
    hijos = el.locator("[data-placeholder]")
    if hijos.count() > 0: 
        placeholder_hijo = hijos.first.get_attribute("data-placeholder")

    return (texto or atributo_aria_label or atributo_place_holder or atributo_name
            or atributo_data_placeholder or placeholder_hijo)


def listar_elementos():
    global ELEMENTOS
    ELEMENTOS = []
    selector = 'a, button, input, select, textarea, [role="button"], [contenteditable="true"], [role="textbox"]'
    selector_dialogo = 'dialog[open], [role="dialog"]'
    pagina = obtener_pagina()
    elementos = pagina.locator(selector)
    dialogos = pagina.locator(selector_dialogo).filter(visible=True)

    if dialogos.count() > 0:
        zona = dialogos.last

        elementos = zona.locator(selector)

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
    selector = '[contenteditable="true"]'

    if numero < 1 or numero > len(ELEMENTOS):
        return f"Ha habido un error: no existe el elemento {numero}. Usa listar_elementos para ver los números disponibles."

    el = ELEMENTOS[numero - 1]
    nombre = nombre_elemento(el)

    if os.environ.get("GRABAR_NAVEGADOR") and re.search(r"\b(publicar|post|enviar|send|compartir|share)\b", str(nombre), re.IGNORECASE):
        return f'Bloqueado: [{numero}] "{nombre}" publica o envía, y eso lo hace el usuario. Deja el texto escrito y PARA.'

    try:
        el.click(timeout=ESPERA_MAXIMA)
        pagina = obtener_pagina()
        pagina.wait_for_load_state(timeout=ESPERA_MAXIMA)

    except PlaywrightTimeoutError:
        return f'Ha habido un error: no se ha podido clicar en [{numero}] "{nombre}" en {ESPERA_MAXIMA // 1000} segundos (puede estar tapado o desactivado). Usa listar_elementos para ver la página actual.'
    except PlaywrightError as e:
        primera_linea = str(e).splitlines()[0]
        return f'Ha habido un error al clicar en [{numero}] "{nombre}": {primera_linea}'

    try:
        pagina.wait_for_selector(selector, timeout=3000)

    except PlaywrightTimeoutError:
        pass

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

        try:
            pagina.wait_for_selector("input[type=password]", state="visible", timeout=3000)

        except PlaywrightTimeoutError:
            return f"Ya se ha iniciado sesion antes continua con la consulta"

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

