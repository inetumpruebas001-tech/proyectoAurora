# Errores comunes en los frameworks (vistos en la implementación real)

## Ambiente e instalación

| Mensaje (última línea del log) | Qué significa | Cómo se arregla |
|---|---|---|
| `No Python at 'C:\Users\otro.usuario\...'` | El venv se copió de otra PC: guarda la ruta del Python de quien lo creó | Borrar `venv` y crearlo: `py -3.12 -m venv venv` |
| `Activate.ps1 cannot be loaded` / `El emisor revocó un certificado` / `running scripts is disabled` | PowerShell bloquea el script de activación | No activar: usar `.\venv\Scripts\python.exe ...` o `venv\Scripts\activate.bat` en CMD |
| `ModuleNotFoundError: No module named 'behave'` (u otro paquete) | Se está usando un Python sin las dependencias | Seleccionar el intérprete del venv y `python -m pip install -r requirements.txt` |
| `Could not find a version that satisfies the requirement pillow==10.3.0` / `Failed building wheel` | Python 3.13/3.14: esa versión no tiene instalador para ese Python | Usar Python 3.12 |
| `OSError: [Errno 28] No space left on device` | Disco lleno durante `pip install` | Liberar espacio y repetir |
| `'py' no se reconoce como un comando` | Python no está instalado o no está en el PATH | Instalar Python 3.12 marcando "Add to PATH" |
| `SSLError: CERTIFICATE_VERIFY_FAILED` | El proxy corporativo usa su propio certificado | Variable `REQUESTS_CA_BUNDLE` con el certificado (no desactivar TLS) |

## Carga del framework (antes de ejecutar un solo paso)

| Mensaje | Qué significa | Cómo se arregla |
|---|---|---|
| `SyntaxError: invalid syntax` (con archivo, línea y `^`) | El archivo tiene un error de escritura; behave no carga **ningún** step | Ir a esa línea; el `^` marca dónde Python dejó de entender |
| `IndentationError: unexpected indent` | Espacios/tabs mezclados o mal alineados | Reindentar con 4 espacios |
| `No module named 'src.test.library'; 'src.test' is not a package` | Un archivo suelto `src/test.py` tapa la carpeta `src/test/` | Eliminar o mover el archivo suelto |
| `NameError: name 'X' is not defined` | Se usa algo que no se importó o no existe | Importarlo o corregir el nombre |
| `AmbiguousStep: @when('...') has already been defined` | Dos steps con el mismo texto | `buscar_step` y dejar uno solo |
| `You can implement step definitions for undefined steps` | Un paso del feature no tiene step | Reutilizar el texto exacto de uno existente o implementarlo |

## Ejecución web (Selenium)

| Mensaje | Qué significa | Cómo se arregla |
|---|---|---|
| `AssertionError: No se encontró el elemento ('id', 'x') en 10 s` | El locator ya no existe o la página no cargó | `explorar_pagina` / `explorar_tras_steps` y actualizar el locator en la page |
| `AssertionError: ... se esperaba 'A' y se obtuvo 'B'` | La verificación falló: la app mostró otra cosa | Ver la captura en el Word: ¿dato incorrecto o bug? |
| `SessionNotCreatedException: This version of ChromeDriver only supports Chrome version N` | Driver y Chrome no coinciden | Dejar `driver_path` vacío (resolución automática) o poner el driver correcto |
| `ConnectionError: Could not reach host` al iniciar | webdriver-manager no tiene internet | El framework pasa a Selenium Manager; si tampoco hay red, usar `driver_path` |
| `ElementClickInterceptedException` | Un loader o modal tapa el botón | Esperar a que desaparezca el loader antes del click |
| `StaleElementReferenceException` | La página se redibujó después de encontrar el elemento | Volver a buscar el elemento (usar los helpers de `BasePage`) |

## Datos (Excel)

| Mensaje | Qué significa | Cómo se arregla |
|---|---|---|
| `KeyError: 'correo'` | La hoja no tiene esa columna (o tiene otro nombre/espacios) | Revisar el encabezado; usar `leer_excel` |
| `IndexError: list index out of range` | `<datos>` apunta a una fila que no existe | La fila 1 es la primera debajo del encabezado; `validar_fila_excel` |
| `El archivo X.xlsx no existe!` | Nombre del tag `@xc-` distinto al archivo | El tag va sin `.xlsx` y respetando mayúsculas |
| `PermissionError: [Errno 13]` / `[WinError 32]` | El Excel o el Word está abierto | Cerrarlo y volver a ejecutar |
| `BadZipFile` / `InvalidFileException` | Se leyó un archivo temporal `~$...xlsx` o el Excel está dañado | Cerrar Excel, borrar el `~$` |

## Servicios (API)

| Mensaje | Qué significa | Cómo se arregla |
|---|---|---|
| `Variables globales no encontradas: AditionalHeaders:access_token` | El escenario que genera el token no corrió antes en la misma ejecución | Ejecutar con un tag que incluya primero el escenario del token |
| `Variables no encontradas en el response: access_token` | El servicio de token no devolvió ese campo | Revisar el response del token y la columna `GlobalVariables` |
| `JSONDecodeError: Expecting property name enclosed in double quotes` | El `Body` del Excel no es JSON válido | Comillas dobles, sin coma final |
| `Request Type no soportado` | Método escrito mal | GET, POST, PUT, PATCH o DELETE |
| `Expected Status Code: 200 / Actual Status Code: 401` | Token vencido, ausente o sin permisos | Revisar `AditionalHeaders` y el escenario del token |
