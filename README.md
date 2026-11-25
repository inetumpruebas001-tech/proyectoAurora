# QE API Framework – Behave + requests, dirigido por Excel

Framework BDD para pruebas de API: **un caso nuevo es una fila del Excel y un número en el `Examples`**,
sin escribir Python. Ambientes como en Postman (`{{baseUrl}}`, `{{semillero}}`…), evidencia en **Word**,
reporte **HTML**, estados en la **Test Execution de Xray**, evidencias ordenadas para **SharePoint**, pipeline en
**GitHub Actions** (o Azure DevOps) y registro opcional en **Azure Table Storage** con la clave en **Key Vault**. Incluye kit de **GitHub Copilot** (instrucciones, skills, agente y MCP) y una
**compuerta de buenas prácticas** que corre en el pre-commit y en el pipeline.

Viene **vacío a propósito**: solo un escenario de ejemplo (`@Ejemplo`, estado de la API). Los escenarios
de cada historia los crea el QE con Copilot + MCP (`/de-historia-a-automatizacion`). Objetivo de práctica:
**Aurora Vida** (API en Render, contrato en GitHub Pages).

---

## 1. Requisitos

Python **3.12.x**, Git, VS Code + GitHub Copilot. (Con 3.13/3.14 fallan dependencias fijadas.)

```powershell
py -3.12 -m venv venv  (de no reconocer ejecutar python -m venv venv)
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install -r tools\mcp_framework\requirements-mcp.txt
Para verificar behave: .\venv\Scripts\python.exe -m behave --version
git config core.hooksPath .githooks          # activa la compuerta en cada commit
```

No copies el `venv` de otra PC. Si `Activate.ps1` está bloqueado no lo necesitas: usa
`.\venv\Scripts\python.exe`. Diagnóstico: `.\venv\Scripts\python.exe tools\mcp_framework\server.py diagnosticar_entorno`.

## 2. Ambientes (`config/ambientes.json`)

Un bloque por ambiente, igual que los environments de Postman:

| Clave | Para qué |
|---|---|
| `baseUrl` | URL base del servicio. Obligatoria. |
| `semillero` | Valor del header `X-Semillero`: aísla tus datos y tu reloj de pruebas |
| `salud` | Ruta que se llama antes de empezar hasta recibir 200 (Render gratuito se duerme) |
| `espera_despertar_seg` | Cuánto esperar a que despierte (por defecto 120) |
| `bloqueado` | `true` en PROD: no corre salvo `PERMITIR_AMBIENTE_BLOQUEADO=si` |

- Se elige con la variable de entorno `AMBIENTE` (`local`, `dev`, `certi`) o `ambiente` en `service.properties`.
- Cualquier clave se sobrescribe con una variable de entorno en MAYÚSCULAS: `SEMILLERO`, `BASEURL`.
- **CERTI y PROD están vacíos**: completa `baseUrl` cuando tengas la URL.
- No pongas aquí tokens ni claves: este archivo se sube al repositorio.

## 3. Ejecutar

```powershell
$env:AMBIENTE  = "dev"
$env:SEMILLERO = "jmq"                       # opcional: tu semillero (por defecto qe-auto)
.\venv\Scripts\python.exe -m behave --tags=@Ejemplo
.\venv\Scripts\python.exe -m behave --dry-run          # valida que todos los steps existan
```

Siempre por tag, nunca la suite completa. Salidas: `src/test/reports/report-<fecha>/` (HTML + un Word
por caso) y `output.xml` (JUnit).

## 4. Crear los escenarios de una historia (con Copilot + MCP)

1. Abre el chat de Copilot en modo agente (agente *QE Automatizador API*) y escribe
   `/de-historia-a-automatizacion`, pegando la historia y el enlace o texto del contrato (Swagger).
2. Copilot hace el análisis QA y propone los escenarios. **Revisa y aprueba** en cada pausa.
3. Copilot arma las filas y te muestra una **vista previa** (escenario, método, endpoint, status).
   Solo si respondes que sí, las agrega al Excel (`agregar_filas_excel`); si el archivo o la hoja no
   existen, los crea desde `plantilla_api.xlsx`. Solo agrega al final, nunca cambia ni borra filas
   existentes, y guarda un respaldo en `.respaldo_excel/`. Cierra el Excel antes de confirmar.
4. Copilot valida cada fila (`validar_fila_excel`), crea el `.feature`, lo valida y lo ejecuta por tag
   (`ejecutar_escenarios`). Si algo falla, `diagnosticar-fallo` dice si es dato, ambiente o bug.
5. Revisa los valores esperados contra las reglas de la historia: el agente puede equivocarse en un
   cálculo o saltarse un límite. Lo que se espera sale de la historia, nunca de lo que respondió la API.

Reglas del Excel (la hoja **Leeme** las explica con ejemplos):

| Columna | Ejemplo |
|---|---|
| `Endpoint` | `{{baseUrl}}/api/v1/recurso` (nunca la URL escrita a mano) |
| `Headers` | `Content-Type: application/json` + salto de línea + `X-Semillero: {{semillero}}` |
| `Body` | JSON, form o XML/SOAP; acepta `{{variables}}` |
| `Expected Response` | JSON con lo esperado; `"*"` = solo valida que la llave exista; `["*"]` = que sea lista |
| `Expected Headers Response` | `{"Location": "*"}` |
| `GlobalVariables` | `recursoId=id` guarda `response.id` como `{{recursoId}}` (ruta: `data.token`, `items.0.id`) |
| `Ejecucion` | `NO` = el caso sale como skipped |
| `Expected Schema` | Opcional: valida **todo** el response contra un JSON Schema (ver abajo) |

**Subir archivos (multipart):** en `Headers`, `Content-Type: multipart/form-data`; en `Body`, una línea
por campo: `descripcion: DNI ficticio` y `archivo: @documento_ficticio.txt` (`;type=application/pdf`
para forzar el tipo). Los archivos van en `src/test/resources/data/archivos/` y siempre son ficticios.

**JSON Schema:** en `Expected Schema` puedes poner el schema en línea, un archivo de
`src/test/resources/data/schemas/` (ej. `ejemplo_salud.schema.json`) o una parte del contrato:
guarda el OpenAPI de Swagger como `schemas/openapi.json` y usa `openapi.json#/components/schemas/<Nombre>`.
Se resuelven las `$ref` internas y las diferencias de OpenAPI 3.0 (`nullable`). Corre dentro del paso
*"se valida la estructura del response…"*: no hace falta un step nuevo.

Variables `{{...}}` en cualquier columna. Orden: guardadas con `GlobalVariables` → del ambiente →
dinámicas (`{{hoy}}`, `{{hoy+30}}`, `{{hoy-1}}`, `{{hoy-18a}}`, `{{hoy+30:dd/mm/aaaa}}`, `{{uuid}}`, `{{aleatorio}}`). Si falta una, el caso
falla con `Variables sin valor en la fila N: ...` y la petición no sale.

Escenario para una historia (mismos steps que `ejemplo_api.feature`; el paso que guarda variables va justo después del status):

```gherkin
@HU01 @xc-cotizador @pg-Cotizaciones
Scenario Outline: Cotizar "<datos>"
  Given se extrae los datos del servicio del excel "<datos>"
  When cuando envio una peticion al servicio "<datos>"
  Then se valida el status code obtenido con el status code esperado "<datos>"
  And se guarda como globales las variables del response "<datos>"
  And se valida la estructura del response obtenido con el response esperado "<datos>"
  And se valida el response obtenido con el response esperado "<datos>"
  And se valida los headers del response obtenido con los headers esperados "<datos>"

  Examples:
    | datos |
    |     1 |
```

`<datos>` = número de fila (1 = primera fila debajo del encabezado).

## 5. Xray y evidencias

Cómo trabaja el equipo: **los casos se registran a mano en Xray** y **el QE crea su Test Execution**
y le asocia los casos. El framework **no crea nada en Xray**: ordena las evidencias y cambia estados.

1. **Clave en el Excel:** el `Escenario` empieza con la clave del caso: `TAP-4234 - Cotiza con edad mínima`.
   El Word sale como `TAP-4234-PASSED.docx`. `validar_fila_excel` avisa si falta o se repite.
2. **Ejecuta** por tag en el ambiente de la Test Execution (`$env:AMBIENTE="dev"`).
3. **`/cerrar-ejecucion TAP-4000 TAP-5000`** (Test Plan y Test Execution):
   - arma `evidencias_sharepoint/TAP-4000/TAP-5000/` con `TAP-4234.docx`, … y `resumen.md`/`resumen.csv`:
     arrastra la carpeta `TAP-4000` al SharePoint;
   - muestra la vista previa de la Test Execution: qué pasa a PASSED/FAILED, qué casos suyos no se
     ejecutaron y qué casos ejecutados no están en ella. **Solo con tu "sí"** cambia los estados,
     con el error (sin tokens) como comentario y el Word adjunto.

Sin Copilot: `python tools/xray/evidencias.py --test-plan TAP-4000 --test-execution TAP-5000` y
`python tools/xray/xray_cloud.py --test-execution TAP-5000 --simular` (quita `--simular` para escribir).

- **API Key de Xray** (Jira → Apps → Xray → API Keys, la crea un administrador): VS Code la pide al
  iniciar el MCP `framework-api` y la guarda cifrada. En la terminal: `$env:XRAY_CLIENT_ID` y `$env:XRAY_CLIENT_SECRET`.
- `config/xray.json`: `jiraUrl` (para el enlace) y la equivalencia `AMBIENTE` → Test Environment
  (avisa si ejecutaste en DEV y la Test Execution es de CERTI).
- **HU en Jira (opcional):** con el MCP oficial de Atlassian (`atlassian` en `.vscode/mcp.json`) Copilot
  lee la historia por su clave. Úsalo solo si el banco lo habilita.

## 6. GitHub Actions (pipeline principal)

`.github/workflows/pruebas-api.yml`: valida tags (bloquea `@prod`) → instala → compuerta → `behave`
por tag con `AMBIENTE` → reportes y JUnit **aunque haya fallos** → carpeta para SharePoint (artefacto
`sharepoint-<TestExecution>`) → estados en la Test Execution indicada. Manual (*Actions → Pruebas API →
Run workflow*: ambiente, tags, Test Plan, Test Execution) o programado de lunes a viernes 06:00 (Perú) en DEV.

- Lanzar el workflow con la clave de la Test Execution es la confirmación. Vacía = no toca Xray.
- *Settings → Secrets and variables → Actions*: secrets `XRAY_CLIENT_ID`, `XRAY_CLIENT_SECRET`
  (y `AZURE_STORAGE_ACCOUNT_KEY` si registras en Azure Table); variables `TAGS_REGRESION`,
  `XRAY_TEST_PLAN`, `XRAY_TE_DEV` (Test Execution de la regresión programada) y, para la tabla,
  `LOG_TABLA=true`, `AZURE_STORAGE_ACCOUNT_NAME`, `AZURE_TABLE_NAME`.

## 7. Azure DevOps (alternativa)

`azure-pipelines.yml`: valida tags (bloquea `@prod`) → instala → compuerta → `behave` por tag con
`AMBIENTE`/`SEMILLERO` → publica Word/HTML y JUnit **aunque haya fallos**. Regresión programada
de lunes a viernes 06:00 (Perú) en DEV. Parámetros al ejecutar: `ambiente` (dev/certi), `tags`,
`agente` (propio/hospedado) y `registrarEnTabla`.

1. **Repositorio:** GitHub privado. En Azure DevOps: *Pipelines → New pipeline → GitHub* →
   autoriza la app de Azure Pipelines solo para este repo → *Existing YAML* → `azure-pipelines.yml`.
2. **Agente:** los proyectos privados nuevos no tienen minutos hospedados hasta pedir el
   *free grant* (formulario de Microsoft, 2–3 días hábiles). Mientras tanto usa un agente propio:
   *Project settings → Agent pools → Default → New agent* e instálalo en tu PC con Python 3.12
   en el PATH. Con el grant aprobado, ejecuta con `agente = hospedado`.
3. **Log en Azure Table (opcional):**
   - Storage Account + tabla `ResultadosAutomatizacion`.
   - Key Vault con el secreto `storage-account-key` (la clave del Storage).
   - *Library → Variable group* `qe-azure-keyvault` enlazado al Key Vault (trae `storage-account-key`)
     con dos variables normales: `AZURE_STORAGE_ACCOUNT_NAME` y `AZURE_TABLE_NAME`.
   - Ejecuta con `registrarEnTabla = true`. Cada escenario queda como una fila con su `Ambiente`.
4. **Pestaña HTML (opcional):** instala la extensión *HTML Viewer* y descomenta los dos últimos pasos.

En local, el log en tabla se activa con `log=true` (o `LOG_TABLA=true`) y la clave por
`AZURE_STORAGE_ACCOUNT_KEY` o Key Vault (`AZURE_KEY_VAULT_NAME` + `az login`). **Nunca en el código.**
Si una clave llegó a un archivo o a un commit, **rótala** en Azure: borrarla del archivo no basta.

## 8. Copilot, compuerta y Git

- `.github/copilot-instructions.md`, 11 skills (`/configurar-entorno`, `/de-historia-a-automatizacion`, `/cerrar-ejecucion`,
  `/resolver-error-python`, `/subir-cambios`, `/trabajar-con-git`…), agente *QE Automatizador API* y
  MCP `framework-api` y `atlassian` (`.vscode/mcp.json`). Sin MCP, las mismas herramientas corren en la terminal.
- Compuerta: `tools\mcp_framework\server.py --revisar --todo`. Falla solo con errores **nuevos**
  respecto de la línea base; la línea base no se actualiza para "hacer pasar" un cambio.

```powershell
git checkout -b feature/HU-02-emision
git add . ; git commit -m "HU-02: casos de emisión"
git push -u origin feature/HU-02-emision    # luego Pull Request a develop
```

Datos: solo datos ficticios. Nada de datos de clientes reales en Excel, features ni commits.
