"""Récap de la semaine écoulée — envoyé chaque Lundi 7h Lagos."""
from datetime import datetime, timedelta
from lib import (
    LAGOS, MOIS_FR, fetch_sessions, fetch_bookings_count, fetch_team,
    fmt_date_short, session_times_lagos, format_hosts,
    tg_send, dry_run, log,
)


def main():
    now = datetime.now(LAGOS)
    monday_this = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    monday_last = monday_this - timedelta(days=7)

    sessions = fetch_sessions(monday_last, monday_this)
    if not sessions:
        log("Aucune session la semaine passée — pas de récap.")
        return

    sunday_last = monday_this - timedelta(days=1)
    lines = [
        f"📊 *Semaine du {monday_last.day} {MOIS_FR[monday_last.month]} au {sunday_last.day} {MOIS_FR[sunday_last.month]}*",
        "",
    ]

    total = 0
    for s in sessions:
        _, depart = session_times_lagos(s)
        tour_name = (s.get("tours") or {}).get("name") or s["tour_slug"]
        participants = fetch_bookings_count(s["tour_slug"], s["session_date"])
        team = fetch_team(s["id"])
        total += participants

        lines.append(f"*{fmt_date_short(depart)} — {tour_name}*")
        lines.append(f"{participants} participant{'s' if participants != 1 else ''} · {format_hosts(team, with_role=False)}")
        lines.append("")

    lines.append(f"*Total :* {total} participant{'s' if total != 1 else ''}")
    lines.append("Merci à tous 🙏")
    msg = "\n".join(lines).rstrip()

    log(f"Récap hebdo — {len(sessions)} session(s), {total} participants")
    if dry_run():
        log("DRY_RUN — message non envoyé :\n" + msg)
        return
    msg_id = tg_send(msg)
    log(f"Envoyé (message_id={msg_id})")


if __name__ == "__main__":
    main()
