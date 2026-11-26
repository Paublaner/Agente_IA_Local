# Agente de IA con LangGraph y Ollama

Agente de IA que **investiga un tema en internet y te devuelve un resumen con fuentes**. Busca en la web, lee páginas, encuentra datos concretos dentro de páginas largas con RAG, **resume documentos largos** tuyos (PDF, Word, TXT, MD) por partes y guarda informes en Markdown.

Además:

- **Responde preguntas sobre tus documentos** (RAG): los indexas una vez desde la barra lateral, se guardan como vectores en **PostgreSQL + pgvector**, y el agente busca en ellos y cita de qué archivo sale cada dato.
- **Te pide permiso antes de actuar** (*human in the loop* con `interrupt` de LangGraph): antes de clicar, escribir en una web o ejecutar algo en Composio, se para y te enseña qué quiere hacer. Tú pulsas **Aprobar** o **Rechazar**.

- **Lee tu Gmail** (solo lectura): busca correos y los lee enteros para resumírtelos. Es **multiusuario**: cada persona conecta **su propia cuenta de Google** desde la app y el agente solo ve sus correos.
- **Maneja un navegador de verdad** (Chrome, con Playwright): abre páginas, ve sus botones y campos, hace clic y escribe. Lo ves trabajar en una ventana, con una flecha que enseña dónde está el ratón. Por ejemplo, **te deja preparada una publicación de LinkedIn** para que tú la revises y la publiques.
- **Lee tu perfil de LinkedIn** a través de **Composio** (MCP remoto).
- **Habla y escucha**: puedes hablarle por el micrófono (Whisper) y te contesta con voz (Piper).

El modelo funciona **en local** con [Ollama](https://ollama.com): no usa ninguna API de pago y tus documentos no salen de tu ordenador. Se usa desde una **interfaz de chat con Streamlit** que guarda **varias conversaciones** (las puedes abrir de nuevo o borrar desde la barra lateral) y enseña qué herramientas va usando.

## Qué sabe hacer

Las herramientas propias están en `agente/herramientas.py`. Las de Composio llegan por MCP desde `mcp_local/conexion_mcp.py`. Las que puede usar el agente son las que están en el diccionario `funciones` de `agente_grafo.py`.

| Herramienta | Qué hace | Activa en el agente |
|---|---|:---:|
| `buscar_web(consulta)` | Busca en internet (DuckDuckGo) y devuelve 5 resultados con título, enlace y resumen. | ✅ |
| `leer_texto(url)` | Descarga una página, la limpia (quita menús, scripts, pie...) y devuelve los primeros 8000 caracteres. Sirve para hacerse una idea general. | ✅ |
| `buscar_en_pagina(url, pregunta)` | **RAG**: trocea la página entera, la convierte en vectores y devuelve solo los fragmentos relacionados con la pregunta. Sirve para datos concretos que están muy abajo en páginas largas. | ✅ |
| `resumir_documento(nombre)` | **Map-reduce**: resume un documento largo de `datos/documentos/` por partes y luego hace un resumen final. Ver [Resumir documentos largos](#resumir-documentos-largos-map-reduce). | ✅ |
| `buscar_en_documentos(pregunta, nombre)` | **RAG sobre tus documentos**: busca en los documentos ya indexados en Postgres y devuelve los fragmentos relacionados, cada uno con su `Fuente:`. `nombre` es opcional, para buscar solo en un archivo. Ver [Preguntar a tus documentos](#preguntar-a-tus-documentos-rag-con-pgvector). | ✅ |
| `leer_documento(nombre)` | Lee un documento corto de `datos/documentos/` (PDF, `.docx`, `.txt`, `.md`). Recorta a 25.000 caracteres avisando. | ✅ |
| `guardar_informe(titulo, contenido)` | Guarda el informe final en `datos/informes/` como archivo Markdown. | ✅ |
| `listar_correos(busqueda, maximo)` | Busca en el Gmail del usuario con la sintaxis de Gmail (`from:`, `is:unread`, `newer_than:7d`...). Devuelve de cada correo su ID, remitente, asunto, fecha y un fragmento. Como mucho 20. | ✅ |
| `leer_correo(id_correo)` | Lee un correo entero con el ID que da `listar_correos`. Saca el texto plano y, si no hay, convierte el HTML a texto. Recorta a 8000 caracteres avisando. | ✅ |
| `leer_pagina(url)` | Abre una página en el **navegador** y devuelve su texto visible (recortado a 8000 caracteres). | ✅ |
| `listar_elementos()` | Lista los enlaces, botones y campos de la página abierta, cada uno con un número: `[5]  BUTTON  Login`. | ✅ |
| `clicar(numero)` | Hace clic en el elemento con ese número. Devuelve la URL nueva y la lista de elementos actualizada. | ✅ |
| `escribir(numero, texto)` | Escribe en un campo (`INPUT`, `TEXTAREA` o `DIV` editable, como el editor de LinkedIn). No envía nada. | ✅ |
| `iniciar_sesion_manual(url)` | Abre la página de login y **espera a que el usuario entre a mano** (hasta 2 minutos). El agente nunca escribe contraseñas. | ✅ |
| `COMPOSIO_*` (4 herramientas) | Buscar, consultar y ejecutar herramientas de Composio, y conectar cuentas. Se usan **solo para leer** el perfil de LinkedIn. Ver [Composio](#composio-linkedin-por-mcp-remoto). | ✅ |
| `fecha_hora()` | Fecha y hora actuales, desde el servidor MCP propio (`servidor_mcp.py`). | ❌ |

`fecha_hora` no está activa: `cargar_herramientas_mcp` ahora solo carga el servidor `composio`. El servidor propio sigue en el proyecto como ejemplo de MCP.

`clicar`, `escribir` y `COMPOSIO_MULTI_EXECUTE_TOOL` **necesitan tu permiso** cada vez que se usan (están en la lista `funciones_a_revisar`). Ver [Aprobación humana](#aprobación-humana-interrupt).

## Cómo funciona

El agente es un grafo de LangGraph con dos nodos. El modelo decide si necesita una herramienta; si la pide, se ejecuta y el resultado vuelve al modelo. El bucle sigue hasta que el modelo responde sin pedir herramientas, o hasta llegar al límite de pasos (`recursion_limit = 40`).

```mermaid
flowchart LR
    START([Inicio]) --> M[node_modelo<br/>qwen3 + herramientas]
    M -->|pide herramientas| H[node_herramientas<br/>ejecuta las tool_calls]
    H --> M
    M -->|responde sin herramientas| FIN([Fin])
```

- **`node_modelo`**: añade las instrucciones de sistema (`agente/instrucciones.py`) delante del historial, junto con la lista de **documentos indexados del usuario** (`documentos_indexados()`), y llama al modelo con las herramientas enlazadas (`bind_tools`). Así el modelo sabe qué archivos tiene y busca en ellos antes que en internet.
- **`node_herramientas`**: coge el último mensaje, ejecuta cada `tool_call` y devuelve los resultados como mensajes. Antes de nada, si la herramienta está en `funciones_a_revisar`, **se para a pedir permiso** con `interrupt` (ver [Aprobación humana](#aprobación-humana-interrupt)). Después hay tres "puertas" (`if / elif / elif`) porque no todas las herramientas se ejecutan igual:
  1. **Gmail** (`funciones_gmail`): se les añaden las credenciales del usuario antes de ejecutarlas (ver [Gmail multiusuario](#gmail-multiusuario)).
  2. **MCP** (`nombres_mcp`): solo funcionan en asíncrono, así que se llaman con `asyncio.run(...ainvoke(...))`.
  3. **El resto**: `.invoke` normal.
- **`decidir`**: si el último mensaje tiene `tool_calls`, va a herramientas; si no, termina.
- **Memoria**: el grafo se compila con un checkpointer `PostgresSaver` (antes era `SqliteSaver` con `datos/memoria.db`). Cada conversación del chat tiene su `thread_id`, así que el agente recuerda lo hablado en esa conversación.
- **Lista de conversaciones**: una tabla propia, `conversaciones` (`hilo`, `titulo`, `creada`), en la misma base de datos. Al hacer la primera pregunta se guarda con su título (el principio de la pregunta). Las funciones `guardar_conversacion`, `listar_conversaciones`, `conversacion(hilo)` (los mensajes guardados) y `eliminar_conversacion` (borra la fila **y** los mensajes con `memory.delete_thread`) son las que usa la barra lateral.
- **`ejecutar_grafo(credenciales, pregunta, hilo, aprobacion=None)`**: usa `stream` en vez de `invoke` y va devolviendo (`yield`) cada paso según ocurre: `("herramienta", llamada)`, `("aprobar", datos)` si el grafo se ha parado a pedir permiso, y `("respuesta", texto)` al final. Si llega `aprobacion` (`True` o `False`), no empieza una pregunta nueva: **reanuda** el grafo donde se paró con `Command(resume=aprobacion)`. Las credenciales de Gmail van por `context`, no por `config`.

## Preguntar a tus documentos (RAG con pgvector)

`resumir_documento` sirve para el documento entero, pero para una pregunta concreta (*"¿qué le pasa al patito en invierno?"*) es mejor buscar solo los trozos que hablan de eso.

```mermaid
flowchart LR
    S[Subir documento] --> I[Botón Indexar]
    I --> T[cargar_texto + trocear<br/>1200 / 100]
    T --> E[bge-m3<br/>embeddings]
    E --> P[(Postgres + pgvector<br/>fuente = archivo)]
    Q[Pregunta] --> B[buscar_en_documentos]
    B --> P
    P -->|5 más parecidos<br/>con distancia < 0.5| R[Fragmentos + Fuente]
```

1. **Indexar** (`indexar_documento`, desde el botón junto a cada documento en la barra lateral): carga el texto con `cargar_texto`, une las palabras partidas con guion al final de línea (`palabra-\nsigue` → `palabrasigue`, típico de los PDF), lo trocea en fragmentos de 1200 caracteres con 100 de solapamiento y los guarda en la colección `documentos` de `PGVector`. Cada trozo lleva en sus metadatos `{"fuente": nombre_del_archivo}`.
2. **Sin duplicados**: antes de guardar, borra los trozos que ya tuviera ese archivo. Volver a indexar **reemplaza**, no suma.
3. **Buscar** (`buscar_en_documentos`): pide los 5 trozos más parecidos a la pregunta (en todos los documentos o, con `nombre`, solo en uno, filtrando por `fuente`) y se queda con los que tienen una distancia **menor que 0.5**. Si no queda ninguno, responde *"La Informacion no aparece en el documento revisado"*.
4. **En la barra lateral** cada documento sale con un icono: ✔ si ya está indexado, o el de documento si todavía no. El botón cambia entre "Indexar" y "Volver a indexar".

Las instrucciones le dicen al modelo que **lo que recuerda de una obra no cuenta como fuente** (el documento puede ser otra edición o traducción): si el título coincide con un documento indexado, busca ahí primero, y no cita un archivo si no lo ha leído en esa respuesta.

**Chroma sigue existiendo** para `buscar_en_pagina` (páginas web): ahí los vectores solo hacen falta un momento y se borran al terminar. Los documentos, en cambio, se indexan una vez y se consultan muchas, así que van a Postgres, que los guarda.

## Aprobación humana (interrupt)

Hay acciones que el agente no debería hacer sin que tú lo veas: clicar y escribir en una web, o ejecutar una herramienta de Composio. Para esas, el grafo **se para a mitad** y espera tu respuesta.

```mermaid
flowchart LR
    M[node_modelo] -->|pide clicar / escribir / Composio| H[node_herramientas]
    H -->|interrupt| U{{Tarjeta en la app:<br/>Aprobar / Rechazar}}
    U -->|Aprobar → Command resume=True| X[Se ejecuta la herramienta]
    U -->|Rechazar → Command resume=False| N[ToolMessage: el usuario lo ha rechazado]
    X --> M
    N --> M
```

1. **Se para**: en `node_herramientas`, si `llamada["name"]` está en `funciones_a_revisar`, se llama a `interrupt({"Funcion nombre": ..., "Argumentos": ...})`. LangGraph guarda el estado en el checkpointer y el `stream` devuelve un paso `__interrupt__`, que `ejecutar_grafo` convierte en `("aprobar", datos)`.
2. **Te pregunta**: `app.py` guarda lo pendiente en `st.session_state.esperando_aprobacion` y pinta una tarjeta con el nombre de la herramienta, sus argumentos y los botones **Aprobar** / **Rechazar**. Mientras tanto la caja del chat se desactiva.
3. **Sigue**: el botón guarda la decisión (con `on_click`, que se ejecuta antes de repintar) y se llama a `ejecutar_grafo(..., aprobacion=True/False)`, que reanuda con `Command(resume=...)`. `interrupt` devuelve ese valor dentro del nodo.
4. **Si rechazas**, no se ejecuta la herramienta: el modelo recibe un `ToolMessage` que dice que el usuario lo ha rechazado, que **no lo reintente** y que te pregunte qué quiere cambiar.

Cada `tool_call` tiene que tener su `ToolMessage` de respuesta, aunque se haya rechazado: así el historial queda completo y el modelo sabe qué ha pasado con lo que pidió. Por eso el rechazo crea uno con el mismo `tool_call_id`.

Si cambias de conversación o empiezas una nueva con un permiso pendiente, ese permiso se descarta (es de la conversación anterior).

## Resumir documentos largos (map-reduce)

Un documento largo no cabe entero en el contexto del modelo, así que `resumir_documento` lo resume en dos fases:

```mermaid
flowchart LR
    D[Documento] --> T1[Trozo 1] --> R1[Resumen 1]
    D --> T2[Trozo 2] --> R2[Resumen 2]
    D --> T3[Trozo ...] --> R3[Resumen ...]
    R1 --> F[Resumen final]
    R2 --> F
    R3 --> F
```

1. **Map:** trocea el texto entero en trozos de 20.000 caracteres y le pide al modelo un resumen de cada uno (máximo 150 palabras).
2. **Reduce:** junta todos los resúmenes y le pide un resumen final, ordenado por temas y en Markdown.

Para resumir usa un `ChatOllama` propio dentro de `herramientas.py`, sin herramientas. No se puede importar el `llm` de `agente_grafo.py` porque `agente_grafo.py` ya importa `herramientas.py` y sería una importación circular.

La carga del documento (ruta segura, lista de archivos disponibles y extracción del texto) está en una función aparte, `cargar_texto`, que devuelve el texto entero sin recortar.

## Navegador (Playwright)

El agente maneja un Chrome real que se abre en una ventana, así que **puedes ver lo que hace**. Las herramientas `@tool` de `herramientas.py` son solo la "fachada": el trabajo de verdad está en `integraciones/navegador.py`.

```mermaid
flowchart LR
    L[leer_pagina] --> E[listar_elementos]
    E --> C[clicar]
    E --> W[escribir]
    C -->|lista nueva| E2[elementos actualizados]
    E2 --> W
    W --> P([PARA: el usuario revisa y publica])
```

**Cómo ve el modelo una página.** El modelo no ve la pantalla. `listar_elementos` busca los elementos con los que se puede interactuar (`a, button, input, select, textarea, [role="button"], [contenteditable="true"], [role="textbox"]`), se queda con los visibles, los guarda en la lista `ELEMENTOS` y le devuelve al modelo un texto numerado:

```
[1]  A  Inicio
[5]  BUTTON  Login
[6]  DIV  Comparte tus ideas…
```

El modelo solo tiene que decir un número: `clicar(5)` o `escribir(6, "texto")`. Los números solo valen para la página actual; por eso `clicar` devuelve ya la lista nueva.

**El nombre de cada elemento** (`nombre_elemento`) se busca en este orden: su texto, `aria-label`, `placeholder`, `name`, `data-placeholder` / `aria-placeholder` y, si no tiene nada, el `data-placeholder` de un hijo. Esto último hacía falta para el editor de LinkedIn, que salía como `[6] DIV None`: el texto "Comparte tus ideas…" está en un `<p>` de dentro.

**Ventanas emergentes.** Si hay un diálogo abierto (`dialog[open]` o `[role="dialog"]`, visible), `listar_elementos` solo lista lo que hay **dentro** del último. Con la ventana de publicar de LinkedIn abierta salían 146 elementos (incluido todo el feed de detrás) y el modelo se perdía; ahora salen solo los de la ventana.

**Sesión guardada.** Chrome se abre con `launch_persistent_context` y una carpeta de perfil propia (`datos/user_data_dir/`). Ahí quedan las cookies: inicias sesión **una vez a mano** y las siguientes veces ya estás dentro. Esa carpeta no se sube a git (con ella se podría entrar en tus cuentas sin contraseña).

**El puntero.** Playwright mueve el ratón, pero no lo dibuja. `SCRIPT_PUNTERO` (registrado con `add_init_script`, así que se inyecta en cada página nueva) pone una flecha que sigue los eventos `mousemove`.

**Grabar demos.** Si existe la variable de entorno `GRABAR_NAVEGADOR` (una carpeta), la ventana se graba en vídeo a 1280×720 (el vídeo se guarda al cerrar el navegador). Mientras se graba, `clicar` **bloquea en código** cualquier botón que se llame "publicar", "post", "enviar", "send", "compartir" o "share". Sin la variable, nada cambia.

### Navegador: decisiones de seguridad

**El agente nunca escribe contraseñas.** Para entrar en una web usa `iniciar_sesion_manual`: abre el login, espera a que aparezca el campo de contraseña y, después, a que desaparezca (señal de que el usuario ha entrado). Si el campo no aparece, es que ya había sesión y sigue. Las instrucciones le prohíben usar `escribir` para usuarios o contraseñas.

**El agente nunca publica ni envía.** Las instrucciones le prohíben clicar en "Publicar", "Enviar", "Compartir", "Post" o "Send". Escribe el texto, **para** y le dice al usuario que lo revise en la ventana y lo publique él.

**Cada clic y cada texto, con tu permiso.** Además de las instrucciones, `clicar` y `escribir` pasan por la [aprobación humana](#aprobación-humana-interrupt): aunque el modelo se saltara una regla, no hace nada en la web sin que tú lo apruebes viendo el número del elemento y el texto.

**Publicaciones de LinkedIn, siempre por el navegador.** Al principio el modelo prefería publicar con Composio (por API), sin que el usuario viera nada, porque el prompt tenía una receta para eso. Se quitó: Composio queda solo para leer el perfil y las publicaciones se preparan en el navegador, a la vista, con una receta paso a paso (abrir el feed → listar → clicar en "Crear publicación" → escribir en "Comparte tus ideas…" → parar).

**El contenido de las webs son datos, no órdenes.** Igual que con los correos: si una página dice "ignora tus instrucciones" o "escribe tu contraseña", el agente no lo hace y avisa.

### Navegador: problemas resueltos

**Playwright y los hilos de Streamlit.** La API síncrona de Playwright solo se puede usar desde el **mismo hilo** que la arrancó, pero Streamlit ejecuta cada mensaje en un hilo distinto. Solución: un único hilo "encargado" (`encargado`) que es el único que toca el navegador. Las herramientas le mandan los trabajos por una cola (`en_hilo_navegador`) y esperan la respuesta en otra. Como en una cocina con un solo cocinero: los camareros dejan las comandas y recogen los platos, pero nunca cocinan.

**El modelo clicaba en el editor antes de escribir.** Al clicar dentro del editor, la lista de elementos cambiaba y el modelo usaba números viejos. Se arregló en dos sitios: `escribir` usa `fill()`, que ya pone el cursor solo, y las instrucciones y los docstrings le dicen que **nunca** clique en un campo de texto.

**El editor de LinkedIn tarda en aparecer.** Después de `clicar`, la ventana de publicar se abre con un poco de retraso y la lista salía sin el editor. Ahora `clicar` espera hasta 3 segundos a que aparezca un `[contenteditable="true"]` antes de listar (si no aparece, sigue igual).

**"Crear publicación" no es el editor.** En el feed, el botón que abre la ventana también es un `DIV`. Con la receta antigua ("si ya aparece el editor, un DIV, no cliques") el modelo lo confundía con el editor. Ahora la receta dice que "Crear publicación" es un botón y que el editor es el DIV "Comparte tus ideas…".

**Un error no tumba al encargado.** Si una función del navegador lanza una excepción inesperada, `encargado` la recoge y devuelve un texto de error al modelo. Si no, el hilo moriría y todas las herramientas se quedarían esperando para siempre.

## Composio (LinkedIn por MCP remoto)

[Composio](https://composio.dev) ofrece herramientas de muchas apps (LinkedIn entre ellas) por un servidor MCP en internet. `conexion_mcp.py` se conecta con `streamable_http`, la URL y la clave del `.env`, y solo deja pasar 4 herramientas (`PERMITIDAS_COMPOSIO`):

- `COMPOSIO_SEARCH_TOOLS`: buscar qué herramienta hace lo que necesitas.
- `COMPOSIO_GET_TOOL_SCHEMAS`: ver qué parámetros necesita.
- `COMPOSIO_MULTI_EXECUTE_TOOL`: ejecutarla. **Pide tu permiso** antes (ver [Aprobación humana](#aprobación-humana-interrupt)).
- `COMPOSIO_MANAGE_CONNECTIONS`: conectar la cuenta de LinkedIn (da un enlace para autorizar).

**Composio y el navegador no comparten sesión.** Composio usa la API de LinkedIn con un token OAuth; el navegador usa cookies. Son dos llaves distintas para la misma casa: conectar una no te da la otra.

**Qué se usa de Composio.** Solo leer el perfil (`LINKEDIN_GET_MY_INFO`). Para publicar, el navegador (ver arriba). Si `cargar_herramientas_mcp` falla (sin internet, clave mala...), imprime el error y devuelve una lista vacía: el agente arranca igual, sin Composio.

## Voz

- **Oído** (`voz/oido.py`): `faster-whisper` (modelo `small`, en CPU) transcribe lo que dices.
- **Boca** (`voz/boca.py`): **Piper** con la voz `es_ES-davefx-medium` convierte la respuesta en audio. `sintetizar_wav` la devuelve como WAV para reproducirla en el navegador.
- **En la app**: la caja del chat tiene un botón de micrófono (`accept_audio=True`). Si hablas, te contesta hablando. En la barra lateral se puede activar que lea también las respuestas escritas.
- **`voz/conversacion.py`**: prueba por terminal: escucha 5 segundos, se lo pasa al agente y escribe la respuesta.

## Gmail multiusuario

Cada persona que abre la app conecta **su** cuenta de Google y el agente lee **su** correo. El token de Google es como la tarjeta de una habitación de hotel: tiene que llegar desde el usuario hasta la herramienta **sin pasar nunca por el LLM**.

```mermaid
flowchart LR
    U[Usuario] -->|Conectar Gmail| G[Google OAuth]
    G -->|code + state| A[auth_gmail.py<br/>session_state]
    A -->|credenciales| E[ejecutar_grafo]
    E -->|context=| N[node_herramientas]
    N -->|copia de la llamada<br/>+ credenciales| T[listar_correos / leer_correo]
    T --> GM[Gmail API]
    M[LLM] -.->|solo pide busqueda / id_correo| N
```

1. **Inicio de sesión** (`auth_gmail.py`): flujo OAuth de tipo *Aplicación web*. El botón "Conectar Gmail" lleva a Google; Google devuelve al usuario a la app con un `code` y un `state`; la app cambia el `code` por las credenciales y las guarda en `st.session_state`. Cada pestaña del navegador tiene su propia sesión, así que cada usuario tiene las suyas.
2. **Hasta el grafo**: `app.py` llama a `ejecutar_grafo(auth_gmail.credenciales_actuales(), ...)` y este se las pasa al `stream` con `context={"credenciales_gmail": ...}`.
3. **Hasta la herramienta**: `node_herramientas` las lee de `runtime.context` y crea una **copia** de la llamada con las credenciales añadidas a los `args`.
4. **Ocultas al LLM**: en `herramientas.py` el parámetro es `credenciales: Annotated[Credentials, InjectedToolArg]`. LangChain no lo enseña en el esquema de la herramienta: el modelo solo ve `busqueda` y `maximo` (o `id_correo`).

Si el usuario no ha conectado Gmail, las credenciales llegan como `None` y `gmail.py` devuelve un error que el agente le explica.

## MCP (Model Context Protocol)

MCP es un protocolo estándar para que una aplicación de IA use herramientas que ofrece **otro programa** (como el USB: el servidor se hace una vez y cualquier app que hable MCP puede usarlo).

- **`servidor_mcp.py`**: servidor MCP propio con `FastMCP`, por `stdio`. Ofrece `fecha_hora`.
- **`conexion_mcp.py`**: cliente con `MultiServerMCPClient` (`langchain-mcp-adapters`) con dos servidores: el propio (`prueba`, por `stdio`, arrancado con `sys.executable`) y **Composio** (remoto, por `streamable_http`). Ahora el agente solo carga las herramientas de Composio.
- **`agente_grafo.py`**: añade las herramientas MCP a `funciones` y guarda sus nombres en `nombres_mcp` para llamarlas en asíncrono.

Las herramientas de Gmail **empezaron en el servidor MCP**, pero se sacaron de ahí. Ver *Gmail fuera del MCP* en las decisiones de diseño.

## Tecnologías

- **Python** + **LangGraph** (`StateGraph`, `MessagesState`, `PostgresSaver` para la memoria, `interrupt` y `Command` para la aprobación humana)
- **Streamlit** para la interfaz de chat (con micrófono, lista de conversaciones e iconos de Material Symbols; estilos propios en `estilos/interfaz.css` y tema en `.streamlit/config.toml`)
- **LangChain**: `ChatOllama`, `@tool`, `RecursiveCharacterTextSplitter`
- **Ollama** en local: `qwen3` (modelo con herramientas) y `bge-m3` (embeddings)
- **PostgreSQL + pgvector** (`psycopg`, `langchain-postgres` con `PGVector`): memoria de las conversaciones, lista de conversaciones y vectores de tus documentos
- **ChromaDB** en memoria para el RAG de páginas web (`buscar_en_pagina`)
- **ddgs** (búsqueda), **requests** + **BeautifulSoup** (páginas web), **pypdf** y **python-docx** (documentos)
- **Playwright** (API síncrona) con el Chrome instalado, para el navegador
- **Gmail API** (`google-api-python-client`) + **OAuth 2.0** (`google-auth-oauthlib`, flujo web con PKCE)
- **MCP**: `mcp` (FastMCP), `langchain-mcp-adapters` y **Composio**
- **Voz**: `faster-whisper` (oír) y `piper-tts` (hablar)

## Instalación

Necesitas Python 3.10+, [Ollama](https://ollama.com), **Google Chrome** y **Docker** para la base de datos **PostgreSQL con pgvector** (ver [Configurar la base de datos](#configurar-la-base-de-datos)). Para Gmail, además, un proyecto en Google Cloud (ver [Configurar Gmail](#configurar-gmail)); para LinkedIn por API, una cuenta de Composio (ver [Configurar Composio](#configurar-composio)).

```bash
# 1. Descargar los modelos
ollama pull qwen3
ollama pull bge-m3

# 2. Crear el entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate        # en Windows
pip install -r requirements.txt

# 3. Arrancar Postgres en Docker (ver "Configurar la base de datos")

# 4. Arrancar la interfaz
streamlit run app.py
```

El navegador usa el **Chrome que ya tienes instalado** (`channel="chrome"`), así que no hace falta `playwright install`.

Para la voz, descarga `es_ES-davefx-medium.onnx` y su `.onnx.json` de las [voces de Piper](https://huggingface.co/rhasspy/piper-voices) y ponlos en `voz/voces/` (no se suben a git porque pesan mucho).

Se abre en `http://localhost:8501`. Es un chat **con memoria**: el agente recuerda lo hablado en la conversación. Mientras trabaja se ve qué herramientas va usando, y cada respuesta guarda en un desplegable las herramientas que usó. Si quiere clicar, escribir o usar Composio, te sale una tarjeta para **aprobarlo o rechazarlo**. En la barra lateral puedes empezar una conversación nueva, **abrir o borrar las anteriores**, **conectar o desconectar tu Gmail** y subir documentos a `datos/documentos/` para que los lea, los resuma o, después de **indexarlos**, le preguntes por ellos.

Ejemplos de lo que le puedes pedir:

- *"Investiga quién es Cristiano Ronaldo y guárdame un informe"*
- *"¿Cuáles son los principios del Zen de Python? Míralo en https://es.wikipedia.org/wiki/Python"*
- *"Resúmeme el documento el-largo-viaje.pdf"* (el archivo tiene que estar en `datos/documentos/`)
- *"En el patito feo, ¿qué le pasa al patito en invierno?"* (con `patitofeo.pdf` indexado)
- *"¿Qué correos me han llegado hoy?"* o *"Resúmeme el último correo de LinkedIn"* (con Gmail conectado)
- *"Prepárame una publicación en LinkedIn sobre lo que he aprendido creando un agente de IA. No la publiques, déjala escrita para que la revise"*

**Antes de volver a arrancar:** para Streamlit con `Ctrl+C` y **cierra la ventana de Chrome del agente**. El perfil `datos/user_data_dir/` solo lo puede usar un Chrome a la vez. Los cambios en las instrucciones (`agente/instrucciones.py`) solo se notan al reiniciar Streamlit y conviene probarlos en una **conversación nueva**: si no, el modelo copia lo que hizo antes en el historial.

### Configurar la base de datos

La memoria, la lista de conversaciones y los vectores de los documentos van en **PostgreSQL** con la extensión **pgvector**, que se arranca en **Docker**. Por ejemplo, con la imagen oficial de pgvector:

```bash
docker run -d --name agente-postgres -e POSTGRES_PASSWORD=tu_contraseña -p 5432:5432 pgvector/pgvector:pg17
```

**Antes de arrancar la app, el contenedor tiene que estar en marcha** (`docker start agente-postgres` las siguientes veces). Si no, la app se queda esperando al conectar, sin dar error.

Las dos direcciones de la base de datos van en el `.env`, junto a las de Composio:

```
DATABASE_URL=postgresql://usuario:contraseña@localhost:5432/basededatos
URL_VECTOR=postgresql+psycopg://usuario:contraseña@localhost:5432/basededatos
```

Son la misma base de datos escrita de dos formas: `DATABASE_URL` la usa `psycopg` directamente (memoria y consultas propias), y `URL_VECTOR` lleva el `+psycopg` que pide `PGVector`, porque va por SQLAlchemy.

`agente/base_datos.py` las lee con `load_dotenv()` y `os.getenv`, y abre dos conexiones: `conexion_memoria` para `PostgresSaver` y `conexion` para las consultas propias. Así la contraseña no está escrita en el código.

Las tablas se crean solas al arrancar: `memory.setup()` crea las del checkpointer, `agente_grafo.py` crea `conversaciones` y `PGVector` crea las suyas (`langchain_pg_collection` y `langchain_pg_embedding`) la primera vez que indexas un documento.

### Configurar Gmail

1. En [Google Cloud Console](https://console.cloud.google.com), crea un proyecto y **habilita la Gmail API**.
2. Configura la **pantalla de consentimiento** (tipo *Externo*) y añade como **usuarios de prueba** los emails de quienes vayan a usar la app.
3. Crea un **ID de cliente de OAuth** de tipo **Aplicación web**, con `http://localhost:8501` como URI de redireccionamiento autorizado.
4. Crea `.streamlit/secrets.toml` (no se sube a git) con los datos del cliente:

```toml
[google]
client_id = "....apps.googleusercontent.com"
client_secret = "..."
redirect_uri = "http://localhost:8501"
```

Al desplegar en la nube, se añade la URL pública como otra URI de redirección y se pega lo mismo en los *Secrets* del servicio.

### Configurar Composio

Crea un archivo `.env` en la raíz (no se sube a git) con:

```
COMPOSIO_API_KEY=...
COMPOSIO_MCP_URL=...
```

Después conecta tu LinkedIn una vez: `python -m mcp_local.conexion_mcp conectar` te da un enlace para autorizar. Con `python -m mcp_local.conexion_mcp conexiones` compruebas que ha funcionado.

**Nunca pegues la clave en un chat, en el código ni en un commit.** Si se te escapa, revócala en el panel de Composio y crea otra.

### Iniciar sesión en LinkedIn (navegador)

La primera vez, pídele algo de LinkedIn al agente: abrirá la página de login y **esperará hasta 2 minutos a que entres tú a mano** en la ventana de Chrome. La sesión queda guardada en `datos/user_data_dir/` para las siguientes veces.

## Decisiones de diseño y problemas resueltos

**Umbral de relevancia en el RAG (distancia < 1.0).** Medí las distancias de `bge-m3` con preguntas reales: las que sí tenían respuesta en la página daban entre **0.49 y 0.73**, y una pregunta que no tenía nada que ver daba entre **1.27 y 1.31**. Con el umbral en 1.0, si ningún fragmento pasa el filtro la herramienta responde *"Esta información no aparece en la página"* en vez de devolver texto que no viene a cuento.

**RAG para páginas largas.** `leer_texto` se queda en 8000 caracteres para no llenar el contexto del modelo, pero eso dejaba fuera datos importantes. Por ejemplo, el Zen de Python en Wikipedia está en el carácter **13.083**. `buscar_en_pagina` trocea la página entera (trozos de 1200 caracteres con 100 de solapamiento) y lo encuentra.

**Duplicados en Chroma.** `Chroma.from_texts` en memoria reutiliza la misma colección dentro del mismo proceso, así que en la segunda llamada se mezclaban trozos de páginas anteriores. Se arregló borrando la colección (`delete_collection()`) después de cada búsqueda.

**Seguridad al leer documentos (path traversal).** `leer_documento` resuelve la ruta real y comprueba con `is_relative_to` que sigue dentro de `documentos/`. Así el modelo no puede leer cosas como `../../secreto.txt`. Si el archivo no existe, devuelve la lista de archivos disponibles para que el modelo se corrija solo (pasó de verdad: pidió `patitofeo` y se corrigió a `patitofeo.pdf`).

**Contexto del modelo (`num_ctx=16384`).** Con el contexto por defecto, Ollama recortaba el historial y el modelo "olvidaba" las instrucciones a mitad de la investigación. Al subirlo a 16384 se arregló.

**Instrucciones contra las alucinaciones.** En las primeras pruebas, el modelo resumía mal listas (daba 7 principios del Zen en vez de 19 y cambiaba palabras) y **decía haber guardado un informe sin llamar a la herramienta**. Añadí dos bloques al prompt:
- *Fidelidad a las fuentes*: copiar listas y citas palabra por palabra, indicar de qué enlace sale cada dato y separar las opiniones propias.
- *Acciones*: no decir nunca que ha hecho algo si la herramienta no lo ha confirmado.

Resultado: copia los 19 principios igual que en la fuente y solo dice que ha guardado el informe cuando es verdad.

**Recetas paso a paso para un modelo pequeño.** `qwen3` (8B) sigue mucho mejor una receta numerada con nombres exactos ("clicar en *Crear publicación*", "el DIV *Comparte tus ideas…*") que una regla general. Y si tiene dos recetas para lo mismo, elige la que más se parece a la petición: por eso, para que no publique por Composio, no bastaba con decirlo; hubo que **quitar** la receta.

**Informe solo si se pide.** El agente guarda informes únicamente cuando el usuario lo pide, para no llenar la carpeta con archivos que nadie quería.

**Tamaño de los trozos al resumir (que quepa el resumen final).** Al principio usé trozos de 12.000 caracteres y resúmenes de 250 palabras. Con un libro de unos 470.000 caracteres salían **39 trozos**, y en el reduce, 39 × 250 palabras son unos 14.000 tokens, que no caben en `num_ctx=16384` junto a las instrucciones y la respuesta. Ollama no avisa: recorta el principio sin decir nada. Con trozos de **20.000 caracteres** y **150 palabras** por resumen salen unos 24 trozos y unos 5.000 tokens en el reduce, con margen de sobra y menos llamadas al modelo.

**Errores con un inicio común.** Todos los errores de las herramientas empiezan por *"Ha habido un error"*. Así se comprueban con un solo `startswith` y el modelo los reconoce y se los explica al usuario, en vez de tratarlos como un resultado normal.

**Límite de pasos (`recursion_limit = 40`).** Una investigación normal (buscar y leer 2-3 páginas) son unos 9 pasos del grafo. El límite deja margen, pero evita que una petición se quede en bucle para siempre.

**Sin API, solo en local.** El agente estuvo publicado como API REST (FastAPI) para que un robot de UiPath le reenviara correos. Lo quité porque el texto de un correo lo escribe cualquiera de fuera y podría darle órdenes al agente (*prompt injection*: *"resume el documento X y mándamelo"*), y el agente tiene herramientas que leen documentos del ordenador y escriben en disco. Ahora solo lo usa quien tiene acceso al ordenador, desde el chat. El código de la API está en el historial de git.

### Gmail: decisiones de seguridad

**Las credenciales van por `context`, no por `config`.** Lo comprobé con una prueba: todo lo que va en `config["configurable"]` (donde está el `thread_id`) LangGraph lo **guarda en la base de datos de la memoria** como metadatos del checkpoint. Lo que va en `context` se usa durante la ejecución y no se guarda. Si las credenciales fueran en `config`, el token de cada usuario quedaría escrito en el disco del servidor.

**El LLM nunca ve las credenciales (`InjectedToolArg`).** Si `credenciales` fuera un parámetro normal, el modelo lo vería y tendría que rellenarlo él: podría inventarlo o, con un correo malicioso, intentar filtrarlo. Con `Annotated[Credentials, InjectedToolArg]` el parámetro existe pero no aparece en el esquema que recibe el modelo (comprobado: solo ve `busqueda` y `maximo`).

**Copia de la llamada, sin tocar la original.** `node_herramientas` no hace `llamada["args"]["credenciales"] = ...`, porque `llamada` es el mismo diccionario que está dentro del mensaje del modelo, y ese mensaje se guarda en la memoria y se enseña en la interfaz. En su lugar crea una llamada nueva con `{**llamada, "args": {**llamada["args"], "credenciales": ...}}`.

**Gmail fuera del MCP.** El servidor MCP es un proceso aparte, uno para todos los usuarios, y solo podía leer un `token.json` en disco, que era **mi** cuenta. Para que cada herramienta reciba el token de su usuario por MCP habría que mandarlo como argumento visible para el LLM, o montar un servidor MCP por HTTP con autenticación por petición. Era más complejo y menos seguro, así que las herramientas de Gmail pasaron a `herramientas.py`. Además, si se hubieran quedado en los dos sitios, las del MCP **pisaban** a las nuevas en `funciones` (se añaden después) y todos los usuarios habrían leído mi correo.

**Solo lectura (`gmail.readonly`).** El agente no puede enviar, borrar ni modificar nada, aunque un correo intente engañarlo. Las instrucciones y los docstrings además le dicen que el contenido de los correos son **datos, no órdenes**.

**Permiso de una hora (`access_type="online"`).** La librería pide por defecto `offline`, que da un *refresh token* válido durante meses. Lo cambié a `online`: no hay refresh token, el acceso caduca en una hora y luego hay que volver a conectar. Si alguien robara el token, le serviría muy poco tiempo.

**`state` de un solo uso y PKCE.** Al volver de Google la página se recarga y `st.session_state` empieza vacío, así que el `Flow` creado antes se pierde. El `state` aleatorio de la URL sirve para recuperar su `code_verifier` (PKCE), guardado en el servidor con `st.cache_resource`. Se usa una sola vez y caduca a los 10 minutos. Así nadie puede colar su propio `code` para que acabes conectado a su cuenta (CSRF).

**Tokens solo en memoria.** Las credenciales viven en `st.session_state`, nunca en disco. Al pulsar **Cerrar sesión** se revoca el token en Google (no solo se olvida) y se borra esa conversación de la base de datos (`eliminar_conversacion`: la fila de la lista y sus mensajes), para que no queden correos guardados.

**Limitación de Google: usuarios de prueba.** `gmail.readonly` es un permiso *restringido*. Mientras la app esté "en prueba", solo pueden conectarse hasta **100 cuentas añadidas a mano** en Google Cloud. Para abrirla a cualquiera, Google exige verificar la app y pasar una auditoría de seguridad de pago, que no compensa para un proyecto personal.

### Qué no se sube a git

| Archivo o carpeta | Por qué |
|---|---|
| `.env` | Claves de Composio y direcciones (con contraseña) de la base de datos PostgreSQL, donde están las conversaciones, incluido lo que el agente ha leído de tus correos. |
| `.streamlit/secrets.toml` | Cliente OAuth de Google. |
| `agente/base_datos.py` | Antes tenía la contraseña escrita. Ya la lee del `.env`, así que se puede quitar del `.gitignore`. |
| `datos/user_data_dir/` | Perfil de Chrome con las cookies: con él se entra en tus cuentas sin contraseña. |
| `datos/memoria.db` | La memoria antigua en SQLite (de antes de pasar a Postgres). |
| `datos/documentos/*` | Tus documentos. |
| `.agents/`, `.claude/`, `.codex/`, `skills-lock.json` | Configuración local de herramientas de IA. |
| `credenciales/`, `token.json`, `credentials.json` | Credenciales de Google para pruebas en local. |
| `voz/voces/` | Modelos de voz (pesan mucho). |

## Estructura del proyecto

```
Agente_IA/
├── app.py                   # Interfaz de chat con Streamlit (punto de entrada)
├── README.md
├── requirements.txt
├── .env                     # Claves de Composio y URLs de la base de datos (no se sube a git)
├── .streamlit/
│   ├── config.toml          # Tema de la interfaz (color, bordes, menú)
│   └── secrets.toml         # Cliente OAuth de Google (no se sube a git)
├── estilos/
│   └── interfaz.css         # Estilos que el tema no alcanza (burbujas, caja del chat, bienvenida...)
├── agente/                  # El cerebro
│   ├── agente_grafo.py      # Grafo de LangGraph: nodos, interrupt, memoria, lista de conversaciones
│   ├── instrucciones.py     # Prompt de sistema del agente
│   ├── herramientas.py      # Herramientas @tool del agente (Gmail, navegador y RAG de documentos incluidos)
│   └── base_datos.py        # Conexiones a PostgreSQL (lee las URLs del .env)
├── integraciones/           # Servicios externos
│   ├── auth_gmail.py        # Inicio de sesión con Google: cada usuario conecta su Gmail
│   ├── gmail.py             # Lógica de Gmail: buscar, leer y sacar el texto de los correos
│   └── navegador.py         # Playwright: hilo encargado, leer, listar, clicar, escribir, login manual
├── mcp_local/               # MCP (no se llama "mcp" para no tapar la librería mcp)
│   ├── servidor_mcp.py      # Servidor MCP propio (fecha_hora)
│   └── conexion_mcp.py      # Cliente MCP: servidor propio + Composio
├── voz/
│   ├── oido.py              # Whisper: de voz a texto
│   ├── boca.py              # Piper: de texto a voz
│   ├── conversacion.py      # Prueba por terminal: hablar con el agente
│   └── voces/               # Modelo de voz de Piper (no se sube a git)
├── datos/                   # Lo que usa y genera el agente (no es código)
│   ├── documentos/          # Pon aquí los documentos que quieras que lea
│   ├── informes/            # Aquí se guardan los informes generados
│   ├── memoria.db           # Memoria antigua en SQLite, ya no se usa (no se sube a git)
│   └── user_data_dir/       # Perfil de Chrome con tus sesiones (no se sube a git)
├── credenciales/            # token.json y credentials.json para probar en local (no se sube a git)
└── versiones_anteriores/
    ├── agente.py            # v1: bucle a mano con la librería ollama
    └── agente1.py           # v2: ChatOllama + bind_tools, bucle a mano
```

Todo se ejecuta **desde la carpeta raíz**. Para probar un archivo suelto (su bloque `if __name__ == "__main__"`), se usa `-m` con la ruta de paquete, para que los imports entre carpetas funcionen:

```bash
python -m agente.herramientas            # prueba resumir_documento
python -m integraciones.gmail            # prueba la conexión con tu Gmail
python -m integraciones.navegador        # pruebas del navegador en the-internet.herokuapp.com
python -m mcp_local.conexion_mcp buscar  # pruebas de Composio (también: conexiones, conectar)
python -m voz.conversacion               # hablar con el agente por el micrófono
```

### Evolución

1. **`agente.py`**: primer agente, con la librería `ollama` y el bucle de herramientas escrito a mano.
2. **`agente1.py`**: el mismo agente con LangChain (`ChatOllama` + `bind_tools`), todavía con el bucle a mano.
3. **`agente_grafo.py`**: el bucle pasa a ser un grafo de LangGraph, con memoria persistente.
4. **`api.py`**: el grafo se publicó como API para UiPath, sin memoria y protegido con clave. Después se quitó (ver *Sin API, solo en local*).
5. **`resumir_documento`**: herramienta map-reduce para resumir documentos largos.
6. **`app.py`**: interfaz de chat con Streamlit, con memoria y viendo las herramientas en directo.
7. **MCP**: servidor propio (`servidor_mcp.py`) y cliente (`conexion_mcp.py`) conectados al grafo.
8. **Gmail con una sola cuenta**: `listar_correos` y `leer_correo` en el servidor MCP, con un `token.json` local.
9. **Gmail multiusuario**: login de Google en la app (`auth_gmail.py`), herramientas de Gmail fuera del MCP y credenciales de cada usuario inyectadas en el grafo.
10. **Voz**: oído con Whisper, boca con Piper y micrófono en la app.
11. **Navegador**: Playwright para abrir páginas, listar elementos, clicar y escribir; hilo encargado para que funcione con Streamlit.
12. **Sesiones**: perfil persistente de Chrome e inicio de sesión manual (el agente nunca toca contraseñas).
13. **Composio y LinkedIn**: MCP remoto para leer el perfil; las publicaciones se preparan en el navegador, a la vista, y las publica el usuario.
14. **Nueva interfaz y varias conversaciones**: iconos de Material Symbols, estilos propios y lista de conversaciones en la barra lateral (abrir y borrar). Las instrucciones pasan a `instrucciones.py`.
15. **De SQLite a PostgreSQL**: la memoria pasa a `PostgresSaver` y la lista de conversaciones a una tabla propia.
16. **RAG sobre documentos**: indexar los documentos del usuario en pgvector y `buscar_en_documentos`, citando el archivo.
17. **Aprobación humana**: `interrupt` antes de `clicar`, `escribir` y `COMPOSIO_MULTI_EXECUTE_TOOL`, con tarjeta de Aprobar / Rechazar en la app.

Las versiones anteriores se pueden ejecutar desde la carpeta raíz con:

```bash
python -m versiones_anteriores.agente1
```

## Próximos pasos

- [x] Herramienta `resumir_documento` para documentos largos (map-reduce: resumir por trozos y luego un resumen final)
- [ ] Reduce por niveles para documentos enormes (resumir los resúmenes por grupos hasta que quepan en el contexto)
- [x] Que `leer_documento` use `cargar_texto` en vez de repetir el mismo código
- [x] Que los pinches (`cargar_texto`, `descargar_pagina`) lancen excepciones con `raise` en vez de devolver texto de error
- [x] Límite de pasos (`recursion_limit`) para que el agente no se quede en bucle
- [x] Añadir `resumir_documento` y `leer_documento` a las instrucciones del agente
- [ ] Recortar el historial de la memoria cuando crezca mucho
- [x] Interfaz web con Streamlit
- [x] Servidor MCP propio conectado al agente
- [x] Gmail multiusuario (cada persona conecta su cuenta)
- [x] Voz: hablarle por el micrófono y que conteste hablando
- [x] Navegador con Playwright (leer, listar, clicar, escribir) y sesión persistente con login manual
- [x] Preparar publicaciones de LinkedIn en el navegador sin publicarlas
- [ ] Que el puntero se vea también encima de las ventanas emergentes (`<dialog>` va en la *top layer*) y que se mueva al escribir
- [ ] Avisar al modelo en `listar_elementos` cuando hay una ventana emergente abierta y solo se listan sus elementos
- [x] Aprobación humana (`interrupt`) antes de clicar, escribir o ejecutar algo en Composio
- [x] RAG sobre los documentos del usuario con PostgreSQL + pgvector
- [x] Varias conversaciones guardadas (abrir y borrar desde la barra lateral)
- [x] Añadir `psycopg`, `langchain-postgres` y `langgraph-checkpoint-postgres` a `requirements.txt`
- [x] Leer la dirección de la base de datos del `.env` en vez de escribirla en `base_datos.py`
- [ ] Quitar `agente/base_datos.py` del `.gitignore` y subirlo (ya no tiene secretos)
- [ ] Avisar con un error claro si falta `DATABASE_URL` o `URL_VECTOR` en el `.env`, o si Postgres no está arrancado
- [ ] Bloquear en código (en `node_herramientas` o en `clicar`) lo que hoy solo prohíben las instrucciones: publicar por Composio, clicar en campos de texto (con la aprobación humana ya no pasa sin que lo veas, y en modo grabación ya se bloquea publicar)
- [ ] Pulir `iniciar_sesion_manual` (mensaje cuando ya había sesión, constante para el tiempo de espera)
- [ ] Volver a cargar `fecha_hora` del servidor MCP propio junto a Composio
- [ ] Preparar correos: crear **borradores** en Gmail (el agente nunca envía; el usuario revisa y envía)
- [ ] Enviar correos con **aprobación humana** (el `interrupt` ya está hecho; falta la herramienta de enviar y añadirla a `funciones_a_revisar`)
- [ ] Desplegar en la nube gratis (Streamlit Community Cloud + un LLM por API, porque allí no hay GPU para Ollama)
- [ ] `fecha_hora` con la zona horaria de España, y que "DATOS DE HOY" no se quede congelado al arrancar
- [ ] Quitar `leer_documento` y `guardar_informe` en la versión pública (un correo malicioso no debe poder leer ni escribir archivos)
- [x] Ruta del MCP que funcione en Linux (`conexion_mcp.py` usa `sys.executable`)
- [ ] Tests de las herramientas
