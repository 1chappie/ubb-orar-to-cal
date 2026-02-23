#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from zoneinfo import ZoneInfo

import ubb2ics_core as core


def ask(prompt: str, default: str | None = None) -> str:
    if default is None:
        return input(f"{prompt}: ").strip()
    ans = input(f"{prompt} [{default}]: ").strip()
    return ans if ans else default


def ask_required(prompt: str) -> str:
    while True:
        s = input(f"{prompt}: ").strip()
        if s:
            return s
        print("  This value is required. Try again.")


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    default = "y" if default_yes else "n"
    ans = input(f"{prompt} (y/n) [{default}]: ").strip().lower()
    if not ans:
        return default_yes
    return ans.startswith("y")


def parse_date_loop(prompt: str):
    while True:
        s = ask(prompt)
        try:
            return core.parse_date_flexible(s)
        except Exception:
            print(
                "  Invalid date. Use DD-MM-YYYY or DD.MM.YYYY (e.g. 23-02-2026 or 23.02.2026)."
            )


def ask_vacations() -> list[tuple[core.date, core.date]]:
    print(
        "\nVacation periods (max 2). Format: DD-MM-YYYY..DD-MM-YYYY or DD.MM.YYYY..DD.MM.YYYY"
    )
    print("You can mix separators too: 06-04-2026..12.04.2026")
    print("Press Enter on an empty line to stop.\n")

    vacs: list[tuple[core.date, core.date]] = []
    while len(vacs) < 2:
        s = input(f"Vacation #{len(vacs)+1}: ").strip()
        if not s:
            break
        parts = s.split("..")
        if len(parts) != 2:
            print("  Invalid format. Example: 06-04-2026..12-04-2026")
            continue
        try:
            a = core.parse_date_flexible(parts[0])
            b = core.parse_date_flexible(parts[1])
        except Exception:
            print("  Invalid dates. Example: 06-04-2026..12-04-2026")
            continue
        if b < a:
            a, b = b, a
        vacs.append((a, b))
    return vacs


def choose_disciplines(rows) -> set[str]:
    disciplines = core.list_disciplines(rows)
    print("\nDisciplines found:\n")
    for i, d in enumerate(disciplines, 1):
        print(f"  {i:>2}. {d}")

    print("\nSelect disciplines to include:")
    print("  - numbers like: 1,3-5,9")
    print("  - blank = ALL\n")

    ans = input("> ").strip()
    if not ans:
        return set(disciplines)

    picked = core.parse_selection(ans, len(disciplines))
    if not picked:
        print("No valid selections. Exiting.")
        sys.exit(1)

    return {disciplines[i - 1] for i in sorted(picked)}


def main():
    print("\nUBB timetable → .ics (curl fetch, interactive CLI)\n")

    url = ask_required("Timetable URL")  # required, no default
    tz_name = ask("Timezone (IANA, e.g. Europe/Bucharest)", core.DEFAULT_TZ)

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        print("Invalid timezone name. Example valid value: Europe/Bucharest")
        sys.exit(1)

    sem_start = parse_date_loop("Semester start (DD-MM-YYYY or DD.MM.YYYY)")
    sem_end = parse_date_loop("Semester end   (DD-MM-YYYY or DD.MM.YYYY)")
    if sem_end < sem_start:
        sem_start, sem_end = sem_end, sem_start

    vacations = ask_vacations()

    add_week_markers = ask_yes_no(
        "Add WEEK number markers? (standalone all-day on teaching Mondays)",
        default_yes=True,
    )
    out = ask("Output .ics filename", core.DEFAULT_OUT)

    print(f"\nFetching timetable via curl:\n  {url}\n")
    html = core.fetch_html(url)
    rows = core.parse_rows(html)
    if not rows:
        print("No timetable rows found after parsing. Exiting.")
        sys.exit(1)

    selected = choose_disciplines(rows)

    ics_text = core.generate_ics(
        rows=rows,
        url=url,
        tz=tz,
        sem_start=sem_start,
        sem_end=sem_end,
        vacations=vacations,
        selected=selected,
        add_week_markers=add_week_markers,
    )

    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(ics_text)

    print(f"\nWrote: {out}")
    print(f"Disciplines included ({len(selected)}):")
    for d in sorted(selected):
        print(f"  - {d}")


if __name__ == "__main__":
    main()
