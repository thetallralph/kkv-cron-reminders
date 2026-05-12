"""Programme de la semaine — envoyé chaque Lundi 12h Lagos."""
from datetime import datetime, timedelta
from lib import (
    LAGOS, MOIS_FR, fetch_sessions, fetch_bookings_count, fetch_team,
    fmt_date_short, fmt_hm, session_times_lagos,
    session_start_location, format_hosts, tg_send, dry_run, log, AGENDA_URL,
)


def main():
    now = datetime.now(LAGOS)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=7)

    sessions = fetch_sessions(monday, sunday)
    if not sessions:
        log("Aucune session cette semaine — pas de message envoyé.")
        return

    saturday = sunday - timedelta(days=1)
    lines = [
        "🗓 *Programme de la semaine*",
        f"_Du {monday.day} {MOIS_FR[monday.month]} au {saturday.day} {MOIS_FR[saturday.month]} {saturday.year}_",
        "",
    ]

    for s in sessions:
        _, depart = session_times_lagos(s)
        tour_name = (s.get("tours") or {}).get("name") or s["tour_slug"]
        start = session_start_location(s)
        end = s.get("end_location") or ""
        team = fetch_team(s["id"])
        participants = fetch_bookings_count(s["tour_slug"], s["session_date"])
        max_p = s.get("max_participants") or 0

        lines.append(f"• *{fmt_date_short(depart)} — {fmt_hm(depart)}*")
        lines.append(f"  {tour_name}")
        if start and end:
            lines.append(f"  {start} → {end}")
        elif start:
            lines.append(f"  {start}")
        lines.append(f"  Hôtes : {format_hosts(team)}")
        lines.append(f"  Réservations : {participants}/{max_p}")
        lines.append("")

    lines.append(f"🔗 {AGENDA_URL}")
    msg = "\n".join(lines).rstrip()

    log(f"Programme hebdo — {len(sessions)} session(s)")
    if dry_run():
        log("DRY_RUN — message non envoyé :\n" + msg)
        return
    msg_id = tg_send(msg)
    log(f"Envoyé (message_id={msg_id})")


if __name__ == "__main__":
    main()
