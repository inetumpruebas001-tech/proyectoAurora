"""Resultado de cada caso ejecutado (resultados_casos.json).

Lo usan la actualización de la Test Execution en Xray y el paquete de evidencias para SharePoint
(tools/xray). Un registro por caso: clave de Xray, estado, error (sin tokens) y nombre de su Word.

Convención: el campo 'Escenario' del Excel empieza con la clave del caso en Xray,
p. ej. "TAP-4234 - Cotiza con edad mínima". Esa clave también nombra el Word de evidencia.
"""
import json
import os
import re
from datetime import datetime

RUTA_RESULTADOS = os.path.join(os.getcwd(), "resultados_casos.json")
_RE_CLAVE = re.compile(r"^\s*([A-Z][A-Z0-9]+-\d+)\b")
_RE_CLAVE_JIRA = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
_RE_SENSIBLE = re.compile(
    r"(Bearer\s+|(?:token|password|secret|api[-_]?key|authorization|clave)[\"']?\s*[:=]\s*[\"']?(?:Bearer\s+)?)[^\s,;\"']+",
    re.IGNORECASE)


def clave_xray(escenario):
    """'TAP-4234 - Cotiza...' -> 'TAP-4234'. Vacío si el escenario no empieza con una clave."""
    m = _RE_CLAVE.match(str(escenario or ""))
    return m.group(1) if m else ""


def nombre_evidencia(escenario, respaldo):
    """Nombre base del Word: la clave de Xray si existe; si no, el respaldo (p. ej. <Api>-<Iteracion>)."""
    return clave_xray(escenario) or respaldo


def enmascarar(texto):
    return _RE_SENSIBLE.sub(r"\1****", str(texto or ""))


def iniciar(context):
    context.resultados_casos = []
    if os.path.exists(RUTA_RESULTADOS) and not context.config.dry_run:
        os.remove(RUTA_RESULTADOS)   # nunca usar resultados de una ejecución anterior


def registrar(context, scenario, escenario, evidencia, clave="", **extra):
    """Agrega el caso. 'evidencia' = nombre base del Word (sin estado ni extensión).
    'clave' = clave de Xray si viene de otra columna; si no, se toma del inicio del escenario."""
    if not hasattr(context, 'resultados_casos'):
        return
    if "soporte" in scenario.effective_tags:   # preparación (reinicio, reloj, login técnico): no es un caso
        return
    error = ""
    for step in scenario.steps:
        if step.status.name == "failed" and step.error_message:
            error = enmascarar(step.error_message)[:1500]
            break
    omitido = getattr(context, 'state', None) is not None
    inicio = getattr(context, 'start_time', None) or datetime.now()
    context.resultados_casos.append({
        "clave": clave_xray(clave) or clave_xray(escenario),
        "escenario": escenario,
        "estado": "skipped" if omitido else scenario.status.name,
        "evidencia": evidencia,
        "requisitos": sorted({t for t in scenario.effective_tags if _RE_CLAVE_JIRA.match(t)}),
        "inicio": inicio.astimezone().isoformat(timespec="seconds"),
        "fin": datetime.now().astimezone().isoformat(timespec="seconds"),
        "error": error,
        **extra,
    })


def guardar(context, ambiente):
    if getattr(context, 'resultados_casos', None):
        with open(RUTA_RESULTADOS, "w", encoding="utf-8") as f:
            json.dump({"ambiente": ambiente, "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "casos": context.resultados_casos}, f, ensure_ascii=False, indent=1)
