"""Tests para la resolución del CA de mkcert en el cliente."""

from unittest.mock import patch

from dev.client.ssl_trust import _mkcert_root_ca, resolve_ssl_verify


class TestResolveSslVerify:
    """Tests para resolve_ssl_verify."""

    def test_returns_explicit_cert_when_file_exists(self, tmp_path) -> None:
        """Si SSL_CERT_FILE apunta a un archivo existente, lo usa tal cual."""
        ca = tmp_path / "rootCA.pem"
        ca.write_text("CERT")

        assert resolve_ssl_verify(str(ca)) == str(ca)

    def test_falls_back_to_mkcert_when_explicit_missing(self, tmp_path) -> None:
        """Si SSL_CERT_FILE no existe, intenta con el CA de mkcert."""
        ca = tmp_path / "rootCA.pem"
        ca.write_text("CERT")

        with patch("dev.client.ssl_trust._mkcert_root_ca", return_value=str(ca)):
            assert resolve_ssl_verify("/no/existe.pem") == str(ca)

    def test_auto_detects_mkcert_root_ca(self, tmp_path) -> None:
        """Sin SSL_CERT_FILE, usa el rootCA.pem detectado de mkcert."""
        ca = tmp_path / "rootCA.pem"
        ca.write_text("CERT")

        with patch("dev.client.ssl_trust._mkcert_root_ca", return_value=str(ca)):
            assert resolve_ssl_verify(None) == str(ca)

    def test_returns_true_when_no_mkcert_and_no_explicit(self) -> None:
        """Sin mkcert y sin SSL_CERT_FILE, delega en la verificación por defecto."""
        with patch("dev.client.ssl_trust._mkcert_root_ca", return_value=None):
            assert resolve_ssl_verify(None) is True

    def test_returns_true_when_explicit_missing_and_no_mkcert(self) -> None:
        """SSL_CERT_FILE inexistente y sin mkcert → verificación por defecto."""
        with patch("dev.client.ssl_trust._mkcert_root_ca", return_value=None):
            assert resolve_ssl_verify("/no/existe.pem") is True


class TestMkcertRootCa:
    """Tests para _mkcert_root_ca."""

    def test_runs_mkcert_and_returns_existing_root_ca(
        self, tmp_path, monkeypatch
    ) -> None:
        """Ejecuta `mkcert -CAROOT` y devuelve <caroot>/rootCA.pem si existe."""
        caroot = tmp_path / "caroot"
        caroot.mkdir()
        (caroot / "rootCA.pem").write_text("CERT")

        fake_mkcert = tmp_path / "mkcert"
        fake_mkcert.write_text(f"#!/bin/sh\necho {caroot}\n")
        fake_mkcert.chmod(0o755)

        monkeypatch.setattr(
            "dev.client.ssl_trust.shutil.which",
            lambda name: str(fake_mkcert) if name == "mkcert" else None,
        )

        assert _mkcert_root_ca() == str(caroot / "rootCA.pem")

    def test_returns_none_when_mkcert_missing(self, monkeypatch) -> None:
        """Si no hay mkcert instalado, devuelve None."""
        monkeypatch.setattr("dev.client.ssl_trust.shutil.which", lambda name: None)

        assert _mkcert_root_ca() is None

    def test_returns_none_when_root_ca_does_not_exist(
        self, tmp_path, monkeypatch
    ) -> None:
        """Si el caroot existe pero no tiene rootCA.pem, devuelve None."""
        caroot = tmp_path / "caroot"
        caroot.mkdir()

        fake_mkcert = tmp_path / "mkcert"
        fake_mkcert.write_text(f"#!/bin/sh\necho {caroot}\n")
        fake_mkcert.chmod(0o755)

        monkeypatch.setattr(
            "dev.client.ssl_trust.shutil.which",
            lambda name: str(fake_mkcert) if name == "mkcert" else None,
        )

        assert _mkcert_root_ca() is None
