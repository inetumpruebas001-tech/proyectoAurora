---
name: revisar-buenas-practicas
description: Revisa que el código del framework cumpla las buenas prácticas y el patrón de diseño (datos en Excel, steps genéricos reutilizados, compuerta Ejecucion, fallas que no se silencian, sin secretos) y que un cambio no introduzca infracciones nuevas. Úsalo después de cada cambio, antes de un commit o PR, o cuando pidan evaluar la calidad del framework.
argument-hint: "[cambios | todo | lista de archivos]"
---

# Revisar buenas prácticas

## Cuándo

- **Siempre** al terminar de modificar código (feature, step o library).
- Antes de sugerir un commit o un PR.
- Cuando pidan una evaluación del framework completo.

## Cómo

1. `revisar_buenas_practicas(alcance="cambios")` para lo modificado (usa git).
   - Para archivos puntuales: `alcance="archivos", archivos=[...]`.
   - Para evaluar todo: `alcance="todo"`.
2. Lee `aprobado`:
   - `false` → hay **errores nuevos**. Corrígelos antes de dar la tarea por terminada.
     No los ocultes ni los agregues a la línea base.
   - `true` → informa los avisos nuevos y propone la mejora, sin bloquear.
3. Los hallazgos con `nuevo: false` son deuda registrada en la línea base: menciónalos
   solo si el usuario pidió una evaluación completa.

## Cómo corregir cada regla

| Regla | Corrección |
|---|---|
| COM-SINTAXIS | Corregir el archivo: con un error de sintaxis behave no carga ningún step |
| COM-MODULO-SOMBRA | Eliminar o mover el script suelto de `src/` (p. ej. `src/test.py`) |
| COM-STEP-DUPLICADO / SIN-DEFINIR | `buscar_step` y reutilizar los steps genéricos con su texto exacto |
| COM-FALLA-SILENCIADA | En el `except`, actualizar `context.custom_message` y `raise AssertionError(...)` |
| COM-COMPUERTA-EJECUTAR | `if context.ejecutar == "SI": ... else: context.state = "NO-EXECUTED"` |
| COM-URL-EN-CODIGO | El endpoint va en la columna `Endpoint` del Excel |
| COM-FEATURE-TAGS | Tag funcional + `@xc-<Excel>` + `@pg-<Hoja>` |
| COM-SLEEP | Reintento con tiempo máximo en lugar de esperas fijas |
| COM-SECRETO | Quitar el valor; usar Key Vault o variables de entorno (`AZURE_STORAGE_ACCOUNT_KEY`, `DB_USER`, `DB_PASSWORD`). Avisar al líder: la clave debe rotarse |
| COM-TLS | Solo informativo: documentar por qué se usa `verify=False` |

## Línea base

La línea base (`tools/mcp_framework/linea_base_buenas_practicas.json`) guarda la deuda
conocida para que no bloquee. Solo el líder técnico la actualiza
(`actualizar_linea_base=True`), normalmente después de pagar deuda. El agente nunca la
actualiza por su cuenta para que una revisión pase.
