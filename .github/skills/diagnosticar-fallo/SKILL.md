---
name: diagnosticar-fallo
description: Diagnostica por qué falló un caso de API del framework Behave (dato de Excel, status, estructura, token encadenado, ambiente o bug real) a partir del último reporte. Úsalo cuando un caso sale en rojo o como skipped sin explicación.
argument-hint: "[tag o nombre del escenario, opcional]"
---

# Diagnosticar un fallo de API

## 1. Obtener el resultado

- `ultimo_resultado` → por cada fallido: paso, `error`, `detalle_paso` (esperado vs
  obtenido, request y response enmascarados), `step_python` y carpeta del reporte.
- Si no hay resultado o es de otra ejecución, pide permiso y usa `ejecutar_escenarios(tag)`.

## 2. Clasificar la causa (elige UNA y justifícala)

| Paso que falla / señal | Causa probable | Qué revisar |
|---|---|---|
| Given: `KeyError`, "error inesperado en lectura_excel" | **Columna faltante** o fila inexistente | `validar_fila_excel` |
| When: "Request Type no soportado" | `Request Type` distinto de GET/POST/PUT/PATCH/DELETE | La fila del Excel |
| When: "Variables globales no encontradas" | No corrió antes el escenario del token en la misma ejecución | Tag que incluya primero `@pg-token`; columna `GlobalVariables` |
| When: "Error al realizar la petición", `JSONDecodeError` | `Body` mal formado, URL inválida, red/VPN | `validar_fila_excel`; ¿hay VPN o proxy? |
| Status: esperado 200, obtenido 401/403 | **Token** no llegó o venció | ¿Corrió antes el escenario del token en el mismo tag? `GlobalVariables`/`AditionalHeaders` |
| Status: esperado ≠ obtenido (400/404/500) | Dato de prueba o posible bug | `detalle_paso` con el response real |
| Estructura: "No existe la llave" | Contrato cambió o el `Expected Response` está mal | Compara llaves del response real |
| Escenario skipped | `Ejecucion = NO` | `leer_excel(..., fila)` |
| Given: "Variables sin valor en la fila N: ..." | `{{variable}}` sin definir: falta en `config/ambientes.json` o no corrió antes el escenario que la guarda | `AMBIENTE` elegido, bloque del ambiente, `GlobalVariables` del escenario previo |
| Antes del primer escenario: "no tiene baseUrl" / "está bloqueado" | Ambiente sin URL o PROD | `config/ambientes.json`; `AMBIENTE` = local, dev o certi |
| Antes del primer escenario: "no respondió 200 en .../health" | Servicio caído o dormido más de lo esperado | Abrir la URL de salud; subir `espera_despertar_seg` |
| Response distinto solo en fechas/edades | Reloj de pruebas no fijado o semillero compartido | Que la hoja `Soporte` corra primero en el mismo tag; `SEMILLERO` propio |
| Sin JSON de resultados, `SyntaxError`, `AmbiguousStep`, `ModuleNotFoundError` | **Framework/entorno** | `validar_features(usar_behave=True)` y `errores_consola` |

## 3. Corregir o reportar

- Dato o Excel: indica la celda exacta y el valor correcto; el usuario edita el Excel.
- Posible bug: no cambies lo esperado para que "pase". Redacta el defecto con endpoint,
  método, request (sin tokens), esperado, obtenido y ruta del Word de evidencia.
- Si el MCP `atlassian` está disponible, ofrece crear el Bug en Jira: muestra el borrador
  (proyecto, resumen, descripción, prioridad propuesta, enlace a la HU y al Test Execution) y
  **créalo solo con el "sí" del QE**. Nunca adjuntes tokens ni datos personales.

Nunca muestres tokens, claves ni datos personales completos en la respuesta.
