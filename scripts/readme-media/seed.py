"""Seed a synthetic demo archive for README screenshots. Usage: ARTIKEEP_HOME=<dir> python3 seed.py <artikeep src>"""
import os
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from artikeep.store import Store  # noqa: E402

store = Store(Path(os.environ["ARTIKEEP_HOME"])).ensure()
P = "/Users/demo/code/"

BASE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;background:{bg};color:{ink}}}
.wrap{{max-width:1120px;margin:0 auto;padding:40px 48px}}h1{{font-size:34px;margin:0 0 6px;letter-spacing:-.02em}}
.sub{{color:{mute};margin:0 0 28px}}.grid{{display:grid;gap:18px}}.card{{background:{card};border-radius:14px;padding:20px 22px;box-shadow:0 1px 2px rgba(0,0,0,.06)}}
.k{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:{mute}}}.v{{font-size:30px;font-weight:700;margin-top:4px}}
.up{{color:#1f9d55;font-size:13px}}.dn{{color:#d0453a;font-size:13px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px 6px;border-bottom:1px solid {line};text-align:left}}
th{{font-size:12px;color:{mute};text-transform:uppercase;letter-spacing:.06em}}.btn{{display:inline-block;padding:11px 20px;border-radius:10px;background:{accent};color:#fff;font-weight:600;text-decoration:none}}
.pill{{display:inline-block;padding:3px 10px;border-radius:99px;background:{line};font-size:12px}}
</style></head><body><div class="wrap">{body}</div></body></html>"""


def page(title, body, bg="#f6f7fb", ink="#141824", mute="#6b7280", card="#fff", line="#e5e7eb", accent="#4f46e5"):
    return BASE.format(title=title, body=body, bg=bg, ink=ink, mute=mute, card=card, line=line, accent=accent).encode()


def bars(vals, color, h=170):
    w = 34
    mx = max(vals)
    out = []
    for i, v in enumerate(vals):
        bh = int(v / mx * (h - 20))
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="5" fill="%s" opacity="%.2f"/>' % (
            i * (w + 14), h - bh, w, bh, color, .45 + .55 * (i + 1) / len(vals)))
    return '<svg viewBox="0 0 %d %d" width="100%%" height="%d">%s</svg>' % (len(vals) * (w + 14), h, h, "".join(out))


def dashboard(v):
    kpis = [("Revenue", "$4.82M", "+12.4%"), ("Net retention", "118%", "+3 pts"), ("New accounts", "1,284", "+9.1%"), ("Churn", "1.9%", "-0.4 pts")]
    if v >= 2:
        kpis[0] = ("Revenue", "$4.91M", "+14.6%")
    rows = [("Enterprise", "$2.31M", "+18%"), ("Mid-market", "$1.64M", "+9%"), ("Self-serve", "$0.87M", "+6%")]
    if v >= 3:
        rows.append(("Partners", "$0.09M", "new"))
    body = '<h1>Q3 revenue review</h1><p class="sub">Acme Analytics · quarter ending September 30%s</p>' % (" · restated after FX close" if v >= 2 else "")
    body += '<div class="grid" style="grid-template-columns:repeat(4,1fr)">' + "".join(
        '<div class="card"><div class="k">%s</div><div class="v">%s</div><div class="%s">%s</div></div>' % (k, val, "dn" if d.startswith("-") and k != "Churn" else "up", d)
        for k, val, d in kpis) + '</div>'
    body += '<div class="grid" style="grid-template-columns:1.6fr 1fr;margin-top:18px"><div class="card"><div class="k">Monthly recurring revenue, $k</div>%s</div>' % bars(
        [980, 1040, 1100, 1180, 1250, 1310, 1420, 1490, 1610 if v >= 2 else 1560], "#4f46e5")
    body += '<div class="card"><div class="k">By segment</div><table><tr><th>Segment</th><th>Revenue</th><th>QoQ</th></tr>%s</table></div></div>' % "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % r for r in rows)
    return page("Q3 revenue review", body)


def pricing(v):
    tiers = [("Starter", "$0", "For side projects", ["1 project", "Community support"]),
             ("Pro", "$24" if v < 3 else "$19", "For growing teams", ["Unlimited projects", "Version history", "Priority support"]),
             ("Business", "$79", "For companies", ["SSO and audit log", "Custom retention", "Dedicated manager"])]
    if v == 1:
        tiers = tiers[:2]
    head = ["Simple pricing for every team", "Pricing that grows with you", "Start free. Upgrade when it clicks.", "Start free. Upgrade when it clicks."][v - 1]
    body = '<div style="text-align:center;padding:30px 0 10px"><span class="pill">Pricing</span><h1 style="font-size:46px;margin-top:14px">%s</h1><p class="sub">No credit card required%s.</p></div>' % (
        head, " · cancel any time" if v >= 4 else "")
    body += '<div class="grid" style="grid-template-columns:repeat(%d,1fr)">' % len(tiers)
    for i, (n, p, d, feats) in enumerate(tiers):
        hi = i == 1
        body += '<div class="card" style="%s"><div class="k" style="%s">%s</div><div class="v" style="font-size:40px">%s<span style="font-size:15px;font-weight:400">/mo</span></div><p>%s</p><ul>%s</ul><a class="btn" style="%s">Choose %s</a></div>' % (
            "background:#111827;color:#fff" if hi else "", "color:#a5b4fc" if hi else "", n, p, d,
            "".join("<li>%s</li>" % f for f in feats), "" if hi else "background:#e0e7ff;color:#3730a3", n)
    body += "</div>"
    return page("Pricing — Acme", body, bg="linear-gradient(180deg,#eef2ff,#fff)")


def kitchen(v):
    cells = [("Fridge", 0, 0, 1, 2, "#93c5fd"), ("Sink", 2, 0, 2, 1, "#86efac"), ("Stove", 5, 0, 2, 1, "#fca5a5"),
             ("Island", 2, 2, 3, 2, "#fde68a"), ("Pantry", 8, 0, 1, 3, "#c4b5fd")]
    if v >= 2:
        cells[3] = ("Island + seating", 2, 2, 4, 2, "#fde68a")
        cells.append(("Dishwasher", 4, 0, 1, 1, "#a7f3d0"))
    u = 74
    svg = '<svg viewBox="0 0 %d %d" width="100%%">' % (9 * u + 4, 5 * u + 4) + '<rect x="2" y="2" width="%d" height="%d" fill="#fff" stroke="#334155" stroke-width="3" rx="6"/>' % (9 * u, 5 * u)
    for n, x, y, w, h, c in cells:
        svg += '<rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="%s"/><text x="%d" y="%d" font-size="14" text-anchor="middle" fill="#1e293b">%s</text>' % (
            x * u + 8, y * u + 8, w * u - 8, h * u - 8, c, x * u + w * u / 2 + 4, y * u + h * u / 2 + 8, n)
    svg += "</svg>"
    body = '<h1>Kitchen layout planner</h1><p class="sub">3.6 × 2.4 m · work triangle %s m</p><div class="grid" style="grid-template-columns:2fr 1fr"><div class="card">%s</div><div class="card"><div class="k">Notes</div><p>Keep 1 m clearance around the island.</p><p>Sink under the window, stove on the outer wall.</p>%s</div></div>' % (
        "5.8" if v >= 2 else "6.4", svg, "<p>Dishwasher next to the sink saves 4 steps per load.</p>" if v >= 2 else "")
    return page("Kitchen layout planner", body, bg="#f8fafc")


def okr(v):
    goals = [("Ship self-serve onboarding", 82), ("Cut p95 API latency below 300 ms", 64 if v < 2 else 91), ("Reach 1,000 weekly active teams", 47), ("Hire 4 engineers", 75)]
    body = '<h1>Team OKR scorecard</h1><p class="sub">Platform team · Q4</p><div class="grid">'
    for g, p in goals:
        col = "#16a34a" if p >= 75 else "#f59e0b" if p >= 50 else "#ef4444"
        body += '<div class="card"><div style="display:flex;justify-content:space-between"><b>%s</b><span>%d%%</span></div><div style="height:10px;background:#e5e7eb;border-radius:99px;margin-top:10px"><div style="width:%d%%;height:100%%;background:%s;border-radius:99px"></div></div></div>' % (g, p, p, col)
    return page("Team OKR scorecard", body + "</div>", bg="#0f172a", ink="#e2e8f0", mute="#94a3b8", card="#1e293b", line="#334155")


def wireframes(v):
    screens = ["Welcome", "Connect your repo", "Invite teammates", "You're all set"]
    if v >= 2:
        screens.insert(2, "Pick a template")
    body = '<h1>Onboarding flow</h1><p class="sub">Wireframes · %d steps</p><div style="display:flex;gap:20px">' % len(screens)
    for i, s in enumerate(screens):
        body += '<div style="width:180px;height:360px;border:3px solid #0f172a;border-radius:26px;background:#fff;padding:22px 14px;flex:none"><div style="height:8px;width:%d%%;background:#f97316;border-radius:9px"></div><h3 style="font-size:16px">%s</h3><div style="height:90px;background:#ffedd5;border-radius:12px"></div><div style="height:10px;background:#e5e7eb;margin:14px 0 8px;border-radius:9px"></div><div style="height:10px;width:70%%;background:#e5e7eb;border-radius:9px"></div><div style="margin-top:80px;height:36px;background:#0f172a;border-radius:10px"></div></div>' % (
            (i + 1) * 100 // len(screens), s)
    return page("Onboarding flow — wireframes", body + "</div>", bg="#fff7ed")


POSTMORTEM = """# Incident postmortem: API latency spike

**Date:** 2026-10-14 · **Severity:** SEV-2 · **Duration:** 47 minutes

## Summary

p95 latency of the payments API rose from 180 ms to 2.4 s after a connection-pool
change rolled out to all regions at once.

## Timeline

| Time | Event |
|---|---|
| 14:02 | Deploy `payments-api@2.31.0` starts |
| 14:09 | Latency alert fires in eu-west |
| 14:21 | Rollback started |
| 14:49 | Latency back to baseline |

## Root cause

The pool size was read from a config key that only existed in staging.
{extra}
## Action items

- [x] Roll out pool changes region by region
- [ ] Fail the deploy when a config key is missing
"""

MIGRATION = """# Database migration plan: orders → partitioned table

## Goal

Split `orders` (1.2 B rows) by month without downtime.

## Steps

1. Create `orders_p` partitioned by `created_at`.
2. Dual-write from the app for {days} days.
3. Backfill in batches of 50k rows, throttled to 30% IO.
4. Swap names inside one transaction.

## Rollback

Keep `orders_old` for 14 days; flip the view back.
"""

TRIP = """# Lisbon, 4 days

## Day 1 — Alfama
Tram 28 early, Miradouro de Santa Luzia, lunch at a tasca, fado in the evening.

## Day 2 — Belém
Jerónimos Monastery, pastéis de Belém, MAAT along the river.

## Day 3 — Sintra
Pena Palace{sintra}, Quinta da Regaleira, back by train.

## Day 4 — LX Factory
Bookshop Ler Devagar, sunset at Miradouro da Senhora do Monte.
"""

RELEASE = """# Release notes 2.4

## New
- Version history for every page
- Compare any two versions side by side{more}

## Fixed
- Search ignored accents in titles
"""

T = "2026-10-%02dT%s:00+03:00"


def save(key, files, when, label=None, **kw):
    store.save_item(key, files, when=when, label=label, **kw)


for v, (d, h, lab) in enumerate([(3, "10:12", "first draft"), (6, "16:40", "FX restatement"), (21, "11:05", "partners segment")], 1):
    save("https://claude.ai/artifact/9a1c-demo-q3", {"index.html": dashboard(v)}, T % (d, h), lab, agent="claude-code",
         project=P + "acme-analytics", url="https://claude.ai/artifact/9a1c-demo-q3", title="Q3 revenue review", main="index.html")
for v, (d, h, lab) in enumerate([(8, "09:30", "two tiers"), (9, "12:15", "add Business"), (15, "18:02", "new headline, Pro $19"), (24, "10:44", "cancel any time")], 1):
    save("https://claude.ai/artifact/77fe-demo-pricing", {"index.html": pricing(v)}, T % (d, h), lab, agent="claude-code",
         project=P + "acme-web", url="https://claude.ai/artifact/77fe-demo-pricing", title="Pricing page redesign", main="index.html")
for v, (d, h, lab) in enumerate([(11, "20:10", None), (12, "09:05", "island with seating")], 1):
    save("mcp::kitchen-layout-planner:index.html", {"index.html": kitchen(v)}, T % (d, h), lab, agent="claude-desktop",
         title="Kitchen layout planner", main="index.html")
for v, (d, h) in enumerate([(17, "15:20"), (19, "10:00")], 1):
    save("https://claude.ai/artifact/c03d-demo-okr", {"index.html": okr(v)}, T % (d, h), None, agent="claude-code",
         project=P + "platform", url="https://claude.ai/artifact/c03d-demo-okr", title="Team OKR scorecard", main="index.html")
for v, (d, h, lab) in enumerate([(13, "13:30", None), (22, "17:45", "template step")], 1):
    save("https://claude.ai/artifact/e51b-demo-onboarding", {"index.html": wireframes(v)}, T % (d, h), lab, agent="claude-code",
         project=P + "acme-web", url="https://claude.ai/artifact/e51b-demo-onboarding", title="Onboarding flow — wireframes", main="index.html")
for v, (d, h) in enumerate([(14, "18:30"), (16, "11:20")], 1):
    extra = "" if v == 1 else "\nStaging and production configs had drifted for three months; nothing compared them.\n"
    save("codex:/tmp/postmortem-latency.md", {"postmortem-latency.md": POSTMORTEM.format(extra=extra).encode()}, T % (d, h), None,
         agent="codex", project=P + "payments-api", origin="/tmp/postmortem-latency.md", main="postmortem-latency.md")
for v, (d, h) in enumerate([(18, "09:40"), (23, "14:10")], 1):
    save("codex:/tmp/migration-plan.md", {"migration-plan.md": MIGRATION.format(days=7 if v == 1 else 10).encode()}, T % (d, h), None,
         agent="codex", project=P + "payments-api", origin="/tmp/migration-plan.md", main="migration-plan.md")
for v, (d, h) in enumerate([(2, "21:00"), (2, "21:30"), (4, "08:15")], 1):
    save("chatgpt:demo-lisbon:1", {"lisbon.md": TRIP.format(sintra=" (book tickets online)" if v >= 2 else "").encode()}, T % (d, h), None,
         agent="chatgpt", title="Lisbon, 4 days", main="lisbon.md")
for v, (d, h) in enumerate([(20, "16:00"), (25, "12:30")], 1):
    save("claude-ai:demo-release:notes", {"release-notes.md": RELEASE.format(more="" if v == 1 else "\n- Restore an old version as the current one").encode()},
         T % (d, h), None, agent="claude-ai", title="Release notes 2.4", main="release-notes.md")
print("seeded", store.root)
