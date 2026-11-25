"""
MCP del framework de automatización (Behave) — Chapter QA

Expone operaciones del propio framework para que el agente de GitHub Copilot
(o cualquier cliente MCP) trabaje sobre el repo real en lugar de adivinar:

  - info_framework        → stack, configuración, tags, Excel y problemas detectados
  - listar_steps          → catálogo de steps existentes (con archivo y línea)
  - buscar_step           → ¿ya existe un step para esta línea de Gherkin?
  - validar_features      → steps sin definir, duplicados y errores de sintaxis
  - leer_excel            → hojas, columnas y filas de datos (con datos sensibles enmascarados)
  - validar_fila_excel    → revisa una fila de datos antes de ejecutar
  - agregar_filas_excel   → (solo API) agrega filas al final de una hoja: vista previa + confirmación del QE
  - preparar_evidencias   → carpeta de evidencias con la estructura del SharePoint (TestPlan/TestExecution/CLAVE)
  - actualizar_test_execution → cambia estados en una Test Execution existente de Xray: vista previa + confirmación
  - ejecutar_escenarios   → ejecuta behave SOLO por tag y devuelve el resultado
  - ultimo_resultado      → resumen del último reporte (fallos, mensajes, evidencias)
  - explorar_pagina       → (solo web) elementos de una página con locators sugeridos
  - explorar_tras_steps   → (solo web) captura la pantalla después de ejecutar pasos existentes
  - revisar_diseno        → (solo web) compara una pantalla con la guía de diseño (config/diseno/<guia>.json)
  - extraer_estilos       → (solo web) estilos y medidas reales de elementos (para armar o revisar la guía)
  - revisar_buenas_practicas → compuerta de calidad (también en pre-commit y pipeline)
  - diagnosticar_entorno  → Python, venv, dependencias, navegador, git y disco

Detecta solo si el repo es el framework WEB (browser.properties) o el de API
(service.properties). Se ejecuta con el Python del venv del framework.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:
    try:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError:
        if len(sys.argv) < 2:
            raise SystemExit("Falta el SDK de MCP: pip install -r tools/mcp_framework/requirements-mcp.txt")

        class _Server:  # modo terminal (Copilot sin MCP, pre-commit, pipeline) sin SDK de MCP
            def __init__(self, *a, **k):
                pass

            def tool(self, *a, **k):
                return lambda f: f

            def run(self, *a, **k):
                pass

# ---------------------------------------------------------------------------
# Rutas y configuración
# ---------------------------------------------------------------------------

ROOT = Path(os.environ.get("FRAMEWORK_ROOT") or Path(__file__).resolve().parents[2]).resolve()


def _env_bool(nombre: str, defecto: bool) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


PERMITIR_EJECUCION = _env_bool("MCP_PERMITIR_EJECUCION", True)
TAGS_BLOQUEADOS = {
    t.strip().lstrip("@").lower()
    for t in os.environ.get("MCP_TAGS_BLOQUEADOS", "").split(",")
    if t.strip()
}
TIMEOUT_MAX_MIN = int(os.environ.get("MCP_TIMEOUT_MAX_MIN", "30"))


def _modo() -> str:
    if (ROOT / "browser.properties").exists():
        return "web"
    if (ROOT / "service.properties").exists():
        return "api"
    return "desconocido"


def _features_dir() -> Path:
    ini = ROOT / "behave.ini"
    if ini.exists():
        for linea in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*paths\s*=\s*(.+)", linea)
            if m and not linea.strip().startswith(("#", ";")):
                return (ROOT / m.group(1).strip()).resolve()
    return ROOT / "src" / "test" / "features"


FEATURES = _features_dir()
STEPS = FEATURES / "steps"
EXCEL_DIR = ROOT / "src" / "test" / "resources" / "data" / "excel"
REPORTS = ROOT / "src" / "test" / "reports"

# ---------------------------------------------------------------------------
# Enmascarado de datos sensibles
# ---------------------------------------------------------------------------

_CLAVES_SENSIBLES = (
    "contraseña", "contrasena", "password", "passwd", "pwd", "clave", "token",
    "secret", "authorization", "apikey", "api_key", "api-key", "credencial",
    "account_key", "client_secret", "pin", "cvv",
)


def _es_sensible(nombre: str) -> bool:
    n = (nombre or "").strip().lower()
    return any(c in n for c in _CLAVES_SENSIBLES)


_RE_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+/]+=*", re.IGNORECASE)
_RE_CLAVE_VALOR = re.compile(
    r"""(["']?(?:%s)[\w\-]*["']?\s*[:=]\s*["']?)([^"'\s,}\]\n]+)""" % "|".join(
        re.escape(c) for c in _CLAVES_SENSIBLES
    ),
    re.IGNORECASE,
)


def _enmascarar(texto: Any) -> str:
    if texto is None:
        return ""
    s = str(texto)
    s = _RE_BEARER.sub(r"\1***", s)
    s = _RE_CLAVE_VALOR.sub(r"\1***", s)
    return s


def _recortar(texto: str, maximo: int = 1500) -> str:
    texto = texto or ""
    return texto if len(texto) <= maximo else texto[:maximo] + f"... [recortado, {len(texto)} caracteres]"


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Catálogo de steps (lectura estática: funciona aunque un archivo tenga errores)
# ---------------------------------------------------------------------------

_RE_DECORADOR = re.compile(
    r"""^\s*@(?P<kw>given|when|then|step)\s*\(\s*[uUrR]{0,2}(?P<q>['"])(?P<pat>(?:\\.|(?!(?P=q)).)*)(?P=q)""",
    re.IGNORECASE,
)


def _cargar_steps() -> tuple[list[dict], list[dict]]:
    """Devuelve (steps, errores_sintaxis)."""
    steps: list[dict] = []
    errores: list[dict] = []
    if not STEPS.exists():
        return steps, errores
    for archivo in sorted(STEPS.rglob("*.py")):
        codigo = archivo.read_text(encoding="utf-8", errors="ignore")
        try:
            ast.parse(codigo)
        except SyntaxError as e:
            errores.append({
                "archivo": _rel(archivo),
                "linea": e.lineno,
                "error": f"SyntaxError: {e.msg}",
                "impacto": "behave no podrá cargar NINGÚN step hasta corregirlo",
            })
        lineas = codigo.splitlines()
        for i, linea in enumerate(lineas, start=1):
            m = _RE_DECORADOR.match(linea)
            if not m:
                continue
            funcion = ""
            for siguiente in lineas[i:i + 4]:
                mf = re.match(r"\s*def\s+(\w+)", siguiente)
                if mf:
                    funcion = mf.group(1)
                    break
            steps.append({
                "tipo": m.group("kw").lower(),
                "patron": m.group("pat").replace("\\'", "'").replace('\\"', '"'),
                "archivo": _rel(archivo),
                "linea": i,
                "funcion": funcion,
            })
    return steps, errores


def _patron_a_regex(patron: str) -> re.Pattern:
    partes = re.split(r"(\{[^{}]*\})", patron)
    regex = ""
    for parte in partes:
        if parte.startswith("{") and parte.endswith("}"):
            regex += r"(-?\d+)" if parte.endswith(":d}") else r"(.+?)"
        else:
            regex += re.escape(parte)
    return re.compile(r"^" + regex + r"$")


def _duplicados(steps: list[dict]) -> list[dict]:
    vistos: dict[tuple[str, str], dict] = {}
    dups = []
    for s in steps:
        for tipo in ([s["tipo"]] if s["tipo"] != "step" else ["given", "when", "then"]):
            clave = (tipo, s["patron"].strip())
            if clave in vistos and vistos[clave] is not s:
                otro = vistos[clave]
                dups.append({
                    "patron": s["patron"],
                    "tipo": tipo,
                    "definido_en": [f'{otro["archivo"]}:{otro["linea"]}', f'{s["archivo"]}:{s["linea"]}'],
                    "impacto": "behave lanza AmbiguousStep al cargar los steps",
                })
            else:
                vistos[clave] = s
    return dups


def _coincidencias(texto: str, tipo: str | None, steps: list[dict]) -> list[dict]:
    salida = []
    for s in steps:
        if _patron_a_regex(s["patron"]).match(texto.strip()):
            compatible = tipo is None or s["tipo"] in (tipo, "step")
            salida.append({**s, "tipo_compatible": compatible})
    return salida


# ---------------------------------------------------------------------------
# Lectura de features
# ---------------------------------------------------------------------------

_KW_PASO = {
    "given": "given", "when": "when", "then": "then", "and": None, "but": None, "*": None,
    "dado": "given", "dada": "given", "cuando": "when", "entonces": "then", "y": None, "pero": None,
}


def _leer_features() -> list[dict]:
    features = []
    if not FEATURES.exists():
        return features
    for archivo in sorted(FEATURES.rglob("*.feature")):
        lineas = archivo.read_text(encoding="utf-8", errors="ignore").splitlines()
        feature = {"archivo": _rel(archivo), "nombre": "", "escenarios": []}
        tags_pendientes: list[str] = []
        escenario = None
        ultimo_tipo = None
        en_examples = False
        for n, cruda in enumerate(lineas, start=1):
            linea = cruda.strip()
            if not linea or linea.startswith("#"):
                continue
            if linea.startswith("@"):
                tags_pendientes += [t for t in linea.split() if t.startswith("@")]
                continue
            low = linea.lower()
            if low.startswith(("feature:", "característica:", "caracteristica:", "funcionalidad:")):
                feature["nombre"] = linea.split(":", 1)[1].strip()
                feature["tags"] = tags_pendientes
                tags_pendientes = []
                continue
            if re.match(r"^(scenario outline|scenario template|scenario|esquema del escenario|escenario)\s*:", low):
                escenario = {
                    "nombre": linea.split(":", 1)[1].strip() or "(sin nombre)",
                    "linea": n,
                    "tags": tags_pendientes,
                    "pasos": [],
                    "filas_examples": [],
                }
                tags_pendientes = []
                feature["escenarios"].append(escenario)
                ultimo_tipo = None
                en_examples = False
                continue
            if re.match(r"^(examples|ejemplos|scenarios)\s*:", low):
                en_examples = True
                continue
            if en_examples and linea.startswith("|") and escenario is not None:
                celdas = [c.strip() for c in linea.strip("|").split("|")]
                escenario["filas_examples"].append(celdas)
                continue
            m = re.match(r"^(\S+)\s+(.*)$", linea)
            if m and escenario is not None and m.group(1).lower() in _KW_PASO:
                en_examples = False
                kw = m.group(1).lower()
                tipo = _KW_PASO[kw] or ultimo_tipo
                ultimo_tipo = tipo
                escenario["pasos"].append({"linea": n, "keyword": m.group(1), "tipo": tipo, "texto": m.group(2)})
        features.append(feature)
    return features


def _tag_valor(tags: list[str], prefijo: str) -> str | None:
    for t in tags:
        t = t.lstrip("@")
        if t.startswith(prefijo):
            return t[len(prefijo):]
    return None


# ---------------------------------------------------------------------------
# Excel (misma convención que src/test/library/excel_reader.py)
# ---------------------------------------------------------------------------


def _abrir_excel(archivo: str):
    import openpyxl

    nombre = archivo if archivo.lower().endswith(".xlsx") else archivo + ".xlsx"
    ruta = (EXCEL_DIR / nombre).resolve()
    if EXCEL_DIR.resolve() not in ruta.parents:
        raise ValueError("Ruta de Excel fuera de src/test/resources/data/excel")
    if not ruta.exists():
        disponibles = sorted(p.name for p in EXCEL_DIR.glob("*.xlsx")) if EXCEL_DIR.exists() else []
        raise FileNotFoundError(f"No existe {nombre}. Archivos disponibles: {disponibles}")
    return openpyxl.load_workbook(ruta, read_only=True, data_only=True), ruta


def _filas_hoja(wb, hoja: str) -> tuple[list[str], list[dict]]:
    if hoja not in wb.sheetnames:
        raise KeyError(f"La hoja '{hoja}' no existe. Hojas: {wb.sheetnames}")
    ws = wb[hoja]
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return [], []
    encabezados = [str(c).strip() if c is not None else "" for c in filas[0]]
    datos = []
    for fila in filas[1:]:
        if fila is None or all(c in (None, "") for c in fila):
            continue
        registro = {}
        for idx, enc in enumerate(encabezados):
            valor = fila[idx] if idx < len(fila) else None
            registro[enc] = str(valor).strip() if valor else ""
        datos.append(registro)
    return encabezados, datos


def _enmascarar_fila(fila: dict) -> dict:
    return {k: ("***" if _es_sensible(k) and v else _enmascarar(v)) for k, v in fila.items()}


# ---------------------------------------------------------------------------
# Resultados de ejecución
# ---------------------------------------------------------------------------


def _leer_json_resultados(desde: float | None = None) -> tuple[list | None, str | None]:
    for nombre in ("New.pretty.output", "json.pretty.output"):
        ruta = ROOT / nombre
        if not ruta.exists():
            continue
        if desde and ruta.stat().st_mtime < desde - 1:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore").strip()
        for candidato in (texto, texto + "]", texto.rstrip("]") + "]"):
            try:
                return json.loads(candidato), nombre
            except json.JSONDecodeError:
                continue
    return None, None


def _resumir_resultados(data: list, max_detalle: int = 25) -> dict:
    resumen: dict[str, Any] = {"passed": 0, "failed": 0, "skipped": 0, "pasados": [], "fallidos": [], "omitidos": []}
    for feature in data or []:
        for esc in feature.get("elements", []):
            if esc.get("type") == "background":
                continue
            estado = esc.get("status", "unknown")
            clave = estado if estado in ("passed", "failed") else "skipped"
            resumen[clave] += 1
            nombre = esc.get("name")
            if clave == "passed":
                resumen["pasados"].append(nombre)
                continue
            if clave == "skipped":
                resumen["omitidos"].append(nombre)
                continue
            item: dict[str, Any] = {"feature": feature.get("name"), "escenario": nombre, "estado": estado}
            if True:
                for paso in esc.get("steps", []):
                    resultado = paso.get("result", {})
                    if resultado.get("status") in ("failed", "undefined") or "result" not in paso:
                        item["paso_fallido"] = f'{paso.get("keyword", "")} {paso.get("name", "")}'.strip()
                        mensaje = resultado.get("error_message") or ""
                        if isinstance(mensaje, list):
                            mensaje = "\n".join(mensaje)
                        item["error"] = _recortar(_enmascarar(mensaje), 1200)
                        detalle = resultado.get("message") or paso.get("text")
                        if detalle and detalle not in ("-", "NO-EXECUTED"):
                            detalle = re.sub(r"</?(strong|span)[^>]*>", "", str(detalle))
                            item["detalle_paso"] = _recortar(_enmascarar(detalle), 1500)
                        if paso.get("location"):
                            item["ubicacion_feature"] = paso.get("location")
                        if paso.get("match", {}).get("location"):
                            item["step_python"] = paso["match"]["location"]
                        if resultado.get("imagen"):
                            item["capturas"] = resultado.get("imagen")
                        break
            resumen["fallidos"].append(item)
    for lista in ("pasados", "fallidos", "omitidos"):
        if len(resumen[lista]) > max_detalle:
            total = len(resumen[lista])
            resumen[lista] = resumen[lista][:max_detalle] + [f"... y {total - max_detalle} más"]
    if resumen["omitidos"]:
        resumen["nota_omitidos"] = "Omitidos = filas con Ejecutar/Ejecucion = NO o escenarios marcados como skipped."
    return resumen


def _ultima_carpeta_reporte(desde: float | None = None) -> dict | None:
    if not REPORTS.exists():
        return None
    carpetas = [p for p in REPORTS.iterdir() if p.is_dir() and p.name.startswith("report-")]
    if desde:
        carpetas = [p for p in carpetas if p.stat().st_mtime >= desde - 1]
    if not carpetas:
        return None
    ultima = max(carpetas, key=lambda p: p.stat().st_mtime)
    info = {"carpeta": _rel(ultima), "html": _rel(ultima / "overview-features.html")}
    evid = ultima / "Evidencias"
    if evid.exists():
        info["evidencias_word"] = [_rel(p) for p in sorted(evid.glob("*.docx"))][:20]
    caps = ultima / "screenshots"
    if caps.exists():
        info["capturas"] = len(list(caps.glob("*.png")))
    return info


# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------

mcp = _Server(
    "framework-behave",
    instructions=(
        "Herramientas del framework de automatización Behave del Chapter QA. "
        "Antes de crear un step usa buscar_step; antes de ejecutar usa validar_features "
        "y validar_fila_excel; ejecuta siempre por tag con ejecutar_escenarios."
    ),
)


@mcp.tool()
def info_framework() -> dict:
    """Resumen del framework: tipo (web/api), rutas, configuración, tags, archivos Excel
    y problemas detectados (errores de sintaxis, steps duplicados, secretos en código).
    Úsalo al iniciar cualquier tarea sobre el repo."""
    import configparser

    modo = _modo()
    steps, errores = _cargar_steps()
    features = _leer_features()

    config: dict[str, Any] = {}
    for nombre in ("browser.properties", "service.properties", "database.properties"):
        ruta = ROOT / nombre
        if ruta.exists():
            cp = configparser.ConfigParser()
            try:
                cp.read(ruta, encoding="utf-8")
            except Exception:
                continue
            for seccion in cp.sections():
                for k, v in cp.items(seccion):
                    if nombre == "database.properties" and k.lower() != "ejecutar":
                        continue  # nunca exponer credenciales ni hosts de BD
                    config[f"{nombre}:{k}"] = "***" if _es_sensible(k) else v

    tags: dict[str, int] = {}
    for f in features:
        for e in f["escenarios"]:
            for t in set(f.get("tags", []) + e["tags"]):
                tags[t] = tags.get(t, 0) + 1

    excels = []
    if EXCEL_DIR.exists():
        for p in sorted(EXCEL_DIR.glob("*.xlsx")):
            try:
                wb, _ = _abrir_excel(p.name)
                excels.append({"archivo": p.name, "hojas": wb.sheetnames})
                wb.close()
            except Exception as e:  # noqa: BLE001
                excels.append({"archivo": p.name, "error": str(e)})

    secretos = []
    for py in (ROOT / "src").rglob("*.py"):
        if "site-packages" in py.parts:
            continue
        for i, linea in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if re.search(r"""\b(account_key|password|passwd|secret|client_secret|token|api_key)\s*=\s*['"][^'"]{8,}['"]""", linea, re.I):
                secretos.append(f"{_rel(py)}:{i}")

    return {
        "tipo_framework": modo,
        "raiz": str(ROOT),
        "python": sys.version.split()[0],
        "comando_ejecucion": "behave --tags=@<Tag>",
        "rutas": {
            "features": _rel(FEATURES),
            "steps": _rel(STEPS),
            "pages": "src/test/pages" if modo == "web" else None,
            "excel": _rel(EXCEL_DIR),
            "reportes": _rel(REPORTS),
        },
        "configuracion": config,
        "features": len(features),
        "escenarios": sum(len(f["escenarios"]) for f in features),
        "steps_definidos": len(steps),
        "tags": dict(sorted(tags.items(), key=lambda kv: -kv[1])),
        "excel": excels,
        "problemas": {
            "errores_sintaxis_steps": errores,
            "steps_duplicados": _duplicados(steps),
            "posibles_secretos_en_codigo": secretos,
        },
    }


@mcp.tool()
def listar_steps(filtro: str = "") -> dict:
    """Catálogo de steps definidos (tipo, patrón, archivo:línea, función).
    'filtro' busca por texto dentro del patrón (opcional)."""
    steps, errores = _cargar_steps()
    if filtro:
        f = filtro.lower()
        steps = [s for s in steps if f in s["patron"].lower()]
    return {"total": len(steps), "steps": steps, "errores_sintaxis": errores}


@mcp.tool()
def buscar_step(texto: str, tipo: str = "") -> dict:
    """Indica si ya existe un step que cubra la línea de Gherkin 'texto'
    (sin la palabra Given/When/Then). 'tipo' opcional: given, when o then.
    Devuelve coincidencias exactas o los steps más parecidos para reutilizar."""
    steps, errores = _cargar_steps()
    texto = re.sub(r"^(given|when|then|and|but|dado|cuando|entonces|y|pero)\s+", "", texto.strip(), flags=re.I)
    tipo_n = tipo.lower().strip() or None
    exactas = _coincidencias(texto, tipo_n, steps)
    if not exactas:  # PowerShell elimina las comillas internas al llamar a Python
        sin_comillas = texto.replace('"', "").replace("'", "")
        exactas = [{**s, "tipo_compatible": tipo_n is None or s["tipo"] in (tipo_n, "step")}
                   for s in steps if _patron_a_regex(s["patron"].replace('"', "").replace("'", "")).match(sin_comillas)]
    if exactas:
        return {
            "existe": True,
            "coincidencias": exactas,
            "indicacion": "Reutiliza este step con el texto EXACTO del patrón; no crees uno nuevo.",
        }
    patrones = [s["patron"] for s in steps]
    parecidos = difflib.get_close_matches(texto, patrones, n=5, cutoff=0.45)
    return {
        "existe": False,
        "parecidos": [s for p in parecidos for s in steps if s["patron"] == p],
        "indicacion": "No existe. Si un parecido sirve, ajusta el Gherkin a ese texto; si no, crea el step nuevo.",
        "errores_sintaxis": errores,
    }


@mcp.tool()
def validar_features(tag: str = "", usar_behave: bool = False) -> dict:
    """Revisa los .feature contra los steps: pasos sin definir, steps duplicados,
    errores de sintaxis y escenarios sin tag de datos (@xc-/@pg-).
    'tag' limita la revisión a escenarios con ese tag. Con usar_behave=True además
    corre 'behave --dry-run' (no abre navegador ni llama servicios) para detectar
    errores de importación."""
    steps, errores = _cargar_steps()
    features = _leer_features()
    tag_n = ("@" + tag.lstrip("@")).lower() if tag else ""
    sin_definir, avisos = [], []
    revisados = 0
    for f in features:
        for e in f["escenarios"]:
            tags = [t.lower() for t in f.get("tags", []) + e["tags"]]
            if tag_n and tag_n not in tags:
                continue
            revisados += 1
            todos = f.get("tags", []) + e["tags"]
            usa_datos = any("{datos}" in s["patron"] for p in e["pasos"] for s in _coincidencias(p["texto"].replace("<datos>", "1"), None, steps))
            if usa_datos or any("<datos>" in p["texto"] for p in e["pasos"]):
                if not (_tag_valor(todos, "xc-") and _tag_valor(todos, "pg-")):
                    avisos.append(f'{f["archivo"]}:{e["linea"]} "{e["nombre"]}" usa <datos> pero le falta @xc-<excel> o @pg-<hoja>')
            if not e["tags"] and not f.get("tags"):
                avisos.append(f'{f["archivo"]}:{e["linea"]} "{e["nombre"]}" no tiene tags: no se podrá ejecutar por tag')
            for p in e["pasos"]:
                texto = re.sub(r"<[^<>]+>", "X", p["texto"])
                if not _coincidencias(texto, p["tipo"], steps) and not _coincidencias(p["texto"], p["tipo"], steps):
                    sin_definir.append({
                        "ubicacion": f'{f["archivo"]}:{p["linea"]}',
                        "escenario": e["nombre"],
                        "paso": f'{p["keyword"]} {p["texto"]}',
                    })
    salida: dict[str, Any] = {
        "escenarios_revisados": revisados,
        "pasos_sin_definir": sin_definir,
        "steps_duplicados": _duplicados(steps),
        "errores_sintaxis_steps": errores,
        "avisos": avisos,
        "ok": not (sin_definir or errores or _duplicados(steps)),
    }
    if usar_behave:
        cmd = [sys.executable, "-m", "behave", "--dry-run", "--no-summary", "-f", "plain", "--no-color"]
        if tag:
            cmd.append(f"--tags=@{tag.lstrip('@')}")
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
        try:
            r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180, encoding="utf-8", errors="ignore")
            salida["behave_dry_run"] = {
                "codigo_salida": r.returncode,
                "salida": _recortar(_enmascarar((r.stdout or "")[-3000:] + "\n" + (r.stderr or "")[-3000:]), 4000),
            }
        except Exception as ex:  # noqa: BLE001
            salida["behave_dry_run"] = {"error": str(ex)}
    return salida


@mcp.tool()
def leer_excel(archivo: str, hoja: str = "", fila: int = 0, max_filas: int = 5) -> dict:
    """Lee los datos de prueba de src/test/resources/data/excel.
    Sin 'hoja' lista las hojas. Con 'hoja' devuelve columnas y filas.
    'fila' usa la misma convención que el framework: "<datos>"=1 es la primera fila
    debajo del encabezado. Los valores sensibles (claves, tokens) se enmascaran."""
    wb, ruta = _abrir_excel(archivo)
    try:
        if not hoja:
            return {"archivo": ruta.name, "hojas": wb.sheetnames}
        encabezados, datos = _filas_hoja(wb, hoja)
        if fila:
            if fila < 1 or fila > len(datos):
                return {"error": f"La fila {fila} no existe; la hoja tiene {len(datos)} filas de datos"}
            return {"archivo": ruta.name, "hoja": hoja, "columnas": encabezados, "fila": fila, "datos": _enmascarar_fila(datos[fila - 1])}
        return {
            "archivo": ruta.name,
            "hoja": hoja,
            "columnas": encabezados,
            "total_filas": len(datos),
            "primeras_filas": [{"fila": i + 1, **_enmascarar_fila(d)} for i, d in enumerate(datos[: max(1, min(max_filas, 20))])],
        }
    finally:
        wb.close()


def _validar_web(enc: list[str], d: dict, todas: list[dict] | None = None) -> tuple[list[str], list[str]]:
    errores, avisos = [], []
    for col in ("Ejecutar", "Escenario", "url"):
        if col not in enc:
            errores.append(f"Falta la columna '{col}'")
    if d.get("Ejecutar", "").upper() not in ("SI", "NO"):
        errores.append(f"'Ejecutar' debe ser SI o NO (tiene '{d.get('Ejecutar', '')}')")
    if d.get("url") and not d["url"].lower().startswith(("http://", "https://", "{{")):
        errores.append("'url' debe empezar con {{baseUrl}} (recomendado) o con http:// o https://")
    elif d.get("url", "").lower().startswith(("http://", "https://")):
        avisos.append("'url' escrita a mano: usa {{baseUrl}}/ruta para que funcione en todos los ambientes")
    for col in ("Precondiciones", "Resultado_Esperado"):
        if col in enc and not d.get(col):
            avisos.append(f"'{col}' vacío: la evidencia Word saldrá incompleta")
    caso = d.get("Caso de Prueba", "")
    if re.match(r"^\s*[A-Z][A-Z0-9]+-\d+\b", caso or ""):
        avisos += _avisos_clave_xray(caso, [f.get("Caso de Prueba", "") for f in (todas or [])])
    else:
        avisos += _avisos_clave_xray(d.get("Escenario", ""), [f.get("Escenario", "") for f in (todas or [])])
    return errores, avisos


def _metodos_soportados_api() -> tuple[str, ...]:
    """Lee util_api.py: la versión mejorada declara METODOS_CON_BODY (PATCH y DELETE incluidos)."""
    util = ROOT / "src" / "test" / "library" / "util_api.py"
    texto = util.read_text(encoding="utf-8", errors="ignore") if util.exists() else ""
    m = re.search(r"METODOS_CON_BODY\s*=\s*\[([^\]]*)\]", texto)
    if m:
        return ("GET",) + tuple(re.findall(r"[A-Z]+", m.group(1)))
    return ("GET", "POST", "PUT")


def _variables_ambientes() -> set:
    """Nombres de variables definidos en config/ambientes.json (todos los ambientes)."""
    ruta = ROOT / "config" / "ambientes.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return {k for amb in datos.values() if isinstance(amb, dict) for k in amb} | {"ambiente"}
    except Exception:  # noqa: BLE001 - sin archivo de ambientes: no hay variables conocidas
        return {"ambiente"}


def _sin_variables(texto: str) -> str:
    """Reemplaza {{x}} por un valor neutro para poder validar el JSON antes de resolver las variables."""
    texto = re.sub(r'"\{\{[^}]+\}\}"', '"x"', texto)
    return re.sub(r"\{\{[^}]+\}\}", "0", texto)


def _avisos_clave_xray(escenario: str, escenarios_hoja: list[str]) -> list[str]:
    """El 'Escenario' empieza con la clave del caso en Xray (TAP-4234 - ...): nombra la evidencia y se
    usa para actualizar la Test Execution. Sin clave, el caso no llega a Xray ni al paquete de SharePoint."""
    m = re.match(r"^\s*([A-Z][A-Z0-9]+-\d+)\b", escenario or "")
    if not m:
        return ["'Escenario' no empieza con la clave del caso en Xray (p. ej. 'TAP-4234 - ...'): "
                "no se podrá actualizar en Xray ni ordenar su evidencia"]
    repetidas = sum(1 for e in escenarios_hoja if re.match(rf"^\s*{re.escape(m.group(1))}\b", e or ""))
    if repetidas > 1:
        return [f"La clave {m.group(1)} aparece en {repetidas} filas de la hoja: en Xray será un solo caso "
                "(FAILED si falla cualquiera)"]
    return []


def _validar_api(enc: list[str], d: dict, todas: list[dict]) -> tuple[list[str], list[str]]:
    errores, avisos = [], []
    requeridas = ["Ejecucion", "Escenario", "Iteracion", "Api", "Endpoint", "Request Type",
                  "Expected Status Code", "Headers", "Params", "Body", "Expected Headers Response",
                  "Expected Response", "Expected Content_1", "AditionalHeaders", "aditionalBody"]
    for col in requeridas:
        if col not in enc:
            errores.append(f"Falta la columna '{col}' (util_api.py la lee siempre y fallará con KeyError)")
    if d.get("Ejecucion", "").upper() not in ("SI", "NO"):
        errores.append(f"'Ejecucion' debe ser SI o NO (tiene '{d.get('Ejecucion', '')}')")
    if d.get("Endpoint") and not d["Endpoint"].lower().startswith(("http://", "https://", "{{")):
        errores.append("'Endpoint' debe ser una URL completa (http/https) o empezar con {{baseUrl}}")
    # Variables {{...}}: deben existir en config/ambientes.json, ser dinámicas o guardarse con GlobalVariables
    usadas = set()
    for valor in d.values():
        usadas |= set(re.findall(r"\{\{\s*([A-Za-z_]\w*(?:-[A-Za-z_]\w*)*)", str(valor)))
    if usadas:
        conocidas = {"hoy", "uuid", "aleatorio"} | _variables_ambientes()
        for f in todas:
            for g in (f.get("GlobalVariables") or "").split(","):
                if g.strip():
                    conocidas.add(g.split("=", 1)[0].strip())
        desconocidas = sorted(usadas - conocidas)
        if desconocidas:
            avisos.append(f"Variables {', '.join('{{'+v+'}}' for v in desconocidas)} no están en config/ambientes.json ni se guardan "
                          "en esta hoja: deben guardarse (GlobalVariables) en un escenario que corra antes")
    metodo = d.get("Request Type", "").strip().upper()
    soportados = _metodos_soportados_api()
    if metodo not in soportados:
        errores.append(f"'Request Type' = '{metodo}': util_api.enviar_peticion solo soporta {', '.join(soportados)}")
    if not re.fullmatch(r"\d{3}", d.get("Expected Status Code", "").split(".")[0]):
        errores.append("'Expected Status Code' debe ser un código HTTP de 3 dígitos")
    if not d.get("Api"):
        avisos.append("'Api' vacío: el Word de evidencia se llamará '.docx'")
    avisos += _avisos_clave_xray(d.get("Escenario", ""), [f.get("Escenario", "") for f in todas])
    for col in ("Headers", "Params"):
        for linea in (d.get(col) or "").splitlines():
            if linea.strip() and ": " not in linea:
                errores.append(f"'{col}': la línea '{_enmascarar(linea)}' debe tener el formato 'Clave: Valor' (con espacio tras ':')")
            if col == "Params" and linea.count(": ") > 1:
                errores.append(f"'Params': '{_enmascarar(linea)}' tiene más de un ': ' y rompe el split del framework")
    body = d.get("Body", "")
    es_multipart = "multipart/form-data" in (d.get("Headers") or "").lower()
    if body and es_multipart:
        carpeta = ROOT / "src" / "test" / "resources" / "data" / "archivos"
        for linea in body.splitlines():
            if not linea.strip():
                continue
            if ": " not in linea:
                errores.append(f"'Body' multipart: la línea '{_enmascarar(linea)}' debe ser 'campo: valor' o 'campo: @archivo'")
                continue
            valor = linea.split(": ", 1)[1].strip()
            if valor.startswith("@"):
                nombre = valor[1:].split(";type=")[0].strip()
                if "{{" not in nombre and not (carpeta / nombre).is_file():
                    errores.append(f"'Body' multipart: no existe src/test/resources/data/archivos/{nombre}")
        if metodo == "GET":
            errores.append("multipart/form-data necesita POST, PUT o PATCH")
    elif es_multipart:
        errores.append("Headers dice multipart/form-data pero 'Body' está vacío (una línea por campo o archivo)")
    elif body:
        if body.lstrip().startswith("<"):
            import xml.dom.minidom as md
            try:
                md.parseString(body)
            except Exception as e:  # noqa: BLE001
                errores.append(f"'Body' XML inválido: {e}")
        else:
            try:
                json.loads(_sin_variables(body))
            except json.JSONDecodeError as e:
                errores.append(f"'Body' no es JSON válido: {e}")
        if metodo == "GET":
            avisos.append("GET con Body: el framework lo envía como data; confirma que el servicio lo espera")
    for col in ("Expected Headers Response", "Expected Response"):
        if d.get(col):
            try:
                json.loads(_sin_variables(d[col]))
            except json.JSONDecodeError as e:
                errores.append(f"'{col}' debe ser JSON válido (usa \"*\" para validar solo la llave): {e}")
    if d.get("Expected Schema"):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        anterior = os.getcwd()
        try:
            os.chdir(ROOT)
            import importlib
            esquema_json = importlib.import_module("src.test.library.esquema_json")
            esquema_json.CARPETA_SCHEMAS = str(ROOT / "src" / "test" / "resources" / "data" / "schemas")
            from jsonschema import Draft202012Validator
            Draft202012Validator.check_schema(esquema_json.cargar(d["Expected Schema"]))
        except Exception as e:  # noqa: BLE001 - se informa como error de la fila
            errores.append(f"'Expected Schema' inválido: {e}")
        finally:
            os.chdir(anterior)
    adicionales = [k.strip() for k in (d.get("AditionalHeaders") or "").split(",") if k.strip()]
    adicionales += [k.strip() for k in (d.get("aditionalBody") or "").split(",") if k.strip()]
    if adicionales:
        globales = {g.split("=", 1)[0].strip() for f in todas for g in (f.get("GlobalVariables") or "").split(",") if g.strip()}
        faltan = [a for a in adicionales if a not in globales]
        if faltan:
            avisos.append(f"Variables {faltan} no se guardan con 'GlobalVariables' en esta hoja: deben venir de un escenario previo (p. ej. @pg-token) en la MISMA ejecución")
    return errores, avisos


@mcp.tool()
def validar_fila_excel(archivo: str, hoja: str, fila: int) -> dict:
    """Valida una fila de datos ANTES de ejecutar (columnas obligatorias, SI/NO,
    URL, formato de Headers/Params, JSON de Body y respuestas esperadas, variables
    globales encadenadas). 'fila' = valor de <datos> en el Examples."""
    wb, ruta = _abrir_excel(archivo)
    try:
        enc, datos = _filas_hoja(wb, hoja)
    finally:
        wb.close()
    if fila < 1 or fila > len(datos):
        return {"valida": False, "errores": [f"La fila {fila} no existe; hay {len(datos)} filas de datos"]}
    d = datos[fila - 1]
    errores, avisos = (_validar_web(enc, d, datos) if _modo() == "web" else _validar_api(enc, d, datos))
    if d.get("Ejecutar", d.get("Ejecucion", "")).upper() == "NO":
        avisos.append("La fila está marcada como NO: el escenario se reportará como skipped")
    return {"archivo": ruta.name, "hoja": hoja, "fila": fila, "valida": not errores, "errores": errores, "avisos": avisos}


# ---------------------------------------------------------------------------
# Escritura en el Excel (solo API): vista previa + confirmación del QE
# ---------------------------------------------------------------------------

RESPALDOS = ROOT / ".respaldo_excel"
PLANTILLAS = {"api": "plantilla_api.xlsx", "web": "plantilla_web.xlsx"}


def _codigo_confirmacion(ruta: Path, hoja: str, filas: list[dict], crear: bool) -> str:
    import hashlib

    estado = ruta.stat().st_mtime_ns if ruta.exists() else 0   # si el Excel cambia, el código ya no sirve
    texto = json.dumps([ruta.name, hoja, filas, crear, estado], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:8].upper()


def _datos_hoja_ultima(ws) -> int:
    """Número de la última fila (de Excel) con algún valor."""
    ultima = 1
    for fila in ws.iter_rows(min_row=2):
        if any(c.value not in (None, "") for c in fila):
            ultima = fila[0].row
    return ultima


@mcp.tool()
def agregar_filas_excel(archivo: str, hoja: str, filas: list[dict], crear: bool = False, confirmacion: str = "") -> dict:
    """Agrega filas de datos AL FINAL de una hoja del Excel. Nunca modifica ni borra filas existentes.

    SIEMPRE en dos pasos:
      1. Llama SIN 'confirmacion'. Valida cada fila y devuelve 'vista_previa' y 'codigo_confirmacion'.
         Muestra la vista previa al QE (escenario, método, endpoint, status) y PREGÚNTALE si la aprueba.
      2. SOLO si el QE responde que sí en el chat, llama otra vez con las MISMAS filas y
         confirmacion=<codigo_confirmacion>. Nunca confirmes por tu cuenta.
    'filas': lista de objetos {columna: valor} con los nombres exactos de las columnas de la hoja.
    'Iteracion' vacía se numera sola por Api. 'Ejecucion' vacía = SI.
    crear=True: si el archivo no existe se crea desde la plantilla (plantilla_api.xlsx o plantilla_web.xlsx);
    si la hoja no existe se crea con los encabezados de la plantilla. En el framework web, una hoja nueva
    agrega al final las columnas de datos de la pantalla que traigan las filas (p. ej. fecha_nacimiento).
    Antes de escribir guarda un respaldo en .respaldo_excel/."""
    import openpyxl
    from openpyxl.styles import Alignment

    if not filas:
        return {"ok": False, "motivo": "No hay filas para agregar"}
    if len(filas) > 50:
        return {"ok": False, "motivo": "Máximo 50 filas por llamada: divide la entrega"}
    nombre = archivo if archivo.lower().endswith(".xlsx") else archivo + ".xlsx"
    ruta = (EXCEL_DIR / nombre).resolve()
    if EXCEL_DIR.resolve() not in ruta.parents:
        return {"ok": False, "motivo": "Ruta de Excel fuera de src/test/resources/data/excel"}
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,31}", hoja):
        return {"ok": False, "motivo": "Nombre de hoja inválido: solo letras, números, - y _ (máx. 31), sin espacios"}
    PLANTILLA_API = PLANTILLAS[_modo()]
    plantilla = EXCEL_DIR / PLANTILLA_API
    if not ruta.exists() and not crear:
        return {"ok": False, "motivo": f"No existe {nombre}. Usa crear=true para crearlo desde {PLANTILLA_API}"}
    if not ruta.exists() and not plantilla.exists():
        return {"ok": False, "motivo": f"No existe {PLANTILLA_API} para crear el archivo nuevo"}

    # Encabezados y filas actuales
    origen = ruta if ruta.exists() else plantilla
    wb = openpyxl.load_workbook(origen, read_only=True, data_only=True)
    try:
        hoja_nueva = hoja not in wb.sheetnames
        if hoja_nueva and not crear:
            return {"ok": False, "motivo": f"La hoja '{hoja}' no existe en {nombre}. Hojas: {wb.sheetnames}. Usa crear=true para crearla"}
        if hoja_nueva:
            wb_p = openpyxl.load_workbook(plantilla, read_only=True, data_only=True)
            try:
                enc, existentes = _filas_hoja(wb_p, "Ejemplo")[0], []
            finally:
                wb_p.close()
        else:
            enc, existentes = _filas_hoja(wb, hoja)
    finally:
        wb.close()

    if hoja_nueva and _modo() == "web":   # columnas de datos propias de la pantalla
        for f in filas:
            for c in f:
                if c not in enc:
                    enc.append(c)
    col_ejec = "Ejecucion" if "Ejecucion" in enc else "Ejecutar"

    # Normalizar y validar
    normalizadas, errores_filas = [], []
    for i, f in enumerate(filas, start=1):
        desconocidas = [c for c in f if c not in enc]
        if desconocidas:
            errores_filas.append({"fila_nueva": i, "errores": [f"Columnas que no existen en la hoja: {desconocidas}"]})
            continue
        d = {c: ("" if f.get(c) is None else str(f.get(c)).strip()) for c in enc}
        d[col_ejec] = (d.get(col_ejec) or "SI").upper()
        normalizadas.append(d)
    previas = list(existentes)
    for d in normalizadas:
        if "Iteracion" in enc and not d.get("Iteracion"):
            d["Iteracion"] = str(sum(1 for x in previas if x.get("Api") == d.get("Api")) + 1)
        previas.append(d)
    todas = existentes + normalizadas
    for i, d in enumerate(normalizadas, start=1):
        errores, avisos = (_validar_web(enc, d, todas) if _modo() == "web" else _validar_api(enc, d, todas))
        if errores or avisos:
            errores_filas.append({"fila_nueva": i, "escenario": d.get("Escenario"), "errores": errores, "avisos": avisos})
    bloqueantes = [e for e in errores_filas if e.get("errores")]
    inicio = len(existentes) + 1
    vista = [{"datos": inicio + i, "Escenario": d.get("Escenario"), "Request Type": d.get("Request Type"),
              "Endpoint": d.get("Endpoint") or d.get("url"), "Expected Status Code": d.get("Expected Status Code"),
              "Ejecucion": d.get(col_ejec)} for i, d in enumerate(normalizadas)]
    if bloqueantes:
        return {"ok": False, "escrito": False, "motivo": "Hay filas con errores: corrígelas antes de pedir confirmación",
                "detalle": errores_filas}

    codigo = _codigo_confirmacion(ruta, hoja, filas, crear)
    examples = "\n".join(f"      | {n['datos']:>5} |" for n in vista)
    if not confirmacion:
        return {
            "ok": True, "escrito": False,
            "accion": ("crear archivo " + nombre + " y " if not ruta.exists() else "") + ("crear hoja " if hoja_nueva else "agregar a la hoja ") + hoja,
            "vista_previa": vista,
            "avisos": errores_filas,
            "codigo_confirmacion": codigo,
            "siguiente_paso": "Muestra la vista previa al QE y pregúntale si la aprueba. Solo si responde que sí, "
                              "vuelve a llamar con las mismas filas y confirmacion=" + codigo,
        }
    if confirmacion.strip().upper() != codigo:
        return {"ok": False, "escrito": False,
                "motivo": "El código no coincide: las filas o el Excel cambiaron desde la vista previa. Pide una vista previa nueva."}

    # Escribir (respaldo primero)
    import shutil
    from datetime import datetime

    if ruta.exists():
        RESPALDOS.mkdir(exist_ok=True)
        respaldo = RESPALDOS / f"{ruta.stem}-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        shutil.copy2(ruta, respaldo)
    else:
        shutil.copy2(plantilla, ruta)
        respaldo = None
    archivo_nuevo = respaldo is None
    try:
        wb = openpyxl.load_workbook(ruta)
        if hoja_nueva:
            base = wb["Ejemplo"] if "Ejemplo" in wb.sheetnames else None
            ws = wb.copy_worksheet(base) if base is not None else wb.create_sheet(hoja)
            ws.title = hoja
            if base is not None:
                ws.delete_rows(2, ws.max_row)
                if archivo_nuevo:          # el archivo nuevo no hereda la fila de ejemplo de la plantilla
                    wb.remove(base)
            else:
                ws.append(enc)
        else:
            ws = wb[hoja]
        enc_hoja = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
        if hoja_nueva:   # columnas de datos nuevas de la pantalla (solo al crear la hoja)
            from copy import copy
            modelo = ws.cell(row=1, column=1)
            for col in [c for c in enc if c not in enc_hoja]:
                celda = ws.cell(row=1, column=len(enc_hoja) + 1, value=col)
                celda.font, celda.fill = copy(modelo.font), copy(modelo.fill)
                enc_hoja.append(col)
        fila_excel = _datos_hoja_ultima(ws) + 1
        for d in normalizadas:
            for col, valor in d.items():
                if col in enc_hoja and valor != "":
                    celda = ws.cell(row=fila_excel, column=enc_hoja.index(col) + 1, value=valor)
                    celda.alignment = Alignment(wrap_text=True, vertical="top")
            fila_excel += 1
        wb.save(ruta)
    except PermissionError:
        return {"ok": False, "escrito": False,
                "motivo": f"No se pudo guardar {nombre}: está abierto en Excel. Ciérralo y vuelve a confirmar."}
    return {
        "ok": True, "escrito": True, "archivo": nombre, "hoja": hoja,
        "filas_agregadas": vista,
        "respaldo": _rel(respaldo) if respaldo else None,
        "examples": "    Examples:\n      | datos |\n" + examples,
        "siguiente_paso": "Valida con validar_fila_excel y agrega estos números al Examples del escenario (tags @xc-"
                          + ruta.stem + " @pg-" + hoja + ").",
    }


# ---------------------------------------------------------------------------
# Xray Cloud y evidencias: el QE registra casos y crea la Test Execution en Xray;
# el framework solo actualiza estados (con confirmación) y ordena las evidencias.
# ---------------------------------------------------------------------------


def _modulo_xray(nombre: str = "xray_cloud"):
    import importlib.util

    carpeta = ROOT / "tools" / "xray"
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))
    os.environ.setdefault("FRAMEWORK_ROOT", str(ROOT))
    spec = importlib.util.spec_from_file_location(nombre, carpeta / f"{nombre}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@mcp.tool()
def preparar_evidencias(test_plan: str, test_execution: str) -> dict:
    """Arma la carpeta de evidencias de la ÚLTIMA ejecución con la estructura del SharePoint:
    evidencias_sharepoint/<TestPlan>/<TestExecution>/<CLAVE>.docx + resumen.md y resumen.csv.
    Solo copia archivos locales (no se conecta a nada). La clave sale del 'Escenario' (TAP-4234 - ...)."""
    ev = _modulo_xray("evidencias")
    try:
        return {"ok": True, **ev.armar(test_plan.strip(), test_execution.strip())}
    except ev.xc.ErrorXray as e:
        return {"ok": False, "motivo": str(e)}


@mcp.tool()
def actualizar_test_execution(test_execution: str, adjuntar_evidencias: bool = True, confirmacion: str = "") -> dict:
    """Cambia en Xray el estado de los casos de una Test Execution QUE EL QE YA CREÓ, con el
    resultado de la última ejecución. Nunca crea casos ni Test Executions. SIEMPRE en dos pasos:
      1. Llama SIN 'confirmacion': lee la Test Execution y devuelve la vista previa
         (qué casos pasan a PASSED/FAILED, cuáles de la Test Execution no se ejecutaron,
         cuáles se ejecutaron pero no están en ella) y un 'codigo_confirmacion'.
         Muestra la vista previa al QE y PREGÚNTALE si actualiza.
      2. SOLO si el QE responde que sí en el chat, llama otra vez con confirmacion=<código>.
    Requiere XRAY_CLIENT_ID y XRAY_CLIENT_SECRET. Nunca pidas ni muestres esos valores."""
    import hashlib

    xc = _modulo_xray()
    clave = test_execution.strip().upper()
    try:
        token = xc.autenticar()
        payload, vista = xc.plan_de_actualizacion(clave, token, adjuntar_evidencias)
    except Exception as e:  # noqa: BLE001 - se informa al QE sin exponer credenciales
        return {"ok": False, "actualizado": False, "motivo": _enmascarar(str(e))}
    huella = json.dumps([vista, adjuntar_evidencias, xc.RUTA_RESULTADOS.stat().st_mtime_ns], sort_keys=True, default=str)
    codigo = hashlib.sha256(huella.encode()).hexdigest()[:8].upper()
    if not payload["tests"]:
        return {"ok": False, "actualizado": False, "vista_previa": vista, "motivo": "No hay casos para actualizar en esta Test Execution"}
    if not confirmacion:
        return {"ok": True, "actualizado": False, "vista_previa": vista, "codigo_confirmacion": codigo,
                "siguiente_paso": "Muestra la vista previa al QE y pregúntale si actualiza la Test Execution "
                                  f"{clave}. Solo si responde que sí, vuelve a llamar con confirmacion={codigo}"}
    if confirmacion.strip().upper() != codigo:
        return {"ok": False, "actualizado": False,
                "motivo": "El código no coincide: hubo una ejecución nueva o la Test Execution cambió. Pide una vista previa nueva."}
    try:
        respuesta = xc.importar(payload, token)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "actualizado": False, "motivo": _enmascarar(str(e))}
    salida = {"ok": True, "actualizado": True, "test_execution": respuesta.get("key", clave),
              "pasados": vista["pasados"], "fallidos": vista["fallidos"]}
    jira = xc.cargar_config().get("jiraUrl")
    if jira:
        salida["url"] = f"{jira.rstrip('/')}/browse/{salida['test_execution']}"
    return salida

@mcp.tool()
def ejecutar_escenarios(tag: str, timeout_min: int = 15) -> dict:
    """Ejecuta 'behave --tags=@<tag>' en el repo y devuelve el resumen
    (pasados, fallidos, paso que falló, mensaje y carpeta del reporte).
    Solo ejecuta por tag (nunca la suite completa) y respeta los tags bloqueados."""
    if not PERMITIR_EJECUCION:
        return {"ejecutado": False, "motivo": "La ejecución está deshabilitada (MCP_PERMITIR_EJECUCION=false)"}
    limpio = tag.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", limpio):
        return {"ejecutado": False, "motivo": "Tag inválido: usa un solo tag, p. ej. HU01 o Cotizador"}
    if limpio.lower() in TAGS_BLOQUEADOS:
        return {"ejecutado": False, "motivo": f"El tag @{limpio} está bloqueado para ejecución desde el agente"}
    timeout = max(1, min(timeout_min, TIMEOUT_MAX_MIN)) * 60
    cmd = [sys.executable, "-m", "behave", f"--tags=@{limpio}", "--no-capture", "--no-skipped"]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    inicio = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="ignore")
    except subprocess.TimeoutExpired:
        return {"ejecutado": True, "estado": "timeout", "motivo": f"Superó {timeout // 60} minutos"}
    duracion = round(time.time() - inicio, 1)
    data, fuente = _leer_json_resultados(desde=inicio)
    salida = {
        "ejecutado": True,
        "comando": f"behave --tags=@{limpio} --no-capture --no-skipped",
        "codigo_salida": r.returncode,
        "duracion_seg": duracion,
        "fuente_resultados": fuente,
        "resumen": _resumir_resultados(data) if data else None,
        "reporte": _ultima_carpeta_reporte(desde=inicio),
        "consola_final": _recortar(_enmascarar("\n".join((r.stdout or "").splitlines()[-60:])), 3500),
    }
    if r.stderr and r.stderr.strip():
        salida["errores_consola"] = _recortar(_enmascarar(r.stderr[-3000:]), 3000)
    if data is None:
        salida["aviso"] = "No se generó JSON de resultados: revisa 'errores_consola' (import, sintaxis o configuración)."
    return salida


@mcp.tool()
def ultimo_resultado() -> dict:
    """Resumen de la última ejecución: escenarios fallidos, paso, mensaje de error
    (enmascarado) y carpeta del reporte con evidencias. No ejecuta nada."""
    data, fuente = _leer_json_resultados()
    if not data:
        return {"encontrado": False, "motivo": "No hay New.pretty.output ni json.pretty.output legibles en la raíz"}
    archivo = ROOT / fuente
    return {
        "encontrado": True,
        "fuente": fuente,
        "fecha": time.strftime("%Y-%m-%d %H:%M", time.localtime(archivo.stat().st_mtime)),
        "resumen": _resumir_resultados(data),
        "reporte": _ultima_carpeta_reporte(),
    }





def _pagina():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pagina

    return pagina


def _crear_driver(headless: bool = True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opciones = Options()
    if headless:
        opciones.add_argument("--headless=new")
    for arg in ("--ignore-certificate-errors", "--window-size=1366,900", "--no-sandbox", "--disable-dev-shm-usage"):
        opciones.add_argument(arg)
    binario = os.environ.get("MCP_CHROME_BINARY") or os.environ.get("CHROME_BINARY")
    if binario:
        opciones.binary_location = binario
    driver_env = os.environ.get("MCP_CHROMEDRIVER") or os.environ.get("WEBDRIVER_PATH")
    if driver_env:
        return webdriver.Chrome(service=Service(driver_env), options=opciones)
    try:
        return webdriver.Chrome(options=opciones)  # Selenium Manager
    except Exception as primero:  # noqa: BLE001
        locales = sorted((ROOT / "src" / "test" / "resources" / "drivers" / "chrome").glob("*/chromedriver*"))
        locales = [p for p in locales if p.is_file() and p.suffix in ("", ".exe")]
        for driver in reversed(locales):
            try:
                return webdriver.Chrome(service=Service(str(driver)), options=opciones)
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError(f"No se pudo iniciar Chrome: {primero}") from primero


@mcp.tool()
def explorar_pagina(url: str, solo_visibles: bool = True, esperar_seg: int = 3) -> dict:
    """(Framework web) Abre la URL en Chrome headless con Selenium y lista los
    elementos interactivos con un locator sugerido en formato del framework
    (By.ID, By.NAME, By.CSS_SELECTOR, By.LINK_TEXT, By.XPATH). Solo lee la página:
    no hace clic ni escribe. Para pantallas detrás de login, pide al usuario el
    HTML o una captura, o explora tras autenticarse manualmente."""
    if _modo() != "web":
        return {"error": "explorar_pagina solo aplica al framework web"}
    if not re.match(r"^https?://", url.strip(), re.I) and not url.startswith("file://"):
        return {"error": "La URL debe empezar con http:// o https://"}
    driver = _crear_driver()
    try:
        driver.set_page_load_timeout(45)
        driver.get(url)
        time.sleep(max(0, min(esperar_seg, 15)))
        return _pagina().capturar(driver, solo_visibles)
    finally:
        driver.quit()


def _modulo_diseno():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import importlib

    modulo = importlib.import_module("src.test.library.diseno")
    modulo.RUTA_GUIAS = str(ROOT / "config" / "diseno")
    return modulo


@mcp.tool()
def revisar_diseno(url: str, guia: str = "hu01", pantalla: str = "inicial", viewport: str = "escritorio", esperar_seg: int = 3) -> dict:
    """(Framework web) Abre la URL y compara la pantalla con la guía de diseño config/diseno/<guia>.json
    (tipografía, colores, medidas, textos y disposición) en un viewport (escritorio, movil).
    Devuelve lo que NO cumple, con esperado y obtenido. Sirve para revisar rápido antes de escribir o
    ejecutar escenarios; para estados que requieren acciones (errores, resultado) usa los escenarios.
    'url' acepta {{baseUrl}} (se resuelve con el AMBIENTE actual)."""
    if _modo() != "web":
        return {"ok": False, "motivo": "Solo disponible en el framework web"}
    dis = _modulo_diseno()
    url = _resolver_url(url)
    driver = _crear_driver(headless=True)
    try:
        definicion = dis.cargar_guia(guia)
        driver.get(url)
        time.sleep(max(0, min(esperar_seg, 15)))   # carga inicial de la SPA (herramienta de diagnóstico)
        dis.preparar_viewport(driver, definicion, viewport)
        resultados = dis.evaluar(driver, definicion, pantalla, viewport)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
    finally:
        driver.quit()
    fallas = [r for r in resultados if not r["ok"]]
    return {"ok": not fallas, "url": url, "guia": guia, "pantalla": pantalla, "viewport": viewport,
            "puntos": len(resultados), "cumplen": len(resultados) - len(fallas), "no_cumplen": fallas[:40]}


@mcp.tool()
def extraer_estilos(url: str, selectores: list[str], viewport: str = "escritorio", esperar_seg: int = 3) -> dict:
    """(Framework web) Estilos calculados (fuente, tamaño, peso, color, fondo, bordes, radio) y medidas
    de los elementos indicados. '@id' busca [data-testid='id'] o #id. Úsalo sobre la PÁGINA DE DISEÑO
    (o Figma exportado) para armar config/diseno/<guia>.json, y sobre la app para comparar."""
    if _modo() != "web":
        return {"ok": False, "motivo": "Solo disponible en el framework web"}
    dis = _modulo_diseno()
    props = ["font-family", "font-size", "font-weight", "color", "background-color", "border-top-width",
             "border-top-color", "border-top-left-radius", "padding-top", "padding-left"]
    url = _resolver_url(url)
    driver = _crear_driver(headless=True)
    try:
        driver.get(url)
        time.sleep(max(0, min(esperar_seg, 15)))
        dis.preparar_viewport(driver, {"viewports": {"escritorio": [1280, 900], "movil": [390, 844]}}, viewport)
        salida = {}
        for sel in selectores[:30]:
            elementos = driver.execute_script(dis._JS_MEDIR, dis.selector_css(sel), props, False)
            if not elementos:
                salida[sel] = "no encontrado"
                continue
            e = elementos[0]
            estilos = {k: (dis._hex(v) if "color" in k else v) for k, v in e["estilos"].items()}
            salida[sel] = {"texto": _recortar(e["texto"], 120), "estilos": estilos,
                           "ancho": round(e["rect"]["ancho"], 1), "alto": round(e["rect"]["alto"], 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
    finally:
        driver.quit()
    return {"ok": True, "url": url, "viewport": viewport, "elementos": salida}


def _resolver_url(url: str) -> str:
    """{{baseUrl}} -> URL del AMBIENTE actual (config/ambientes.json)."""
    if "{{" not in url:
        return url
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    anterior = os.getcwd()
    try:
        os.chdir(ROOT)
        import importlib

        ca = importlib.import_module("src.test.library.config_ambiente")
        ca.RUTA_AMBIENTES = str(ROOT / "config" / "ambientes.json")
        resuelta, faltan = ca.resolver(url, {}, ca.cargar_ambiente())
    finally:
        os.chdir(anterior)
    if faltan:
        raise ValueError(f"Variables sin valor en la URL: {faltan}")
    return resuelta


@mcp.tool()
def explorar_tras_steps(tag: str, hasta_paso: str = "", solo_visibles: bool = True, timeout_min: int = 10) -> dict:
    """(Framework web) Para pantallas detrás del login u otros pasos previos: ejecuta un
    escenario EXISTENTE por su tag (con su navegador y sus datos de Excel) y captura los
    elementos de la pantalla con locators sugeridos justo después del paso cuyo texto
    contiene 'hasta_paso' (o al final del escenario si se omite). Ej.: tag='Login',
    hasta_paso='Se verifica el Login correcto' para obtener los locators del dashboard."""
    if _modo() != "web":
        return {"error": "explorar_tras_steps solo aplica al framework web"}
    if not PERMITIR_EJECUCION:
        return {"ejecutado": False, "motivo": "La ejecución está deshabilitada (MCP_PERMITIR_EJECUCION=false)"}
    limpio = tag.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_\-\.]+", limpio):
        return {"ejecutado": False, "motivo": "Tag inválido: usa un solo tag, p. ej. Login"}
    if limpio.lower() in TAGS_BLOQUEADOS:
        return {"ejecutado": False, "motivo": f"El tag @{limpio} está bloqueado para ejecución desde el agente"}
    import tempfile

    salida = Path(tempfile.gettempdir()) / f"mcp_captura_{os.getpid()}_{int(time.time())}.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8",
           "MCP_CAPTURA_SALIDA": str(salida), "MCP_HASTA_PASO": hasta_paso,
           "MCP_SOLO_VISIBLES": "1" if solo_visibles else "0"}
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "explorador_behave.py"),
           f"--tags=@{limpio}", "--no-capture", "--no-skipped"]
    timeout = max(1, min(timeout_min, TIMEOUT_MAX_MIN)) * 60
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="ignore")
    except subprocess.TimeoutExpired:
        return {"ejecutado": True, "estado": "timeout"}
    if not salida.exists():
        hooks = [l.strip() for l in (r.stdout or "").splitlines() if "HOOK-ERROR" in l]
        return {
            "ejecutado": True,
            "capturado": False,
            "errores_hooks": [_recortar(_enmascarar(h), 400) for h in hooks[:5]],
            "pista": "Si hay HOOK-ERROR in before_scenario, el navegador no pudo abrirse (driver/red)." if any("before_scenario" in h for h in hooks) else "",
            "motivo": "No se llegó a capturar: el escenario no se ejecutó (¿fila con Ejecutar=NO, tag sin escenarios?) o falló antes del paso indicado.",
            "consola_final": _recortar(_enmascarar("\n".join((r.stdout or "").splitlines()[-40:])), 2500),
            "errores_consola": _recortar(_enmascarar((r.stderr or "")[-2000:]), 2000),
        }
    datos = json.loads(salida.read_text(encoding="utf-8"))
    try:
        salida.unlink()
    except OSError:
        pass
    datos["ejecutado"] = True
    datos["capturado"] = True
    if hasta_paso and str(datos.get("capturado_en", "")).startswith("fin"):
        datos["aviso"] = f"Ningún paso contiene '{hasta_paso}': se capturó al final del escenario. Revisa el texto con listar_steps."
    return datos


LINEA_BASE = Path(__file__).resolve().parent / "linea_base_buenas_practicas.json"


# ---------------------------------------------------------------------------
# Diagnóstico del entorno (ambiente virtual, dependencias, navegador, git, disco)
# ---------------------------------------------------------------------------

def _comando(args: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr or "").strip()
    except Exception:  # noqa: BLE001 - herramienta ausente: se informa como vacío
        return ""


def _version_chrome() -> str:
    if os.name == "nt":
        for clave in (r"HKCU\Software\Google\Chrome\BLBeacon", r"HKLM\Software\Google\Chrome\BLBeacon"):
            salida = _comando(["reg", "query", clave, "/v", "version"])
            m = re.search(r"version\s+REG_SZ\s+([\d.]+)", salida)
            if m:
                return m.group(1)
        return ""
    for exe in ("google-chrome", "chromium", "chromium-browser"):
        m = re.search(r"([\d]+\.[\d.]+)", _comando([exe, "--version"]))
        if m:
            return m.group(1)
    return ""


def _requisitos_vs_instalado(archivo: Path) -> dict:
    from importlib import metadata

    faltantes, distintos = [], []
    for linea in archivo.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.split("#")[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=)?\s*([\w.]+)?", linea)
        if not linea or not m:
            continue
        paquete, operador, version = m.group(1), m.group(2), m.group(3)
        try:
            instalada = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            faltantes.append(paquete)
            continue
        if operador == "==" and version and instalada != version:
            distintos.append(f"{paquete}: requiere {version}, instalada {instalada}")
    return {"archivo": _rel(archivo), "faltantes": faltantes, "version_distinta": distintos}


@mcp.tool()
def diagnosticar_entorno() -> dict:
    """Revisa el entorno del QE antes de trabajar: versión de Python y si corre dentro del
    ambiente virtual del proyecto, si ese venv fue copiado de otra PC, dependencias faltantes
    o con otra versión, navegador/driver (web), estado de git (rama, cambios sin subir,
    hook de calidad) y espacio en disco. Devuelve 'problemas' con la acción para cada uno.
    Úsalo cuando algo no instala, no importa, no abre el navegador o antes de un commit."""
    import platform
    import shutil

    problemas: list[dict] = []

    def problema(que: str, accion: str) -> None:
        problemas.append({"problema": que, "accion": accion})

    # --- Python y venv ---
    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    py = {"version": platform.python_version(), "ejecutable": sys.executable, "en_venv": en_venv}
    if sys.version_info[:2] != (3, 12):
        problema(f"Python {py['version']}: el framework está probado con 3.12 (pillow 10.3.0 no tiene wheel para 3.13+)",
                 "Instala Python 3.12 y crea el venv con: py -3.12 -m venv venv")
    venvs = [d for d in ("venv", ".venv") if (ROOT / d / "pyvenv.cfg").exists()]
    py["venvs_en_proyecto"] = venvs
    if not venvs:
        problema("No hay ambiente virtual en el proyecto",
                 "py -3.12 -m venv venv  y luego  .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    for d in venvs:
        cfg = (ROOT / d / "pyvenv.cfg").read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^home\s*=\s*(.+)$", cfg, re.M)
        if m and not Path(m.group(1).strip()).exists():
            problema(f"El venv '{d}' apunta a un Python que no existe en esta PC ({m.group(1).strip()}): fue copiado de otra máquina",
                     f"Bórralo (Remove-Item -Recurse -Force .\\{d}) y créalo de nuevo con py -3.12 -m venv {d}")
    py["usa_venv_del_proyecto"] = any(Path(sys.prefix).resolve() == (ROOT / d).resolve() for d in venvs)
    if venvs and not py["usa_venv_del_proyecto"]:
        problema("Esta herramienta no se está ejecutando con el Python del venv del proyecto",
                 f"Usa .\\{venvs[0]}\\Scripts\\python.exe (o selecciónalo en VS Code: Python: Select Interpreter)")

    # --- dependencias ---
    deps = {}
    for nombre in ("requirements.txt", "tools/mcp_framework/requirements-mcp.txt"):
        archivo = ROOT / nombre
        if archivo.exists():
            r = _requisitos_vs_instalado(archivo)
            deps[nombre] = r
            if r["faltantes"]:
                problema(f"Faltan paquetes de {nombre}: {', '.join(r['faltantes'][:8])}",
                         f"python -m pip install -r {nombre}")
            if r["version_distinta"]:
                problema(f"Versiones distintas a {nombre}: {'; '.join(r['version_distinta'][:5])}",
                         f"python -m pip install -r {nombre} (reinstala las versiones fijadas)")

    # --- navegador (web) ---
    navegador = {}
    if _modo() == "web":
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(ROOT / "browser.properties", encoding="utf-8")
        navegador = {
            "browser": cfg.get("General", "browser", fallback=""),
            "headless": cfg.get("General", "headless", fallback=""),
            "driver_path": cfg.get("General", "driver_path", fallback="") or os.environ.get("WEBDRIVER_PATH", ""),
            "chrome_instalado": _version_chrome(),
        }
        if navegador["browser"].lower() == "chrome" and not navegador["chrome_instalado"]:
            problema("No se detectó Google Chrome", "Instálalo o cambia 'browser' en browser.properties")
        if navegador["driver_path"] and not Path(navegador["driver_path"]).exists():
            problema(f"driver_path no existe: {navegador['driver_path']}", "Corrige la ruta o déjala vacía para resolver el driver automáticamente")

    # --- git ---
    git = {}
    if (ROOT / ".git").exists():
        estado = _comando(["git", "status", "--porcelain", "-b"])
        lineas = estado.splitlines()
        cabecera = lineas[0] if lineas else ""
        git = {
            "rama": _comando(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "archivos_sin_commit": len(lineas) - 1 if lineas else 0,
            "estado_remoto": cabecera.replace("## ", ""),
            "hook_calidad_activo": _comando(["git", "config", "core.hooksPath"]) == ".githooks",
        }
        if git["rama"] in ("main", "master", "develop"):
            problema(f"Estás trabajando directo en '{git['rama']}'",
                     "Crea una rama: git checkout -b feature/HU-123-descripcion")
        if "ahead" in cabecera:
            problema("Tienes commits que no están en el repositorio remoto", "git push")
        if "behind" in cabecera:
            problema("Tu rama está desactualizada respecto al remoto", "git pull (o git merge origin/develop en tu rama)")
        if "no branch" in cabecera or "..." not in cabecera:
            if git["rama"] not in ("", "HEAD"):
                problema("La rama no tiene rama remota asociada (el código solo está en tu PC)",
                         f"git push -u origin {git['rama']}")
        if not git["hook_calidad_activo"]:
            problema("El hook de buenas prácticas no está activo", "git config core.hooksPath .githooks")
    else:
        problema("La carpeta no es un repositorio git (o se abrió una subcarpeta)",
                 "Abre en VS Code la carpeta clonada del repositorio")

    # --- disco ---
    libre_gb = round(shutil.disk_usage(ROOT).free / 1024 ** 3, 1)
    if libre_gb < 2:
        problema(f"Poco espacio en disco ({libre_gb} GB libres): pip falla con 'Errno 28 No space left on device'",
                 "Libera espacio (papelera, Descargas, %TEMP%) y repite la instalación")

    return {
        "ok": not problemas,
        "framework": _modo(),
        "raiz": str(ROOT),
        "python": py,
        "dependencias": deps,
        "navegador": navegador,
        "git": git,
        "disco_libre_gb": libre_gb,
        "problemas": problemas,
    }


def _hallazgos_steps_features() -> list[dict]:
    """Convierte los problemas de steps/features al formato de reglas.py."""
    import reglas

    r = reglas._Recolector()
    steps, _ = _cargar_steps()
    for d in _duplicados(steps):
        archivo, linea = d["definido_en"][1].rsplit(":", 1)
        r.add("COM-STEP-DUPLICADO", "error", archivo, int(linea), f'Step duplicado: "{d["patron"]}" ({", ".join(d["definido_en"])})',
              "Deja una sola definición y reutilízala desde los features.", d["patron"])
    v = validar_features()
    for p in v["pasos_sin_definir"]:
        archivo, linea = p["ubicacion"].rsplit(":", 1)
        r.add("COM-STEP-SIN-DEFINIR", "error", archivo, int(linea), f'Paso sin step: {p["paso"]}',
              "Implementa el step o ajusta el texto a uno existente (buscar_step).", p["paso"])
    for aviso in v["avisos"]:
        m = re.match(r"(\S+?):(\d+) (.*)", aviso)
        if m:
            r.add("COM-FEATURE-TAGS", "aviso", m.group(1), int(m.group(2)), m.group(3),
                  "Agrega un tag funcional y, si usa <datos>, @xc-<Excel> y @pg-<Hoja>.", m.group(3))
    return r.items


@mcp.tool()
def revisar_buenas_practicas(alcance: str = "cambios", archivos: list[str] | None = None, actualizar_linea_base: bool = False) -> dict:
    """Revisa si el código cumple las buenas prácticas y el patrón de diseño del framework
    (Page Object con context, esperas explícitas, evidencia, columnas en excelObjects,
    verificaciones que fallan, steps delgados y con compuerta Ejecutar, sin secretos...).
    alcance: 'cambios' (archivos modificados en git, por defecto), 'todo' o 'archivos'
    (lista en 'archivos'). 'aprobado' es False si hay errores NUEVOS respecto de la línea
    base. Úsalo SIEMPRE después de modificar código. actualizar_linea_base=True registra
    la deuda actual (solo cuando el líder técnico lo indique)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import reglas

    resultado = reglas.revisar(ROOT, _modo(), alcance, archivos, _hallazgos_steps_features, LINEA_BASE)
    if actualizar_linea_base:
        total = reglas.guardar_baseline(LINEA_BASE, resultado)
        resultado["linea_base_actualizada"] = f"{total} hallazgos registrados en {_rel(LINEA_BASE)}"
    if len(resultado["hallazgos"]) > 150:
        resultado["hallazgos_omitidos"] = len(resultado["hallazgos"]) - 150
        resultado["hallazgos"] = resultado["hallazgos"][:150]
    return resultado


def _cli_revisar(argv: list[str]) -> int:
    """python tools/mcp_framework/server.py --revisar [--todo] [--linea-base]
    Código de salida 1 si hay errores nuevos (para pre-commit y pipeline)."""
    alcance = "todo" if "--todo" in argv else "cambios"
    res = revisar_buenas_practicas(alcance=alcance, actualizar_linea_base="--linea-base" in argv)
    print(f"Revisión de buenas prácticas ({res['alcance']}): {res['nota']}")
    print(f"Totales  -> errores: {res['totales']['error']}  avisos: {res['totales']['aviso']}  info: {res['totales']['info']}")
    print(f"Nuevos   -> errores: {res['nuevos']['error']}  avisos: {res['nuevos']['aviso']}")
    for h in res["hallazgos"]:
        if h["nuevo"] and h["severidad"] in ("error", "aviso"):
            ubic = f'{h["archivo"]}:{h["linea"]}' if h["linea"] else h["archivo"]
            print(f'  [{h["severidad"].upper()}] {h["regla"]} {ubic} - {h["mensaje"]}\n      -> {h["recomendacion"]}')
    if res.get("linea_base_actualizada"):
        print(res["linea_base_actualizada"])
        return 0
    print("RESULTADO:", "APROBADO" if res["aprobado"] else "RECHAZADO (corrige los errores nuevos)")
    return 0 if res["aprobado"] else 1


HERRAMIENTAS = (
    "info_framework", "listar_steps", "buscar_step", "validar_features", "leer_excel",
    "validar_fila_excel", "agregar_filas_excel", "preparar_evidencias", "actualizar_test_execution", "ejecutar_escenarios", "ultimo_resultado", "explorar_pagina",
    "explorar_tras_steps", "revisar_diseno", "extraer_estilos", "revisar_buenas_practicas", "diagnosticar_entorno",
)


def _cli_herramienta(argv: list[str]) -> int:
    """Modo terminal: python tools/mcp_framework/server.py <herramienta> clave=valor ...
    Ej.: buscar_step texto="Usuario ingresa su correo"
         leer_excel archivo=Data hoja=Login fila=1
         ejecutar_escenarios tag=Login
    Imprime el resultado en JSON (lo mismo que devolvería la herramienta MCP)."""
    import inspect

    nombre = argv[1]
    funcion = globals()[nombre]
    firma = inspect.signature(funcion)
    kwargs: dict[str, Any] = {}
    for par in argv[2:]:
        if "=" not in par:
            print(json.dumps({"error": f"Argumento '{par}' inválido: usa clave=valor"}, ensure_ascii=False))
            return 2
        clave, valor = par.split("=", 1)
        if clave not in firma.parameters:
            print(json.dumps({"error": f"'{clave}' no es parámetro de {nombre}. Válidos: {list(firma.parameters)}"}, ensure_ascii=False))
            return 2
        tipo = str(firma.parameters[clave].annotation)
        if "bool" in tipo:
            kwargs[clave] = valor.strip().lower() in ("1", "true", "si", "sí", "yes")
        elif "int" in tipo:
            kwargs[clave] = int(valor)
        elif "list" in tipo and valor.startswith("@"):
            kwargs[clave] = json.loads(Path(valor[1:]).read_text(encoding="utf-8"))   # filas=@filas.json
        elif "list" in tipo and valor.lstrip().startswith("["):
            kwargs[clave] = json.loads(valor)
        elif "list" in tipo:
            kwargs[clave] = [v.strip() for v in valor.split(",") if v.strip()]
        else:
            kwargs[clave] = valor
    try:
        resultado = funcion(**kwargs)
    except Exception as e:  # noqa: BLE001
        resultado = {"error": f"{type(e).__name__}: {e}"}
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    if "--revisar" in sys.argv:
        sys.exit(_cli_revisar(sys.argv))
    if len(sys.argv) > 1 and sys.argv[1] in HERRAMIENTAS:
        sys.exit(_cli_herramienta(sys.argv))
    if len(sys.argv) > 1:
        print("Uso: server.py <herramienta> clave=valor ...  |  server.py --revisar [--todo]")
        print("Herramientas:", ", ".join(HERRAMIENTAS))
        sys.exit(2)
    mcp.run()
