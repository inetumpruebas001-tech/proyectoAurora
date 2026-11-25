---
name: disenar-escenarios
description: Diseña los escenarios de prueba de una historia ya analizada aplicando valores límite, clases de equivalencia, tablas de decisión y transición de estados; escribe cada escenario en Gherkin de negocio, decide su capa (API, UI o manual), su prioridad y los datos de prueba (filas de Excel). Úsalo cuando haya que definir qué probar de una historia o qué automatizar.
argument-hint: "[historia analizada o reglas de negocio]"
---

# Diseñar escenarios de prueba

## Antes de empezar

Si la historia tiene preguntas abiertas al PO que cambian reglas, dilo y propone resolverlas
primero (skill `analizar-historia`). Diseñar sobre reglas inciertas genera retrabajo.

## Principio: la cobertura nace de las reglas, no de los criterios

No generes un escenario por criterio de aceptación. Lista las reglas de negocio (RN-01...) y
para cada una pregunta: ¿cómo se cumple?, ¿cómo se incumple?, ¿dónde está el borde exacto?,
¿qué pasa si el dato no existe o llega dos veces? Cada escenario declara de qué regla nace.

## Técnicas (aplica la que corresponda a la forma de la regla)

| Si la regla… | Técnica | Produce |
|---|---|---|
| define un rango (montos, plazos, edades) | Valores límite | mínimo, máximo, uno por debajo, uno por encima |
| define un conjunto de valores (productos, monedas, canales) | Clases de equivalencia | un válido por clase + uno inválido |
| combina condiciones | Tabla de decisión | solo las combinaciones donde cambia el resultado |
| tiene estados (activa, bloqueada, cancelada) | Transición de estados | transiciones válidas + al menos una inválida |
| involucra fechas u horarios de corte | Partición temporal | pasado, hoy, borde, fuera de plazo |
| exige unicidad o evita duplicados | Colisión | operación repetida / simultánea |

Ejemplos en `tecnicas-diseno.md` (en esta misma carpeta).

## Escenarios en Gherkin de negocio

- Un escenario, un comportamiento.
- Datos con significado: "transfiere S/ 5 001 cuando el máximo es S/ 5 000", no "monto = 5001".
- Nómbralo por lo que verifica: "Rechazo por monto mayor al máximo permitido".
- Sin selectores, endpoints ni códigos HTTP en el Gherkin: eso va en los datos de prueba
  (filas de Excel) y en el resultado esperado.

## Decidir la capa (una sola por escenario)

| Capa | Cuándo | Framework |
|---|---|---|
| **API** | La regla vive en el backend: cálculos, validaciones de datos, estados, seguridad | framework de servicios (Behave + Excel) |
| **UI** | Lo que se verifica es lo que la persona ve o puede hacer: mensajes, flujo recorrible, controles | framework web (Behave + Selenium) |
| **Manual** | Depende de un sistema no controlable, requiere juicio humano, o automatizar cuesta más que su valor | — |

Pregunta clave: **¿dónde vive la regla?** Si el tope lo aplica el servicio, el escenario es de
API aunque se vea en pantalla; en UI va otro escenario: que el usuario reciba el mensaje.
Justifica siempre la capa en una línea.

## Prioridad

Alta: protege dinero, acceso o es visible al cliente · Media: regla sin impacto económico
directo · Baja: formato y mensajes. Marca `@Smoke` solo 3 a 5 escenarios por historia.

## Datos de prueba (filas de Excel)

Por cada escenario automatizable indica la fila de datos que necesita, con las columnas de la
hoja del framework (usa `leer_excel` para ver las columnas reales). Ejecutar/Ejecucion = SI.
Si el dato no existe en el ambiente, márcalo como **bloqueado por datos**.

## Formato de salida

```markdown
## Escenarios — [CLAVE] [título]
**Cobertura:** N escenarios · N API · N UI · N manual · Reglas RN-01..RN-n

### Matriz de cobertura
| Regla | Escenarios | Técnica |

### Escenarios
| ID | Título | Capa | Prioridad | Regla |
[Gherkin de cada escenario]

### Datos de prueba (filas de Excel por escenario)

### Hallazgos (reglas no escritas, contradicciones, datos inexistentes)
```

Comprobación final: cada regla debe tener al menos un escenario que la **incumple**.
Más de 40 % de escenarios positivos indica que faltan caminos alternos.

## Lo que no hace

No implementa la automatización (eso lo hacen `automatizar-escenario-web` y
`automatizar-servicio-api`), no inventa reglas y no escribe en el Excel (eso es de la etapa de automatización, con confirmación del QE).
