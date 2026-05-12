"""Utilités partagées : Supabase, Telegram, formatage français."""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

LAGOS = ZoneInfo("Africa/Lagos")

SUPA_MAIN_URL = os.environ["SUPABASE_MAIN_URL"]
SUPA_MAIN_KEY = os.environ["SUPABASE_MAIN_SERVICE_ROLE_KEY"]
SUPA_OPS_URL = os.environ["SUPABASE_OPS_URL"]
SUPA_OPS_KEY = os.environ["SUPABASE_OPS_SERVICE_ROLE_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_GROUP = os.environ["TELEGRAM_GROUP_ID"]
AGENDA_URL = os.environ.get("AGENDA_URL", "koinkoinvelo.com/agenda")

JOUR_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
MOIS_FR = ["", "janv", "févr", "mars", "avril", "mai", "juin",
           "juil", "août", "sept", "oct", "nov", "déc"]


def supa_get(base_url, key, path, params=None):
    r = requests.get(
        f"{base_url}/rest/v1/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params=params or {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def fetch_sessions(start_utc, end_utc):
    """Sessions tour_sessions dans [start_utc, end_utc[, hors community, hors hidden."""
    sessions = supa_get(
        SUPA_MAIN_URL, SUPA_MAIN_KEY, "tour_sessions",
        [
            ("select",
             "id,tour_slug,session_date,max_participants,status,end_location"),
            ("session_date", f"gte.{start_utc.isoformat()}"),
            ("session_date", f"lt.{end_utc.isoformat()}"),
            ("order", "session_date.asc"),
        ],
    )
    slugs = sorted({s["tour_slug"] for s in sessions if s.get("tour_slug")})
    tours_by_slug = {}
    if slugs:
        tours = supa_get(
            SUPA_MAIN_URL, SUPA_MAIN_KEY, "tours",
            [
                ("select", "slug,name,start_location,is_community,is_hidden"),
                ("slug", "in.(" + ",".join(f'"{s}"' for s in slugs) + ")"),
            ],
        )
        tours_by_slug = {t["slug"]: t for t in tours}
    out = []
    for s in sessions:
        t = tours_by_slug.get(s["tour_slug"]) or {}
        if not t or t.get("is_community") or t.get("is_hidden"):
            continue
        if s.get("status") == "cancelled":
            continue
        s["tours"] = t
        out.append(s)
    return out


def fetch_bookings_count(tour_slug, session_date_iso):
    """Nb de participants confirmés pour une session."""
    rows = supa_get(
        SUPA_MAIN_URL, SUPA_MAIN_KEY, "bookings",
        {
            "select": "participant_count",
            "tour_id": f"eq.{tour_slug}",
            "session_date": f"eq.{session_date_iso}",
            "status": "not.in.(cancelled,no_show)",
        },
    )
    return sum(int(b.get("participant_count") or 0) for b in rows)


def fetch_team(session_id):
    """Équipe d'une session : [(role_in_session, full_name), ...] dans l'ordre lead puis support."""
    rows = supa_get(
        SUPA_OPS_URL, SUPA_OPS_KEY, "session_teams",
        {
            "select": "role_in_session,profile_id",
            "session_id": f"eq.{session_id}",
        },
    )
    ids = sorted({r["profile_id"] for r in rows if r.get("profile_id")})
    profiles_by_id = {}
    if ids:
        profs = supa_get(
            SUPA_OPS_URL, SUPA_OPS_KEY, "profiles",
            {
                "select": "id,full_name",
                "id": "in.(" + ",".join(ids) + ")",
            },
        )
        profiles_by_id = {p["id"]: p for p in profs}
    for r in rows:
        r["profiles"] = profiles_by_id.get(r.get("profile_id")) or {}
    leads = [r for r in rows if r.get("role_in_session") == "lead"]
    supports = [r for r in rows if r.get("role_in_session") == "support"]
    out = []
    for r in leads:
        out.append(("P", (r.get("profiles") or {}).get("full_name") or "?"))
    for i, r in enumerate(supports):
        out.append((f"H{i+2}", (r.get("profiles") or {}).get("full_name") or "?"))
    return out


def first_name(full):
    return (full or "").split()[0] if full else "?"


def format_hosts(team, with_role=True):
    if not team:
        return "— (à assigner)"
    if with_role:
        return ", ".join(f"{first_name(n)} ({r})" for r, n in team)
    return ", ".join(first_name(n) for _, n in team)


def fmt_hm(dt):
    """17h ou 17h30."""
    if dt.minute == 0:
        return f"{dt.hour}h"
    return f"{dt.hour}h{dt.minute:02d}"


def fmt_date_short(dt):
    """Mer 14 mai."""
    return f"{JOUR_FR[dt.weekday()]} {dt.day} {MOIS_FR[dt.month]}"


def fmt_date_with_year(dt):
    """14 mai 2026."""
    return f"{dt.day} {MOIS_FR[dt.month]} {dt.year}"


def session_times_lagos(session):
    """Retourne (rdv_dt, depart_dt) en Africa/Lagos. session_date = départ ; RDV = -30 min."""
    depart_utc = datetime.fromisoformat(session["session_date"].replace("Z", "+00:00"))
    depart = depart_utc.astimezone(LAGOS)
    rdv = depart - timedelta(minutes=30)
    return rdv, depart


def session_start_location(session):
    sl = (session.get("tours") or {}).get("start_location") or ""
    if isinstance(sl, dict):
        return sl.get("name") or sl.get("address") or ""
    return sl


def tg_send(text):
    """Envoie un message Markdown sur le groupe Telegram. Retourne le message_id."""
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={
            "chat_id": TG_GROUP,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data}")
    return data["result"]["message_id"]


def log(msg):
    print(f"[{datetime.now(LAGOS).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def dry_run():
    return os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
