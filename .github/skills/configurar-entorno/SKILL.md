---
name: configurar-entorno
description: Revisa y deja listo el ambiente de trabajo del QE — Python 3.12, ambiente virtual propio o uno existente, dependencias, navegador y git — y explica cómo corregir cada problema. Úsalo cuando el QE empieza en el proyecto, cuando algo no instala, no importa o no abre, o cuando pregunta por el venv.
argument-hint: "[nuevo | reutilizar]"
---

# Configurar el entorno

## 1. Diagnosticar

Ejecuta `diagnosticar_entorno` (herramienta MCP). Si no está disponible, en la terminal:
`.\venv\Scripts\python.exe tools\mcp_framework\server.py diagnosticar_entorno`.
Si el venv está roto o no existe: `py -3.12 tools\mcp_framework\server.py diagnosticar_entorno`.

Muestra los problemas en una tabla **Problema | Comando para resolverlo**, en el orden en que hay que resolverlos.

## 2. Elegir el modo

Si el QE no dijo si quiere un ambiente **nuevo** o **reutilizar** uno existente, pregúntaselo en una sola línea.
Si el diagnóstico dice que el venv apunta a un Python que no existe en esta PC, el modo es **nuevo** (fue copiado de otra máquina).

**Nuevo**

```powershell
Remove-Item -Recurse -Force .\venv -ErrorAction SilentlyContinue
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install -r tools\mcp_framework\requirements-mcp.txt
```

**Reutilizar**

1. `Ctrl+Shift+P` → *Python: Select Interpreter* → `.\venv\Scripts\python.exe`.
2. Comprobar cuál se usa: `python -c "import sys; print(sys.executable)"`.
3. Si faltan paquetes: `.\venv\Scripts\python.exe -m pip install -r requirements.txt`.

No hace falta `Activate.ps1`: usa siempre `.\venv\Scripts\python.exe` (en algunas PCs el script está bloqueado).

## 3. Confirmar

1. Vuelve a ejecutar `diagnosticar_entorno`: `ok` debe ser `true`.
2. `.\venv\Scripts\python.exe -m behave --dry-run`: debe terminar con `0 undefined`.

## Reglas

- No instales paquetes fuera del venv ni cambies versiones de `requirements.txt`.
- Explica cada comando antes de pedir que lo ejecute.
- Si un error no está en el diagnóstico, usa la skill `resolver-error-python`.
