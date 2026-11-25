"""Peticiones multipart/form-data (subida de archivos) desde el Excel.

Se activa cuando la columna Headers trae 'Content-Type: multipart/form-data'.
El Body se escribe una línea por campo, con el mismo formato que Headers:

    descripcion: Documento de identidad
    archivo: @dni_ficticio.pdf
    foto: @selfie.png;type=image/png

'@nombre' toma el archivo de src/test/resources/data/archivos/. El tipo se deduce de la
extensión; ';type=...' lo fuerza. Un campo puede repetirse (varios archivos con el mismo nombre).
El boundary lo arma requests: el Content-Type del Excel se quita antes de enviar.
"""
import mimetypes
import os

CARPETA_ARCHIVOS = os.path.join(os.getcwd(), "src", "test", "resources", "data", "archivos")


def es_multipart(headers):
    if not isinstance(headers, dict):
        return False
    return any(k.lower() == "content-type" and "multipart/form-data" in str(v).lower() for k, v in headers.items())


def sin_content_type(headers):
    return {k: v for k, v in headers.items() if k.lower() != "content-type"}


def _ruta_archivo(nombre):
    ruta = os.path.normpath(os.path.join(CARPETA_ARCHIVOS, nombre))
    if not ruta.startswith(os.path.normpath(CARPETA_ARCHIVOS)):
        raise AssertionError(f"El archivo '{nombre}' debe estar dentro de src/test/resources/data/archivos")
    if not os.path.isfile(ruta):
        raise AssertionError(f"No existe el archivo '{nombre}' en src/test/resources/data/archivos")
    return ruta


def interpretar(body):
    """Body del Excel -> lista de (campo, valor, archivo|None, tipo|None). Valida el formato."""
    partes = []
    for linea in str(body or "").splitlines():
        if not linea.strip():
            continue
        if ": " not in linea:
            raise AssertionError(f"Body multipart: la línea '{linea}' debe tener el formato 'campo: valor' o 'campo: @archivo'")
        campo, valor = linea.split(": ", 1)
        campo, valor = campo.strip(), valor.strip()
        if valor.startswith("@"):
            nombre, _, tipo = valor[1:].partition(";type=")
            partes.append((campo, None, nombre.strip(), tipo.strip() or None))
        else:
            partes.append((campo, valor, None, None))
    return partes


def preparar(body):
    """Devuelve (files para requests, resumen para log/Word). Lee los archivos en memoria."""
    files, resumen = [], {}
    for campo, valor, archivo, tipo in interpretar(body):
        if archivo is None:
            files.append((campo, (None, valor)))
            resumen[campo] = valor
            continue
        ruta = _ruta_archivo(archivo)
        tipo = tipo or mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        with open(ruta, "rb") as f:
            contenido = f.read()
        files.append((campo, (os.path.basename(ruta), contenido, tipo)))
        resumen[campo] = f"@{archivo} ({len(contenido)} bytes, {tipo})"
    if not files:
        raise AssertionError("Body multipart vacío: agrega al menos un campo 'campo: valor' o 'campo: @archivo'")
    return files, resumen
