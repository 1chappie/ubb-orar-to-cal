#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
import hashlib
import subprocess
from html.parser import HTMLParser
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/Bucharest"
DEFAULT_OUT = "schedule.ics"

DAY_TO_INDEX = {
    "Luni": 0,
    "Marti": 1,
    "Marți": 1,
    "Miercuri": 2,
    "Joi": 3,
    "Vineri": 4,
    "Sambata": 5,
    "Sâmbătă": 5,
    "Duminica": 6,
    "Duminică": 6,
}

TIP_PREFIX = {
    "Curs": "CURS",
    "Seminar": "SEM",
    "Laborator": "LAB",
    "Laboratorul": "LAB",
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def parse_date_flexible(s: str) -> date:
    """
    Accepts:
      - DD-MM-YYYY
      - DD.MM.YYYY
    """
    s = norm(s)
    m = re.match(r"^(\d{2})[-.](\d{2})[-.](\d{4})$", s)
    if not m:
        raise ValueError(f"Invalid date format: {s!r}")
    d, mo, y = map(int, m.groups())
    return date(y, mo, d)


def parse_time_interval(s: str) -> tuple[time, time]:
    s = norm(s).replace("–", "-")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?$", s)
    if not m:
        raise ValueError(f"Cannot parse time interval: {s!r}")
    h1, mi1, h2, mi2 = m.groups()
    return time(int(h1), int(mi1 or 0)), time(int(h2), int(mi2 or 0))


def parse_frequency(freq: str) -> int | None:
    # None => weekly, 1 => sapt. 1, 2 => sapt. 2
    f = norm(freq).lower()
    if not f:
        return None
    m = re.search(r"s[ăa]pt\.?\s*(1|2)", f)
    return int(m.group(1)) if m else None


def stable_uid(seed: str) -> str:
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"{h[:16]}@ubb2ics"


def ics_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def format_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def format_dt_utc(dt_local: datetime, tz: ZoneInfo) -> str:
    dt = dt_local.replace(tzinfo=tz).astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def monday_on_or_after(d: date) -> date:
    return d + timedelta(days=(0 - d.weekday()) % 7)


def parity_ok(freq_parity: int | None, teaching_week_num: int) -> bool:
    if freq_parity is None:
        return True
    is_odd = teaching_week_num % 2 == 1
    return (freq_parity == 1 and is_odd) or (freq_parity == 2 and not is_odd)


def fetch_html(url: str) -> str:
    """
    Fix C: use system curl (macOS trust store), avoids Python SSL CA issues.
    """
    p = subprocess.run(
        ["curl", "-L", "-s", "--fail", url], capture_output=True, text=True
    )
    if p.returncode != 0:
        raise RuntimeError(f"curl failed ({p.returncode}): {p.stderr.strip()}")
    return p.stdout


# first table -> rows
class FirstTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tr = False
        self.in_cell = False
        self.done = False

        self.cell_buf = []
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag == "table" and not self.in_table:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_tr = True
            self.row = []
        elif self.in_tr and tag in ("td", "th"):
            self.in_cell = True
            self.cell_buf = []

    def handle_endtag(self, tag):
        if self.done:
            return
        if self.in_cell and tag in ("td", "th"):
            self.in_cell = False
            self.row.append(norm("".join(self.cell_buf)))
        elif self.in_tr and tag == "tr":
            self.in_tr = False
            if any(c.strip() for c in self.row):
                self.rows.append(self.row)
        elif self.in_table and tag == "table":
            self.in_table = False
            self.done = True

    def handle_data(self, data):
        if self.in_cell:
            self.cell_buf.append(data)


def parse_rows(html: str):
    p = FirstTableParser()
    p.feed(html)
    grid = p.rows
    if not grid:
        raise RuntimeError("No table parsed (0 rows).")

    headers = grid[0]

    def idx(name: str) -> int:
        try:
            return headers.index(name)
        except ValueError:
            raise RuntimeError(f"Missing header {name!r}. Found: {headers}")

    i_ziua = idx("Ziua")
    i_orele = idx("Orele")
    i_frec = idx("Frecventa")
    i_sala = idx("Sala")
    i_tip = idx("Tipul")
    i_disc = idx("Disciplina")
    i_cadru = idx("Cadrul didactic")

    rows = []
    for r in grid[1:]:
        r = r + [""] * (len(headers) - len(r))
        day = r[i_ziua]
        if day not in DAY_TO_INDEX:
            continue
        rows.append(
            {
                "ziua": day,
                "orele": r[i_orele],
                "frecventa": r[i_frec],
                "sala": r[i_sala],
                "tipul": r[i_tip],
                "disciplina": r[i_disc],
                "cadru": r[i_cadru],
            }
        )
    return rows


def in_vacation_week(monday: date, vacations: list[tuple[date, date]]) -> bool:
    for a, b in vacations:
        if a <= monday <= b:
            return True
    return False


def build_teaching_mondays(
    sem_start: date, sem_end: date, vacations: list[tuple[date, date]]
) -> list[date]:
    cur = monday_on_or_after(sem_start)
    mondays = []
    while cur <= sem_end:
        if not in_vacation_week(cur, vacations):
            mondays.append(cur)
        cur += timedelta(days=7)
    return mondays


# Subject selection helpers (still useful to keep in core)
def parse_selection(expr: str, n: int) -> set[int]:
    expr = norm(expr)
    if not expr:
        return set()
    out: set[int] = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            lo, hi = min(a, b), max(a, b)
            for i in range(lo, hi + 1):
                if 1 <= i <= n:
                    out.add(i)
        else:
            i = int(part)
            if 1 <= i <= n:
                out.add(i)
    return out


def list_disciplines(rows) -> list[str]:
    return sorted({r["disciplina"] for r in rows})


# ICS generation
def generate_ics(
    rows,
    url: str,
    tz: ZoneInfo,
    sem_start: date,
    sem_end: date,
    vacations: list[tuple[date, date]],
    selected: set[str],
    add_week_markers: bool,
) -> str:
    teaching_mondays = build_teaching_mondays(sem_start, sem_end, vacations)
    if not teaching_mondays:
        raise RuntimeError(
            "No teaching weeks after applying vacations. Check semester dates/vacations."
        )

    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ubb2ics-cli//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    # Week markers: all-day events on Mondays for teaching weeks only
    if add_week_markers:
        for i, mon in enumerate(teaching_mondays, 1):
            uid = stable_uid(f"week-marker|{mon.isoformat()}")
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"SUMMARY:{ics_escape(f'WEEK {i}')}",
                f"DTSTART;VALUE=DATE:{format_date(mon)}",
                f"DTEND;VALUE=DATE:{format_date(mon + timedelta(days=1))}",
                "END:VEVENT",
            ]

    # Course events: one VEVENT per actual occurrence
    for r in rows:
        if r["disciplina"] not in selected:
            continue

        start_t, end_t = parse_time_interval(r["orele"])
        day_offset = DAY_TO_INDEX[r["ziua"]]
        freq_parity = parse_frequency(r["frecventa"])

        tip = norm(r["tipul"])
        prefix = TIP_PREFIX.get(tip, tip.upper() if tip else "")
        summary = f"{prefix} {r['disciplina']}".strip()

        for week_num, week_mon in enumerate(teaching_mondays, 1):
            if not parity_ok(freq_parity, week_num):
                continue

            occ_date = week_mon + timedelta(days=day_offset)
            if occ_date < sem_start or occ_date > sem_end:
                continue

            dtstart_local = datetime.combine(occ_date, start_t)
            dtend_local = datetime.combine(occ_date, end_t)

            uid = stable_uid(
                f"{summary}|{occ_date.isoformat()}|{r['orele']}|{r['sala']}|{r['cadru']}"
            )

            desc_parts = []
            if norm(r["cadru"]):
                desc_parts.append(f"Teacher: {norm(r['cadru'])}")
            if norm(r["frecventa"]):
                desc_parts.append(
                    f"Frequency: {norm(r['frecventa'])} (odd/even teaching weeks)"
                )
            desc_parts.append(f"Source: {url}")

            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"SUMMARY:{ics_escape(summary)}",
                f"DTSTART:{format_dt_utc(dtstart_local, tz)}",
                f"DTEND:{format_dt_utc(dtend_local, tz)}",
            ]
            if norm(r["sala"]):
                lines.append(f"LOCATION:{ics_escape(norm(r['sala']))}")
            lines.append(f"DESCRIPTION:{ics_escape('\\n'.join(desc_parts))}")
            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
