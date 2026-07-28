# pdf-extractext

## Integrantes

- **Tomás Faure  | 10823**
- **José Morata  | 10877**
- **Braian Rojas | 10922**

## Descripción

**pdf-extractext** es una herramienta orientada a la extracción de texto desde documentos PDF utilizando técnicas de procesamiento y automatización.

El objetivo principal del proyecto es facilitar la obtención de información textual desde archivos PDF para su posterior análisis, almacenamiento o procesamiento mediante herramientas de inteligencia artificial.

Este proyecto busca resolver problemas comunes como:

- Extraer texto estructurado desde documentos PDF
- Automatizar el procesamiento de documentos
- Preparar datos para pipelines de análisis o IA
- Integrar extracción de información con bases de datos

---

## Requisitos previos

- **Docker** y **Docker Compose** (Instalados y activos en el sistema).
- mkcert (Necesario para generar los certificados TLS locales que usa Traefik; ver sección Infraestructura: Traefik como Reverse Proxy).
- *Python 3.12* y *uv* (Opcional, únicamente si se desea ejecutar el servidor de forma nativa sin usar contenedores).

---

## Configuración Inicial

Antes de levantar cualquiera de los entornos, es indispensable generar el archivo de configuración de entorno local. En la raíz del proyecto, ejecute:

```bash
cp .env.example .env
```

> 💡 **Nota:** Abra el archivo `.env` recién creado y configure las variables correspondientes. Preste especial atención a `MONGO_URI` y `API_BASE_URL` según el entorno que vaya a iniciar.


| Variable                                      | Usada por            | Descripción |
|---                                            |---                   |---          |
| `MONGO_URI`                                   | Servidor (FastAPI)   | Cadena de conexión a MongoDB. En desarrollo: `mongodb://mongodb:27017` (nombre del servicio en `docker-compose.dev.yml`). En producción: la IP/dominio del clúster real del cliente. |
| `MONGO_DB_NAME`                               | Servidor             | Nombre de la base de datos dentro de MongoDB. |
| `MONGO_ROOT_USERNAME` / `MONGO_ROOT_PASSWORD` | Solo Modo Desarrollo | Credenciales del contenedor de MongoDB local, usadas por `docker-compose.dev.yml` para inicializarlo. No aplican en producción (base externa). |
| `MAX_FILE_SIZE_MB`                            | Servidor             | Tamaño máximo permitido para un PDF subido, en megabytes. Se valida antes de procesar el archivo. |
| `API_BASE_URL`                                | CLI (`fast-pdf`)     | **No la consume el servidor**, solo el cliente de consola. Debe apuntar a donde el servidor sea alcanzable desde donde se ejecute el CLI. |
 
## Infraestructura: Traefik como Reverse Proxy
 
Todo el tráfico hacia la API pasa obligatoriamente por **Traefik** (`traefik:v3.5`), que actúa como *reverse proxy* y punto único de entrada HTTPS. La API **no expone ningún puerto directamente al host** : el contenedor `app` solo es alcanzable dentro de la red interna de Docker, y es Traefik quien recibe el tráfico externo por el puerto `443` y lo redirige internamente hacia el contenedor correspondiente según el `Host` de la petición.
 
Esto significa que **Traefik debe estar corriendo antes que la aplicación**, ya que además de enrutar tráfico, es quien crea la red Docker externa (`fast_pdf_network`) que luego consumen `docker-compose.yml` y `docker-compose.dev.yml`.
 
### Componentes de la infraestructura (`.infra/`)
 
| Archivo                           | Rol     |
|---                                |---      |
| `.infra/docker-compose.infra.yml` | Levanta el contenedor de Traefik. Publica los puertos `443` (entrada HTTPS), `6379` y `27017` en el host, monta el socket de Docker (para el *service discovery* automático), la configuración estática/dinámica y los certificados. Crea la red `fast_pdf_network`, que **no es externa acá**: este stack es el dueño de la red. |
| `.infra/config/traefik.yml`       | Configuración **estática** de Traefik. Define: el *provider* de Docker (`exposedByDefault: false`, por eso cada servicio necesita la label `traefik.enable=true` explícita para ser enrutado), el *provider* de archivo (lee `config.yml` para reglas dinámicas), el dashboard (`api.dashboard: true`) y los `entryPoints` `https` (`:443`) y `redis` (`:6379`, reservado para un futuro servicio de Redis — hoy no hay ningún contenedor escuchando ahí). |
| `.infra/config/config.yml`        | Configuración **dinámica** de Traefik. Declara el router del dashboard (`Host(api.pdfmanager.local)` + `PathPrefix(/api` o `/dashboard)`) y la ruta a los certificados TLS (`/etc/certs/pdfmanager.pem` y `pdfmanager-key.pem`, montados como volumen de solo lectura desde `.infra/certs/`). |
| `.infra/certs/`                   | Carpeta donde se guardan los certificados TLS locales generados con `mkcert`. Está vacía por defecto (solo tiene un `.gitkeep`) porque los certificados **no se versionan** — cada máquina de desarrollo genera los suyos. |
 
El propio servicio `app` (en `docker-compose.yml`) se integra a Traefik solo mediante labels, sin exponer puertos:
 
```yaml
labels:
    - "traefik.enable=true"
    - "traefik.http.routers.pdf-app.rule=Host(`api.pdfmanager.local`)"
    - "traefik.http.routers.pdf-app.entrypoints=https"
    - "traefik.http.routers.pdf-app.tls=true"
    - "traefik.http.services.pdf-app.loadbalancer.server.port=8000"
```
 
Traefik descubre este contenedor automáticamente (vía el socket de Docker montado), ve que tiene `traefik.enable=true`, y lo enruta cuando la petición llega con `Host: api.pdfmanager.local`, terminando TLS y reenviando en texto plano al puerto interno `8000` del contenedor (el mismo que declara `EXPOSE 8000` en el `Dockerfile`).
 
### 1. Generar los certificados TLS locales
 
Traefik necesita un certificado válido para `api.pdfmanager.local` (y su dominio comodín). Se genera con `mkcert`, que crea una autoridad certificadora local de confianza para el sistema:
 
```bash
cd .infra/certs
mkcert "pdfmanager.local" "*.pdfmanager.local"
mv pdfmanager.local+1.pem pdfmanager.pem
mv pdfmanager.local+1-key.pem pdfmanager-key.pem
```
 
> ⚠️ **Importante:** cada computadora del equipo debe generar **sus propios certificados** — no se comparten ni se suben al repositorio (por eso están en `.gitignore`). Si es la primera vez que usás `mkcert` en la máquina, corré `mkcert -install` antes para registrar la autoridad certificadora local y evitar advertencias de "certificado no confiable" en el navegador.
 
### 2. Resolver el dominio local
 
`api.pdfmanager.local` no es un dominio real, así que el sistema operativo necesita saber que apunta a `localhost`. Agregá esta línea al archivo de hosts:
 
- **Linux / macOS:** `/etc/hosts`
- **Windows:** `C:\Windows\System32\drivers\etc\hosts`
```
127.0.0.1   api.pdfmanager.local   pdfmanager.local
```
 
### 3. Levantar Traefik
 
Con los certificados generados y el dominio resuelto, se levanta el proxy **antes** de la aplicación:
 
```bash
docker compose -f .infra/docker-compose.infra.yml up -d
```
 
Este comando crea la red externa `fast_pdf_network` que los `docker-compose.yml` de la app esperan encontrar. Si se intenta levantar la app antes que Traefik, Docker Compose falla porque esa red externa todavía no existe (ver [Troubleshooting](#troubleshooting)).
 
Para bajar el proxy:
 
```bash
docker compose -f .infra/docker-compose.infra.yml down
```
 
> ⚠️ Si Traefik se baja mientras la app sigue corriendo, la red `fast_pdf_network` puede quedar en uso y no eliminarse hasta que también se bajen los contenedores que dependen de ella.
 
### URL final de acceso
 
Una vez con Traefik arriba y la aplicación corriendo (ver [Modos de Ejecución](#modos-de-ejecución-del-proyecto)), el acceso es **el mismo en ambos modos** (desarrollo y producción), porque quien enruta el tráfico siempre es Traefik y el `Host` configurado es el mismo:
 
| Recurso                         | URL                                       |
|---                              |---                                        |
| API (endpoints `/api/pdfs/...`) | `https://api.pdfmanager.local/api/pdfs`   |
| Dashboard de Traefik            | `https://api.pdfmanager.local/dashboard/` |
 
> 💡 La barra final en `/dashboard/` es necesaria: Traefik redirige `/dashboard` sin barra, pero algunos clientes HTTP no siguen la redirección automáticamente.
 
Como el certificado es generado localmente por `mkcert`, el navegador o `curl` deben confiar en él. Si corriste `mkcert -install`, el navegador lo reconoce automáticamente. Con `curl` sin haber instalado la CA local, se puede probar igual ignorando la validación (solo para pruebas locales):
 
```bash
curl -k https://api.pdfmanager.local/api/pdfs
```


## Modos de Ejecución del Proyecto

El despliegue de la aplicación está diseñado bajo un principio de desacoplamiento de infraestructura. Cuenta con dos flujos independientes según el caso de uso:

> ⚠️ **Prerrequisito para ambas opciones:** Traefik debe estar corriendo primero (ver [Infraestructura: Traefik como Reverse Proxy](#infraestructura-traefik-como-reverse-proxy)), porque `docker-compose.yml` declara `fast_pdf_network` como red **externa** — es decir, espera que ya exista, no la crea.

### Opción A: Modo Desarrollo (Ecosistema Completo Local)

*Ideal para el equipo de desarrollo, pruebas locales o evaluación académica.*

Este comando levanta tanto la API de FastAPI como un contenedor local y aislado de **MongoDB 7**, configurando un volumen de persistencia automático y un sistema de control de arranque (*healthcheck*) para asegurar que la API no inicie hasta que la base de datos esté lista:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Opción B: Modo Producción / Entrega al Cliente (Solo la API)

*Ideal para el despliegue final en la infraestructura del cliente.*

Si el cliente ya cuenta con su propio clúster de base de datos administrado (local o en la nube), no requiere contenedores de bases de datos redundantes. Asegúrese de colocar la dirección de su base de datos externa en la variable `MONGO_URI` del `.env` y ejecute:

```bash
docker compose up -d --build
```

Esto compilará y empaquetará el código fuente de forma estática bajo la imagen inmutable `parse-documents-fast:1.0.0` y levantará **únicamente el servicio de la API** corriendo de forma segura bajo un usuario sin privilegios (`appuser`).

### Gestión y Control de Servicios

Para administrar el ciclo de vida de los contenedores según el modo en el que los haya iniciado, utilice los siguientes comandos:

#### 1. Detener los servicios

Detiene la ejecución del servidor sin eliminar los contenedores de la memoria del sistema:

```bash

docker compose stop
```

#### 2. Apagar y limpiar el entorno

Remueve los contenedores de la memoria RAM del sistema de forma segura (los datos de la base de datos no se perderán gracias a los volúmenes):

```bash

# Si los levantó en Modo Producción:
docker compose down

# Si los levantó en Modo Desarrollo:
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

#### 3. Ver registros (Logs) en tiempo real

Si necesita monitorear las peticiones HTTP entrantes o depurar errores internos de la API FastAPI:

```bash
docker compose logs -f app
```

#### 4. Limpieza total de base de datos (Solo Desarrollo)

Si durante la etapa de pruebas requiere eliminar por completo la base de datos local y los volúmenes de almacenamiento para iniciar un entorno limpio desde cero:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
```

#### 5. Detener o reiniciar Traefik
 
Traefik se gestiona con su propio archivo compose, independiente del de la app:
 
```bash
# Ver logs del proxy (útil para depurar routing o certificados)
docker compose -f .infra/docker-compose.infra.yml logs -f reverse-proxy
 
# Bajar el proxy
docker compose -f .infra/docker-compose.infra.yml down
```

---

## Troubleshooting
 
Problemas comunes al levantar el stack completo (Traefik + app) y cómo diagnosticarlos.
 
### 1. El contenedor `app` no aparece en el dashboard de Traefik
 
Entrá a `https://api.pdfmanager.local/dashboard/` → sección **HTTP Routers**. Si `pdf-app` no aparece:
 
- Confirmá que el contenedor está corriendo: `docker compose ps` (debería figurar como `Up`, no `Exited`).
- Confirmá que tiene la label `traefik.enable=true` — Traefik la requiere explícitamente porque `exposedByDefault: false` en `.infra/config/traefik.yml`. Sin esa label, el contenedor es invisible para Traefik aunque esté corriendo.
- Confirmá que `app` y `reverse-proxy` (Traefik) están conectados a la **misma red** `fast_pdf_network`: `docker network inspect fast_pdf_network` debería listar ambos contenedores.
### 2. Error `network fast_pdf_network declared as external, but could not be found`
 
Significa que se intentó levantar `docker-compose.yml` (o el overlay de dev) **antes** que Traefik. La red la crea `.infra/docker-compose.infra.yml`, no la app. Solución: levantar Traefik primero (ver [Infraestructura: Traefik como Reverse Proxy](#infraestructura-traefik-como-reverse-proxy)).
 
### 3. El navegador muestra "certificado no válido" o "conexión no privada"
 
El certificado lo emite una autoridad certificadora local (`mkcert`), no una CA pública. Si el navegador no la conoce:
 
- Corré `mkcert -install` en la máquina (registra la CA local en el sistema y en los navegadores compatibles) y reiniciá el navegador.
- Para pruebas rápidas por terminal sin instalar la CA, usá `curl -k` (omite la verificación del certificado).
### 4. `404 page not found` al entrar a `https://api.pdfmanager.local/...`
 
- Verificá que el archivo de hosts tenga la entrada `127.0.0.1 api.pdfmanager.local pdfmanager.local` (sin esto, el navegador ni siquiera llega a Traefik).
- Verificá que la ruta pedida coincide con el `rule=Host(...)` de las labels en `docker-compose.yml` — cualquier otro `Host` no matchea el router y Traefik responde 404 por defecto.
### 5. El CLI (`fast-pdf`) da `Error: No se pudo conectar con la API`
 
Desde la Issue #84 el puerto 8000 ya no está publicado en el host. Ver el aviso completo en [Uso de la herramienta](#uso-de-de-la-herramienta): o se corre el CLI dentro del contenedor (`docker compose exec app fast-pdf ...`), o se apunta `API_BASE_URL` a `https://api.pdfmanager.local` a través de Traefik.
 
### 6. MongoDB no conecta en Modo Desarrollo
 
`docker-compose.dev.yml` define un *healthcheck* para Mongo — la API espera a que el healthcheck pase antes de iniciar. Si tarda mucho o falla:
 
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f mongodb
```
 
Y confirmá que `MONGO_URI=mongodb://mongodb:27017` en `.env` (el nombre de host `mongodb` es el nombre del servicio dentro de la red de Docker; `localhost` no funciona desde dentro del contenedor `app`).
 
---

## Uso de de la herramienta

Una vez levantado docker y sincronizado uv se puede usar directamente con: `fast-pdf <comando>` en caso
de que falle, se puede usar `uv run fast-pdf <comando>` para minimizar errores. Se puede usar `fast-pdf -h` para ayuda.

> ⚠️ **Sobre `API_BASE_URL` y el puerto 8000:** el CLI (`dev/client/cli.py`) es un cliente HTTP delgado que le pega a `API_BASE_URL` (variable definida en `.env` / `dev/config.py`). El valor de ejemplo en `.env.example` es `http://localhost:8000`, pero desde la Issue #84 el contenedor `app` **ya no publica ese puerto sobre el host** — solo es alcanzable dentro de la red Docker o a través de Traefik. Esto significa que correr `fast-pdf` directamente desde la terminal del host, contra ese valor por defecto, va a fallar con un error de conexión. Hay dos formas de usarlo correctamente:
>
> 1. **Ejecutar el CLI dentro del contenedor** (recomendado, no requiere tocar `.env`):
>    ```bash
>    docker compose exec app fast-pdf list
>    ```
>    Desde adentro del contenedor, `localhost:8000` sí es válido porque es el propio proceso de `uvicorn`.
> 2. **Apuntar el CLI a Traefik** cambiando `API_BASE_URL=https://api.pdfmanager.local` en `.env` y corriendo el CLI desde el host. Como el certificado es local (`mkcert`), puede requerir confiar en la CA local (`mkcert -install`) para que `httpx` no rechace la conexión por TLS no verificado.

### Comandos

```bash
Comandos:

  # Sube un archivo PDF al servidor.
  upload <direccion_archivo>

  # Lista todos los documentos PDF persistidos.
  list

  # Muestra el texto extraído de un PDF por consola.
  get <id_pdf>

  # Elimina un documento PDF del servidor. 
  delete <id_pdf>

  # Descarga el texto extraído de un PDF como archivo .txt
  download <id_pdf>

Flags:

  -h --help
  
  # Usando en download permite renombrar el archivo de salida.
  --output <nombre_archivo.txt> 

```

---

## Endpoints de la API
 
El CLI es un cliente HTTP delgado: por debajo, cada comando llama a uno de estos endpoints REST expuestos por `dev/servers/views/pdf_router.py`, bajo el prefijo `/api/pdfs`. Se pueden consumir directamente (por ejemplo con `curl` o desde otro sistema) sin pasar por el CLI:
 
| Método | Ruta | Descripción | Códigos de respuesta |
|---|---|---|---|
| `POST` | `/api/pdfs` | Sube un PDF (`multipart/form-data`: `file`, `title`, `description`). Valida formato y tamaño, calcula el checksum SHA-256, extrae el texto y lo persiste. | `200` creado · `400` archivo inválido · `409` duplicado (mismo checksum ya existente) |
| `GET` | `/api/pdfs` | Lista todos los PDFs registrados, ordenados por fecha de creación descendente. | `200` |
| `GET` | `/api/pdfs/{id}` | Devuelve los metadatos de un PDF puntual. | `200` · `404` no existe |
| `DELETE` | `/api/pdfs/{id}` | Elimina el registro de un PDF de la base de datos. | `204` · `404` no existe |
| `GET` | `/api/pdfs/{id}/text` | Devuelve el texto extraído como JSON (`{"pdf_id": ..., "text": ...}`). | `200` · `404` no existe |
| `GET` | `/api/pdfs/{id}/download` | Descarga el texto extraído como archivo `.txt` (header `Content-Disposition: attachment`). | `200` · `404` no existe |
 
Ejemplo directo con `curl` (a través de Traefik, con certificado local confiado):
 
```bash
curl -X POST https://api.pdfmanager.local/api/pdfs \
  -F "file=@mi_archivo.pdf" \
  -F "title=Mi Documento"
```
 
> 💡 El campo `id` de la respuesta es un `ObjectId` de MongoDB, generado automáticamente por Beanie/Motor al persistir el documento.
 
---

## Arquitectura

El proyecto sigue una arquitectura basada en **3 capas**, lo que permite separar responsabilidades y facilitar el mantenimiento.

### 1. Capa de Presentación

Encargada de la interacción con el usuario o sistema externo.

Responsabilidades:

- Recibir archivos PDF
- Iniciar el proceso de extracción
- Mostrar resultados o exportarlos

En el código, esta capa está implementada por dos puntos de entrada que consumen la misma API:
 
- `dev/servers/views/pdf_router.py`: router de FastAPI, define los endpoints HTTP (ver [Endpoints de la API](#endpoints-de-la-api)) y traduce entre el mundo HTTP (`UploadFile`, `HTTPException`) y las funciones de la capa de negocio.
- `dev/client/cli.py`: cliente de consola (`fast-pdf`). No contiene lógica propia — arma requests HTTP con `httpx` contra los mismos endpoints y formatea la respuesta para la terminal.
- `dev/main.py`: entry point del paquete (`fast-pdf` como comando instalado vía `pyproject.toml → [project.scripts]`), delega directamente en `cli.py`.

---

### 2. Capa de Lógica de Negocio

Contiene la lógica principal del sistema.

Responsabilidades:

- Procesamiento del PDF
- Extracción de texto
- Integración con herramientas de IA
- Transformación y limpieza de datos

En el código, esta capa vive en `dev/servers/controllers/` (orquestación) y `dev/servers/services/` (lógica pura). Los detalles de procesamiento que aplica, en orden, cuando se sube un PDF (`POST /api/pdfs`):
 
1. **Validación de formato real (`pdf_validator.py`):** no confía en la extensión del nombre del archivo. Verifica que el contenido comience con los *magic bytes* `%PDF-`, que es el encabezado real de cualquier PDF válido. También valida que el tamaño no supere `MAX_FILE_SIZE_MB` (configurable por variable de entorno).
2. **Cálculo de checksum SHA-256:** se hashea el contenido binario completo. Este hash funciona como huella digital del archivo — dos archivos con el mismo hash tienen exactamente el mismo contenido, sin importar el nombre. Se usa para bloquear duplicados: si ya existe un documento con ese checksum, la API responde `409 Conflict` antes de gastar tiempo procesando el PDF de nuevo.
3. **Extracción de texto en memoria (`pdf_extractor.py`):** usa `pypdf` para leer el contenido página por página, con `extraction_mode="layout"` (preserva mejor la disposición espacial del texto original que el modo por defecto). El PDF **nunca se escribe a disco**: se procesa directamente desde los bytes recibidos, envueltos en un `io.BytesIO`.
4. **Persistencia del resultado:** solo se guarda en MongoDB el texto ya extraído junto a los metadatos (título, descripción, tamaño, checksum). Como no se conserva el archivo original en ningún punto, tampoco hay nada que borrar del disco al eliminar un documento — `delete_pdf` solo elimina el registro de la base.

---

### 3. Capa de Datos

Encargada del almacenamiento y persistencia.

Responsabilidades:

- Guardar texto extraído
- Conectar con bases de datos
- Manejo de almacenamiento estructurado

En este proyecto se utiliza **MongoDB** como sistema de almacenamiento, accedido de forma asíncrona vía `motor` y modelado con el ODM `beanie`.
 
El documento `Pdf` (`dev/models/pdf_document.py`), colección `pdfs`, tiene estos campos:
 
| Campo            | Tipo                            | Descripción                                                       |
|---               |---                              |---                                                                |
| `title`          | `str`                           | Título del documento (por defecto, el nombre del archivo subido). |
| `description`    | `str \| None`                   | Descripción opcional.                                             |
| `size`           | `int`                           | Tamaño del archivo en bytes.                                      |
| `created_at`     | `datetime`                      | Fecha de creación, asignada automáticamente al insertar.          |
| `extracted_text` | `str \| None`                   | Texto ya extraído del PDF en el momento del upload.               |
| `checksum`       | `str \| None` (indexado, único) | SHA-256 del contenido binario. El índice único es lo que le permite a MongoDB rechazar duplicados a nivel de base, además de la verificación explícita que hace el controlador antes de insertar. |
 
La conexión se inicializa en `dev/models/database.py` (`get_client`, usando `MONGO_URI`) y se registra en el ciclo de vida de la aplicación FastAPI (`dev/servers/app.py`, función `lifespan`): el cliente de Mongo se abre al arrancar el servidor y se cierra prolijamente al apagarlo.
 

---

## Estructura del Proyecto

A continuación se describe la estructura principal del repositorio:

| Carpeta / Archivo            | Descripción                              |
|-------------------           |------------------------------------------|
| `dev/main.py`                | Entry point del comando `fast-pdf`, delega en el CLI. |
| `dev/config.py`              | `Settings` (pydantic-settings): centraliza toda la configuración por variables de entorno. |
| `dev/client/cli.py`          | Cliente de consola (`fast-pdf`), capa de presentación por terminal. |
| `dev/models/database.py`     | Conexión a MongoDB (`motor`). |
| `dev/models/pdf_document.py` | Modelo `Pdf` (`beanie`), esquema del documento persistido. |
| `dev/servers/app.py`         | Instancia y arranque de la aplicación FastAPI, ciclo de vida (conexión/desconexión de Mongo). |
| `dev/servers/views/`         | Routers de FastAPI — capa de presentación HTTP. |
| `dev/servers/controllers/`   | Orquestación de la lógica de negocio (CRUD de PDFs). |
| `dev/servers/services/`      | Lógica pura: extracción de texto (`pdf_extractor.py`) y validación (`pdf_validator.py`). |
| `test/`                      | Pruebas automatizadas (`pytest`), un archivo por módulo del sistema. |
| `test/fixtures/`             | Archivos de prueba (PDFs de muestra) usados por los tests. |
| `docs/`                      | Diagramas UML (`.puml` fuente y `.svg` renderizado). |
| `.infra/`                    | Infraestructura de Traefik: proxy reverso, TLS y routing (ver [Infraestructura: Traefik como Reverse Proxy](#infraestructura-traefik-como-reverse-proxy)). |
| `Dockerfile`                 | Build de la imagen de la API: instala dependencias con `uv`, corre como usuario no-root (`appuser`), expone el puerto interno `8000`. |
| `docker-compose.yml`         | Stack de producción: solo el servicio `app`, conectado a Traefik vía labels, sin puertos publicados al host. |
| `docker-compose.dev.yml`     | Overlay de desarrollo: agrega el contenedor de MongoDB local con *healthcheck*, para usarse junto con `docker-compose.yml`. |
| `.env.example`               | Plantilla de variables de entorno; se copia a `.env` antes de levantar cualquier entorno. |
| `pyproject.toml`             | Dependencias, metadata del paquete y definición del comando `fast-pdf` (`[project.scripts]`). |
| `uv.lock`                    | Lockfile de dependencias exactas, usado por `uv sync --frozen` en el `Dockerfile`. |
| `.python-version`            | Versión de Python fijada para `uv` (3.12). |
| `README.md`                  | Documentación principal del repositorio. |
| `.gitignore`                 | Archivos ignorados por Git (incluye certificados TLS locales, entornos virtuales, cachés, etc.). |

Esta organización permite mantener una separación clara entre código, pruebas y documentación.

---

## Diagramas UML

### Infograma

![Infograma del sistema](docs/infograma.svg)

> Una vista general del sistema en lenguaje no técnico: qué hace,
> cómo fluye la información y desde dónde se puede usar.

### Diagrama de Clases

![Diagrama de clases](docs/diagrama_clases.svg)

> Un diagrama de clases en Lenguaje Unificado de Modelado (UML) es un tipo de diagrama de estructura estática que describe la estructura de un sistema mostrando las clases del sistema, sus atributos, operaciones (o métodos), y las relaciones entre los objetos.

### Diagrama de Secuencia

![Diagrama de secuencia](docs/diagrama_secuencia.svg)

>Un diagrama de secuencia muestra cómo interactúan los componentes de un sistema en orden cronológico, representando el flujo de mensajes entre participantes para ilustrar un proceso específico.

---

## Tecnologías Utilizadas

El proyecto utiliza diversas tecnologías para el procesamiento y análisis de documentos:

- **Python**
  Lenguaje principal de desarrollo.
- **UV**
  Herramienta moderna para la gestión de dependencias y entornos Python.
- **Inteligencia Artificial (IA)**
  Utilizada para análisis avanzado del contenido extraído.
- **OpenCode**
  Herramienta utilizada dentro del flujo de desarrollo.
- **MongoDB**
  Base de datos NoSQL utilizada para almacenar la información extraída.
- **pypdf**
  Librería usada para leer y extraer el texto de los archivos PDF.
- **httpx**
  Cliente HTTP usado por el CLI (`fast-pdf`) para comunicarse con la API.
- **Docker / Docker Compose**
  Empaquetado y orquestación de los servicios (API, MongoDB en desarrollo, Traefik).
- **Traefik**
  Reverse proxy que centraliza el acceso HTTPS a la API y expone su dashboard de monitoreo de routers (ver [Infraestructura: Traefik como Reverse Proxy](#infraestructura-traefik-como-reverse-proxy)).
- **mkcert**
  Generación de certificados TLS locales de confianza para el dominio de desarrollo.
- **Inteligencia Artificial (IA)**
  Utilizada para análisis avanzado del contenido extraído.
- **OpenCode**
  Herramienta utilizada dentro del flujo de desarrollo.

---

## Metodologías y Principios Aplicados

El proyecto sigue varias metodologías y principios de ingeniería de software para mejorar la calidad del código.

### TDD (Test Driven Development)

El desarrollo se basa en la creación de pruebas antes de implementar la funcionalidad. Esto permite:

- mejorar la calidad del código
- detectar errores temprano
- facilitar refactorizaciones

La suite de tests vive en `test/` (uno por módulo: API, CLI, config, modelos, extractor) y se corre con:
 
```bash
uv run pytest
```

---

### 12-Factor App

Se aplican principios del modelo **12 Factor App**, orientados a construir aplicaciones escalables y mantenibles.

Algunos principios aplicados incluyen:

- configuración mediante variables de entorno
- separación entre código y configuración
- procesos stateless

---

### Principios de Desarrollo

El proyecto también sigue principios clásicos de diseño de software:

**KISS (Keep It Simple, Stupid)**
Mantener el código simple y fácil de entender.

**DRY (Don't Repeat Yourself)**
Evitar duplicación de lógica en el código.

**YAGNI (You Aren't Gonna Need It)**
Implementar solo lo necesario.

**SOLID**
Conjunto de principios para diseño orientado a objetos que mejora la mantenibilidad del software.

---

## Objetivo del Proyecto

El objetivo es construir una herramienta robusta y extensible para el procesamiento automático de documentos PDF dentro de pipelines de datos y sistemas de inteligencia artificial.
