# Sistema de Pagos y Suscripciones — Diseño

**Fecha:** 2026-06-04
**Proyecto:** football-predictor
**Feature:** Sistema de monetización del bot de Telegram con planes escalonados, prueba gratis y pagos via Mercado Pago y PayPal.

---

## Objetivo

Monetizar el acceso al análisis táctico del bot de Telegram mediante:
- **1 análisis de prueba gratis** en partidos destacados del día con picks conservadores
- **3 planes de suscripción mensual** con límites diarios de análisis
- **Pagos via Mercado Pago y PayPal** (sin exponer datos personales del dueño)

---

## Planes

| Plan | Análisis/día | Precio | Código |
|---|---|---|---|
| 🎁 Prueba | 1 análisis total | Gratis | `trial` |
| 🥉 Básico | 4 análisis/día | $5 USD/mes | `basic` |
| 🥈 Pro | 7 análisis/día | $10 USD/mes | `pro` |
| 🥇 Ilimitado | Sin límite | $20 USD/mes | `unlimited` |

- Los análisis diarios se reinician a medianoche hora Argentina (UTC-3)
- La prueba es **única por usuario** — no se puede repetir
- La prueba solo está disponible para partidos destacados preseleccionados

---

## Arquitectura

```
Usuario Telegram
    │
    ├── /start (nuevo) → muestra prueba gratis con partidos destacados
    ├── /suscribir → muestra planes con botones de pago
    ├── /mi_plan → estado actual, análisis restantes, fecha de vencimiento
    ├── /historial → últimos pagos
    ├── /cancelar → cancelar suscripción
    │
    ├── Solicita análisis → bot.py verifica acceso en SQLite
    │       ├── Sin acceso → ofrece trial o planes
    │       ├── Trial disponible → solo partidos destacados
    │       └── Suscripción activa → análisis normal
    │
    └── Pago completado → webhook Flask → actualiza SQLite → notifica usuario

Flask API (Railway)
    ├── POST /webhook/mercadopago
    └── POST /webhook/paypal

SQLite (Railway persistent volume)
    ├── users
    ├── subscriptions
    └── payments
```

---

## Base de Datos (SQLite)

### Tabla `users`
```sql
CREATE TABLE users (
    telegram_id     INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    trial_used      INTEGER DEFAULT 0  -- 0=disponible, 1=usada
);
```

### Tabla `subscriptions`
```sql
CREATE TABLE subscriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER NOT NULL,
    plan                TEXT NOT NULL,  -- basic/pro/unlimited
    status              TEXT NOT NULL,  -- active/cancelled/expired
    analyses_today      INTEGER DEFAULT 0,
    last_reset_date     TEXT,           -- YYYY-MM-DD en ART
    starts_at           DATETIME,
    expires_at          DATETIME,
    payment_provider    TEXT,           -- mercadopago/paypal
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);
```

### Tabla `payments`
```sql
CREATE TABLE payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id      TEXT UNIQUE,        -- ID externo de MP o PayPal
    telegram_id     INTEGER NOT NULL,
    plan            TEXT NOT NULL,
    amount_usd      REAL NOT NULL,
    provider        TEXT NOT NULL,      -- mercadopago/paypal
    status          TEXT DEFAULT 'pending',  -- pending/approved/failed
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);
```

---

## Archivos nuevos/modificados

| Archivo | Responsabilidad |
|---|---|
| `src/db.py` | Crear tablas, CRUD de usuarios/suscripciones/pagos, verificar acceso |
| `src/payments.py` | Generar links de pago MP y PayPal, verificar estado |
| `src/bot_subscription.py` | Handlers Telegram: /suscribir, /mi_plan, /historial, /cancelar |
| `src/app.py` | Nuevos endpoints: POST /webhook/mercadopago, POST /webhook/paypal |
| `bot.py` | Integrar verificación de acceso antes de análisis, agregar handlers de suscripción |
| `requirements.txt` | Agregar `mercadopago`, `paypalrestsdk` |

---

## Lógica de acceso (db.py)

```python
def can_analyze(telegram_id) -> tuple[bool, str]:
    """
    Retorna (puede_analizar, razón).
    razón: 'trial' | 'subscription' | 'no_trial' | 'limit_reached' | 'expired'
    """
```

Flujo:
1. ¿Usuario tiene suscripción activa y no vencida?
   - Plan `unlimited` → True
   - Plan `basic`/`pro` → verificar `analyses_today < límite` → True o 'limit_reached'
2. ¿Sin suscripción activa?
   - `trial_used = 0` → True con razón 'trial'
   - `trial_used = 1` → False con razón 'no_trial'

---

## Reset diario de análisis

Un job del APScheduler existente a medianoche ART:
```python
scheduler.add_job(reset_daily_analyses, CronTrigger(hour=0, minute=0), id="reset_daily")
```

`reset_daily_analyses()` hace:
```sql
UPDATE subscriptions 
SET analyses_today = 0, last_reset_date = 'YYYY-MM-DD'
WHERE status = 'active' AND last_reset_date != 'YYYY-MM-DD'
```

---

## Partidos destacados para la prueba gratis

Los partidos destacados se seleccionan automáticamente desde:
- Champions League
- Premier League  
- La Liga
- Brasileirao
- Liga Argentina

Criterio: los primeros 3-5 partidos no completados del scoreboard de esas ligas (ESPN ya los ordena por relevancia).

El bot presenta al usuario una lista de máximo 5 partidos para elegir. El análisis de prueba usa el prompt conservador existente.

---

## Generación de links de pago

### Mercado Pago
- API: Mercado Pago Checkout Pro
- Se genera una `preference` con el plan, monto y `external_reference = telegram_id|plan`
- El usuario recibe un link de checkout que abre en su browser
- Webhook notifica en `/webhook/mercadopago` cuando el pago se aprueba

### PayPal
- API: PayPal Orders API v2
- Se crea una `order` con el monto y `custom_id = telegram_id|plan`
- El usuario recibe un link de checkout de PayPal
- Webhook notifica en `/webhook/paypal` cuando el pago se captura

En ambos casos el dueño del bot no aparece — el usuario solo ve el checkout de MP o PayPal.

---

## Flujo de suscripción completo

```
Usuario: /suscribir
Bot: muestra 3 planes con botones:
     [🥉 Básico $5/mes] [🥈 Pro $10/mes] [🥇 Ilimitado $20/mes]

Usuario: toca "Pro $10/mes"
Bot: ¿Cómo querés pagar?
     [Mercado Pago] [PayPal]

Usuario: toca "Mercado Pago"
Bot: "Hacé click para completar el pago 👇"
     [💳 Pagar $10 con Mercado Pago] ← link externo
     "Una vez completado el pago, tu plan se activa automáticamente."

Usuario completa pago → Webhook → DB actualizada → Bot notifica:
     "✅ ¡Suscripción activada! Ya podés usar el análisis táctico."
```

---

## Menú de gestión (/mi_plan)

```
📊 Tu plan actual

Plan: Pro 🥈
Estado: Activo
Análisis hoy: 3/7 usados
Se reinicia: a las 00:00 ART
Vence: 04/07/2026

[📋 Ver historial] [🔄 Cambiar plan] [❌ Cancelar]
```

---

## Variables de entorno nuevas

| Variable | Descripción |
|---|---|
| `MP_ACCESS_TOKEN` | Access token de Mercado Pago (producción) |
| `MP_WEBHOOK_SECRET` | Secret para validar webhooks de MP |
| `PAYPAL_CLIENT_ID` | Client ID de PayPal |
| `PAYPAL_CLIENT_SECRET` | Client Secret de PayPal |
| `WEBHOOK_BASE_URL` | URL base pública para webhooks (Railway URL) |

---

## Degradación graceful

- Si MP falla al generar link → mostrar solo opción PayPal
- Si PayPal falla → mostrar solo opción MP
- Si webhook llega duplicado → ignorar (verificar `payment_id` único en DB)
- Si DB falla → denegar acceso con mensaje de error claro
- Pagos pendientes que no se confirman en 24h → limpiar de la DB

---

## Seguridad

- Validar firma de webhooks de MP (`X-Signature` header)
- Validar webhooks de PayPal via verificación de evento en la API
- No loggear tokens ni datos de tarjeta
- `telegram_id` como identificador principal (nunca username, puede cambiar)
