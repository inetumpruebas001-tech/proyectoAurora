---
name: automatizar-servicio-api
description: Automatiza casos de un servicio REST/SOAP en el framework Behave dirigido por Excel (filas de datos, escenario con steps genéricos, encadenamiento de token). Úsalo cuando pidan automatizar o agregar casos de un endpoint o API.
argument-hint: "[endpoint, método y casos; o un curl, colección de Postman o contrato OpenAPI]"
---

# Automatizar un servicio

## 1. Entender el servicio

Necesitas: endpoint, método, headers, body de ejemplo, respuesta esperada y si requiere token.
Acepta un `curl`, una colección/environment de Postman o un contrato OpenAPI (Swagger) y extrae
esos datos. El contrato manda: códigos de error, formato de error y campos obligatorios salen de ahí.
Si falta el método o el endpoint, haz UNA sola pregunta. No pidas ni muestres tokens reales.

Variables de un environment de Postman → `config/ambientes.json` (una clave por variable,
un bloque por ambiente). Variables que se llenan en ejecución (ids, tokens) **no** van ahí:
se guardan con `GlobalVariables`.

## 2. Revisar el repo con el MCP

1. `info_framework` → Excel y hojas existentes, tags, problemas abiertos
   (si hay `errores_sintaxis_steps`, avisa: nada se ejecutará hasta corregirlos).
2. `leer_excel(archivo, hoja)` de una hoja parecida para copiar el formato real de las columnas.

## 3. Diseñar los casos

Por cada caso (positivo, negativos de validación, 401 sin token, 404, etc.) define:
`Escenario`, `Request Type`, `Headers`, `Params`, `Body`, `Expected Status Code`,
`Expected Response` (JSON de llaves, `"*"` si el valor varía), `Expected Content_1..`.
Propón una tabla con una fila por caso y pide confirmación antes de seguir.

Resultados deterministas: si el resultado depende de la fecha (edad, vencimientos) o de datos
previos, busca en el contrato endpoints de soporte de pruebas (reinicio de datos, reloj fijo,
cabecera de aislamiento como `X-Semillero`) y úsalos en una hoja `Soporte` que corre primero.
Calcula los valores esperados con las reglas de la historia; no los copies de una ejecución.

## 4. Agregar las filas al Excel (con confirmación del QE)

- **Escribe las filas con `agregar_filas_excel`, siempre en dos pasos:**
  1. Llámala sin `confirmacion`: valida y devuelve la vista previa y un código.
  2. Muestra al QE la vista previa (datos, escenario, método, endpoint, status) y pregunta:
     "¿Agrego estas N filas a `<archivo>` / hoja `<hoja>`?". **Espera su respuesta.**
  3. Solo con un "sí" explícito del QE, llama de nuevo con las mismas filas y `confirmacion=<código>`.
     Si pide cambios, corrige y vuelve al paso 1 (el código anterior ya no sirve).
- Si el Excel o la hoja no existen, usa `crear=true` (se crean desde `plantilla_api.xlsx`) y dilo en la pregunta.
- Nunca modifiques ni borres filas existentes, ni edites el .xlsx por otro medio (Python, openpyxl,
  terminal). Para corregir una fila existente, indica al QE la celda y el valor; la edita él.
- Si responde que el archivo está abierto, pide al QE cerrarlo en Excel y vuelve a confirmar.
- `Iteracion` vacía se numera sola por `Api`; `Ejecucion` vacía = `SI`.
- `Endpoint` siempre como `{{baseUrl}}/ruta`; nunca la URL de un ambiente escrita a mano.
- Valores del ambiente en headers o body con `{{nombre}}` (p. ej. `X-Semillero: {{semillero}}`);
  fechas relativas con `{{hoy}}`, `{{hoy+30}}`, edades con `{{hoy-18a}}` y formato con `{{hoy+30:dd/mm/aaaa}}`.
- Para reutilizar un dato del response: `GlobalVariables = cotizacionId=id` (alias=ruta, la ruta
  admite `data.token` o `items.0.id`) y en filas siguientes `{{cotizacionId}}` en cualquier columna.
- Si necesita token: la fila del token con `GlobalVariables = access_token` y las demás con
  `AditionalHeaders = access_token` (o `Authorization: Bearer {{access_token}}` en `Headers`).
- Si una clave nueva hace falta en `config/ambientes.json`, indícala al QE; no la inventes.
- **Subir archivos:** `Headers` con `Content-Type: multipart/form-data` y `Body` con una línea por
  campo: `descripcion: DNI` / `archivo: @nombre.pdf` (`;type=application/pdf` opcional). El archivo
  debe existir en `src/test/resources/data/archivos/` y ser ficticio; si falta, pídeselo al QE.
- **JSON Schema** (`Expected Schema`, opcional): valida TODO el response, no solo las llaves de
  `Expected Response`. Si el contrato es OpenAPI, pide al QE guardar el JSON del contrato en
  `src/test/resources/data/schemas/openapi.json` y usa `openapi.json#/components/schemas/<Nombre>`.
  Úsalo en los casos exitosos y en el formato de error; los casos de valor puntual siguen en `Expected Response`.

## 5. Escenario

- Reutiliza la plantilla de `.github/copilot-instructions.md` con los steps genéricos.
- Tags: funcional (`@ConsultaCliente`), `@xc-<Excel>`, `@pg-<Hoja>`.
- `Examples` con un número de fila por caso.
- Solo si una validación no la cubren los steps genéricos: `buscar_step` y luego un step
  nuevo usando `UTIL_API`.

## 6. Validar y ejecutar

1. Después de escribir: `validar_fila_excel` por cada fila agregada.
2. `validar_features(tag="<TagFuncional>")` → `ok: true`.
   Si escribiste Python: `revisar_buenas_practicas(alcance="cambios")` → `aprobado: true`.
3. `ejecutar_escenarios(tag="<TagFuncional>")` con el ambiente que eligió el QE (`AMBIENTE=local|dev|certi`).
   Nunca contra `prod`. Si falla, usa la skill `diagnosticar-fallo`
   (un `Variables sin valor` = falta la clave en `ambientes.json` o el escenario que la guarda no corrió antes).
4. Entrega: escenario agregado, filas agregadas (archivo, hoja, números de `datos`), respaldo, resultado y ruta del reporte y los Word.
