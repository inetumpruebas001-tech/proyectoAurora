"""Validación del response contra un JSON Schema (columna opcional 'Expected Schema' del Excel).

Valores aceptados en la columna:
  - JSON en línea:            {"type": "object", "required": ["id"]}
  - Archivo de schemas/:      cotizacion.schema.json
  - Parte de un contrato:     openapi.json#/components/schemas/Cotizacion

Los archivos viven en src/test/resources/data/schemas/. Un contrato OpenAPI (Swagger) se puede
guardar ahí tal cual: las referencias internas ($ref: '#/components/schemas/...') se resuelven
y se adaptan las diferencias de OpenAPI 3.0 (nullable, exclusiveMinimum booleano).
"""
import copy
import json
import os

from jsonschema import Draft202012Validator

CARPETA_SCHEMAS = os.path.join(os.getcwd(), "src", "test", "resources", "data", "schemas")
MAX_ERRORES = 10


class ErrorSchema(AssertionError):
    pass


def _puntero(documento, puntero):
    actual = documento
    for parte in [p for p in puntero.strip("/").split("/") if p]:
        parte = parte.replace("~1", "/").replace("~0", "~")
        if isinstance(actual, list):
            actual = actual[int(parte)]
        elif isinstance(actual, dict) and parte in actual:
            actual = actual[parte]
        else:
            raise ErrorSchema(f"No existe '{puntero}' en el archivo de schema")
    return actual


def _adaptar_openapi(nodo):
    """OpenAPI 3.0 -> JSON Schema 2020-12 (nullable y exclusiveMinimum/Maximum booleanos)."""
    if isinstance(nodo, list):
        return [_adaptar_openapi(n) for n in nodo]
    if not isinstance(nodo, dict):
        return nodo
    nodo = {k: _adaptar_openapi(v) for k, v in nodo.items()}
    if nodo.pop("nullable", False):
        tipo = nodo.get("type")
        if isinstance(tipo, str):
            nodo["type"] = [tipo, "null"]
        elif "type" not in nodo and ("$ref" in nodo or "allOf" in nodo or "oneOf" in nodo):
            nodo = {"anyOf": [nodo, {"type": "null"}]}
    for exclusivo, limite in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(nodo.get(exclusivo), bool):
            if nodo.pop(exclusivo) and limite in nodo:
                nodo[exclusivo] = nodo.pop(limite)
    return nodo


def cargar(valor):
    """Devuelve el schema listo para validar a partir del valor de la columna."""
    valor = (valor or "").strip()
    if not valor:
        return None
    if valor.startswith("{"):
        try:
            return _adaptar_openapi(json.loads(valor))
        except json.JSONDecodeError as e:
            raise ErrorSchema(f"'Expected Schema' no es JSON válido: {e}") from e
    archivo, _, puntero = valor.partition("#")
    ruta = os.path.normpath(os.path.join(CARPETA_SCHEMAS, archivo))
    if not ruta.startswith(os.path.normpath(CARPETA_SCHEMAS)):
        raise ErrorSchema("El schema debe estar dentro de src/test/resources/data/schemas")
    if not os.path.exists(ruta):
        raise ErrorSchema(f"No existe el schema {archivo} en src/test/resources/data/schemas")
    with open(ruta, encoding="utf-8") as f:
        documento = json.load(f)
    schema = copy.deepcopy(_puntero(documento, puntero) if puntero else documento)
    if puntero and isinstance(schema, dict):
        # Las $ref internas ('#/components/...', '#/definitions/...') apuntan a la raíz del documento
        for clave in ("components", "definitions", "$defs"):
            if clave in documento and clave not in schema:
                schema[clave] = documento[clave]
    return _adaptar_openapi(schema)


def validar(schema, dato):
    """Lista de errores legibles ('ruta: mensaje'). Vacía si el dato cumple el schema."""
    validador = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errores = sorted(validador.iter_errors(dato), key=lambda e: list(e.absolute_path))
    salida = []
    for e in errores[:MAX_ERRORES]:
        ruta = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path)
        salida.append(f"{ruta}: {e.message}")
    if len(errores) > MAX_ERRORES:
        salida.append(f"... y {len(errores) - MAX_ERRORES} errores más")
    return salida
