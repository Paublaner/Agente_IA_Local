"""Inicio de sesión con Google para que cada persona conecte SU Gmail.

Flujo OAuth de "Aplicación web":
  1. enlace_conexion() crea la URL de Google y apunta su `state` en el servidor.
  2. Google pide permiso al usuario y lo devuelve a la app con ?code=...&state=...
  3. completar_conexion() comprueba el `state`, cambia el code por las credenciales
     y las guarda en st.session_state (solo en memoria, nada en disco).

Decisiones de seguridad:
  - Scope solo lectura (gmail.readonly).
  - Sin access_type="offline": no pedimos refresh_token. El permiso dura ~1 hora y luego
    hay que volver a conectar. Si alguien robara el token, caduca enseguida.
  - El `state` es de un solo uso y caduca a los 10 minutos (protege contra CSRF:
    que alguien te cuele SU código y acabes conectado a SU cuenta).
  - Al cerrar sesión se revoca el token en Google, no solo se olvida.
"""
import time
import requests
import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CADUCIDAD_STATE = 600  # segundos que tiene el usuario para aceptar en Google


@st.cache_resource
def _pendientes():
    """Diccionario compartido por todo el servidor: state -> (code_verifier, hora).

    Hace falta porque al volver de Google la página se recarga y st.session_state
    empieza VACÍO: el Flow que creamos antes se ha perdido. Con el state de la URL
    recuperamos su code_verifier (PKCE). El state es aleatorio e imposible de adivinar.
    """
    return {}


def _crear_flujo(state=None):
    google = st.secrets["google"]
    config = {
        "web": {
            "client_id": google["client_id"],
            "client_secret": google["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=google["redirect_uri"], state=state)


def _limpiar_caducados():
    ahora = time.time()
    pendientes = _pendientes()
    for state in [s for s, (_, hora) in pendientes.items() if ahora - hora > CADUCIDAD_STATE]:
        pendientes.pop(state, None)


def enlace_conexion():
    """URL de Google para conectar Gmail. Devuelve la misma mientras dure la sesión."""
    if "enlace_gmail" not in st.session_state:
        _limpiar_caducados()
        flujo = _crear_flujo()
        # access_type="online": la librería pone "offline" por defecto (refresh_token de larga duración)
        url, state = flujo.authorization_url(access_type="online", prompt="select_account")
        _pendientes()[state] = (flujo.code_verifier, time.time())
        st.session_state.enlace_gmail = url
    return st.session_state.enlace_gmail


def completar_conexion():
    """Si venimos de Google (?code=...&state=...), termina el inicio de sesión.

    Hay que llamarla al principio de app.py, antes de pintar nada.
    """
    parametros = st.query_params
    if "code" not in parametros and "error" not in parametros:
        return

    code = parametros.get("code")
    state = parametros.get("state")
    error = parametros.get("error")
    st.query_params.clear()  # quitar el code de la barra de direcciones (y que no se reutilice)

    if error:  # el usuario pulsó "Cancelar" en Google
        st.session_state.aviso_gmail = "Has cancelado la conexión con Gmail."
        return

    pendiente = _pendientes().pop(state, None)  # pop: un solo uso
    if pendiente is None or time.time() - pendiente[1] > CADUCIDAD_STATE:
        st.session_state.aviso_gmail = "El enlace de conexión no es válido o ha caducado. Vuelve a intentarlo."
        return

    try:
        flujo = _crear_flujo(state)
        flujo.code_verifier = pendiente[0]
        flujo.fetch_token(code=code)  # si el usuario desmarcó el permiso de Gmail, esto falla
        credenciales = flujo.credentials

        perfil = build("gmail", "v1", credentials=credenciales).users().getProfile(userId="me").execute()

        st.session_state.credenciales_gmail = credenciales
        st.session_state.email_gmail = perfil["emailAddress"]
    except Exception as e:
        print(f"Error al conectar Gmail: {e}")  # el detalle al log, no a la pantalla
        st.session_state.aviso_gmail = "No se ha podido conectar Gmail. Asegúrate de marcar el permiso de leer correos."


def credenciales_actuales():
    """Credenciales del usuario de ESTA sesión, o None si no ha conectado o han caducado."""
    credenciales = st.session_state.get("credenciales_gmail")
    if credenciales is None:
        return None
    if not credenciales.valid:  # sin refresh_token no se pueden renovar: toca reconectar
        desconectar(revocar=False)
        st.session_state.aviso_gmail = "La conexión con Gmail ha caducado. Vuelve a conectar."
        return None
    return credenciales


def desconectar(revocar=True):
    """Olvida las credenciales de la sesión y, si se puede, las invalida también en Google."""
    credenciales = st.session_state.pop("credenciales_gmail", None)
    st.session_state.pop("email_gmail", None)
    st.session_state.pop("enlace_gmail", None)

    if revocar and credenciales is not None and credenciales.token:
        try:
            requests.post("https://oauth2.googleapis.com/revoke",
                          params={"token": credenciales.token}, timeout=10)
        except requests.RequestException as e:
            print(f"No se pudo revocar el token: {e}")
