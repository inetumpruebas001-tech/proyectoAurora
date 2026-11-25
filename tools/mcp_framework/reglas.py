"""
Reglas de buenas prácticas del framework Behave (web Selenium / API requests).

Cada hallazgo: regla, severidad (error | aviso | info), archivo, linea, mensaje,
recomendacion y huella. La huella no depende del número de línea, para que la
línea base (deuda conocida) sobreviva a cambios de posición en el archivo.

Lo usa server.py (herramienta MCP revisar_buenas_practicas y la CLI --revisar).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Callable

SEVERIDADES = ("error", "aviso", "info")

CATALOGO = {
    # comunes
    "COM-SINTAXIS": "Archivo Python con error de sintaxis",
    "COM-STEP-DUPLICADO": "Dos steps con el mismo texto (AmbiguousStep)",
    "COM-STEP-SIN-DEFINIR": "Paso de un feature sin step que lo implemente",
    "COM-FEATURE-TAGS": "Escenario sin tags o sin @xc-/@pg- siendo data-driven",
    "COM-SECRETO": "Credencial o clave escrita en el repositorio",
    "COM-MODULO-SOMBRA": "Módulo suelto que tapa al paquete src/test",
    "COM-FALLA-SILENCIADA": "except que no vuelve a lanzar: el escenario puede pasar sin validar",
    "COM-SLEEP": "Espera fija con time.sleep",
    "COM-COMPUERTA-EJECUTAR": "Step que no respeta la columna Ejecutar/Ejecucion = NO",
    "COM-URL-EN-CODIGO": "URL fija en código: debe venir del Excel/configuración",
    "COM-PIPELINE-EXIT0": "El pipeline nunca falla aunque fallen las pruebas",
    "COM-GITIGNORE": "Archivos generados o entornos sin ignorar en git",
    "COM-DRIVERS-EN-REPO": "Ejecutables de drivers versionados en el repo",
    "COM-TLS": "Verificación TLS desactivada (verify=False)",
    # web
    "WEB-PAGE-CONTEXT": "Page Object que no recibe context (ni directo ni vía BasePage)",
    "WEB-STEP-UI": "Step con lógica de UI (find_element/WebDriverWait/driver)",
    "WEB-LOCATOR-EN-LINEA": "Locator literal dentro de un método (centralizar en pages/Objects)",
    "WEB-LOCATOR-EN-PAGE": "Locator (By.*) definido en la page en vez de pages/Objects/<pantalla>Objects.py",
    "WEB-XPATH-ABSOLUTO": "XPath absoluto (/html/...)",
    "WEB-XPATH-POSICIONAL": "XPath posicional ([1], [2]...) frágil",
    "WEB-SIN-EVIDENCIA": "Acción de UI sin evidencia (send_text + add_image_to_word)",
    "WEB-COLUMNA-LITERAL": "Nombre de columna de Excel escrito suelto (usar excelObjects)",
    "WEB-IMPLICIT-WAIT": "implicitly_wait mezclado con esperas explícitas",
}

_RE_SECRETO = re.compile(
    r"""\b(account_key|password|passwd|pwd|secret|client_secret|token|api_key|apikey)\s*=\s*['"][^'"]{8,}['"]""",
    re.I,
)


def _huella(regla: str, archivo: str, texto: str) -> str:
    normal = re.sub(r"\s+", " ", texto.strip())
    base = f"{regla}|{archivo}|{normal}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


class _Recolector:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, regla: str, sev: str, archivo: str, linea: int | None, mensaje: str, rec: str, texto: str = "") -> None:
        self.items.append({
            "regla": regla,
            "severidad": sev,
            "archivo": archivo,
            "linea": linea,
            "mensaje": mensaje,
            "recomendacion": rec,
            "huella": _huella(regla, archivo, texto or mensaje),
        })


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p)


def _categoria(rel: str) -> str:
    if "/features/steps/" in rel:
        return "steps"
    if rel.endswith("features/environment.py"):
        return "environment"
    if "/pages/Objects/" in rel:
        return "objects"
    if "/pages/" in rel:
        return "pages"
    if "/library/" in rel:
        return "library"
    if "/app/" in rel:
        return "app"
    return "otro"


def _es_decorador_step(dec: ast.expr) -> bool:
    f = dec.func if isinstance(dec, ast.Call) else dec
    nombre = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
    return nombre.lower() in ("given", "when", "then", "step")


def _llamadas(nodo: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(nodo) if isinstance(n, ast.Call)]


def _nombre_llamada(c: ast.Call) -> str:
    f = c.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _texto_linea(lineas: list[str], n: int | None) -> str:
    if n and 0 < n <= len(lineas):
        return lineas[n - 1]
    return ""


def _revisar_python(root: Path, archivo: Path, modo: str, r: _Recolector) -> None:
    rel = _rel(root, archivo)
    cat = _categoria(rel)
    if cat == "app":
        return  # lanzador gráfico, fuera del patrón de pruebas
    codigo = archivo.read_text(encoding="utf-8", errors="ignore")
    lineas = codigo.splitlines()

    for i, linea in enumerate(lineas, start=1):
        if _RE_SECRETO.search(linea) and "excelObjects" not in rel:
            r.add("COM-SECRETO", "error", rel, i, "Valor sensible escrito en el código",
                  "Muévelo a Azure Key Vault / variable de entorno del pipeline y rota la clave expuesta.", linea)

    try:
        arbol = ast.parse(codigo)
    except SyntaxError as e:
        r.add("COM-SINTAXIS", "error", rel, e.lineno, f"SyntaxError: {e.msg}",
              "Corrige la sintaxis: behave no carga ningún step mientras exista.", _texto_linea(lineas, e.lineno))
        return

    # --- reglas sobre todo el archivo ---
    for c in _llamadas(arbol):
        nombre = _nombre_llamada(c)
        if nombre == "sleep" and isinstance(c.func, ast.Attribute) and getattr(c.func.value, "id", "") == "time":
            sev = "error" if (modo == "web" and cat in ("pages", "steps")) else "aviso"
            r.add("COM-SLEEP", sev, rel, c.lineno, "time.sleep en el flujo de prueba",
                  "Usa las esperas de BasePage (self.visible/self.click) o WebDriverWait + expected_conditions.", _texto_linea(lineas, c.lineno))
        if nombre == "implicitly_wait" and modo == "web":
            r.add("WEB-IMPLICIT-WAIT", "aviso", rel, c.lineno, "implicitly_wait combinado con esperas explícitas",
                  "Selenium desaconseja mezclarlos: deja solo WebDriverWait.", _texto_linea(lineas, c.lineno))
        for kw in c.keywords:
            if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                r.add("COM-TLS", "info", rel, c.lineno, "Petición con verify=False",
                      "Aceptable solo en ambientes de prueba con certificados internos; documentarlo o usar el CA de la organización.",
                      _texto_linea(lineas, c.lineno))

    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and modo == "web" and cat in ("pages", "steps", "objects"):
            v = n.value.strip()
            if v.startswith("/html"):
                r.add("WEB-XPATH-ABSOLUTO", "error", rel, n.lineno, f"XPath absoluto: {v[:60]}",
                      "Usa id, name, atributos estables o XPath por texto.", _texto_linea(lineas, n.lineno))
            elif v.startswith(("//", "(//")) and re.search(r"/[\w*]+\[\d+\]", v):
                r.add("WEB-XPATH-POSICIONAL", "aviso", rel, n.lineno, f"XPath posicional: {v[:60]}",
                      "Ancla el XPath a un atributo o texto estable en vez de la posición.", _texto_linea(lineas, n.lineno))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and cat in ("pages", "steps"):
            if re.match(r"^https?://", n.value.strip()):
                r.add("COM-URL-EN-CODIGO", "aviso", rel, n.lineno, f"URL fija: {n.value.strip()[:60]}",
                      "La URL debe venir del Excel (columna url/Endpoint) o de la configuración por ambiente.",
                      _texto_linea(lineas, n.lineno))

    # --- except que silencian fallas ---
    if cat in ("pages", "steps", "library"):
        for n in ast.walk(arbol):
            if not isinstance(n, ast.ExceptHandler):
                continue
            tipos = []
            if n.type is None:
                tipos = ["(bare)"]
            elif isinstance(n.type, ast.Tuple):
                tipos = [getattr(e, "id", getattr(e, "attr", "")) for e in n.type.elts]
            else:
                tipos = [getattr(n.type, "id", getattr(n.type, "attr", ""))]
            relevantes = {"(bare)", "Exception", "NoSuchElementException", "TimeoutException", "AssertionError", "WebDriverException"}
            if not relevantes.intersection(tipos):
                continue
            if any(isinstance(x, ast.Raise) for x in ast.walk(ast.Module(body=n.body, type_ignores=[]))):
                continue
            sev = "error" if cat in ("pages", "steps") else "aviso"
            r.add("COM-FALLA-SILENCIADA", sev, rel, n.lineno, f"except {', '.join(tipos)} sin raise",
                  "Registra la evidencia y lanza AssertionError con un mensaje claro; si no, el escenario queda en verde sin validar.",
                  _texto_linea(lineas, n.lineno))

    # --- steps ---
    if cat == "steps":
        for fn in [x for x in ast.walk(arbol) if isinstance(x, ast.FunctionDef)]:
            if not any(_es_decorador_step(d) for d in fn.decorator_list):
                continue
            fuente = ast.get_source_segment(codigo, fn) or ""
            if "ejecutar" not in fuente:
                r.add("COM-COMPUERTA-EJECUTAR", "aviso", rel, fn.lineno, f"El step '{fn.name}' no revisa context.ejecutar",
                      "Envuelve la lógica en `if context.ejecutar == \"SI\":` para respetar las filas marcadas NO.",
                      f"def {fn.name}" + _texto_linea(lineas, fn.lineno - 1))
            if modo == "web":
                for c in _llamadas(fn):
                    if _nombre_llamada(c) in ("find_element", "find_elements", "WebDriverWait", "execute_script"):
                        r.add("WEB-STEP-UI", "aviso", rel, c.lineno, "El step interactúa directo con Selenium",
                              "Mueve la interacción a un método del Page Object; el step solo orquesta.",
                              _texto_linea(lineas, c.lineno))

    # --- capa de objetos (web): los locators viven en pages/Objects ---
    if cat == "pages" and modo == "web" and not rel.endswith("BasePage.py"):
        for n in ast.walk(arbol):
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "By"):
                r.add("WEB-LOCATOR-EN-PAGE", "error", rel, n.lineno, f"Locator By.{n.attr} definido en la page",
                      "Decláralo en pages/Objects/<pantalla>Objects.py (p. ej. txtEmail = (By.ID, \"input-email\")) "
                      "y úsalo como loginObjects.txtEmail.", _texto_linea(lineas, n.lineno))

    # --- pages (web) ---
    if cat == "pages" and modo == "web":
        for cls in [x for x in arbol.body if isinstance(x, ast.ClassDef)]:
            bases = [getattr(b, "id", getattr(b, "attr", "")) for b in cls.bases]
            init = next((m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
            args = [a.arg for a in init.args.args] if init else []
            # Válido: recibe context en su __init__, o hereda de BasePage sin redefinir __init__
            recibe_context = "context" in args or (init is None and "BasePage" in bases)
            if not recibe_context:
                r.add("WEB-PAGE-CONTEXT", "error", rel, cls.lineno,
                      f"La page '{cls.name}' no recibe context en __init__",
                      "Patrón vigente: class XPage(BasePage) (hereda el __init__ con context) y los locators en pages/Objects/.",
                      f"class {cls.name}")
            for m in [x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name != "__init__"]:
                llamadas = _llamadas(m)
                nombres = {_nombre_llamada(c) for c in llamadas}
                # self.click(...)/self.escribir(...) son helpers de BasePage que ya dejan evidencia
                acciones = {_nombre_llamada(c) for c in llamadas
                            if not (isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
                                    and c.func.value.id == "self")}
                for c in llamadas:
                    if _nombre_llamada(c) in ("find_element", "find_elements") and len(c.args) >= 2 and isinstance(c.args[1], ast.Constant):
                        r.add("WEB-LOCATOR-EN-LINEA", "aviso", rel, c.lineno, f"Locator literal en {cls.name}.{m.name}",
                              "Declara el locator en pages/Objects/<pantalla>Objects.py y úsalo como <pantalla>Objects.txtX.",
                              _texto_linea(lineas, c.lineno))
                if {"click", "send_keys"} & acciones and not {"send_text", "add_image_to_word", "_evidencia", "evidencia"} & nombres:
                    r.add("WEB-SIN-EVIDENCIA", "aviso", rel, m.lineno, f"{cls.name}.{m.name} actúa sin dejar evidencia",
                          "Usa los helpers de BasePage (self.click, self.escribir, self.evidencia) o generateWord.send_text + add_image_to_word.",
                          f"def {m.name}")
                for sub in [x for x in ast.walk(m) if isinstance(x, ast.Subscript)]:
                    if isinstance(sub.slice, ast.Constant) and isinstance(sub.slice.value, str):
                        cadena = ast.get_source_segment(codigo, sub.value) or ""
                        if "get_data()" in cadena:
                            r.add("WEB-COLUMNA-LITERAL", "aviso", rel, sub.lineno, f"Columna '{sub.slice.value}' escrita suelta",
                                  "Declárala en excelObjects.py y úsala como excelObjects.columnX.",
                                  _texto_linea(lineas, sub.lineno))


def _revisar_repo(root: Path, modo: str, r: _Recolector) -> None:
    src = root / "src"
    if src.exists():
        for p in src.glob("*.py"):
            if (src / p.stem).is_dir():
                r.add("COM-MODULO-SOMBRA", "error", _rel(root, p), 1,
                      f"{_rel(root, p)} tapa al paquete src/{p.stem}/ y rompe los imports del framework",
                      "Elimina o mueve el script fuera de src/.", p.name)

    props = root / "database.properties"
    if props.exists():
        for i, linea in enumerate(props.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            m = re.match(r"\s*(\w*(password|pass|pwd)\w*)\s*=\s*(\S+)", linea, re.I)
            if m:
                r.add("COM-SECRETO", "error", "database.properties", i, f"Contraseña de BD en {m.group(1)}",
                      "Usa Key Vault o variables de entorno; deja el archivo con valores de ejemplo.", linea.split("=")[0])
    for cred in root.glob("src/test/resources/data/json/*.json"):
        texto = cred.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'"(password|pass|clave|token|secret)\w*"\s*:\s*"[^"]+"', texto, re.I):
            r.add("COM-SECRETO", "error", _rel(root, cred), 1, "Archivo JSON con contraseñas versionado",
                  "Sácalo del repo (gitignore) y entrega un .example sin valores.", cred.name)

    pipe = root / "azure-pipelines.yml"
    if pipe.exists():
        texto = pipe.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"behave", texto) and re.search(r"^\s*exit 0", texto, re.M):
            r.add("COM-PIPELINE-EXIT0", "aviso", "azure-pipelines.yml", None,
                  "El paso de behave termina con exit 0 y PublishTestResults tiene failTaskOnFailedTests: false",
                  "Deja que el pipeline falle (o marca el build como parcialmente exitoso) cuando hay escenarios fallidos.",
                  "exit 0")

    gi = root / ".gitignore"
    contenido = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
    faltan = [p for p in ("venv", ".venv", "*.output", "output.xml", "src/test/reports") if p not in contenido]
    if faltan:
        r.add("COM-GITIGNORE", "aviso", ".gitignore", None, f"No ignora: {', '.join(faltan)}",
              "Agrega esas entradas para no versionar entornos, resultados ni reportes.", ",".join(faltan))

    drivers = [p for p in root.glob("src/test/resources/drivers/**/*") if p.is_file() and p.suffix in (".exe", ".zip", "")]
    if drivers:
        r.add("COM-DRIVERS-EN-REPO", "info", "src/test/resources/drivers", None,
              f"{len(drivers)} ejecutables/zip de drivers versionados",
              "Ya usan webdriver-manager/Selenium Manager: elimina los binarios del repo.", "drivers")


def _archivos_cambiados(root: Path) -> list[str] | None:
    try:
        subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, check=True, timeout=15)
    except Exception:  # noqa: BLE001
        return None
    salida: set[str] = set()
    for cmd in (["git", "-C", str(root), "diff", "--name-only", "HEAD"],
                ["git", "-C", str(root), "diff", "--name-only", "--cached"],
                ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            salida.update(x.strip().replace("\\", "/") for x in r.stdout.splitlines() if x.strip())
        except Exception:  # noqa: BLE001
            continue
    return sorted(salida)


def revisar(
    root: Path,
    modo: str,
    alcance: str = "todo",
    archivos: list[str] | None = None,
    hallazgos_steps: Callable[[], list[dict]] | None = None,
    baseline_path: Path | None = None,
) -> dict:
    """alcance: 'todo' | 'cambios' | 'archivos'."""
    r = _Recolector()
    objetivo: set[str] | None = None
    if alcance == "cambios":
        cambiados = _archivos_cambiados(root)
        if cambiados is None:
            alcance = "todo"
            nota = "No hay repositorio git: se revisó todo el proyecto."
        else:
            objetivo = set(cambiados)
            nota = f"{len(cambiados)} archivos cambiados respecto de HEAD."
    elif alcance == "archivos":
        objetivo = {a.replace("\\", "/").lstrip("./") for a in (archivos or [])}
        nota = f"{len(objetivo)} archivos indicados."
    else:
        nota = "Revisión completa del proyecto."

    for py in sorted((root / "src").rglob("*.py")) if (root / "src").exists() else []:
        if any(parte in ("site-packages", "__pycache__", "venv", ".venv") for parte in py.parts):
            continue
        rel = _rel(root, py)
        if objetivo is not None and rel not in objetivo:
            continue
        _revisar_python(root, py, modo, r)

    if objetivo is None:
        _revisar_repo(root, modo, r)
    else:
        sub = _Recolector()
        _revisar_repo(root, modo, sub)
        r.items += [h for h in sub.items if h["archivo"] in objetivo or h["regla"] == "COM-MODULO-SOMBRA"]

    if hallazgos_steps:
        for h in hallazgos_steps():
            if objetivo is None or h["archivo"] in objetivo or h["regla"] in ("COM-STEP-DUPLICADO", "COM-SINTAXIS"):
                if not any(x["huella"] == h["huella"] for x in r.items):
                    r.items.append(h)

    baseline: dict[str, int] = {}
    if baseline_path and baseline_path.exists():
        try:
            crudo = json.loads(baseline_path.read_text(encoding="utf-8")).get("huellas", {})
            baseline = {h: 1 for h in crudo} if isinstance(crudo, list) else {k: int(v) for k, v in crudo.items()}
        except Exception:  # noqa: BLE001
            baseline = {}
    vistos: dict[str, int] = {}
    for h in sorted(r.items, key=lambda x: (x["archivo"], x["linea"] or 0)):
        vistos[h["huella"]] = vistos.get(h["huella"], 0) + 1
        h["nuevo"] = vistos[h["huella"]] > baseline.get(h["huella"], 0)

    orden = {s: i for i, s in enumerate(SEVERIDADES)}
    r.items.sort(key=lambda h: (not h["nuevo"], orden[h["severidad"]], h["archivo"], h["linea"] or 0))
    por_regla: dict[str, int] = {}
    for h in r.items:
        por_regla[h["regla"]] = por_regla.get(h["regla"], 0) + 1
    nuevos_error = [h for h in r.items if h["nuevo"] and h["severidad"] == "error"]
    return {
        "alcance": alcance,
        "nota": nota,
        "linea_base": str(baseline_path.name) if baseline_path and baseline_path.exists() else None,
        "totales": {s: sum(1 for h in r.items if h["severidad"] == s) for s in SEVERIDADES},
        "nuevos": {s: sum(1 for h in r.items if h["nuevo"] and h["severidad"] == s) for s in SEVERIDADES},
        "por_regla": dict(sorted(por_regla.items(), key=lambda kv: -kv[1])),
        "aprobado": not nuevos_error,
        "criterio": "Se bloquea si hay errores NUEVOS (no registrados en la línea base).",
        "hallazgos": r.items,
        "catalogo": {k: CATALOGO[k] for k in por_regla if k in CATALOGO},
    }


def guardar_baseline(baseline_path: Path, resultado: dict) -> int:
    huellas: dict[str, int] = {}
    for h in resultado["hallazgos"]:
        huellas[h["huella"]] = huellas.get(h["huella"], 0) + 1
    huellas = dict(sorted(huellas.items()))
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps({
        "descripcion": "Deuda técnica conocida. Solo bloquean los hallazgos que NO estén aquí.",
        "huellas": huellas,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return sum(huellas.values())
