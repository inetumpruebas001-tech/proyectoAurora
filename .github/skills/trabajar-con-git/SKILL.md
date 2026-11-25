---
name: trabajar-con-git
description: Guía el versionamiento con Git y GitHub en el repositorio del equipo — crear rama, commit, push, Pull Request, merge, actualizar la rama con develop y resolver conflictos — sin dejar código solo en la PC. Úsalo cuando el QE quiera subir cambios, crear un PR, hacer merge, tenga un conflicto, un push rechazado o pregunte por Git.
argument-hint: "[subir | pr | actualizar | conflicto | deshacer]"
---

# Trabajar con Git y GitHub

Regla del chapter: **el código no se queda en la PC**. Todo trabajo termina en el repositorio
del equipo, en una rama propia, y entra a `develop` por Pull Request.

Antes de cualquier operación, revisa el estado con `diagnosticar_entorno` (sección `git`)
o `git status -sb`. Explica cada comando antes de pedir que lo ejecute.

## Flujo normal

```powershell
git checkout develop
git pull                                   # traer lo último
git checkout -b feature/HU-123-login       # una rama por historia
# ... trabajar ...
git status                                 # qué cambió
git add src/test/features/login.feature src/test/pages/LoginPage.py
git commit -m "HU-123: automatiza login exitoso"   # corre la compuerta de buenas prácticas
git push -u origin feature/HU-123-login    # la primera vez; luego solo git push
```

Luego en GitHub: **Compare & pull request** → base `develop` → descripción → revisores.

Nombres de rama: `feature/HU-<n>-<descripcion>`, `fix/<descripcion>`, `chore/<descripcion>`.
Mensaje de commit: `HU-<n>: <qué hace, en presente>`. Commits pequeños y frecuentes.

## Descripción del Pull Request (plantilla)

```
## Qué cambia
- <escenarios/archivos>
## Cómo se probó
- behave --tags=@<Tag>  -> <n> pasados, <n> fallidos
- Compuerta de buenas prácticas: APROBADO
## Pendientes
- <columnas de Excel, datos, locators por confirmar>
```

## Mantener la rama al día (antes de abrir o actualizar el PR)

```powershell
git fetch origin
git merge origin/develop       # en TU rama, nunca al revés
```

Si hay conflicto, sigue la sección siguiente. Al terminar: `git push`.

## Resolver un conflicto

1. `git status` lista los archivos en conflicto ("both modified").
2. En VS Code, cada conflicto muestra **Accept Current / Accept Incoming / Accept Both / Compare**.
   - *Current* = lo tuyo. *Incoming* = lo que viene de develop.
   - En features y steps casi siempre corresponde **Accept Both** y luego ordenar.
3. Revisa que no queden marcas `<<<<<<<`, `=======`, `>>>>>>>`.
4. Valida antes de cerrar: `behave --dry-run` (steps duplicados o sin definir) y la compuerta.
5. `git add <archivo>` → `git commit` (sin `-m`: Git propone el mensaje del merge) → `git push`.

Si no estás seguro de qué versión conservar, **no adivines**: pregunta al autor del otro cambio.
Para abortar y volver a como estabas: `git merge --abort`.

## Errores frecuentes

| Mensaje | Qué hacer |
|---|---|
| `! [rejected] ... (fetch first)` / `non-fast-forward` | Alguien subió antes: `git pull` (o `git merge origin/<rama>`) y luego `git push` |
| `fatal: The current branch has no upstream branch` | `git push -u origin <rama>` |
| `Your branch is ahead of 'origin/...' by N commits` | Tus commits no están en GitHub: `git push` |
| `pre-commit ... RECHAZADO` | La compuerta encontró errores nuevos: corrígelos (skill `revisar-buenas-practicas`) |
| `Permission denied` / `403` | No tienes permiso en ese repo: pedir acceso al líder |
| Hiciste commit en `develop` por error | `git branch feature/mi-cambio` → `git reset --hard origin/develop` (solo si NO hiciste push) → `git checkout feature/mi-cambio` |

## Nunca

- Commit de `venv/`, reportes, `Evidencias/`, `*.output`, drivers ni `.idea/` (ya están en `.gitignore`).
- Commit de claves, tokens o datos reales de clientes. Si pasó: avisar al líder **de inmediato**;
  la clave se debe **rotar** (borrarla en un commit nuevo no la quita del historial).
- `git push --force` sobre `develop` o `main`, ni `git commit --no-verify` para saltar la compuerta.
- Trabajar directo en `develop` o `main`.

## Si Copilot tiene acceso a GitHub

Si la organización habilitó el servidor MCP oficial de GitHub, Copilot puede crear el PR y leer
comentarios de revisión. Aun así, **pide confirmación** antes de crear, aprobar o hacer merge de un PR.
