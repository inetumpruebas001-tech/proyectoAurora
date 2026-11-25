"""Ambientes, variables {{...}} y despertar del servicio.

config/ambientes.json define un bloque por ambiente (como los environments de Postman):

    {
      "dev":   {"baseUrl": "https://mi-api-dev...", "semillero": "qe-auto", "salud": "/api/health"},
      "certi": {"baseUrl": "https://mi-api-certi...", ...},
      "prod":  {"baseUrl": "https://mi-api...", "bloqueado": true}
    }

El ambiente se elige con la variable de entorno AMBIENTE (o 'ambiente' en service.properties / browser.properties).
Cualquier variable se puede sobrescribir por entorno en MAYÚSCULAS: BASEURL, SEMILLERO, ...

En el Excel se usa {{nombre}} en cualquier columna. Se resuelve, en este orden:
  1. variables guardadas por escenarios anteriores (columna GlobalVariables),
  2. variables del ambiente,
  3. valores dinámicos: {{hoy}}, {{hoy+30}}, {{hoy-1}}, {{hoy-18a}} (años), {{uuid}}, {{aleatorio}}.
     Formato de fecha opcional: {{hoy+30:dd/mm/aaaa}} (por defecto aaaa-mm-dd).
Si un {{nombre}} no existe, la prueba se detiene con un mensaje claro (nunca sale la petición a medias).
"""
import configparser
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

RUTA_AMBIENTES = os.path.join(os.getcwd(), "config", "ambientes.json")
ZONA_PERU = timezone(timedelta(hours=-5))
_PATRON = re.compile(r"\{\{\s*([A-Za-z_]\w*(?:-[A-Za-z_]\w*)*)\s*([+-]\s*\d+\s*[da]?)?\s*(?::\s*([^}]+?))?\s*\}\}")


class ErrorAmbiente(AssertionError):
    pass


def nombre_ambiente():
    config = configparser.ConfigParser()
    config.read(["service.properties", "browser.properties"])   # API o web
    return (os.environ.get("AMBIENTE") or config.get("General", "ambiente", fallback="dev")).strip().lower()


def cargar_ambiente(nombre=None):
    nombre = (nombre or nombre_ambiente()).lower()
    if not os.path.exists(RUTA_AMBIENTES):
        raise ErrorAmbiente(f"No existe {RUTA_AMBIENTES}: crea config/ambientes.json con el bloque '{nombre}'")
    with open(RUTA_AMBIENTES, encoding="utf-8") as f:
        todos = json.load(f)
    if nombre not in todos:
        raise ErrorAmbiente(f"El ambiente '{nombre}' no está en config/ambientes.json. Disponibles: {', '.join(todos)}")
    variables = {k: v for k, v in todos[nombre].items() if not k.startswith("_")}
    for clave in list(variables):  # sobrescritura por variable de entorno (SEMILLERO, BASEURL...)
        if os.environ.get(clave.upper()):
            variables[clave] = os.environ[clave.upper()]
    variables["ambiente"] = nombre
    if not str(variables.get("baseUrl", "")).strip():
        raise ErrorAmbiente(f"El ambiente '{nombre}' no tiene baseUrl en config/ambientes.json (o variable BASEURL)")
    variables["baseUrl"] = str(variables["baseUrl"]).rstrip("/")
    return variables


def validar_permitido(variables):
    """Los ambientes marcados "bloqueado": true (p. ej. PROD) solo corren con PERMITIR_AMBIENTE_BLOQUEADO=si."""
    if variables.get("bloqueado") and os.environ.get("PERMITIR_AMBIENTE_BLOQUEADO", "").lower() != "si":
        raise ErrorAmbiente(
            f"El ambiente '{variables['ambiente']}' está bloqueado para pruebas automatizadas. "
            "Si es intencional (solo pruebas de lectura), define PERMITIR_AMBIENTE_BLOQUEADO=si.")


def despertar(variables, espera_max_seg=None):
    """Llama al endpoint de salud hasta que responda 200 (servicios que se duermen, como Render gratuito)."""
    ruta = variables.get("salud")
    if not ruta:
        return None
    espera_max = int(espera_max_seg or variables.get("espera_despertar_seg", 120))
    url = variables["baseUrl"] + ruta
    inicio = time.time()
    ultimo = ""
    while time.time() - inicio < espera_max:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                seg = round(time.time() - inicio, 1)
                print(f"[LOG] Servicio despierto ({url}) en {seg} s")
                return seg
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            ultimo = e.__class__.__name__
        time.sleep(5)
    raise ErrorAmbiente(f"El servicio no respondió 200 en {url} después de {espera_max} s (último: {ultimo})")


def _sumar_anios(fecha, anios):
    try:
        return fecha.replace(year=fecha.year + anios)
    except ValueError:            # 29/02 en año no bisiesto -> 28/02
        return fecha.replace(year=fecha.year + anios, day=28)


def _dinamico(nombre, desplazamiento, formato=None):
    hoy = datetime.now(ZONA_PERU).date()
    texto = (desplazamiento or "").replace(" ", "")
    if nombre == "hoy":
        if texto.endswith("a"):
            fecha = _sumar_anios(hoy, int(texto[:-1]))
        else:
            fecha = hoy + timedelta(days=int(texto.rstrip("d")) if texto else 0)
        if formato:
            patron = formato.lower().replace("aaaa", "%Y").replace("yyyy", "%Y").replace("dd", "%d").replace("mm", "%m")
            return fecha.strftime(patron)
        return fecha.isoformat()
    if nombre == "uuid":
        return str(uuid.uuid4())
    if nombre == "aleatorio":
        return str(random.randint(100000, 999999))
    return None


def resolver(texto, variables_globales, variables_ambiente):
    """Reemplaza {{nombre}} en un texto. Devuelve (texto, faltantes)."""
    if not isinstance(texto, str) or "{{" not in texto:
        return texto, []
    faltantes = []

    def reemplazo(m):
        nombre, desplazamiento, formato = m.group(1), m.group(2), m.group(3)
        if not desplazamiento and not formato:
            if nombre in variables_globales:
                return str(variables_globales[nombre])
            if nombre in variables_ambiente:
                return str(variables_ambiente[nombre])
        valor = _dinamico(nombre, desplazamiento, formato)
        if valor is None:
            faltantes.append(nombre)
            return m.group(0)
        return valor

    return _PATRON.sub(reemplazo, texto), faltantes
