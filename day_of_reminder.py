"""Rappel jour J — envoyé chaque jour à 9h Lagos pour les sessions du jour."""
from datetime import datetime, timedelta
from lib import (
    LAGOS, fetch_sessions, fetch_team,
    fmt_date_short, fmt_hm, session_times_lagos,
    session_start_location, format_hosts, tg_send, dry_run, log,
)


def build_message(s):
    rdv, depart = session_times_lagos(s)
    tour_name = (s.get("tours") or {}).get("name") or s["tour_slug"]
    start = session_start_location(s)
    team = fetch_team(s["id"])

    lines = [
        f"🚀 *Aujourd'hui — {fmt_date_short(depart)}*",
        "",
        f"*{tour_name}*",
        f"🕒 RDV {fmt_hm(rdv)} · Départ {fmt_hm(depart)}",
    ]
    if start:
        lines.append(f"📍 {start}")
    lines.append("")
    lines.append(f"Hôtes : {format_hosts(team, with_role=False)}")
    lines.append("")
    lines.append("Bonne journée à tous ✨")
    return "\n".join(lines)


def main():
    now = datetime.now(LAGOS)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    sessions = fetch_sessions(today, tomorrow)
    if not sessions:
        log("Pas de session aujourd'hui — pas de rappel jour J.")
        return

    log(f"Rappel jour J — {len(sessions)} session(s)")
    for s in sessions:
        msg = build_message(s)
        if dry_run():
            log("DRY_RUN — message non envoyé :\n" + msg)
            continue
        msg_id = tg_send(msg)
        log(f"Envoyé session {s['id']} (message_id={msg_id})")


if __name__ == "__main__":
    main()
