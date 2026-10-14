# fianza

[![ci](https://github.com/KlGamers/fianza/actions/workflows/ci.yml/badge.svg)](https://github.com/KlGamers/fianza/actions/workflows/ci.yml)

Contrato inteligente en Vyper para guardar el depósito en garantía de una renta
sin que ninguna de las dos partes pueda quedárselo por su cuenta.

## El problema

Al rentar una casa o un local, el inquilino deja un depósito. Al terminar, el
arrendador decide cuánto devolver y el inquilino no tiene más remedio que
aceptar o pelear. fianza deja el dinero en un contrato con reglas fijas: el
arrendador puede reclamar una deducción, el inquilino puede aceptarla o
disputarla, y un árbitro que ambos eligieron decide solo si hay desacuerdo.
Si alguien deja de responder, los plazos resuelven el caso solos.

## Flujo

```
create ──> fund ──> (fin de la renta) ──> claim ──> accept ─────────────┐
  │          │                              │                          ├──> settled ──> withdraw
  │          └──> release ──────────────────┼──> dispute ──> resolve ──┘
  └──> cancel                               └──> (sin respuesta) finalize
```

| Función | Quién | Cuándo | Efecto |
|---|---|---|---|
| `create` | arrendador | cuando sea | Registra inquilino, árbitro, monto y fecha de fin |
| `fund` | inquilino | antes del fin | Deposita exactamente el monto acordado |
| `cancel` | arrendador | antes del depósito | Cancela una renta que nunca se pagó |
| `release` | arrendador | renta activa | Devuelve todo al inquilino |
| `claim` | arrendador | dentro de `CLAIM_WIN` tras el fin | Propone una deducción con un hash del motivo |
| `accept` | inquilino | tras el reclamo | Acepta la deducción |
| `dispute` | inquilino | dentro de `REPLY_WIN` tras el reclamo | Pasa el caso al árbitro |
| `resolve` | árbitro | dentro de `RULING_WIN` tras la disputa | Decide cuánto recibe el arrendador, sin superar lo reclamado |
| `finalize` | cualquiera | al vencer un plazo | Cierra el caso según quién no respondió |
| `withdraw` | cualquiera con saldo | cuando sea | Retira lo que le corresponde |

### Qué pasa cuando alguien no responde

| Situación | Resultado de `finalize` |
|---|---|
| El arrendador no reclama dentro de `CLAIM_WIN` | Todo regresa al inquilino |
| El inquilino no responde al reclamo dentro de `REPLY_WIN` | Se aplica la deducción reclamada |
| El árbitro no decide dentro de `RULING_WIN` | La deducción se parte a la mitad |

Los plazos se fijan al desplegar el contrato y no se pueden cambiar.

## Decisiones de diseño

- **Retiro en dos pasos.** Al cerrar un caso el contrato solo anota saldos.
  Cada quien retira el suyo con `withdraw`. Así un destinatario que rechaza
  pagos no puede bloquear el cierre para los demás.
- **Efectos antes de interacciones.** `withdraw` pone el saldo en cero antes de
  enviar el dinero y además usa `@nonreentrant`.
- **El árbitro no cobra ni puede quedarse con nada.** Solo reparte entre las
  dos partes y nunca más de lo que el arrendador reclamó.
- **Partes independientes.** El árbitro no puede ser ni el arrendador ni el
  inquilino, y el inquilino no puede ser el arrendador.
- **El motivo va como hash.** El contrato guarda 32 bytes, por ejemplo el
  hash de las fotos o del acta de entrega, y no datos personales.

## Pruebas

```sh
pip install -r requirements-dev.txt
pytest -q tests --cov --cov-config=.coveragerc
```

Las pruebas cubren el 100% de las instrucciones del contrato, y el CI falla
si alguna línea queda sin probar.

- **Unitarias:** cada función, cada mensaje de error, cada plazo y cada
  permiso.
- **Reentrada:** un contrato atacante intenta volver a llamar `withdraw` desde
  su función de recepción. La transacción se revierte y el saldo del contrato
  queda intacto.
- **Propiedades con Hypothesis:** 200 secuencias aleatorias de hasta 60
  operaciones, con saltos de tiempo. Después de cada paso se comprueba que el
  saldo del contrato sea igual a lo bloqueado más los saldos pendientes, que
  ninguna deducción supere el depósito y que el árbitro y terceros nunca
  reciban dinero.

Para comprobar que las pruebas sirven, inyecté a mano tres errores en el
contrato (pagar de más al inquilino, descontar mal lo bloqueado y dejar que el
árbitro otorgue más de lo reclamado). Las pruebas detectaron los tres.

## Seguridad

Ver [SECURITY.md](SECURITY.md). El contrato no ha pasado por una auditoría
profesional. No lo uses con dinero real sin una.

## Límites

- Solo funciona con la moneda nativa de la red, no con tokens ERC-20.
- Un árbitro por renta, elegido al crearla.
- No hay forma de cambiar de árbitro ni de extender plazos.

## Licencia

MIT
