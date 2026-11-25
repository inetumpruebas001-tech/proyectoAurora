# Técnicas de diseño con ejemplos bancarios

## Valores límite
Regla: *el monto por transferencia es de S/ 1 a S/ 5 000.*

| Monto | Resultado | Por qué |
|---|---|---|
| S/ 0.99 | Rechazo | Justo debajo del mínimo |
| S/ 1.00 | Aceptación | Mínimo exacto |
| S/ 5 000.00 | Aceptación | Máximo exacto |
| S/ 5 000.01 | Rechazo | Justo encima del máximo |

El defecto típico es `<` en lugar de `<=`: solo se detecta probando el borde exacto.

## Clases de equivalencia
Regla: *se puede abrir cuenta en soles o en dólares.*
Un escenario por moneda (cada una tiene su tratamiento) y uno con una moneda no admitida.
Dos valores son la misma clase solo si el sistema hace exactamente lo mismo con ambos.

## Tabla de decisión
Regla: *se aprueba el desembolso si el cliente no está en lista restringida, tiene la
evaluación aprobada y el monto no supera la línea.*

| Lista restringida | Evaluación | Monto ≤ línea | Resultado |
|---|---|---|---|
| No | Aprobada | Sí | Desembolsa |
| Sí | Aprobada | Sí | Rechazo por lista restringida |
| No | Rechazada | Sí | Rechazo por evaluación |
| No | Aprobada | No | Rechazo por exceder la línea |

Cuatro escenarios en lugar de ocho: combinar dos fallos solo prueba el orden de validación,
salvo que ese orden esté especificado como regla.

## Transición de estados
Estados de la clave de internet: *activa → bloqueada* (3 intentos fallidos), *bloqueada →
activa* (desbloqueo por canal autorizado).
- Tercer intento fallido bloquea la clave
- Con la clave bloqueada no se puede ingresar aunque la clave sea correcta (transición inválida)
- El desbloqueo devuelve la clave a activa

## Partición temporal
Regla: *las transferencias interbancarias hechas después de las 18:00 se procesan el siguiente día hábil.*

| Momento | Resultado |
|---|---|
| 17:59 | Se procesa hoy |
| 18:00 | Borde: confirmar con el PO si es hoy o mañana |
| 18:01 | Siguiente día hábil |
| Viernes 18:01 | Lunes (o siguiente hábil) |

## Colisión
Regla: *una operación no se puede registrar dos veces.*
- La misma solicitud enviada dos veces (doble clic, reintento) no genera dos cargos.
Si la historia no lo define, es un hallazgo para el PO, no un escenario inventado.

## Señales de cobertura desbalanceada
- Más del 40 % de escenarios positivos.
- Ninguna regla con más de un escenario (se copiaron los criterios).
- Todo en la misma capa (se eligió por comodidad).
- Smoke de más de cinco casos.
