# kkv-cron-reminders

Tous les crons KKV dans un seul conteneur Coolify.

## 1. Tick loop — rappels Email + Slack (T-30 / T-10 min)

`cron_reminders.py` tourne en boucle (60s) et envoie des rappels juste avant chaque événement à :
- Balades (`tour_sessions` Main)
- Locations vélos (`rentals` Main)
- Vélo School (`veloschool_sessions` Main)

Canaux : email aux destinataires métier + Slack `#operations`. Idempotent via state file.

## 2. Scheduled tasks — Telegram groupe KKV - Hôtes

Quatre scripts one-shot, déclenchés par Coolify Scheduled Tasks :

| Script | Cron (UTC) | Heure Lagos | Contenu |
|---|---|---|---|
| `weekly_program.py` | `0 11 * * 1` | Lundi 12h | Programme des balades de la semaine |
| `weekly_recap.py` | `0 6 * * 1` | Lundi 7h | Bilan de la semaine écoulée |
| `eve_reminder.py` | `0 19 * * *` | Daily 20h | Rappel des sessions du lendemain |
| `day_of_reminder.py` | `0 8 * * *` | Daily 9h | Rappel des sessions du jour |

Les scripts daily filtrent eux-mêmes : pas de message s'il n'y a pas de session.
Les balades `is_community=true` ou `is_hidden=true` sont exclues.

Commande Coolify pour chaque scheduled task :
```
python /app/<script>.py
```

## Variables d'environnement

| Var | Utilisé par |
|---|---|
| `SUPABASE_MAIN_URL` | tick + telegram |
| `SUPABASE_MAIN_ANON_KEY` | tick |
| `SUPABASE_MAIN_SERVICE_ROLE_KEY` | tick + telegram |
| `SUPABASE_OPS_URL` | tick + telegram |
| `SUPABASE_OPS_ANON_KEY` | tick |
| `SUPABASE_OPS_SERVICE_ROLE_KEY` | tick + telegram |
| `RESEND_API_KEY` | tick |
| `SLACK_BOT_TOKEN` | tick |
| `SLACK_CHANNEL` | tick (default `C06Q7NF89DJ` = #operations) |
| `EMAIL_FROM` | tick (default `Koin Koin Vélo <support@koinkoinvelo.com>`) |
| `EMAIL_REPLY_TO` | tick (default `ralph@koinkoinvelo.com`) |
| `OPS_CC_EMAIL` | tick (default `ralph@koinkoinvelo.com`) |
| `TICK_SECONDS` | tick (default 60) |
| `TELEGRAM_BOT_TOKEN` | telegram |
| `TELEGRAM_GROUP_ID` | telegram (default `-1003788212369` = KKV - Hôtes) |
| `AGENDA_URL` | telegram (default `koinkoinvelo.com/agenda`) |
| `DRY_RUN` | telegram — si `1`, log le message au lieu d'envoyer |

## Test local d'un script Telegram

```bash
cp .env.example .env  # remplir
pip install -r requirements.txt
DRY_RUN=1 python weekly_program.py
```

## Déploiement

Géré via Coolify (server.labojaune.com), projet KoinKoin.
