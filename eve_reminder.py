"""Rappel veille de session — envoyé chaque jour à 20h Lagos pour les sessions du lendemain."""
from datetime import datetime, timedelta
from lib import (
    LAGOS, fetch_sessions, fetch_bookings_count, fetch_team,
    fmt_date_short, fmt_hm, session_times_lagos,
    session_start_location, format_hosts, tg_send, dry_run, log,
)


def build_message(s):
    rdv, depart = session_times_lagos(s)
    tour_name = (s.get("tours") or {}).get("name") or s["tour_slug"]
    start = session_start_location(s)
    team = fetch_team(s["id"])
    participants = fetch_bookings_count(s["tour_slug"], s["session_date"])

    lines = [
        f"⏰ *Demain — {fmt_date_short(depart)}*",
        "",
        f"*{tour_name}*",
        f"🕒 Rendez-vous {fmt_hm(rdv)} · Départ {fmt_hm(depart)}",
    ]
    if start:
        lines.append(f"📍 {start}")
    lines.append(f"🚴 {participants} vélo{'s' if participants != 1 else ''} à préparer")
    lines.append("")
    lines.append(f"👥 Hôtes : {format_hosts(team)}")
    lines.append("")
    lines.append("Merci de confirmer votre présence 🙏")
    return "\n".join(lines)


def main():
    now = datetime.now(LAGOS)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_after = tomorrow + timedelta(days=1)

    sessions = fetch_sessions(tomorrow, day_after)
    if not sessions:
        log("Pas de session demain — pas de rappel veille.")
        return

    log(f"Rappel veille — {len(sessions)} session(s)")
    for s in sessions:
        msg = build_message(s)
        if dry_run():
            log("DRY_RUN — message non envoyé :\n" + msg)
            continue
        msg_id = tg_send(msg)
        log(f"Envoyé session {s['id']} (message_id={msg_id})")


if __name__ == "__main__":
    main()
