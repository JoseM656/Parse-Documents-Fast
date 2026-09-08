"""Tests para el módulo de configuración."""

import tomllib
from pathlib import Path

import pytest
from dev.config import Settings, settings

def _pyproject_version() -> str:
    """Lee la versión declarada en pyproject.toml (la misma fuente que usa config.py)."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


@pytest.fixture
def default_settings() -> Settings:
    """Instancia de Settings aislada de cualquier .env del entorno.
 
    Se usa en los tests que verifican los VALORES POR DEFECTO declarados en
    config.py, para que no dependan de si existe un .env activo (por ejemplo,
    copiado de .env.example) en la máquina donde corren los tests. `settings`
    (la instancia global) sí lee el .env real y es la que usa el resto de la
    aplicación — por eso los tests de "sanity" sobre configuración activa
    siguen usando `settings`, no este fixture.
    """
    return Settings(_env_file=None)

class TestConfig:
    """Tests para verificar la configuración de la aplicación."""

    def test_settings_app_name_is_defined(self):
        """La aplicación tiene un nombre configurado."""
        assert settings.APP_NAME is not None
        assert settings.APP_NAME == "PDF Manager"

    def test_settings_version_is_defined(self):
        """La aplicación tiene una versión configurada."""
        assert settings.VERSION is not None
        assert settings.VERSION == _pyproject_version()

    def test_settings_mongo_uri_is_defined(self):
        """La aplicación tiene una URI de MongoDB configurada."""
        assert settings.MONGO_URI is not None
        assert "mongodb" in settings.MONGO_URI.lower()

    def test_settings_mongo_db_name_is_defined(self, default_settings):
        """La aplicación tiene un nombre de base de datos configurado."""
        assert default_settings.MONGO_DB_NAME is not None
        assert default_settings.MONGO_DB_NAME == "pdf_manager"

    def test_settings_api_base_url_is_defined(self):
        """La aplicación tiene una URL base de API configurada."""
        assert settings.API_BASE_URL is not None
        assert settings.API_BASE_URL.startswith("http")

    def test_settings_api_base_url_default_is_localhost(self, default_settings):
        """La URL base por defecto apunta a localhost:8000."""
        assert "localhost:8000" in default_settings.API_BASE_URL

    def test_settings_ssl_cert_file_defaults_to_none(self, default_settings):
        """La ruta al CA local es opcional y por defecto no está configurada."""
        assert default_settings.SSL_CERT_FILE is None