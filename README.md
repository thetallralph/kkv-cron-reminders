# kkv-cron-reminders

Cron unifié envoyant des rappels (Email + Slack) à T-30min et T-10min pour :
- Balades (table `tour_sessions` Supabase Main)
- Locations vélos (table `rentals` Supabase Main)
- Vélo School (table `veloschool_sessions` Supabase Main)

## Variables d'environnement requises

| Var | Rôle |
|---|---|
| `SUPABASE_MAIN_URL` | URL Supabase Main |
| `SUPABASE_MAIN_ANON_KEY` | Clé anon Main |
| `SUPABASE_MAIN_SERVICE_ROLE_KEY` | Clé service Main |
| `SUPABASE_OPS_URL` | URL Supabase Ops |
| `SUPABASE_OPS_ANON_KEY` | Clé anon Ops |
| `SUPABASE_OPS_SERVICE_ROLE_KEY` | Clé service Ops |
| `RESEND_API_KEY` | Clé Resend pour emails |
| `SLACK_BOT_TOKEN` | Token bot Slack |
| `SLACK_CHANNEL` | Channel Slack (default `C06Q7NF89DJ` = #operations) |
| `EMAIL_FROM` | Expéditeur (default `Koin Koin Vélo <support@koinkoinvelo.com>`) |
| `EMAIL_REPLY_TO` | Reply-to (default `ralph@koinkoinvelo.com`) |
| `OPS_CC_EMAIL` | Email ops en CC (default `ralph@koinkoinvelo.com`) |
| `TICK_SECONDS` | Période du loop (default 60) |

## Déploiement

Géré via Coolify (server.labojaune.com), projet KoinKoin.
