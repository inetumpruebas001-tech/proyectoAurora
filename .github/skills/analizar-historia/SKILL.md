---
name: analizar-historia
description: Analiza una historia de usuario desde la mirada de QA antes de diseñar o automatizar pruebas (forma, criterios de aceptación, reglas de negocio implícitas, testabilidad, dependencias y riesgo) y devuelve preguntas al PO y criterios propuestos en Gherkin. Úsalo cuando peguen una historia, un requerimiento o una clave de Jira, o pregunten si una historia está lista para probar.
argument-hint: "[texto de la historia con sus criterios de aceptación, o clave de Jira]"
---

# Analizar una historia de usuario

El objetivo es descubrir los huecos de la historia **antes** de diseñar escenarios o escribir
código. Un criterio ambiguo automatizado tal cual produce una prueba que "pasa" sin probar lo
que el negocio quería.

## Regla que sostiene todo

**Cada afirmación se sustenta en el texto de la historia o se marca como pregunta al PO.**
Nunca completes una regla de negocio que no esté escrita, aunque parezca obvia en banca
(límites diarios, horarios de corte, intentos de clave). Si no está escrita, es una pregunta.

Distingue siempre tres registros en la salida:

| Registro | Cómo se escribe | Ejemplo |
|---|---|---|
| Está en la historia | Cítalo | "CA-2 dice: *se rechaza la transferencia*" |
| Falta y hay que preguntarlo | Pregunta concreta | "¿Cuál es el monto máximo por operación?" |
| Convención del equipo | Supuesto declarado | "Supuesto: aplica el tipo de cambio del día" |

## Cómo obtener la historia

1. Texto pegado en el chat: analízalo tal cual (lo más común).
2. Si hay una herramienta de Jira conectada, lee la historia y sus comentarios.
3. Si solo hay una clave sin acceso: pide el texto. No supongas su contenido.

No pegues datos reales de clientes (DNI, cuentas, tarjetas) en el chat.

## Las seis dimensiones (veredicto: Sólido / Ajustar / Bloqueante)

1. **Forma**: ¿rol real (cliente, asesor de negocios, analista de créditos, operador) o "el usuario"?
   ¿El "para" es un beneficio de negocio o repite la funcionalidad?
2. **Criterios de aceptación**: ¿cada uno es verificable? ¿hay caminos alternos y negativos?
   ¿describen comportamiento o interfaz ("el botón se pone gris")? ¿un criterio con tres "y" son tres?
   ¿están definidos los textos de los mensajes?
3. **Reglas de negocio implícitas**: topes y montos, condiciones por producto/canal/tipo de
   cliente, estados y transiciones, fechas y horarios de corte, reintentos y doble envío,
   permisos por rol, qué pasa si falla un servicio externo. Pregunta solo por las que la
   historia deja abiertas.
4. **Testabilidad y datos**: qué datos de prueba hacen falta (clientes, cuentas, productos en
   cierto estado), si existen en el ambiente, si el resultado es observable en pantalla o
   respuesta de servicio.
5. **Dependencias e impactos**: servicios, pantallas e historias relacionadas; qué puede
   romper (alcance de regresión).
6. **Riesgo**: alto / medio / bajo con una línea de justificación (dinero, cliente final,
   regulatorio, flujo muy usado, integraciones frágiles).

No diseñes escenarios aquí: eso lo hace la skill `disenar-escenarios` con las respuestas del PO.

## Formato de salida

```markdown
## [CLAVE] — [título]
**Veredicto: Lista para probar | Lista con observaciones | No lista** — [una línea]

### Diagnóstico
| Dimensión | Veredicto | Hallazgo principal |
|---|---|---|

### Reglas de negocio identificadas
RN-01 … RN-n (citando el criterio de origen o marcadas ⚠ si dependen de una pregunta)

### Preguntas al PO (máximo 7, ordenadas por impacto)
1. **[Tema]** — [pregunta respondible con un dato]. *Por qué importa:* [...]

### Criterios de aceptación propuestos (Gherkin de negocio, ⚠ si dependen de respuesta)

### Datos de prueba necesarios

### Enfoque de prueba sugerido (2-3 líneas)
```

Gherkin de negocio: estado inicial, acción y resultado observable, sin IDs, selectores ni
endpoints. "Dado que el cliente tiene un saldo de S/ 500 / Cuando transfiere S/ 600 /
Entonces la transferencia se rechaza por saldo insuficiente".

## Lo que no hace

No edita la historia (propone; el QA y el PO deciden), no inventa reglas, no diseña escenarios,
no estima y no publica nada en Jira sin confirmación explícita del QA.
