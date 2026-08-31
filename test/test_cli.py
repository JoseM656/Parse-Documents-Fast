"""Tests de integración para el CLI de fast-pdf.

El CLI ahora actúa como cliente HTTP de la API FastAPI.
Los tests mockean httpx para no requerir que el servidor esté corriendo,
verificando que el CLI construye los requests correctos y maneja las
respuestas del servidor apropiadamente.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCliSubcommands:
    """Tests que verifican que el CLI reconoce sus subcomandos."""

    def test_cli_requires_a_subcommand(self) -> None:
        """Sin subcomando, el CLI debe salir con error (código 2 de argparse)."""
        result = subprocess.run(
            [sys.executable, "-m", "dev.main"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, "Debe fallar si no se pasa ningún subcomando"

    def test_cli_upload_requires_pdf_argument(self) -> None:
        """El subcomando upload sin archivo debe salir con código 2."""
        result = subprocess.run(
            [sys.executable, "-m", "dev.main", "upload"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, "upload sin archivo debe fallar con error de argumentos"

    def test_cli_get_requires_id_argument(self) -> None:
        """El subcomando get sin ID debe salir con código 2."""
        result = subprocess.run(
            [sys.executable, "-m", "dev.main", "get"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2

    def test_cli_delete_requires_id_argument(self) -> None:
        """El subcomando delete sin ID debe salir con código 2."""
        result = subprocess.run(
            [sys.executable, "-m", "dev.main", "delete"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2


class TestUploadCommand:
    """Tests para el subcomando 'upload'."""

    def test_upload_fails_when_file_does_not_exist(self, tmp_path: Path) -> None:
        """upload con un archivo inexistente debe retornar código 1."""
        result = subprocess.run(
            [sys.executable, "-m", "dev.main", "upload", str(tmp_path / "noexiste.pdf")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "no existe" in result.stderr.lower()

    def test_upload_reports_connection_error_when_server_is_down(self, tmp_path: Path) -> None:
        """Si el servidor no responde, upload debe informar el error claramente."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        # Apuntamos a un puerto donde no hay nada corriendo
        result = subprocess.run(
            [sys.executable, "-m", "dev.main", "upload", str(pdf_file)],
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "API_BASE_URL": "http://localhost:19999",
            },
        )

        assert result.returncode == 1
        assert "conectar" in result.stderr.lower() or "connect" in result.stderr.lower()

    def test_upload_sends_file_to_api(self, tmp_path: Path) -> None:
        """upload debe enviar el archivo a POST /api/pdfs y mostrar el ID."""
        pdf_file = tmp_path / "documento.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc123",
            "title": "documento",
            "size": 16,
            "created_at": "2026-01-01T00:00:00",
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            from dev.client.cli import _cmd_upload
            import argparse

            args = argparse.Namespace(pdf_file=pdf_file, info=False)
            result = _cmd_upload(args)

            assert result == 0
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            # Verifica que el archivo se mandó en el campo "file"
            assert "files" in call_kwargs.kwargs or len(call_kwargs.args) > 0

    def test_upload_passes_verify_to_httpx(self, tmp_path: Path) -> None:
        """upload debe pasar un argumento `verify` para confiar en el CA local."""
        pdf_file = tmp_path / "documento.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc123",
            "title": "documento",
            "size": 16,
            "created_at": "2026-01-01T00:00:00",
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            from dev.client.cli import _cmd_upload
            import argparse

            args = argparse.Namespace(pdf_file=pdf_file, info=False)
            result = _cmd_upload(args)

            assert result == 0
            verify = mock_post.call_args.kwargs.get("verify")
            assert verify is True or isinstance(verify, str)

    def test_upload_with_info_flag_shows_size_and_date(self, tmp_path: Path, capsys) -> None:
        """--info debe mostrar tamaño y fecha además del ID."""
        pdf_file = tmp_path / "documento.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc123",
            "title": "documento",
            "size": 1024,
            "created_at": "2026-01-01T00:00:00",
        }

        with patch("httpx.post", return_value=mock_response):
            from dev.client.cli import _cmd_upload
            import argparse

            args = argparse.Namespace(pdf_file=pdf_file, info=True)
            _cmd_upload(args)

            captured = capsys.readouterr()
            assert "1024" in captured.out
            assert "2026-01-01" in captured.out

    def test_upload_shows_duplicate_message_on_409(self, tmp_path: Path, capsys) -> None:
        """Si el servidor retorna 409, debe mostrar el ID del documento existente."""
        pdf_file = tmp_path / "dup.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "detail": {
                "message": "Este documento ya fue subido anteriormente.",
                "existing_id": "existing-abc-123",
            }
        }

        with patch("httpx.post", return_value=mock_response):
            from dev.client.cli import _cmd_upload
            import argparse

            args = argparse.Namespace(pdf_file=pdf_file, info=False)
            result = _cmd_upload(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "existing-abc-123" in captured.out
            assert "duplicado" in captured.out.lower()

    def test_upload_shows_validation_error_on_400(self, tmp_path: Path, capsys) -> None:
        """Si el servidor retorna 400, debe mostrar el mensaje de error de validación."""
        pdf_file = tmp_path / "invalido.pdf"
        pdf_file.write_bytes(b"esto no es un pdf")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "detail": "El archivo 'invalido.pdf' no es un PDF válido."
        }

        with patch("httpx.post", return_value=mock_response):
            from dev.client.cli import _cmd_upload
            import argparse

            args = argparse.Namespace(pdf_file=pdf_file, info=False)
            result = _cmd_upload(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "validación" in captured.err.lower() or "error" in captured.err.lower()


class TestListCommand:
    """Tests para el subcomando 'list'."""

    def test_list_shows_empty_message_when_no_pdfs(self, capsys) -> None:
        """Si no hay PDFs, list debe informarlo claramente."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_list
            import argparse

            result = _cmd_list(argparse.Namespace())

            assert result == 0
            captured = capsys.readouterr()
            assert "no hay" in captured.out.lower()

    def test_list_shows_pdf_entries(self, capsys) -> None:
        """list debe mostrar ID, título, tamaño y fecha de cada PDF."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "abc123",
                "title": "Mi Documento",
                "size": 2048,
                "created_at": "2026-01-15T10:30:00",
            }
        ]

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_list
            import argparse

            result = _cmd_list(argparse.Namespace())

            assert result == 0
            captured = capsys.readouterr()
            assert "abc123" in captured.out
            assert "Mi Documento" in captured.out


class TestGetCommand:
    """Tests para el subcomando 'get'."""

    def test_get_shows_extracted_text(self, capsys) -> None:
        """get debe imprimir el texto extraído del PDF."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pdf_id": "abc123",
            "text": "Contenido del documento PDF.",
        }

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_get
            import argparse

            args = argparse.Namespace(pdf_id="abc123")
            result = _cmd_get(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "Contenido del documento PDF." in captured.out

    def test_get_returns_1_when_pdf_not_found(self, capsys) -> None:
        """get debe retornar código 1 y mensaje de error si el ID no existe."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_get
            import argparse

            args = argparse.Namespace(pdf_id="id-inexistente")
            result = _cmd_get(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "no existe" in captured.err.lower()


class TestDeleteCommand:
    """Tests para el subcomando 'delete'."""

    def test_delete_confirms_deletion(self, capsys) -> None:
        """delete debe confirmar que el documento fue eliminado."""
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.delete", return_value=mock_response):
            from dev.client.cli import _cmd_delete
            import argparse

            args = argparse.Namespace(pdf_id="abc123")
            result = _cmd_delete(args)

            assert result == 0
            captured = capsys.readouterr()
            assert "eliminado" in captured.out.lower()

    def test_delete_returns_1_when_pdf_not_found(self, capsys) -> None:
        """delete debe retornar código 1 si el ID no existe."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.delete", return_value=mock_response):
            from dev.client.cli import _cmd_delete
            import argparse

            args = argparse.Namespace(pdf_id="id-inexistente")
            result = _cmd_delete(args)

            assert result == 1
            

class TestDownloadCommand:
    """Tests para el subcomando 'download'."""

    def test_download_saves_file_with_default_name(
        self, tmp_path: Path, capsys
    ) -> None:
        """download guarda el texto en un archivo con el nombre del título."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Contenido del PDF."
        mock_response.headers = {
            "content-disposition": 'attachment; filename="Mi Documento.txt"'
        }

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_download
            import argparse
            import os

            os.chdir(tmp_path)
            args = argparse.Namespace(pdf_id="abc123", output=None)
            result = _cmd_download(args)

            assert result == 0
            assert (tmp_path / "Mi Documento.txt").exists()

    def test_download_saves_file_with_custom_name(
        self, tmp_path: Path
    ) -> None:
        """--output permite especificar el nombre del archivo."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Contenido del PDF."
        mock_response.headers = {
            "content-disposition": 'attachment; filename="Mi Documento.txt"'
        }

        output_file = tmp_path / "mi_archivo.txt"

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_download
            import argparse

            args = argparse.Namespace(pdf_id="abc123", output=output_file)
            result = _cmd_download(args)

            assert result == 0
            assert output_file.exists()
            assert output_file.read_text() == "Contenido del PDF."

    def test_download_returns_1_when_pdf_not_found(self, capsys) -> None:
        """download retorna código 1 si el ID no existe."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.get", return_value=mock_response):
            from dev.client.cli import _cmd_download
            import argparse

            args = argparse.Namespace(pdf_id="id-inexistente", output=None)
            result = _cmd_download(args)

            assert result == 1