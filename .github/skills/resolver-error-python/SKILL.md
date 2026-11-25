---
name: resolver-error-python
description: Lee un error de Python, Behave, Selenium o pip (traceback o log de consola), explica en simple qué pasó, ubica el archivo y la línea del proyecto que lo causa y propone la corrección. Úsalo cuando el QE pegue un error, un log rojo de la terminal, o diga "no instala", "no corre", "me sale este error".
argument-hint: "[pega el error o el log completo]"
---

# Resolver un error de Python

El objetivo no es solo arreglarlo: el QE debe aprender a leer el error. Explica siempre
**cómo lo encontraste** en el log, en 3 a 5 líneas.

## 1. Leer el traceback de abajo hacia arriba

1. **Última línea** = tipo de error + mensaje (`KeyError: 'correo'`). Es lo primero que se explica.
2. Sube por los `File "...", line N` y detente en el **primero que sea del proyecto**
   (`src/...`, `features/...`). Las líneas de `site-packages` o de `behave/` son librerías:
   casi nunca el error está ahí.
3. Ese archivo y línea es donde se mira. Ábrelo y léelo antes de proponer nada.
4. Si hay varios errores encadenados (`During handling of the above exception...` o
   `The above exception was the direct cause...`), el **primero** es la causa real.

Si el QE pegó solo una parte, pide el log completo desde la primera línea roja.

## 2. Clasificar con la tabla

Usa [errores-comunes.md](errores-comunes.md). Si el error es de instalación o de ambiente,
ejecuta primero `diagnosticar_entorno` (herramienta MCP o terminal):
`.\venv\Scripts\python.exe tools\mcp_framework\server.py diagnosticar_entorno`.
Si el venv está roto, ejecútalo con el Python del sistema: `py -3.12 tools\mcp_framework\server.py diagnosticar_entorno`.

## 3. Responder con este formato

```
Qué pasó:      <una frase sin jerga>
Dónde:         <archivo:línea del proyecto>  (cómo lo ubicaste en el log)
Por qué:       <causa>
Cómo arreglar: <comando o cambio concreto>
Cómo evitarlo: <hábito o validación previa: dry-run, validar_fila_excel, diagnosticar_entorno...>
```

## Reglas

- No cambies código si el problema es de ambiente (venv, versión de Python, red, driver).
- No silencies el error con `try/except` para que "pase": eso crea un falso verde y la
  compuerta de buenas prácticas lo rechaza (COM-FALLA-SILENCIADA).
- Si el log muestra tokens, claves o datos de clientes, no los repitas en la respuesta.
- Si es un fallo funcional del sistema (la app respondió distinto a lo esperado con datos
  correctos), usa la skill `diagnosticar-fallo`: puede ser un bug, no un error de código.
