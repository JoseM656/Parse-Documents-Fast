"""Resolución del CA local (mkcert) para que el CLI confíe en el certificado HTTPS.

El CLI usa httpx contra `https://api.pdfmanager.local`, cuyo certificado lo
emite el rootCA de mkcert de la máquina. Como mkcert no está instalado como CA
de sistema, Python no confía en él por defecto. Este módulo resuelve la ruta de
ese rootCA para pasarla como `verify=` a httpx, sin obligar a exportar
`SSL_CERT_FILE` manualmente en cada entorno.
"""

import shutil
import subprocess
from pathlib import Path


def _mkcert_root_ca() -> str | None:
    """Devuelve la ruta a `rootCA.pem` de mkcert, o None si no está disponible."""
    mkcert = shutil.which("mkcert")
    if mkcert is None:
        return None

    try:
        caroot = subprocess.run(
            [mkcert, "-CAROOT"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None

    root_ca = Path(caroot) / "rootCA.pem"
    return str(root_ca) if root_ca.is_file() else None


def resolve_ssl_verify(ssl_cert_file: str | None) -> str | bool:
    """Resuelve el argumento `verify` para httpx.

    Prioridad:
        1. `ssl_cert_file` explícito (si el archivo existe).
        2. rootCA.pem auto-detectado con `mkcert -CAROOT`.
        3. `True` (verificación por defecto del sistema) como fallback.
    """
    if ssl_cert_file and Path(ssl_cert_file).is_file():
        return ssl_cert_file

    auto = _mkcert_root_ca()
    if auto:
        return auto

    return True
