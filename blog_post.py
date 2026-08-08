"""Blog post generator - auto-posts the daily report to a static HTML blog.

Each run of `python blog_post.py` (or `daily_report.py --blog`):
1. Runs `daily_report.py` and captures its output.
2. Wraps it in a dated HTML post (blog/posts/YYYY-MM-DD.html).
3. Adds the REGIME + trade plan gate (regime_filter) and a short
   "what we did / how to use AI in the market" section.
4. Regenerates blog/index.html (newest first) - open it in a browser.

Static + local = zero server cost. Can later be pushed to GitHub Pages.
"""
import datetime
import html
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BLOG = os.path.join(ROOT, "blog")
POSTS = os.path.join(BLOG, "posts")
INDEX = os.path.join(BLOG, "index.html")
PY = sys.executable

DISCLAIMER = (
    "Educational research only - not investment advice. Markets carry risk; "
    "you can lose money. Never risk money you cannot afford to lose."
)

# Educational block: how to trade the market with AI (from research).
EDU_AI_SETUP = [
    ("1. Build data first, decide second",
     "Download history once, cache it (we cache to data/). All our analysis reads "
     "from cache - nothing re-downloads every day. Fast, free, repeatable."),
    ("2. Know the regime before you trade",
     "Classify the market: trending vs ranging x high vs low volatility. A trend "
     "strategy in a chop market loses money - the regime filter blocks that (RANGE_LV "
     "= NO TRADE). This is the single biggest loss-avoidance tool."),
    ("3. Risk rules come first, entries second",
     "Max 1% of capital per trade. Stop loss placed BEFORE entry, at 1.5x ATR (market "
     "structure, not a guess). 3% daily loss = stop trading for the day. No averaging "
     "down, ever."),
    ("4. Trade defined-risk only",
     "Selling naked options on a leveraged product is how accounts blow up. Buy "
     "spreads / iron condors so your max loss is known and small."),
    ("5. Paper trade 30+ days, then micro size",
     "Run the signals on live data with fake money first. If paper P&L deviates >15-20% "
     "from backtest, the backtest is wrong - fix it. Then trade 1 lot for 2 weeks."),
    ("6. AI is a filter, not a fortune teller",
     "Our ML meta-blender is ~51% vs 52% baseline - no magic edge. Use AI to organize "
     "signals (OI walls, FII/DII flow, regime, agreement counter) and to enforce "
     "discipline. The profit comes from risk control, not prediction."),
]


def _esc(text):
    return html.escape(str(text))


def _render_post(title, date_str, body_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; max-width: 900px; margin: 0 auto;
         padding: 24px 16px; background: #0f1419; color: #e6e6e6; line-height: 1.55; }}
  h1 {{ font-size: 1.7em; border-bottom: 2px solid #4f8cff; padding-bottom: 8px; }}
  h2 {{ font-size: 1.25em; margin-top: 1.6em; color: #8ab4ff; }}
  pre {{ background: #161c24; border: 1px solid #2a3540; border-radius: 8px; padding: 14px;
        overflow-x: auto; font-size: 0.82em; }}
  .meta {{ color: #8899aa; font-size: 0.9em; }}
  .gate {{ border-left: 5px solid; padding: 10px 14px; border-radius: 6px; margin: 12px 0; }}
  .gate.TRADE {{ background: #0f2b1d; border-color: #2ecc71; }}
  .gate.TRADE_REDUCED, .gate.TRADE_SMALL {{ background: #2b240f; border-color: #f1c40f; }}
  .gate.NO_TRADE {{ background: #2b0f0f; border-color: #e74c3c; }}
  .card {{ background: #161c24; border: 1px solid #2a3540; border-radius: 8px; padding: 14px 18px; margin: 12px 0; }}
  a {{ color: #8ab4ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
  .back {{ display: inline-block; margin-bottom: 16px; }}
  .warn {{ color: #f1c40f; font-size: 0.85em; margin-top: 24px; border-top: 1px solid #2a3540; padding-top: 10px; }}
  .edu h3 {{ margin-bottom: 2px; color: #4f8cff; }}
</style>
</head>
<body>
<p class="back"><a href="index.html">&larr; All posts</a></p>
<h1>{_esc(title)}</h1>
<p class="meta">{_esc(date_str)} &middot; NIFTY research toolset &middot; auto-generated</p>
{body_html}
<p class="warn">{_esc(DISCLAIMER)}</p>
</body>
</html>"""


def _render_index(posts):
    cards = "".join(
        f'<div class="card"><a href="{p["file"]}"><strong>{_esc(p["title"])}</strong></a>'
        f'<br><span class="meta">{_esc(p["date"])} &middot; {_esc(p["summary"])}</span></div>\n'
        for p in posts
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NIFTY AI Research - Daily Blog</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; max-width: 900px; margin: 0 auto;
         padding: 24px 16px; background: #0f1419; color: #e6e6e6; line-height: 1.55; }}
  h1 {{ border-bottom: 2px solid #4f8cff; padding-bottom: 8px; }}
  .card {{ background: #161c24; border: 1px solid #2a3540; border-radius: 8px; padding: 14px 18px; margin: 12px 0; }}
  a {{ color: #8ab4ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
  .meta {{ color: #8899aa; font-size: 0.9em; }}
  .warn {{ color: #f1c40f; font-size: 0.85em; margin-top: 24px; border-top: 1px solid #2a3540; padding-top: 10px; }}
</style>
</head>
<body>
<h1>NIFTY AI Research - Daily Blog</h1>
<p class="meta">Auto-posts every trading day: option-chain OI, FII/DII flow, regime gate,
stock accumulation scan and strategy edge. Built locally, pushed by our own pipeline.</p>
{cards}
<p class="warn">{_esc(DISCLAIMER)}</p>
</body>
</html>"""


def build_post(report_text, date_str=None, title=None):
    """Create one dated HTML post from the raw daily report text."""
    date_str = date_str or datetime.date.today().strftime("%Y-%m-%d")
    title = title or f"NIFTY Daily Report - {date_str}"

    # regime gate
    regime_html = ""
    try:
        import regime_filter
        plan = regime_filter.trade_plan()
        gate_cls = "NO_TRADE" if plan["gate"] == "NO_TRADE" else plan["gate"]
        fav = ", ".join(plan["favored_strategies"]) or "none"
        avd = ", ".join(plan["avoid_strategies"]) or "none"
        vix = plan.get("vix")
        vix_line = ""
        if vix:
            vix_line = (f"<br>India VIX {vix['level']} ({vix['zone'].replace('VIX_', '')} zone, "
                        f"{vix['percentile']:.0f}th pct) | premium side {plan['premium_side']} | "
                        f"expected move {vix['expected_move']} pts")
        regime_html = f"""<h2>Market Regime + Trade Gate</h2>
<div class="gate {_esc(gate_cls)}">
<strong>{_esc(plan["gate"])}</strong> &middot; {_esc(plan["regime"])} &middot; {_esc(plan["action"])}<br>
Bias: {_esc(plan["bias"])} | confidence {plan["confidence"]:.0f}% | size x{plan["size_mult"]} |
stop {plan["stop_dist"]} pts ({plan["stop_pct"]}%) | risk/trade {plan["risk_per_trade_pct"]:.0f}%{vix_line}<br>
{_esc(plan["regime_note"])}<br>
Favored: {_esc(fav)}<br>Avoid: {_esc(avd)}
</div>"""
    except Exception as e:
        regime_html = f'<div class="gate NO_TRADE">regime unavailable: {_esc(e)}</div>'

    edu_html = """<h2>How to trade the market with AI - setup guide</h2>""" + "".join(
        f'<div class="edu"><h3>{_esc(t)}</h3><p>{_esc(d)}</p></div>' for t, d in EDU_AI_SETUP
    )

    body = (
        regime_html
        + "<h2>Today's Report (auto-generated)</h2>"
        + '<pre>' + _esc(report_text) + '</pre>'
        + edu_html
    )
    return _render_post(title, date_str, body)


def main():
    os.makedirs(POSTS, exist_ok=True)

    # 1. run the daily report
    r = subprocess.run([PY, os.path.join(ROOT, "daily_report.py")], capture_output=True,
                       text=True, timeout=900)
    report_text = r.stdout.strip()
    if not report_text:
        report_text = f"report produced no output (rc={r.returncode})\n{r.stderr[-3000:]}"

    # 2. build today's post (one post per day - refresh/overwrite on re-runs)
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    post_path = os.path.join(POSTS, f"{date_str}.html")
    with open(post_path, "w", encoding="utf-8") as f:
        f.write(build_post(report_text, date_str=date_str))

    # 3. regenerate index (newest first). Sort key = full datetime from
    #    filename (date[-HHMM].html); plain date post treated as 00:00.
    posts = []
    for fn in os.listdir(POSTS):
        if not fn.endswith(".html"):
            continue
        stem = fn[:-5]
        key = stem
        try:
            key = f"{stem[:10]}T{stem[11:15] or '0000'}"
        except Exception:
            key = stem
        full = os.path.join(POSTS, fn)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        t = ""
        m = content.find("<title>")
        if m != -1:
            t = content[m + 7:content.find("</title>")]
        posts.append({"file": f"posts/{fn}", "title": t, "date": fn[:10], "key": key})
    posts.sort(key=lambda p: p["key"], reverse=True)
    posts = posts[:60]
    for i, p in enumerate(posts):
        p["summary"] = f"post {len(posts) - i}"
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(_render_index(posts))

    print(f"blog: wrote {post_path}")
    print(f"blog: index at {INDEX} ({len(posts)} posts)")
    return post_path


if __name__ == "__main__":
    main()
