"""
Build generated/streak.svg from the GitHub GraphQL contribution calendar.

Self-hosted replacement for streak-stats.demolab.com — that shared instance
is rate-limited and often slower than GitHub Camo's ~4s image timeout, which
is why the streak card kept showing up broken. This runs in Actions with the
repo's own token, so there is nothing external left to fail.

Stdlib only, no dependencies.
"""
import datetime
import json
import os
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
USER = os.environ.get("GH_USER", "VineshReddyK")
OUT = "generated/streak.svg"


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def fetch_daily_counts():
    """date -> contribution count, from account creation through today."""
    created = gql(
        "query($u:String!){ user(login:$u){ createdAt } }", {"u": USER}
    )["user"]["createdAt"]
    start_year = int(created[:4])
    today = datetime.date.today()

    q = """
    query($u:String!,$from:DateTime!,$to:DateTime!){
      user(login:$u){
        contributionsCollection(from:$from,to:$to){
          contributionCalendar{ weeks{ contributionDays{ date contributionCount } } }
        }
      }
    }"""
    days = {}
    for year in range(start_year, today.year + 1):
        data = gql(q, {
            "u": USER,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        })
        cal = data["user"]["contributionsCollection"]["contributionCalendar"]
        for week in cal["weeks"]:
            for d in week["contributionDays"]:
                date = datetime.date.fromisoformat(d["date"])
                if date <= today:
                    days[date] = d["contributionCount"]
    return days


def compute_stats(days):
    today = datetime.date.today()
    active = {d for d, c in days.items() if c > 0}
    total = sum(days.values())
    first_day = min(days) if days else today

    # current streak — today not counting yet shouldn't break the chain,
    # so if today is inactive we allow the streak to end at yesterday
    d = today if today in active else today - datetime.timedelta(days=1)
    cur = 0
    while d in active:
        cur += 1
        d -= datetime.timedelta(days=1)
    cur_start = d + datetime.timedelta(days=1)

    # longest streak — scan runs of consecutive active days
    longest, best_start, best_end, run = 0, None, None, 0
    prev = None
    for d in sorted(active):
        run = run + 1 if (prev and (d - prev).days == 1) else 1
        if run > longest:
            longest, best_end = run, d
            best_start = d - datetime.timedelta(days=run - 1)
        prev = d
    return {
        "total": total,
        "first_day": first_day,
        "cur": cur,
        "cur_start": cur_start,
        "longest": longest,
        "best_start": best_start,
        "best_end": best_end,
    }


def fmt(d):
    return f"{d:%b} {d.day}, {d.year}" if d else "—"


def fmt_short(d):
    return f"{d:%b} {d.day}" if d else "—"


def render(s):
    # tokyonight-ish palette to match the other cards on the profile
    bg, fg, blue, purple, dim = "#1a1b27", "#a9b1d6", "#7aa2f7", "#bb9af7", "#565f89"
    cur_range = f"{fmt_short(s['cur_start'])} - Present" if s["cur"] else "No active streak"
    best_range = f"{fmt_short(s['best_start'])} - {fmt_short(s['best_end'])}" if s["longest"] else "—"
    font = "'Segoe UI', Ubuntu, sans-serif"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 495 195" width="495" height="195">
  <rect width="495" height="195" rx="6" fill="{bg}"/>
  <line x1="165" y1="30" x2="165" y2="165" stroke="{dim}" stroke-opacity=".4"/>
  <line x1="330" y1="30" x2="330" y2="165" stroke="{dim}" stroke-opacity=".4"/>

  <!-- total contributions -->
  <text x="82" y="90" text-anchor="middle" font-family={font!r} font-size="30" font-weight="700" fill="{blue}">{s['total']:,}</text>
  <text x="82" y="120" text-anchor="middle" font-family={font!r} font-size="13" fill="{fg}">Total Contributions</text>
  <text x="82" y="142" text-anchor="middle" font-family={font!r} font-size="10" fill="{dim}">{fmt(s['first_day'])} - Present</text>

  <!-- current streak -->
  <circle cx="247" cy="82" r="42" fill="none" stroke="{purple}" stroke-width="4"/>
  <text x="247" y="93" text-anchor="middle" font-family={font!r} font-size="30" font-weight="700" fill="{purple}">{s['cur']}</text>
  <text x="247" y="150" text-anchor="middle" font-family={font!r} font-size="13" font-weight="600" fill="{purple}">Current Streak</text>
  <text x="247" y="170" text-anchor="middle" font-family={font!r} font-size="10" fill="{dim}">{cur_range}</text>

  <!-- longest streak -->
  <text x="412" y="90" text-anchor="middle" font-family={font!r} font-size="30" font-weight="700" fill="{blue}">{s['longest']}</text>
  <text x="412" y="120" text-anchor="middle" font-family={font!r} font-size="13" fill="{fg}">Longest Streak</text>
  <text x="412" y="142" text-anchor="middle" font-family={font!r} font-size="10" fill="{dim}">{best_range}</text>
</svg>
"""


def main():
    days = fetch_daily_counts()
    stats = compute_stats(days)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(stats))
    print(f"wrote {OUT}: total={stats['total']} current={stats['cur']} longest={stats['longest']}")


if __name__ == "__main__":
    main()
