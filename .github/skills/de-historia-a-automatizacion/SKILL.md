---
name: de-historia-a-automatizacion
description: Lleva una historia de usuario de punta a punta en el framework de servicios (Behave + Excel) — análisis QA, diseño de escenarios, filas de Excel, escenario con steps genéricos, validación y ejecución — con pausas para que el QE apruebe. Úsalo cuando peguen una historia completa y pidan probar o automatizar sus servicios.
argument-hint: "[clave de Jira (AUR-12) o historia pegada + contrato del servicio]"
---

# De historia a automatización (framework de servicios)

Recorre las etapas en orden. **Detente en cada ⏸ y espera la respuesta del QE.**

## Etapa 0 — Entrada

Necesitas: la historia con sus criterios y el contrato del servicio (endpoint, método,
request y response de ejemplo, si requiere token). Acepta un curl o un request de Postman.

Si el QE da una **clave de Jira** (p. ej. `AUR-12`) y el MCP `atlassian` está disponible, lee la
historia de Jira (descripción, criterios, adjuntos/enlaces al contrato) en lugar de pedir que la pegue.
Si no está disponible, pide que la pegue. Guarda la clave: será el tag de Jira del feature.
Nunca pidas tokens reales: el token llega por `GlobalVariables` / `AditionalHeaders`.

## Etapa 1 — Análisis (skill `analizar-historia`)

Diagnóstico, reglas RN-01..n y preguntas al PO.
⏸ **Pausa:** "¿Seguimos con estas reglas o esperas respuesta del PO?"

## Etapa 2 — Diseño (skill `disenar-escenarios`)

Escenarios con técnica, capa, prioridad y regla de origen. Los de capa **UI** se entregan
como lista para el framework web; los manuales, para ejecución manual.
⏸ **Pausa:** "¿Apruebas estos escenarios de API para automatizar?"

## Etapa 3 — Filas de Excel

1. `info_framework` y `leer_excel(archivo="plantilla_api", hoja="Ejemplo")` (o una hoja parecida) para copiar el formato real.
   Si el servicio no tiene Excel, se crea desde la plantilla con `crear=true`; una hoja por grupo de casos.
2. Una fila por escenario con TODAS las columnas (Ejecucion, Escenario, Iteracion, Api,
   Endpoint, Request Type, Headers, Params, Body, Expected Status Code, Expected Headers
   Response, Expected Response, Expected Content_1.., AditionalHeaders, aditionalBody,
   GlobalVariables, Expected Schema opcional). Request Type: GET, POST, PUT, PATCH o DELETE.
   `Escenario` empieza con la clave del caso en Xray (`TAP-4234 - ...`). Si el QE aún no registró los
   casos, redáctale el texto de cada caso para que lo registre en Xray y pídele las claves antes de escribir.
3. `Endpoint` como `{{baseUrl}}/ruta` y valores del ambiente con `{{nombre}}`
   (reglas en la skill `automatizar-servicio-api`, sección 4). Ids que se reutilizan:
   `GlobalVariables = alias=ruta` y luego `{{alias}}`.
4. Si requiere token: primero la fila del token con `GlobalVariables = access_token`.
5. Si el resultado depende de la fecha o de datos previos: hoja `Soporte` (reinicio, reloj fijo) que corre primero.
6. `agregar_filas_excel` **sin** `confirmacion` → vista previa.
⏸ **Pausa:** muestra la vista previa y pregunta "¿Agrego estas N filas a `<archivo>` / `<hoja>`?".
Solo con un "sí" del QE: `agregar_filas_excel(..., confirmacion=<código>)`. Luego `validar_fila_excel` por cada fila.

## Etapa 4 — Escenario (skill `automatizar-servicio-api`)

Tag de la HU de Jira en la línea del `Feature` (p. ej. `@AUR-12`): deja la trazabilidad historia → escenarios.
Los escenarios de preparación (reinicio, reloj) llevan `@soporte`: no son casos y no se reportan a Xray.
`Scenario Outline` con los steps genéricos, tags funcional + `@xc-<Excel>` + `@pg-<Hoja>` y
un número de fila por caso en `Examples`. Python nuevo solo si una validación no la cubren
los steps genéricos (`buscar_step` antes).

## Etapa 5 — Calidad

`validar_features(tag)` → `ok: true`; si escribiste Python,
`revisar_buenas_practicas(alcance="cambios")` → `aprobado: true`.

## Etapa 6 — Ejecución y entrega

1. ⏸ "¿Ejecuto el tag @X ahora?" → `ejecutar_escenarios(tag)`.
2. Si falla, skill `diagnosticar-fallo`.
3. Entrega: matriz regla → escenario → capa → estado, filas agregadas, resultado, ruta del
   reporte y Word, preguntas al PO pendientes y posibles defectos.
4. Ofrece cerrar la ejecución (skill `cerrar-ejecucion`): evidencias para SharePoint y estados en la
   Test Execution que el QE creó en Xray (con vista previa y confirmación).
