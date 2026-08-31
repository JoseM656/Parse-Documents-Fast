"""Fixtures compartidos para todos los tests."""

import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Configurar PYTHONPATH para importar dev
sys.path.insert(0, str(Path(__file__).parent.parent))

from dev.dev.server.app import app

#Client fixture para test de API
@pytest.fixture(scope="function")
def client()-> TestClient:
    """Proporciona un TestClient de FastAPI para tests de integración."""
    return TestClient(app)


# Upload directory fixture
@pytest.fixture(scope="function")
def temp_upload_dir() -> Generator[Path, None, None]:
    """Proporciona un directorio temporal para uploads de PDF."""
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_path = Path(tmpdir) / "uploads"
        upload_path.mkdir(parents=True, exist_ok=True)
        yield upload_path


# Sample PDF content fixture
@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Retorna el contenido binario de un PDF de prueba."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    pdf_path = fixtures_dir / "sample.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    # PDF mínimo válido si no existe el archivo
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
        b"/Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n"
        b"0000000101 00000 n\n0000000270 00000 n\n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n369\n%%EOF\n"
    )
