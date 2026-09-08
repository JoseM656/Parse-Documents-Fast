import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

def get_version():
    """
    Consigue la version del programa desde el .toml
    """
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as f:
            return tomllib.load(f)["project"]["version"]

    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):

        return "unknown" # en caso de que no lo encuentre.

class Settings(BaseSettings):
    APP_NAME: str = "PDF Manager"
    VERSION: str = get_version()

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "pdf_manager"

    MAX_FILE_SIZE_MB: int = 10
    API_BASE_URL: str = "http://localhost:8000"

    # Ruta opcional al CA bundle (ej. rootCA.pem de mkcert) para que el CLI
    # confíe en certificados locales. Si se deja vacía, el CLI lo auto-detecta.
    SSL_CERT_FILE: str | None = None

    # Esta linea es clave para sobreescribir la configuracion del entorno.
    model_config = SettingsConfigDict(env_file=".env", extra="allow")


settings = Settings()