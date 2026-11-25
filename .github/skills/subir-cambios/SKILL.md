---
name: subir-cambios
description: Sube el trabajo del QE al repositorio del equipo — revisa la compuerta de calidad, crea la rama si hace falta, propone el commit, hace push y redacta la descripción del Pull Request. Se invoca solo a pedido con /subir-cambios.
argument-hint: "[HU-123 descripción corta]"
disable-model-invocation: true
---

# Subir cambios

Sigue la skill `trabajar-con-git` para las reglas. Pide confirmación antes de cada comando que
modifique el repositorio (`commit`, `push`).

Si el QE no indicó la historia (por ejemplo `HU-123 login exitoso`), pregúntala en una sola línea:
se usa para el nombre de la rama y el mensaje del commit.

## Pasos

1. **Estado:** `diagnosticar_entorno` (sección `git`) o `git status -sb`. Informa rama, archivos cambiados y si hay commits sin subir.
2. **Calidad:** `revisar_buenas_practicas(alcance="cambios")`. Si `aprobado` es `false`, detente y explica qué corregir (skill `revisar-buenas-practicas`).
3. **Rama:** si está en `develop` o `main`, propone `git checkout -b feature/HU-<n>-<descripcion>` antes del commit.
4. **Qué subir:** muestra `git status` y propone los archivos. Nunca `venv/`, reportes, `Evidencias/`, `*.output`, drivers ni secretos.
5. **Commit y push:** propone
   ```powershell
   git add <archivos>
   git commit -m "HU-<n>: <qué hace, en presente>"
   git push -u origin <rama>
   ```
   y espera la confirmación del QE.
6. **Pull Request a `develop`:** redacta la descripción:
   ```
   ## Qué cambia
   - <escenarios / archivos>
   ## Cómo se probó
   - behave --tags=@<Tag>  -> <n> pasados, <n> fallidos
   - Compuerta de buenas prácticas: APROBADO
   ## Pendientes
   - <columnas de Excel, datos, locators por confirmar>
   ```

## Nunca

- `git push --force`, `git commit --no-verify` ni trabajar directo en `develop` o `main`.
- Crear, aprobar o hacer merge de un PR sin confirmación explícita del QE.
