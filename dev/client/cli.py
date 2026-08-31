"""
CLI entry-point para fast-pdf.

El CLI actúa como cliente HTTP delgado de la API FastAPI.
Toda la lógica de negocio (validación, extracción, checksum, persistencia)
vive en el servidor — el CLI solo serializa argumentos y muestra respuestas.

Uso:
    fast-pdf upload archivo.pdf
    fast-pdf upload archivo.pdf --info
    fast-pdf list
    fast-pdf get <id>
    fast-pdf delete <id>
"""

import argparse
import sys
from pathlib import Path

import httpx

from dev.client.ssl_trust import resolve_ssl_verify
from dev.config import settings

# Endpoint base de la API. Se construye una sola vez y se reutiliza en todos
# los comandos para evitar repetir la URL en cada función.
_API_PDFS = f"{settings.API_BASE_URL}/api/pdfs"

# Verificación TLS: resuelve el CA local de mkcert (o el explícito de
# SSL_CERT_FILE) una sola vez, para no exportar nada a mano en cada entorno.
_VERIFY = resolve_ssl_verify(settings.SSL_CERT_FILE)


# ---------------------------------------------------------------------------
# Handlers de cada subcomando
# ---------------------------------------------------------------------------

def _cmd_upload(args: argparse.Namespace) -> int:
    """Sube un archivo PDF a la API.

    Delega en el servidor toda la lógica: validación de formato, magic bytes,
    tamaño, detección de duplicados por checksum y extracción de texto.

    Args:
        args: Namespace con 'pdf_file' (Path) y 'info' (bool).

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    pdf_path: Path = args.pdf_file

    if not pdf_path.exists():
        print(f"Error: El archivo '{pdf_path}' no existe.", file=sys.stderr)
        return 1

    try:
        with pdf_path.open("rb") as f:
            response = httpx.post(
                _API_PDFS,
                files={"file": (pdf_path.name, f, "application/pdf")},
                data={"title": pdf_path.stem},
                verify=_VERIFY,
            )

        # 409 Conflict: el servidor detectó un duplicado por checksum
        if response.status_code == 409:
            detail = response.json().get("detail", {})
            existing_id = detail.get("existing_id", "desconocido")
            print(
                f"Duplicado detectado: este PDF ya fue subido anteriormente.\n"
                f"ID del documento existente: {existing_id}"
            )
            return 1

        # 400 Bad Request: validación fallida (magic bytes, tamaño, etc.)
        if response.status_code == 400:
            detail = response.json().get("detail", response.text)
            print(f"Error de validación: {detail}", file=sys.stderr)
            return 1

        response.raise_for_status()
        data = response.json()

        print(f"PDF subido exitosamente.")
        print(f"  ID:    {data['id']}")
        print(f"  Título: {data['title']}")

        # --info muestra además tamaño y fecha
        if args.info:
            print(f"  Tamaño: {data['size']} bytes")
            print(f"  Fecha:  {data['created_at']}")

        return 0

    except httpx.ConnectError:
        print(
            f"Error: No se pudo conectar con la API en '{settings.API_BASE_URL}'.\n"
            f"Verificá que el servidor esté corriendo.",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPStatusError as e:
        print(f"Error del servidor: {e.response.status_code}", file=sys.stderr)
        return 1


def _cmd_list(_args: argparse.Namespace) -> int:
    """Lista todos los PDFs persistidos en el servidor.

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    try:
        response = httpx.get(_API_PDFS, verify=_VERIFY)
        response.raise_for_status()
        pdfs = response.json()

        if not pdfs:
            print("No hay documentos registrados.")
            return 0

        print(f"{'ID':<26} {'Título':<30} {'Tamaño':>10}  {'Fecha'}")
        print("-" * 80)
        for pdf in pdfs:
            print(
                f"{pdf['id']:<26} "
                f"{pdf['title'][:28]:<30} "
                f"{pdf['size']:>10} bytes  "
                f"{pdf['created_at'][:19]}"
            )
        return 0

    except httpx.ConnectError:
        print(
            f"Error: No se pudo conectar con la API en '{settings.API_BASE_URL}'.",
            file=sys.stderr,
        )
        return 1


def _cmd_get(args: argparse.Namespace) -> int:
    """Muestra el texto extraído de un PDF por su ID.

    Args:
        args: Namespace con 'pdf_id' (str).

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    try:
        response = httpx.get(f"{_API_PDFS}/{args.pdf_id}/text", verify=_VERIFY)

        if response.status_code == 404:
            print(f"Error: No existe un PDF con ID '{args.pdf_id}'.", file=sys.stderr)
            return 1

        response.raise_for_status()
        data = response.json()
        text = data.get("text", "")

        if not text:
            print("El documento no contiene texto extraíble.")
        else:
            print(text)

        return 0

    except httpx.ConnectError:
        print(
            f"Error: No se pudo conectar con la API en '{settings.API_BASE_URL}'.",
            file=sys.stderr,
        )
        return 1


def _cmd_delete(args: argparse.Namespace) -> int:
    """Elimina un PDF por su ID.

    Args:
        args: Namespace con 'pdf_id' (str).

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    try:
        response = httpx.delete(f"{_API_PDFS}/{args.pdf_id}", verify=_VERIFY)

        if response.status_code == 404:
            print(f"Error: No existe un PDF con ID '{args.pdf_id}'.", file=sys.stderr)
            return 1

        response.raise_for_status()
        print(f"Documento '{args.pdf_id}' eliminado correctamente.")
        return 0

    except httpx.ConnectError:
        print(
            f"Error: No se pudo conectar con la API en '{settings.API_BASE_URL}'.",
            file=sys.stderr,
        )
        return 1


def _cmd_download(args: argparse.Namespace) -> int:
    """Descarga el texto extraído de un PDF y lo guarda en disco.

    Args:
        args: Namespace con 'pdf_id' (str) y 'output' (Path | None).

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    try:
        response = httpx.get(f"{_API_PDFS}/{args.pdf_id}/download", verify=_VERIFY)

        if response.status_code == 404:
            print(f"Error: No existe un PDF con ID '{args.pdf_id}'.", file=sys.stderr)
            return 1

        response.raise_for_status()

        # Determinar nombre del archivo de salida
        if args.output:
            output_path = args.output
        else:
            # Extraer nombre del header Content-Disposition
            disposition = response.headers.get("content-disposition", "")
            filename = "documento.txt"
            if 'filename="' in disposition:
                filename = disposition.split('filename="')[1].rstrip('"')
            output_path = Path(filename)

        output_path.write_text(response.text, encoding="utf-8")
        print(f"Texto guardado en: {output_path}")
        return 0

    except httpx.ConnectError:
        print(
            f"Error: No se pudo conectar con la API en '{settings.API_BASE_URL}'.",
            file=sys.stderr,
        )
        return 1

# ---------------------------------------------------------------------------
# Parseo de argumentos
# ---------------------------------------------------------------------------

def _parse_arguments() -> argparse.Namespace:
    """Configura el parser principal con sus subcomandos.

    Cada subcomando corresponde a un endpoint de la API:
        upload  → POST   /api/pdfs
        list    → GET    /api/pdfs
        get     → GET    /api/pdfs/{id}/text
        delete  → DELETE /api/pdfs/{id}

    Returns:
        Namespace con el subcomando seleccionado y sus argumentos.
    """
    parser = argparse.ArgumentParser(
        prog="fast-pdf",
        description="Cliente CLI para el gestor de documentos PDF",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="comando")
    subparsers.required = True  # Sin subcomando → mostrar ayuda con error

    # --- upload ---
    upload_parser = subparsers.add_parser(
        "upload",
        help="Sube un archivo PDF al servidor",
    )
    upload_parser.add_argument(
        "pdf_file",
        type=Path,
        help="Ruta al archivo PDF a subir",
    )
    upload_parser.add_argument(
        "--info",
        action="store_true",
        help="Muestra tamaño y fecha además del ID",
    )

    # --- list ---
    subparsers.add_parser(
        "list",
        help="Lista todos los documentos PDF persistidos",
    )

    # --- get ---
    get_parser = subparsers.add_parser(
        "get",
        help="Muestra el texto extraído de un PDF",
    )
    get_parser.add_argument(
        "pdf_id",
        type=str,
        help="ID del documento",
    )

    # --- delete ---
    delete_parser = subparsers.add_parser(
        "delete",
        help="Elimina un documento PDF",
    )
    delete_parser.add_argument(
        "pdf_id",
        type=str,
        help="ID del documento a eliminar",
    )
    
    # --- download ---
    download_parser = subparsers.add_parser(
        "download",
        help="Descarga el texto extraído de un PDF como archivo .txt",
    )
    download_parser.add_argument(
        "pdf_id",
        type=str,
        help="ID del documento",
    )
    download_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Nombre del archivo de salida (default: título del documento)",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Mapa subcomando → handler. Desacopla el dispatch del parseo: agregar un
# nuevo subcomando solo requiere definir su handler y registrarlo aquí.
_COMMANDS = {
    "upload": _cmd_upload,
    "list": _cmd_list,
    "get": _cmd_get,
    "delete": _cmd_delete,
    "download": _cmd_download,
}


def main() -> int:
    """Entry point del CLI."""
    args = _parse_arguments()
    handler = _COMMANDS[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())