# Framework de automatización de servicios — Behave + requests (Python)

Repo de pruebas de API **dirigido por Excel**: la mayoría de casos nuevos se agregan como filas
del Excel y filas del `Examples`, sin escribir Python. Responde siempre en español.

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/test/features/*.feature` | Escenarios Gherkin |
| `src/test/features/steps/api_steps.py` | Los 7 steps genéricos de API |
| `src/test/features/environment.py` | Hooks: arma JSON, reporte HTML, JUnit y Word |
| `src/test/library/util_api.py` | `UTIL_API`: lee la fila, envía la petición y valida |
| `src/test/resources/data/excel/*.xlsx` | Datos de cada servicio (una fila = un caso) |
| `config/ambientes.json` | Un bloque por ambiente (`local`, `dev`, `certi`, `prod`): `baseUrl`, `semillero`, `salud`… |
| `src/test/library/config_ambiente.py` | Carga el ambiente, resuelve `{{variables}}` y despierta el servicio |
| `service.properties` | `ambiente`, `timeout_seg`, `log`, `Proyecto`, `Ciclo`, `Word` (`Individual`), `verify_ssl` |
| `azure-pipelines.yml` | Pipeline: compuerta → behave por tag → Word/HTML/JUnit (+ Azure Table opcional) |

Ejecutar (PowerShell, desde la raíz; no hace falta `Activate.ps1`):
`$env:AMBIENTE="dev"; .\venv\Scripts\python.exe -m behave --tags=@<Tag>`
`behave.ini` excluye `@skip` por defecto.

## Steps genéricos (reutilízalos SIEMPRE con este texto exacto)

```gherkin
Given se extrae los datos del servicio del excel "<datos>"
When cuando envio una peticion al servicio "<datos>"
Then se valida el status code obtenido con el status code esperado "<datos>"
And se valida la estructura del response obtenido con el response esperado "<datos>"
And se valida el response obtenido con el response esperado "<datos>"
And se valida los headers del response obtenido con los headers esperados "<datos>"
And se guarda como globales las variables del response "<datos>"
```

Plantilla de escenario:

```gherkin
@<TagFuncional> @xc-<ArchivoExcel> @pg-<Hoja>
Scenario Outline: Api Test "<datos>"
  Given se extrae los datos del servicio del excel "<datos>"
  When cuando envio una peticion al servicio "<datos>"
  Then se valida el status code obtenido con el status code esperado "<datos>"
  And se valida la estructura del response obtenido con el response esperado "<datos>"
  And se valida el response obtenido con el response esperado "<datos>"

  Examples:
    | datos |
    |     1 |
```

`<datos>` = número de fila de datos (`1` = primera fila debajo del encabezado).

## Columnas del Excel (todas deben existir en la hoja; `util_api.py` las lee siempre)

| Columna | Formato |
|---|---|
| `Ejecucion` | `SI` / `NO` (NO = escenario skipped) |
| `Escenario` | Nombre que se verá en el reporte |
| `Iteracion` | `1` en la primera fila de cada Api (crea la tabla inicial del Word) |
| `Api` | Nombre del Word de evidencia (`<Api>.docx`) |
| `Endpoint` | `{{baseUrl}}/ruta` (o URL completa `https://...`) |
| `Request Type` | `GET`, `POST`, `PUT`, `PATCH` o `DELETE` (mayúsculas o minúsculas) |
| `Headers` / `Params` | Una línea por valor: `Clave: Valor` (p. ej. `X-Semillero: {{semillero}}`) |
| `Body` | JSON válido, XML si empieza con `<`, o `campo: valor` / `campo: @archivo` por línea si `Headers` dice `multipart/form-data` (archivos en `data/archivos`) |
| `Expected Status Code` | Código HTTP (`200`) |
| `Expected Headers Response` | JSON `{"Content-Type": "*"}`; `*` = solo valida que exista |
| `Expected Response` | JSON con las llaves esperadas; `"*"` = solo valida la llave |
| `Expected Content_1..6` | Textos que deben aparecer en el response |
| `GlobalVariables` | Llaves del response a guardar: `access_token`, o con alias `cotizacionId=id`, `token=data.token` |
| `Expected Schema` | Opcional. JSON Schema del response completo: JSON en línea, `archivo.schema.json` o `openapi.json#/components/schemas/<Nombre>` (carpeta `data/schemas`) |
| `AditionalHeaders` | Variables globales a enviar como header (`access_token` → `Authorization: Bearer ...`) |
| `aditionalBody` | Variables globales a insertar en el body |

Encadenamiento: el escenario del token (`@pg-token`) guarda `access_token` con `GlobalVariables`,
y los siguientes lo usan con `AditionalHeaders`. Deben correr **en la misma ejecución**
(mismo tag) y el del token primero. Si la variable no existe, la petición se detiene con
`AssertionError: Variables globales no encontradas: ...` (antes salía sin token y fallaba con 401).
Los valores de `Authorization`, tokens y claves se enmascaran (`****`) en log, reporte y Word.
Ejemplo mínimo: `src/test/features/ejemplo_api.feature` + `plantilla_api.xlsx` (hoja **Ejemplo**; la hoja **Leeme** explica cada columna).
Para un servicio nuevo, `agregar_filas_excel(..., crear=true)` crea el archivo o la hoja desde la plantilla.

## Escribir en el Excel (solo con confirmación del QE)

- Las filas se agregan con `agregar_filas_excel`: 1) sin `confirmacion` → vista previa y código;
  2) muestras la vista previa y **preguntas al QE**; 3) solo con su "sí", llamas con `confirmacion=<código>`.
- Solo agrega al final. Nunca modifiques ni borres filas existentes ni edites el .xlsx con Python u otra herramienta.
- Antes de escribir se guarda un respaldo en `.respaldo_excel/`.

## Ambientes y variables `{{...}}` (como Postman)

- El ambiente se elige con `AMBIENTE=dev|certi|local` (o `ambiente` en `service.properties`).
  Cualquier clave se sobrescribe con una variable de entorno en MAYÚSCULAS (`BASEURL`, `SEMILLERO`).
- `{{nombre}}` funciona en **cualquier columna** del Excel. Orden de resolución:
  1. variables guardadas antes con `GlobalVariables` (p. ej. `{{cotizacionId}}`),
  2. variables del ambiente (`{{baseUrl}}`, `{{semillero}}`),
  3. dinámicas: `{{hoy}}`, `{{hoy+30}}`, `{{hoy-1}}`, `{{hoy-18a}}` (años), con formato opcional
     `{{hoy+30:dd/mm/aaaa}}` (fecha de Perú), `{{uuid}}`, `{{aleatorio}}`.
- Si una `{{variable}}` no existe, el escenario falla con un mensaje claro y la petición no sale.
- Nunca escribas URLs de ambiente en el Excel: usa `{{baseUrl}}`. Nunca agregues datos reales al JSON.
- `prod` está marcado `"bloqueado": true`: no se ejecuta salvo `PERMITIR_AMBIENTE_BLOQUEADO=si`
  (y nunca desde el pipeline). No propongas correr pruebas que escriban datos en PROD.
- Antes de la primera prueba se llama a `salud` hasta recibir 200 (servicios gratuitos que se duermen).

## Jira, Xray y evidencias

- **Casos de prueba:** se registran a mano en Xray (descripción y campos propios). Nunca crees casos
  ni Test Executions en Xray. Si el QE aún no registró un caso, puedes redactarle el texto del caso
  (título, precondición, pasos, resultado esperado) para que él lo registre.
- **Clave del caso:** el `Escenario` del Excel empieza con la clave de Xray: `TAP-4234 - Cotiza con
  edad mínima`. Esa clave nombra el Word de evidencia (`TAP-4234-PASSED.docx`).
- **Cerrar una ejecución** (skill `cerrar-ejecucion`):
  - `preparar_evidencias(test_plan, test_execution)` → `evidencias_sharepoint/<TestPlan>/<TestExecution>/<CLAVE>.docx`
    + `resumen.md`/`resumen.csv`, lista para arrastrar al SharePoint (local, sin conexión).
  - `actualizar_test_execution(test_execution)` → cambia estados en la Test Execution que el QE creó:
    vista previa y **"sí" del QE** antes de escribir. No agrega casos que no estén en ella.
- **HU en Jira:** si el MCP `atlassian` está habilitado, lee la historia por su clave en vez de pedir
  que la peguen. Cualquier escritura en Jira (Bug, comentario) va con borrador y "sí" del QE.
- La API Key de Xray la pide VS Code al iniciar el MCP (`inputs` de `.vscode/mcp.json`); nunca en archivos.

## Reglas

- Un servicio nuevo = hoja o filas nuevas en el Excel + `Scenario Outline` con la plantilla.
  Solo escribe Python si la validación no la cubren los steps genéricos.
- Si escribes un step nuevo, usa `UTIL_API(context).enviar_peticion(endpoint=..., method=...,
  headers=..., body=...)` y respeta el patrón `if context.ejecutar == "SI": ... else:
  context.state = "NO-EXECUTED"` y `context.custom_message` (alimenta el reporte).
- Antes de crear un step, `buscar_step`: dos steps con el mismo texto rompen toda la carga (`AmbiguousStep`).
- Nunca pongas tokens, claves ni datos de clientes reales en features, Excel, `ambientes.json`, código o commits.
- No dejes scripts sueltos en `src/` (p. ej. `src/test.py`): tapan el paquete `src/test`
  y rompen los imports del framework.
- Nunca imprimas el valor de una variable global ni de un header sensible: usa `ocultar_sensibles()`.
- La clave del Storage de Azure solo por variable de entorno `AZURE_STORAGE_ACCOUNT_KEY` o Key Vault.

## Skills disponibles

| Pedido del QE | Skill |
|---|---|
| Pega una historia completa y quiere probarla o automatizarla | `de-historia-a-automatizacion` |
| Solo quiere el análisis QA de una historia | `analizar-historia` |
| Quiere los escenarios y la cobertura de una historia | `disenar-escenarios` |
| Trae un endpoint, curl o casos de un servicio | `automatizar-servicio-api` |
| Algo falló | `diagnosticar-fallo` |
| Revisar calidad antes de un commit | `revisar-buenas-practicas` |
| Empieza en el proyecto o algo no instala / no abre | `configurar-entorno` |
| Pega un error o log de la terminal | `resolver-error-python` |
| Quiere registrar resultados en Xray o preparar evidencias | `cerrar-ejecucion` |
| Quiere subir su trabajo (commit, push y PR) | `subir-cambios` |
| Quiere actualizar su rama, hacer merge o tiene un conflicto | `trabajar-con-git` |

## Atajos con `/` en el chat

Todas las skills se pueden invocar escribiendo `/` + su nombre. Las más usadas:

| Atajo | Para qué |
|---|---|
| `/configurar-entorno` | Revisar y crear o reutilizar el ambiente virtual |
| `/resolver-error-python` | Entender un error del log y dónde está |
| `/de-historia-a-automatizacion` | De historia de usuario o contrato a casos en Excel ejecutados |
| `/cerrar-ejecucion` | Evidencias ordenadas para SharePoint + estados en la Test Execution de Xray |
| `/subir-cambios` | Compuerta + rama + commit + push + descripción del PR |
| `/trabajar-con-git` | Actualizar la rama con develop, merge y conflictos |

Si el QE no da un dato que la skill necesita (URL, hoja de Excel, historia), pregúntalo en un solo mensaje.

## Git (obligatorio)

- Nunca trabajes en `develop` ni `main`: rama `feature/HU-<n>-<descripcion>`.
- El trabajo termina con `git push` y Pull Request a `develop`; el código no se queda en la PC.
- No propongas `--force`, `--no-verify` ni commits de `venv/`, reportes o secretos.

## Compuerta de calidad (obligatoria)

Después de **cada** cambio de código ejecuta `revisar_buenas_practicas(alcance="cambios")`
(skill `revisar-buenas-practicas`). Si `aprobado` es `false`, corrige los errores nuevos antes
de terminar. Nunca actualices la línea base para que la revisión pase. La misma revisión corre
en el pre-commit y en el pipeline.

## Herramientas MCP disponibles (`framework-api`)

`info_framework`, `listar_steps`, `buscar_step`, `validar_features`, `leer_excel`,
`validar_fila_excel`, `agregar_filas_excel`, `preparar_evidencias`, `actualizar_test_execution`, `ejecutar_escenarios`, `ultimo_resultado`, `revisar_buenas_practicas`, `diagnosticar_entorno`.
`validar_fila_excel` detecta los errores de Excel más comunes antes de ejecutar.
`agregar_filas_excel` agrega filas (vista previa → confirmación del QE → escritura con respaldo).
`preparar_evidencias` ordena las evidencias para SharePoint; `actualizar_test_execution` cambia estados en Xray (vista previa → confirmación).

### Si las herramientas MCP no están disponibles

En organizaciones con `Chat › MCP: Access = registry` el servidor `framework-api` no se carga.
En ese caso **ejecuta la misma herramienta en la terminal** (devuelve el mismo JSON) y
continúa el flujo igual. Argumentos como `clave=valor`; no hace falta activar el venv.

| Herramienta | Comando en terminal |
|---|---|
| `info_framework` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py info_framework` |
| `listar_steps` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py listar_steps filtro="texto"` |
| `buscar_step` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py buscar_step texto="Usuario ingresa su correo"` |
| `validar_features` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py validar_features tag=Ejemplo` |
| `leer_excel` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py leer_excel archivo=plantilla_api hoja=Ejemplo fila=1` |
| `validar_fila_excel` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py validar_fila_excel archivo=plantilla_api hoja=Ejemplo fila=1` |
| `agregar_filas_excel` | Guarda las filas en `.respaldo_excel\filas-pendientes.json` y: `.\venv\Scripts\python.exe tools\mcp_framework\server.py agregar_filas_excel archivo=cotizador hoja=Cotizaciones crear=true filas=@.respaldo_excel\filas-pendientes.json` (vista previa); tras el "sí" del QE, lo mismo + `confirmacion=<código>` |
| `preparar_evidencias` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py preparar_evidencias test_plan=TAP-4000 test_execution=TAP-5000` |
| `actualizar_test_execution` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py actualizar_test_execution test_execution=TAP-5000` (vista previa); tras el "sí" del QE, lo mismo + `confirmacion=<código>`. Requiere `XRAY_CLIENT_ID`/`XRAY_CLIENT_SECRET` en la terminal |
| `ejecutar_escenarios` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py ejecutar_escenarios tag=Ejemplo` |
| `ultimo_resultado` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py ultimo_resultado` |
| `revisar_buenas_practicas` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py revisar_buenas_practicas alcance=cambios` |
| `diagnosticar_entorno` | `.\venv\Scripts\python.exe tools\mcp_framework\server.py diagnosticar_entorno` (venv roto: `py -3.12 tools\mcp_framework\server.py diagnosticar_entorno`) |
