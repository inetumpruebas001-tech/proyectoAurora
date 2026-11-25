"""Actualiza en Xray Cloud una Test Execution que el QE ya creó, con el resultado de la última ejecución.

Reglas (acordadas con el equipo):
  - Los casos de prueba se registran MANUALMENTE en Xray. Este módulo nunca crea Tests ni
    Test Executions: solo cambia el estado de los casos que ya están en la Test Execution.
  - La clave del caso viene del campo 'Escenario' del Excel: "TAP-4234 - Cotiza con edad mínima".
  - Casos ejecutados que no están en la Test Execution: se informan, no se agregan.
  - Casos de la Test Execution que no se ejecutaron: se informan, quedan como estaban.

Credenciales (nunca en el repo): XRAY_CLIENT_ID y XRAY_CLIENT_SECRET, una API Key de Xray
(Jira → Apps → Xray → API Keys, la crea un administrador de Jira).

Uso (pipeline o terminal):
    python tools/xray/xray_cloud.py --test-execution TAP-5000 [--simular] [--sin-evidencias]
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(os.environ.get("FRAMEWORK_ROOT") or Path(__file__).resolve().parents[2]).resolve()
RUTA_CONFIG = ROOT / "config" / "xray.json"
RUTA_RESULTADOS = ROOT / "resultados_casos.json"
CARPETAS_REPORTES = [ROOT / "src" / "test" / "reports", ROOT / "reports"]
URL_XRAY = os.environ.get("XRAY_BASE_URL", "https://xray.cloud.getxray.app").rstrip("/")
TIMEOUT = 60
MAX_EVIDENCIA_BYTES = 5 * 1024 * 1024
TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_RE_CLAVE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_RE_SENSIBLE = re.compile(
    r"(Bearer\s+|(?:token|password|secret|api[-_]?key|authorization)[\"']?\s*[:=]\s*[\"']?(?:Bearer\s+)?)[^\s,;\"']+",
    re.IGNORECASE)


class ErrorXray(Exception):
    pass


def _enmascarar(texto: str) -> str:
    return _RE_SENSIBLE.sub(r"\1****", texto or "")


def _fecha(valor: str) -> str:
    return valor if re.search(r"[+-]\d{2}:\d{2}$|Z$", valor) else valor + "-05:00"


def cargar_config() -> dict:
    config = {"jiraUrl": "", "ambientes": {"local": "LOCAL", "dev": "DEV", "certi": "CERTI"}}
    if RUTA_CONFIG.exists():
        config.update({k: v for k, v in json.loads(RUTA_CONFIG.read_text(encoding="utf-8")).items()
                       if not k.startswith("_")})
    return config


def cargar_resultados() -> dict:
    if not RUTA_RESULTADOS.exists():
        raise ErrorXray("No hay resultados: ejecuta primero los escenarios (behave --tags=@...)")
    return json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))


def ultima_carpeta_reporte() -> Path | None:
    carpetas = [Path(c) for base in CARPETAS_REPORTES for c in glob.glob(str(base / "report-*"))]
    return max(carpetas, key=os.path.getmtime) if carpetas else None


def archivo_evidencia(caso: dict) -> Path | None:
    """Word del caso en el último reporte: <evidencia>-<ESTADO>.docx (o _2, _3 si se repite)."""
    carpeta = ultima_carpeta_reporte()
    if not carpeta or not caso.get("evidencia"):
        return None
    candidatos = sorted(glob.glob(str(carpeta / "Evidencias" / f"{glob.escape(caso['evidencia'])}-*.docx")))
    return Path(candidatos[0]) if candidatos else None


# ---------------------------------------------------------------------------
# Resultados agrupados por clave (sin red)
# ---------------------------------------------------------------------------

def casos_por_clave() -> tuple[dict, list, str]:
    """{clave: {estado, comentario, inicio, fin, casos}} de los casos ejecutados; lista sin clave; ambiente."""
    resultados = cargar_resultados()
    por_clave, sin_clave = {}, []
    for c in resultados["casos"]:
        if c["estado"] not in ("passed", "failed"):
            continue
        if not c.get("clave"):
            sin_clave.append(c["escenario"])
            continue
        g = por_clave.setdefault(c["clave"], {"estado": "PASSED", "lineas": [], "inicio": c["inicio"], "fin": c["fin"], "casos": []})
        if c["estado"] == "failed":
            g["estado"] = "FAILED"   # varias filas con la misma clave: falla si falla alguna
        origen = f"{c.get('excel', '')}/{c.get('hoja', '')} fila {c.get('datos', '')}".strip(" /")
        g["lineas"].append(f"[{c['estado'].upper()}] {c['escenario']} ({origen})"
                           + (f"\nError: {_enmascarar(c['error'])}" if c.get("error") else ""))
        g["inicio"], g["fin"] = min(g["inicio"], c["inicio"]), max(g["fin"], c["fin"])
        g["casos"].append(c)
    return por_clave, sin_clave, resultados.get("ambiente", "")


# ---------------------------------------------------------------------------
# Xray Cloud
# ---------------------------------------------------------------------------

def autenticar() -> str:
    cid, secreto = os.environ.get("XRAY_CLIENT_ID"), os.environ.get("XRAY_CLIENT_SECRET")
    if not cid or not secreto:
        raise ErrorXray("Faltan XRAY_CLIENT_ID y XRAY_CLIENT_SECRET (API Key de Xray) en las variables de entorno")
    r = requests.post(f"{URL_XRAY}/api/v2/authenticate", json={"client_id": cid, "client_secret": secreto}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ErrorXray(f"Xray rechazó la API Key (HTTP {r.status_code}). Revisa XRAY_CLIENT_ID / XRAY_CLIENT_SECRET")
    return r.json()


_CONSULTA = """
query($jql: String!, $inicio: Int!) {
  getTestExecutions(jql: $jql, limit: 1) {
    results {
      issueId
      jira(fields: ["key", "summary"])
      %s
      tests(limit: 100, start: $inicio) { total results { jira(fields: ["key"]) } }
    }
  }
}"""


def _graphql(token: str, consulta: str, variables: dict) -> dict:
    r = requests.post(f"{URL_XRAY}/api/v2/graphql", headers={"Authorization": f"Bearer {token}"},
                      json={"query": consulta, "variables": variables}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ErrorXray(f"Xray respondió HTTP {r.status_code} al leer la Test Execution: {r.text[:300]}")
    return r.json()


def leer_test_execution(clave: str, token: str) -> dict:
    """{clave, resumen, ambientes, tests:[claves]}. Falla si no existe."""
    if not _RE_CLAVE.match(clave or ""):
        raise ErrorXray(f"'{clave}' no parece una clave de Jira (ej. TAP-5000)")
    campo_amb = "testEnvironments"
    tests, inicio, datos = [], 0, None
    while True:
        respuesta = _graphql(token, _CONSULTA % campo_amb, {"jql": f'key = "{clave}"', "inicio": inicio})
        if respuesta.get("errors") and campo_amb:
            campo_amb = ""          # versión de Xray sin ese campo: se consulta sin ambientes
            continue
        if respuesta.get("errors"):
            raise ErrorXray(f"No se pudo leer la Test Execution {clave}: {respuesta['errors'][0].get('message', '')}")
        resultados = respuesta["data"]["getTestExecutions"]["results"]
        if not resultados:
            raise ErrorXray(f"No existe la Test Execution {clave} o tu usuario no tiene acceso")
        datos = resultados[0]
        bloque = datos["tests"]
        tests += [t["jira"]["key"] for t in bloque["results"]]
        inicio += len(bloque["results"])
        if not bloque["results"] or inicio >= bloque["total"]:
            break
    return {"clave": clave, "resumen": datos["jira"].get("summary", ""),
            "ambientes": datos.get("testEnvironments") or [], "tests": tests}


def plan_de_actualizacion(test_execution: str, token: str, adjuntar_evidencias: bool = True) -> tuple[dict, dict]:
    """(payload Xray JSON, vista previa). Lee la Test Execution, no escribe nada."""
    te = leer_test_execution(test_execution, token)
    por_clave, sin_clave, ambiente = casos_por_clave()
    if not por_clave and not sin_clave:
        raise ErrorXray("La última ejecución no tiene casos ejecutados")
    en_te = set(te["tests"])
    actualizar = {k: v for k, v in por_clave.items() if k in en_te}
    config = cargar_config()
    entorno = config["ambientes"].get(ambiente, ambiente.upper()) if ambiente else ""
    tests = []
    for clave, g in sorted(actualizar.items()):
        t = {"testKey": clave, "status": g["estado"], "start": _fecha(g["inicio"]), "finish": _fecha(g["fin"]),
             "comment": f"Ejecución automatizada ({entorno or 'ambiente sin dato'})\n\n" + "\n\n".join(g["lineas"])}
        if adjuntar_evidencias:
            evidencias = []
            for c in g["casos"]:
                ruta = archivo_evidencia(c)
                if ruta and ruta.stat().st_size <= MAX_EVIDENCIA_BYTES:
                    evidencias.append({"data": base64.b64encode(ruta.read_bytes()).decode(),
                                       "filename": ruta.name, "contentType": TIPO_DOCX})
            if evidencias:
                t["evidence"] = evidencias
        tests.append(t)
    avisos = []
    if entorno and te["ambientes"] and entorno not in te["ambientes"]:
        avisos.append(f"La ejecución se hizo en {entorno} pero la Test Execution es de {', '.join(te['ambientes'])}")
    if not actualizar:
        avisos.append("Ningún caso ejecutado está en esta Test Execution: no hay nada que actualizar")
    vista = {
        "test_execution": te["clave"], "resumen_te": te["resumen"], "ambientes_te": te["ambientes"],
        "ambiente_ejecucion": entorno,
        "a_actualizar": [{"clave": k, "estado": v["estado"]} for k, v in sorted(actualizar.items())],
        "pasados": sum(1 for v in actualizar.values() if v["estado"] == "PASSED"),
        "fallidos": sum(1 for v in actualizar.values() if v["estado"] == "FAILED"),
        "en_te_sin_ejecutar": sorted(en_te - set(por_clave)),
        "ejecutados_fuera_de_la_te": sorted(set(por_clave) - en_te),
        "ejecutados_sin_clave": sin_clave[:30],
        "evidencias_adjuntas": sum(len(t.get("evidence", [])) for t in tests),
        "avisos": avisos,
    }
    return {"testExecutionKey": te["clave"], "tests": tests}, vista


def importar(payload: dict, token: str) -> dict:
    r = requests.post(f"{URL_XRAY}/api/v2/import/execution", json=payload,
                      headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT * 3)
    if r.status_code != 200:
        raise ErrorXray(f"Xray no aceptó la actualización (HTTP {r.status_code}): {_enmascarar(r.text[:800])}")
    return r.json()


def actualizar(test_execution: str, adjuntar_evidencias: bool = True, simular: bool = False) -> dict:
    token = autenticar()
    payload, vista = plan_de_actualizacion(test_execution, token, adjuntar_evidencias)
    if simular or not payload["tests"]:
        return {"actualizado": False, "vista_previa": vista}
    respuesta = importar(payload, token)
    salida = {"actualizado": True, "test_execution": respuesta.get("key", test_execution), "vista_previa": vista}
    jira = cargar_config().get("jiraUrl")
    if jira:
        salida["url"] = f"{jira.rstrip('/')}/browse/{salida['test_execution']}"
    return salida


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Actualiza una Test Execution existente de Xray Cloud")
    p.add_argument("--test-execution", required=True, help="Clave de la Test Execution creada por el QE (ej. TAP-5000)")
    p.add_argument("--sin-evidencias", action="store_true")
    p.add_argument("--simular", action="store_true", help="Solo lee Xray y muestra qué se actualizaría")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        salida = actualizar(args.test_execution.strip(), not args.sin_evidencias, args.simular)
    except (ErrorXray, requests.RequestException) as e:
        print(f"[XRAY] {_enmascarar(str(e))}", file=sys.stderr)
        return 1
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    v = salida["vista_previa"]
    for etiqueta, lista in (("fuera de la Test Execution", v["ejecutados_fuera_de_la_te"]),
                            ("sin clave de Xray en 'Escenario'", v["ejecutados_sin_clave"])):
        if lista and os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning::{len(lista)} casos {etiqueta}: no se actualizaron en Xray")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
