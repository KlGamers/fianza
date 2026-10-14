# Seguridad

Esta es una revisión propia del contrato, no una auditoría profesional.

## Supuestos

- El árbitro es honesto dentro de su papel. Puede decidir mal, pero solo entre
  cero y lo reclamado.
- La red no censura transacciones por más tiempo que los plazos configurados.
- `block.timestamp` puede variar unos segundos. Los plazos se miden en días,
  así que eso no cambia el resultado.

## Riesgos revisados

| Riesgo | Mitigación |
|---|---|
| Reentrada en `withdraw` | Saldo en cero antes de enviar y `@nonreentrant`. Cubierto por `test_reentrancy_is_blocked` |
| Destinatario que rechaza pagos | Retiro en dos pasos: solo se afecta a sí mismo |
| Dinero atrapado si alguien no responde | Cada estado intermedio tiene un plazo y `finalize` lo puede llamar cualquiera |
| Árbitro que se queda con el depósito | El árbitro nunca recibe saldo. Lo comprueba la prueba de propiedades |
| Deducción mayor al depósito | Se rechaza en `claim` y en `resolve` |
| Depósito con monto incorrecto | `fund` exige el monto exacto |
| Llamadas fuera de turno | Cada función revisa estado y remitente. Cubierto por las pruebas unitarias |
| Pérdida de valor por redondeo | Al partir a la mitad, el wei sobrante va al inquilino. Lo comprueba `test_odd_amounts_conserve_value` |

## Fuera de alcance

- Que el motivo del reclamo sea verdadero. El contrato solo guarda su hash.
- Colusión entre el árbitro y una de las partes.

## Reportar un problema

Abre un issue en este repositorio.
