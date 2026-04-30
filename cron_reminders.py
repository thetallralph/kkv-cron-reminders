#!/usr/bin/env python3
"""
KKV Reminders Cron — unifié pour balades, locations, vélo school.

Tick toutes les ~60s. Pour chaque événement à venir, envoie un rappel email
(au(x) destinataire(s) métier) et Slack (#operations) à T-30min et T-10min.
Idempotent via state file persistant.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ───────── Config ─────────
SUPABASE_MAIN_URL = os.environ["SUPABASE_MAIN_URL"].rstrip("/")
SUPABASE_MAIN_ANON = os.environ["SUPABASE_MAIN_ANON_KEY"]
SUPABASE_MAIN_SR = os.environ["SUPABASE_MAIN_SERVICE_ROLE_KEY"]

SUPABASE_OPS_URL = os.environ["SUPABASE_OPS_URL"].rstrip("/")
SUPABASE_OPS_ANON = os.environ["SUPABASE_OPS_ANON_KEY"]
SUPABASE_OPS_SR = os.environ["SUPABASE_OPS_SERVICE_ROLE_KEY"]

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "Koin Koin Vélo <support@koinkoinvelo.com>")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "ralph@koinkoinvelo.com")

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "C06Q7NF89DJ")  # #operations

# Optional ops cc — un email reçoit aussi tous les rappels (pour visibilité)
OPS_CC_EMAIL = os.environ.get("OPS_CC_EMAIL", "ralph@koinkoinvelo.com")

STATE_PATH = Path(os.environ.get("STATE_PATH", "/data/cron_state.json"))
TICK_SECONDS = int(os.environ.get("TICK_SECONDS", "60"))

BENIN_TZ = timezone(timedelta(hours=1))

REMINDER_OFFSETS_MIN = [30, 10]  # minutes avant l'événement
WINDOW_SECONDS = 90  # tolérance autour de chaque offset


# ───────── Helpers temps ─────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_local_time(dt_utc: datetime) -> str:
    return dt_utc.astimezone(BENIN_TZ).strftime("%Hh%M")


def fmt_local_date(dt_utc: datetime) -> str:
    JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    local = dt_utc.astimezone(BENIN_TZ)
    return f"{JOURS[local.weekday()]} {local.day} {MOIS[local.month - 1]}"


def parse_iso_utc(s: str) -> datetime:
    if not s:
        raise ValueError("empty timestamp")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_rental_time(date_str: str, time_str: str) -> datetime | None:
    """rentals.date = YYYY-MM-DD ; pickup_time = '07h00' ou '07:00'."""
    if not date_str or not time_str:
        return None
    try:
        y, m, d = [int(x) for x in date_str.split("-")]
    except ValueError:
        return None
    t = time_str.strip().lower().replace("h", ":")
    if ":" not in t:
        return None
    parts = t.split(":")
    try:
        hh = int(parts[0])
        mm = int(parts[1]) if parts[1] else 0
    except ValueError:
        return None
    local = datetime(y, m, d, hh, mm, tzinfo=BENIN_TZ)
    return local.astimezone(timezone.utc)


def parse_veloschool_time(date_str: str, time_str: str | None) -> datetime | None:
    """veloschool_sessions.scheduled_date = YYYY-MM-DD ; scheduled_time HH:MM."""
    if not date_str:
        return None
    if not time_str:
        time_str = "09:00"
    return parse_rental_time(date_str, time_str)


# ───────── Supabase fetch ─────────
def supa_get(base: str, anon: str, sr: str, table: str, qs: str) -> Any:
    url = f"{base}/rest/v1/{table}?{qs}"
    req = urllib.request.Request(url, headers={
        "apikey": anon,
        "Authorization": f"Bearer {sr}",
        "User-Agent": "kkv-cron-reminders/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_balades(window_start: datetime, window_end: datetime) -> list[dict]:
    qs = (
        f"select=id,tour_slug,session_date,max_participants,status"
        f"&session_date=gte.{urllib.parse.quote(window_start.isoformat())}"
        f"&session_date=lt.{urllib.parse.quote(window_end.isoformat())}"
        f"&order=session_date.asc"
    )
    rows = supa_get(SUPABASE_MAIN_URL, SUPABASE_MAIN_ANON, SUPABASE_MAIN_SR, "tour_sessions", qs)
    out = []
    for r in rows:
        if r.get("status") == "cancelled":
            continue
        try:
            event_at = parse_iso_utc(r["session_date"])
        except Exception:
            continue
        out.append({
            "kind": "balade",
            "id": r["id"],
            "event_at": event_at,
            "raw": r,
        })
    return out


def fetch_rentals(local_today: datetime) -> list[dict]:
    """rentals: on charge la date du jour et celle du lendemain pour couvrir les bords."""
    today = local_today.date().isoformat()
    tomorrow = (local_today + timedelta(days=1)).date().isoformat()
    qs = (
        f"select=id,customer_name,customer_email,customer_phone,date,pickup_time,"
        f"return_time,bike_count,pickup_location,total_amount,status,manoeuvre_id,manoeuvre_name"
        f"&date=in.({today},{tomorrow})"
        f"&status=neq.cancelled"
    )
    rows = supa_get(SUPABASE_MAIN_URL, SUPABASE_MAIN_ANON, SUPABASE_MAIN_SR, "rentals", qs)
    out = []
    for r in rows:
        if (r.get("status") or "").lower() in ("cancelled", "done"):
            continue
        event_at = parse_rental_time(r["date"], r.get("pickup_time", ""))
        if not event_at:
            continue
        out.append({
            "kind": "rental",
            "id": r["id"],
            "event_at": event_at,
            "raw": r,
        })
    return out


def fetch_veloschool(local_today: datetime) -> list[dict]:
    today = local_today.date().isoformat()
    tomorrow = (local_today + timedelta(days=1)).date().isoformat()
    qs = (
        f"select=id,cohort_id,session_number,scheduled_date,scheduled_time,location,status"
        f"&scheduled_date=in.({today},{tomorrow})"
        f"&status=eq.scheduled"
    )
    rows = supa_get(SUPABASE_MAIN_URL, SUPABASE_MAIN_ANON, SUPABASE_MAIN_SR, "veloschool_sessions", qs)
    out = []
    for r in rows:
        event_at = parse_veloschool_time(r.get("scheduled_date"), r.get("scheduled_time"))
        if not event_at:
            continue
        out.append({
            "kind": "veloschool",
            "id": r["id"],
            "event_at": event_at,
            "raw": r,
        })
    return out


def fetch_tour_meta(slug: str) -> dict | None:
    qs = f"select=slug,name,start_location,location,start_time,duration&slug=eq.{slug}&limit=1"
    rows = supa_get(SUPABASE_MAIN_URL, SUPABASE_MAIN_ANON, SUPABASE_MAIN_SR, "tours", qs)
    return rows[0] if rows else None


def fetch_cohort_meta(cohort_id: str) -> dict | None:
    qs = f"select=id,name,program,instructor_name&id=eq.{cohort_id}&limit=1"
    rows = supa_get(SUPABASE_MAIN_URL, SUPABASE_MAIN_ANON, SUPABASE_MAIN_SR, "veloschool_cohorts", qs)
    return rows[0] if rows else None


def fetch_profile(profile_id: str) -> dict | None:
    qs = f"select=id,full_name,email,phone&id=eq.{profile_id}&limit=1"
    rows = supa_get(SUPABASE_OPS_URL, SUPABASE_OPS_ANON, SUPABASE_OPS_SR, "profiles", qs)
    return rows[0] if rows else None


# ───────── State ─────────
def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(STATE_PATH)


def state_key(event: dict, offset_min: int) -> str:
    iso = event["event_at"].isoformat()
    return f"{event['kind']}:{event['id']}:{iso}:T-{offset_min}"


def gc_state(state: dict, now: datetime) -> dict:
    """Supprime les entrées > 24h pour limiter la taille."""
    cutoff = now - timedelta(hours=24)
    out = {}
    for k, v in state.items():
        sent_at = v.get("sent_at") if isinstance(v, dict) else None
        if not sent_at:
            continue
        try:
            ts = parse_iso_utc(sent_at)
        except Exception:
            continue
        if ts > cutoff:
            out[k] = v
    return out


# ───────── Notifications ─────────
def send_email(to: list[str], subject: str, html: str, cc: list[str] | None = None) -> None:
    to = [t for t in to if t]
    if not to:
        return
    payload: dict = {
        "from": EMAIL_FROM,
        "to": to,
        "reply_to": EMAIL_REPLY_TO,
        "subject": subject,
        "html": html,
    }
    if cc:
        payload["cc"] = [c for c in cc if c and c not in to]
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
        if r.status >= 400:
            raise RuntimeError(f"resend error {r.status}: {body}")


def send_slack(text: str) -> None:
    payload = {"channel": SLACK_CHANNEL, "text": text}
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.loads(r.read())
        if not body.get("ok"):
            raise RuntimeError(f"slack error: {body}")


# ───────── Build messages ─────────
def email_html_balade(event: dict, offset_min: int) -> tuple[str, str]:
    raw = event["raw"]
    meta = fetch_tour_meta(raw["tour_slug"]) or {}
    name = meta.get("name") or raw["tour_slug"]
    loc = meta.get("start_location") or meta.get("location") or "—"
    when = fmt_local_time(event["event_at"])
    when_when = "dans 30 minutes" if offset_min == 30 else "dans 10 minutes"
    subject = f"Rappel balade – {name} ({when}, {when_when})"
    html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; max-width:560px; margin:0 auto;">
  <h2 style="color:#1a1a1a;">⏰ Rappel — {when_when}</h2>
  <p><strong>🚴 {name}</strong> à <strong>{when}</strong></p>
  <p>📍 {loc}</p>
  <p style="color:#666;">Préparez-vous, c'est bientôt l'heure du départ.</p>
</div>"""
    return subject, html


def slack_text_balade(event: dict, offset_min: int) -> str:
    raw = event["raw"]
    meta = fetch_tour_meta(raw["tour_slug"]) or {}
    name = meta.get("name") or raw["tour_slug"]
    when = fmt_local_time(event["event_at"])
    loc = meta.get("start_location") or meta.get("location") or "—"
    return (
        f":alarm_clock: *Rappel balade — T-{offset_min}min*\n"
        f"• 🚴 *{name}* à *{when}*\n"
        f"• 📍 {loc}"
    )


def email_html_rental(event: dict, offset_min: int) -> tuple[str, str]:
    r = event["raw"]
    when = fmt_local_time(event["event_at"])
    when_when = "dans 30 minutes" if offset_min == 30 else "dans 10 minutes"
    bikes = r.get("bike_count") or 1
    loc = r.get("pickup_location") or "Dépôt"
    customer = r.get("customer_name") or ""
    subject = f"Rappel location {when} – {when_when}"
    html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; max-width:560px; margin:0 auto;">
  <h2 style="color:#1a1a1a;">⏰ Rappel — {when_when}</h2>
  <p><strong>🚲 Location de {bikes} vélo{'s' if bikes>1 else ''}</strong> à <strong>{when}</strong></p>
  <p>📍 Retrait : {loc}</p>
  <p>👤 Client : {customer}</p>
  <p style="color:#666;">À tout de suite au point de retrait.</p>
</div>"""
    return subject, html


def slack_text_rental(event: dict, offset_min: int) -> str:
    r = event["raw"]
    when = fmt_local_time(event["event_at"])
    bikes = r.get("bike_count") or 1
    loc = r.get("pickup_location") or "Dépôt"
    customer = r.get("customer_name") or ""
    manoeuvre = r.get("manoeuvre_name")
    lines = [
        f":alarm_clock: *Rappel location — T-{offset_min}min*",
        f"• 🚲 *{customer}* — {bikes} vélo{'s' if bikes>1 else ''} à *{when}*",
        f"• 📍 {loc}",
    ]
    if manoeuvre:
        lines.append(f"• 🧰 Manoeuvre : {manoeuvre}")
    return "\n".join(lines)


def email_html_veloschool(event: dict, offset_min: int) -> tuple[str, str]:
    r = event["raw"]
    cohort = fetch_cohort_meta(r["cohort_id"]) or {}
    name = cohort.get("name") or "Vélo School"
    when = fmt_local_time(event["event_at"])
    when_when = "dans 30 minutes" if offset_min == 30 else "dans 10 minutes"
    loc = r.get("location") or "—"
    subject = f"Rappel Vélo School – {name} ({when}, {when_when})"
    html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; max-width:560px; margin:0 auto;">
  <h2 style="color:#1a1a1a;">⏰ Rappel — {when_when}</h2>
  <p><strong>🎓 {name} — séance #{r.get('session_number','')}</strong> à <strong>{when}</strong></p>
  <p>📍 {loc}</p>
</div>"""
    return subject, html


def slack_text_veloschool(event: dict, offset_min: int) -> str:
    r = event["raw"]
    cohort = fetch_cohort_meta(r["cohort_id"]) or {}
    name = cohort.get("name") or "Vélo School"
    when = fmt_local_time(event["event_at"])
    loc = r.get("location") or "—"
    return (
        f":alarm_clock: *Rappel Vélo School — T-{offset_min}min*\n"
        f"• 🎓 *{name}* — séance #{r.get('session_number','?')} à *{when}*\n"
        f"• 📍 {loc}"
    )


def recipients_for(event: dict) -> list[str]:
    kind = event["kind"]
    if kind == "rental":
        emails = []
        ce = (event["raw"].get("customer_email") or "").strip()
        if ce:
            emails.append(ce)
        mid = event["raw"].get("manoeuvre_id")
        if mid:
            try:
                p = fetch_profile(mid)
                if p and p.get("email") and not p["email"].endswith(".internal"):
                    emails.append(p["email"])
            except Exception as e:
                print(f"[recipients] manoeuvre profile fetch failed: {e}", file=sys.stderr)
        return emails
    # balade & veloschool : pas de mailing automatique aux participants — ops_cc seulement.
    return []


# ───────── Tick ─────────
def process_event(event: dict, state: dict, now: datetime) -> list[str]:
    fired = []
    for offset_min in REMINDER_OFFSETS_MIN:
        target = event["event_at"] - timedelta(minutes=offset_min)
        delta = abs((now - target).total_seconds())
        if delta > WINDOW_SECONDS:
            continue
        key = state_key(event, offset_min)
        if key in state:
            continue
        try:
            kind = event["kind"]
            if kind == "balade":
                subject, html = email_html_balade(event, offset_min)
                slack_text = slack_text_balade(event, offset_min)
            elif kind == "rental":
                subject, html = email_html_rental(event, offset_min)
                slack_text = slack_text_rental(event, offset_min)
            elif kind == "veloschool":
                subject, html = email_html_veloschool(event, offset_min)
                slack_text = slack_text_veloschool(event, offset_min)
            else:
                continue

            recipients = recipients_for(event)
            cc = [OPS_CC_EMAIL] if OPS_CC_EMAIL else []
            if recipients:
                send_email(recipients, subject, html, cc=cc)
            elif cc:
                send_email(cc, subject, html)
            send_slack(slack_text)

            state[key] = {
                "sent_at": now.isoformat(),
                "kind": kind,
                "id": event["id"],
                "offset_min": offset_min,
                "recipients": recipients,
            }
            fired.append(f"{kind}/{event['id']} T-{offset_min}min")
        except Exception as e:
            print(f"[process_event] error on {event['kind']}/{event['id']} T-{offset_min}: {e}", file=sys.stderr)
    return fired


def tick() -> int:
    now = now_utc()
    local_today = now.astimezone(BENIN_TZ)
    window_start = now - timedelta(minutes=5)
    window_end = now + timedelta(hours=2)

    events: list[dict] = []
    for fetcher, label in (
        (lambda: fetch_balades(window_start, window_end), "balades"),
        (lambda: fetch_rentals(local_today), "rentals"),
        (lambda: fetch_veloschool(local_today), "veloschool"),
    ):
        try:
            events.extend(fetcher())
        except Exception as e:
            print(f"[tick] fetch {label} failed: {e}", file=sys.stderr)

    state = load_state()
    state = gc_state(state, now)

    fired_total: list[str] = []
    for ev in events:
        fired_total.extend(process_event(ev, state, now))

    save_state(state)

    if fired_total:
        print(f"[tick] {now.isoformat()} fired: {', '.join(fired_total)}")
    else:
        print(f"[tick] {now.isoformat()} ok ({len(events)} events scanned)")
    return len(fired_total)


def main() -> int:
    print(f"[cron] start tick={TICK_SECONDS}s state={STATE_PATH}")
    while True:
        try:
            tick()
        except Exception as e:
            print(f"[main] tick crashed: {e}", file=sys.stderr)
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
