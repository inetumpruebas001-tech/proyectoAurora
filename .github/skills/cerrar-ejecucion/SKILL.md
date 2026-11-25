---
name: cerrar-ejecucion
description: Cierra una ejecución — arma la carpeta de evidencias para SharePoint (Test Plan / Test Execution / clave) y actualiza los estados de la Test Execution que el QE ya creó en Xray, con vista previa y confirmación. Úsalo cuando el QE quiera registrar resultados en Xray o subir evidencias.
argument-hint: "[Test Plan] [Test Execution], ej. TAP-4000 TAP-5000"
---

# Cerrar una ejecución (evidencias + Xray)

Reglas del equipo:
- Los **casos** se registran a mano en Xray (llevan descripción y campos propios). Nunca los crees.
- La **Test Execution** la crea el QE en Xray y le asocia sus casos. Nunca la crees.
- El framework solo **cambia estados** de esa Test Execution y **ordena las evidencias**.

## 1. Antes

- Toma la **última ejecución**. Si no es la que el QE quiere cerrar, primero `ejecutar_escenarios(tag)`
  con el ambiente correcto (`AMBIENTE`).
- Cada `Escenario` del Excel empieza con la clave del caso en Xray: `TAP-4234 - ...`. Los que no
  la tengan no llegan a Xray ni al paquete; indícale al QE qué filas corregir (celda exacta).
- Escenarios `@soporte` (reinicio, reloj, login técnico) no cuentan como casos.
- Pide al QE el **Test Plan** y la **Test Execution** (claves) si no los dio.

## 2. Evidencias para SharePoint (local, sin conexión)

`preparar_evidencias(test_plan, test_execution)` → `evidencias_sharepoint/<TestPlan>/<TestExecution>/`
con un Word por clave (`TAP-4234.docx`), `resumen.md` y `resumen.csv`. Dile al QE que arrastre la
carpeta `<TestPlan>` al SharePoint. Avisa de casos sin evidencia o sin clave.

## 3. Estados en Xray (vista previa → pregunta → confirmación)

1. `actualizar_test_execution(test_execution)` **sin** `confirmacion`.
2. Muestra al QE: Test Execution y su ambiente (avisa si no coincide con el de la ejecución),
   cuántos pasan a PASSED y FAILED, **casos de la Test Execution que no se ejecutaron** y **casos
   ejecutados que no están en ella** (no se agregan: si deben ir, el QE los asocia en Xray y repite).
3. Pregunta: "¿Actualizo la Test Execution <clave> con estos N resultados?" y **espera**.
4. Solo con un "sí": `actualizar_test_execution(test_execution, confirmacion=<código>)`.
5. Entrega el enlace a la Test Execution y el resumen.

Si responde que faltan XRAY_CLIENT_ID/XRAY_CLIENT_SECRET o que Xray rechazó la API Key, explica que VS Code la pide al iniciar
el MCP `framework-api` (la crea un administrador de Jira en Apps → Xray → API Keys).
Nunca pidas, escribas ni muestres la API Key ni tokens.
