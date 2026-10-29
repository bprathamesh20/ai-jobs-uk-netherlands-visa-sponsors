"""Rebuild README.md, jobs.csv and employers.csv from the AI Expat Jobs feeds.

Usage: python scripts/build.py [path-or-url]   (default: https://aiexpatjobs.com/data/jobs.json)
Runs daily from .github/workflows/update.yml. Exits without writing anything if the feed looks broken.
"""
import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

FEED = "https://aiexpatjobs.com/data/jobs.json"
EMPLOYERS = "https://aiexpatjobs.com/data/employers.csv"  # one row per employer: register entities, open roles, pay
ROOT = Path(__file__).resolve().parent.parent
MIN_JOBS = 50  # a smaller feed means something upstream broke; keep yesterday's list

COUNTRIES = [("UK", "🇬🇧 United Kingdom"), ("NL", "🇳🇱 Netherlands")]
FAMILIES = [
    ("ai_eng", "AI & ML engineering"),
    ("fde", "Forward-deployed engineering"),
    ("research", "AI research"),
    ("data_science", "Data science"),
]
REGISTERS = {
    "UK": "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers",
    "NL": "https://ind.nl/en/public-register-recognised-sponsors",
}


def load(src: str) -> dict:
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "ai-jobs-uk-netherlands-visa-sponsors (+github)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    return json.loads(Path(src).read_text())


def load_employers() -> list[dict]:
    # Optional: if the employer feed is down, the README is built without the employer table.
    try:
        req = urllib.request.Request(EMPLOYERS, headers={"User-Agent": "ai-jobs-uk-netherlands-visa-sponsors (+github)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"Employer feed unavailable ({e}); skipping the employer table.")
        return []
    (ROOT / "employers.csv").write_text(text)
    rows = list(csv.DictReader(text.splitlines()))
    return [r for r in rows if int(r.get("open_ai_roles") or 0) > 0]


def employer_section(emps: list[dict], heading: str) -> list[str]:
    # Answers "which AI companies sponsor visas?" directly: the companies, the legal entity on each register, and today's roles.
    uk = sum(bool(e["uk_register_entity"]) for e in emps)
    nl = sum(bool(e["nl_register_entity"]) for e in emps)
    names = [f"{e['employer']} ({e['open_ai_roles']})" for e in emps[:5]]
    top = f"{', '.join(names[:-1])} and {names[-1]}" if len(names) > 1 else names[0]
    out = [
        f"## {heading}",
        "",
        f"**{len(emps)} companies with open AI, ML or data roles today are on an official sponsor register**: {uk} on the UK Home Office "
        f"register of licensed sponsors and {nl} on the Dutch IND register of recognised sponsors. The most open roles are at {top}.",
        "",
        "The table gives the legal entity each one is registered under, which is often not the brand name. Being on a register means the "
        "company *can* sponsor a visa; the last columns show how many of its postings mention sponsorship, and what pay they state.",
        "",
        "| Company | Open roles | Registered as | Postings mentioning sponsorship | Stated pay |",
        "|---|---|---|---|---|",
    ]
    for e in emps:
        reg = " · ".join(x for x in [
            f"🇬🇧 {cell(e['uk_register_entity'])}" if e["uk_register_entity"] else "",
            f"🇳🇱 {cell(e['nl_register_entity'])}" if e["nl_register_entity"] else "",
        ] if x)
        pay = " · ".join(x for x in [cell(e["stated_pay_uk"]), cell(e["stated_pay_nl"])] if x)
        visa = e["postings_mentioning_visa_sponsorship"]
        out.append(f"| [{cell(e['employer'])}]({e['employer_page']}) | {e['open_ai_roles']} | {reg} | {visa if visa != '0' else ''} | {pay} |")
    out += ["", f"Every company's register entry, check date and open roles: [aiexpatjobs.com/employers](https://aiexpatjobs.com/employers/).", ""]
    return out


def cell(s: str) -> str:
    return " ".join(str(s).split()).replace("|", "\\|")


def anchor(text: str) -> str:
    # GitHub heading anchors: lowercase, drop punctuation and emoji, each space becomes a hyphen.
    keep = "".join(ch for ch in text.lower() if ch.isalnum() or ch in " -")
    return keep.replace(" ", "-")  # no strip: GitHub keeps the hyphen left by a leading emoji


def table(rows: list[dict], new_since: str) -> list[str]:
    out = ["| Company | Role | Location | Pay | Notes | Added | |", "|---|---|---|---|---|---|---|"]
    for j in rows:
        notes = " ".join(n for n, on in [("🆕", j["firstSeen"] >= new_since), ("🛂", j["visaMentioned"]), ("✈️", j["relocationMentioned"])] if on)
        added = dt.date.fromisoformat(j["firstSeen"]).strftime("%-d %b")
        out.append(
            f"| **{cell(j['company'])}** | [{cell(j['title'])}]({j['page']}) | {cell(j['location'])} | {cell(j['pay'] or '')} "
            f"| {notes} | {added} | [Apply ↗]({j['apply']}) |"
        )
    return out


def main() -> None:
    feed = load(sys.argv[1] if len(sys.argv) > 1 else FEED)
    emps = sorted(load_employers(), key=lambda e: (-int(e["open_ai_roles"]), e["employer"].lower()))
    emp_heading = "Which AI companies sponsor visas in the UK and the Netherlands?"
    jobs = feed.get("jobs") or []
    if len(jobs) < MIN_JOBS:
        sys.exit(f"Feed has {len(jobs)} jobs (< {MIN_JOBS}); not updating.")

    as_of = feed["asOf"]
    new_since = (dt.date.fromisoformat(as_of) - dt.timedelta(days=7)).isoformat()
    employers = len({j["company"] for j in jobs})
    by_country = {c: [j for j in jobs if c in j["countries"]] for c, _ in COUNTRIES}
    order = lambda j: (-dt.date.fromisoformat(j["firstSeen"]).toordinal(), j["company"].lower(), j["title"].lower())
    as_of_text = dt.date.fromisoformat(as_of).strftime("%-d %B %Y")
    new_count = sum(j["firstSeen"] >= new_since for j in jobs)

    md = [
        "# AI jobs in the UK & Netherlands at visa sponsors",
        "",
        f"![Updated](https://img.shields.io/badge/updated-{as_of.replace('-', '--')}-2f7d5b)"
        f" ![Roles](https://img.shields.io/badge/open_roles-{len(jobs)}-2f7d5b)"
        f" ![New this week](https://img.shields.io/badge/new_this_week-{new_count}-c2410c)",
        "",
        f"**{len(jobs)} open AI, ML and data roles at {employers} employers**, updated every day. Every employer here is on an official "
        f"visa-sponsor register: the UK Home Office [register of licensed sponsors]({REGISTERS['UK']}) or the Dutch IND "
        f"[public register of recognised sponsors]({REGISTERS['NL']}). Postings that say the company can't sponsor are left out.",
        "",
        "Search, filter by city and role, and get a free weekly email of new roles at **[aiexpatjobs.com](https://aiexpatjobs.com)**.",
        "",
        "> [!NOTE]",
        "> Being on a register means an employer *can* sponsor a visa, not that every role will. Check the posting, and ask the recruiter early.",
        "",
        "**Key:** 🆕 added in the last 7 days · 🛂 the posting mentions visa sponsorship · ✈️ the posting mentions relocation support. "
        "Pay is shown only when the posting states it. Click a role for the employer's register details; **Apply ↗** goes to the employer's own posting.",
        "",
        "## Contents",
        "",
    ]
    if emps:
        md.append(f"- [{emp_heading}](#{anchor(emp_heading)}) ({len(emps)} companies)")
    for c, name in COUNTRIES:
        md.append(f"- [{name.split(' ', 1)[1]}](#{anchor(name)}) ({len(by_country[c])})")
        for f, fname in FAMILIES:
            n = sum(j["family"] == f for j in by_country[c])
            if n:
                md.append(f"  - [{fname}](#{anchor(fname + ' ' + c)}) ({n})")
    md += ["- [How this list is made](#how-this-list-is-made)", "- [Data and licence](#data-and-licence)", ""]
    if emps:
        md += employer_section(emps, emp_heading)

    for c, name in COUNTRIES:
        md += [f"## {name}", "", f"{len(by_country[c])} roles. Register checked {feed['registersChecked'].get(c, '')}.", ""]
        for f, fname in FAMILIES:
            rows = sorted((j for j in by_country[c] if j["family"] == f), key=order)
            if rows:
                md += [f"### {fname} ({c})", ""] + table(rows, new_since) + [""]

    md += [
        "## How this list is made",
        "",
        "1. Every morning, roles are read from about 150 AI employers' own job boards (Greenhouse, Ashby, Lever and others). "
        "Only AI, ML, forward-deployed and data roles in the UK and the Netherlands are kept.",
        "2. Each employer is matched to the UK and Dutch sponsor registers by its legal entity name. Matches are reviewed by hand, "
        "because brand names rarely match legal names.",
        "3. An AI model reads each posting for stated pay and for sponsorship and relocation mentions. A role is left out for saying "
        "it can't sponsor only when that sentence is found in the posting. These notes can still be wrong, so always check the posting.",
        f"4. A GitHub Action rebuilds this README from [aiexpatjobs.com/data/jobs.json](https://aiexpatjobs.com/data/jobs.json) every day. "
        f"This version is from {as_of_text}.",
        "",
        "Big employers on Workday or their own careers sites (for example Booking.com and ASML) aren't covered yet.",
        "",
        "**Wrong or missing?** [Open an issue](../../issues) with the employer or role. Please don't edit the tables by hand; they're regenerated daily.",
        "",
        "## Data and licence",
        "",
        "- [`jobs.csv`](jobs.csv) in this repo: one row per role, updated daily. [`employers.csv`](employers.csv): one row per company, "
        "with its legal entity on each register.",
        "- JSON feed: [aiexpatjobs.com/data/jobs.json](https://aiexpatjobs.com/data/jobs.json). One row per employer: "
        "[aiexpatjobs.com/data/employers.csv](https://aiexpatjobs.com/data/employers.csv).",
        "- The data is free to reuse under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); please credit "
        "**AI Expat Jobs ([aiexpatjobs.com](https://aiexpatjobs.com))**. The code in `scripts/` is MIT licensed.",
        "",
    ]
    (ROOT / "README.md").write_text("\n".join(md))

    fields = ["company", "title", "family", "countries", "location", "pay", "visaMentioned", "relocationMentioned", "firstSeen", "page", "apply"]
    with open(ROOT / "jobs.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(fields + ["asOf"])
        for j in sorted(jobs, key=lambda j: (j["company"].lower(), j["title"].lower())):
            w.writerow([" ".join(j[k]) if k == "countries" else j[k] for k in fields] + [as_of])
    print(f"Wrote README.md, jobs.csv{' and employers.csv' if emps else ''}: {len(jobs)} roles at {employers} employers, as of {as_of}.")


if __name__ == "__main__":
    main()
