"""Entorno aislado para los tests: datos en un directorio temporal, sin demoras y sin LLM."""

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="abasto_tests_")
os.environ["ABASTO_DATA_DIR"] = _TMP
os.environ["SIM_DELAY_SECONDS"] = "0"
os.environ["SIM_MODE"] = "fijo"
os.environ["EXTRACCION_MODE"] = "auto"
os.environ["ANTHROPIC_API_KEY"] = ""  # pisa el .env: los tests no llaman a la API
# pisa el .env: archivos, salvo que se pida una base de prueba (borra todo lo que tenga)
os.environ["DATABASE_URL"] = os.environ.get("ABASTO_TEST_DATABASE_URL", "")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
