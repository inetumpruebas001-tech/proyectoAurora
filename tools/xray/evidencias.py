"""Arma la carpeta de evidencias de la última ejecución con la estructura del SharePoint:

    evidencias_sharepoint/<TestPlan>/<TestExecution>/<CLAVE>.docx
                                                     resumen.md   (tabla clave / estado / motivo)
                                                     resumen.csv

Lista para arrastrar al SharePoint. No se conecta a nada: solo copia archivos locales.

Uso:  python tools/xray/evidencias.py --test-plan TAP-4000 --test-execution TAP-5000
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xray_cloud as xc  # noqa: E402

SALIDA = xc.ROOT / "evidencias_sharepoint"
_RE_CLAVE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def armar(test_plan: str, test_execution: str) -> dict:
    for nombre, valor in (("Test Plan", test_plan), ("Test Execution", test_execution)):
        if not _RE_CLAVE.match(valor or ""):
            raise xc.ErrorXray(f"{nombre} '{valor}' no parece una clave de Jira (ej. TAP-5000)")
    por_clave, sin_clave, ambiente = xc.casos_por_clave()
    destino = SALIDA / test_plan / test_execution
    if destino.exists():
        shutil.rmtree(destino)   # se rehace completa: siempre refleja la última ejecución
    destino.mkdir(parents=True)
    filas, sin_word = [], []
    for clave, g in sorted(por_clave.items()):
        archivos = [a for a in (xc.archivo_evidencia(c) for c in g["casos"]) if a]
        for i, origen in enumerate(archivos, start=1):
            nombre = f"{clave}.docx" if len(archivos) == 1 else f"{clave}_{i}.docx"
            shutil.copy2(origen, destino / nombre)
        if not archivos:
            sin_word.append(clave)
        motivo = next((c["error"].splitlines()[0][:200] for c in g["casos"] if c.get("error")), "")
        filas.append({"clave": clave, "estado": g["estado"], "evidencias": len(archivos),
                      "escenario": g["casos"][0]["escenario"], "motivo": xc._enmascarar(motivo)})
    with open(destino / "resumen.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["clave", "estado", "evidencias", "escenario", "motivo"], delimiter=";")
        w.writeheader()
        w.writerows(filas)
    pasados = sum(1 for f in filas if f["estado"] == "PASSED")
    lineas = [f"# {test_execution} ({test_plan})", "",
              f"Ambiente: {ambiente.upper() or '-'} · Casos: {len(filas)} · Pasados: {pasados} · Fallidos: {len(filas) - pasados}", "",
              "| Clave | Estado | Escenario | Motivo |", "|---|---|---|---|"]
    lineas += [f"| {f['clave']} | {f['estado']} | {f['escenario']} | {f['motivo'].replace('|', '/')} |" for f in filas]
    if sin_clave:
        lineas += ["", "Ejecutados sin clave de Xray en 'Escenario' (no incluidos):"] + [f"- {e}" for e in sin_clave]
    (destino / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return {"carpeta": str(destino.relative_to(xc.ROOT)), "casos": len(filas), "pasados": pasados,
            "fallidos": len(filas) - pasados, "sin_evidencia": sin_word, "sin_clave": sin_clave[:30]}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Arma la carpeta de evidencias para SharePoint")
    p.add_argument("--test-plan", required=True)
    p.add_argument("--test-execution", required=True)
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(armar(args.test_plan.strip(), args.test_execution.strip()), ensure_ascii=False, indent=1))
    except xc.ErrorXray as e:
        print(f"[EVIDENCIAS] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
