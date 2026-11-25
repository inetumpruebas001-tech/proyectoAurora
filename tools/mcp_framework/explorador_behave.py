"""
Ejecuta behave con un gancho que captura la pantalla (elementos + locators) durante un
escenario real. Lo lanza la herramienta explorar_tras_steps de server.py; no se usa a mano.

Variables de entorno:
  MCP_CAPTURA_SALIDA  archivo JSON donde se guarda la captura
  MCP_HASTA_PASO      texto (parcial) del paso tras el cual capturar; vacío = fin del escenario
  MCP_SOLO_VISIBLES   "1" (por defecto) o "0"

No modifica environment.py: envuelve Runner.run_hook en memoria, solo para esta ejecución.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pagina  # noqa: E402
from behave.__main__ import main as behave_main  # noqa: E402
from behave.runner import Runner  # noqa: E402

SALIDA = Path(os.environ["MCP_CAPTURA_SALIDA"])
HASTA = os.environ.get("MCP_HASTA_PASO", "").strip().lower()
SOLO_VISIBLES = os.environ.get("MCP_SOLO_VISIBLES", "1") != "0"
_estado = {"hecho": False}
_original = Runner.run_hook


def _capturar(context, momento: str) -> None:
    driver = getattr(context, "driver", None)
    if driver is None:
        return
    try:
        datos = pagina.capturar(driver, SOLO_VISIBLES)
    except Exception as e:  # noqa: BLE001
        datos = {"error_captura": f"{type(e).__name__}: {e}"}
    datos["capturado_en"] = momento
    escenario = getattr(context, "scenario", None)
    datos["escenario"] = getattr(escenario, "name", "")
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    _estado["hecho"] = True


def _run_hook(self, name, context, *args):
    if name == "after_scenario" and not _estado["hecho"]:
        _capturar(context, "fin del escenario (antes de cerrar el navegador)")
    _original(self, name, context, *args)
    if name == "after_step" and HASTA and not _estado["hecho"] and args:
        paso = args[0]
        if HASTA in (getattr(paso, "name", "") or "").lower():
            _capturar(context, f"después del paso: {paso.keyword} {paso.name}")


Runner.run_hook = _run_hook

if __name__ == "__main__":
    sys.exit(behave_main(sys.argv[1:]))
