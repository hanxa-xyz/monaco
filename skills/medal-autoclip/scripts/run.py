"""One command for the live case: parse → analyze both games → print scorecards + draft closes,
save figures, and (by default) build an executed notebook to screen-share and extend.

    /opt/anaconda3/bin/python .claude/skills/medal-autoclip/scripts/run.py <packet dir|xlsx|csv> \
        --out companies/medal/live [--no-nb] [--launch rl=2026-05-07 --launch gj=2026-05-21]
"""
import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import medal_parse as mp  # noqa: E402
import medal_views as mv  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("packet")
    ap.add_argument("--out", default="companies/medal/live")
    ap.add_argument("--no-nb", action="store_true")
    ap.add_argument("--launch", action="append", default=[], help="game=YYYY-MM-DD override")
    ap.add_argument("--event", action="append", default=[], help="game=YYYY-MM-DD:YYYY-MM-DD:label")
    a = ap.parse_args()
    for kv in a.launch:
        g, dt = kv.split("=")
        mp.GAMES[g]["launch"] = dt
    for kv in a.event:
        g, rest = kv.split("=", 1)
        s, e, lbl = rest.split(":", 2)
        mp.GAMES[g]["events"].append((s, e, lbl))
    out = Path(a.out)
    (out / "figs").mkdir(parents=True, exist_ok=True)

    P = mp.load_packet(a.packet)
    P.report()

    pv = mv.platform(P.get("platform", "platform"))
    if pv:
        t = pv["table"]
        print("\nPLATFORM — top games by clips (auto share, delete/share EVENTS per clip)")
        print(t[["rank", "game", "clips_total", "auto_share", "delete_ev_per_clip", "share_ev_per_clip"]]
              .head(20).to_string(index=False, formatters={"clips_total": "{:,.0f}".format, "auto_share": "{:.0%}".format,
                                                          "delete_ev_per_clip": "{:.2f}".format, "share_ev_per_clip": "{:.3f}".format}))
        print(f"corr(auto share, delete/clip) = {pv['corr']['delete_ev_per_clip']:+.2f}; "
              f"corr(auto share, share/clip) = {pv['corr']['share_ev_per_clip']:+.2f}")
        mv.fig_platform(pv).savefig(out / "figs" / "platform.png")
        plt.close("all")

    closes = [f"# Draft close — {Path(a.packet).resolve().parent.name if Path(a.packet).name == 'packet' else Path(a.packet).name}\n"]
    for g in P.games():
        A = mv.analyze_game(P, g)
        if A is None:
            continue
        print(f"\n{'=' * 100}\n{A['name'].upper()} — launch {A['launch'].date()}  "
              f"(PRE {mv.PRE_DAYS}d · skip {mv.RAMP}d ramp · POST {mv.POST_DAYS}d)")
        print(mv.fmt_scorecard(A["sc"]).to_string(index=False))
        A["sc"].to_csv(out / f"scorecard_{g}.csv", index=False)
        if A["purge_spans"]:
            print(f"deletion spikes excluded: {A['purge_spans']}")
        if A["o14"] is not None:
            print("\n14D outcomes, post-launch by class:")
            print(A["o14"]["post"][["clips_captured", "deleted_rate", "shared_rate", "post_rate", "pct_of_clips",
                                    "pct_of_shares"]].round(3).to_string())
        if A["trig"] is not None:
            print("\nTriggers:")
            print(A["trig"]["table"][["trigger_name", "clips_captured", "pct_volume", "delete_rate", "share_rate",
                                      "pct_shares", "verdict"]].round(3).to_string(index=False))
        if A["rr"] is not None:
            print(f"\nReturn rate: wk2 gap {A['rr']['gap_wk2']:+.1%}, wk5 gap {A['rr']['gap_wk5']:+.1%} (selection-biased)")
        if A["ext"]:
            x = A["ext"]
            print("\nExternal (vs pre-launch baseline, sale/DAU spikes excluded):")
            for m, r in x["res"].items():
                print(f"  {m:<19} pre {r['pre']:>9,.3g}  post {r['post']:>9,.3g}  naive {r['naive']:+.1%}  "
                      f"vs {'trend' if r['trend'] else 'level'} {r['its']:+.1%}  95% CI {mv._band(r)}  → {r['call']}")
            if x["penetration"]:
                print(f"  Medal penetration of DAU: {x['penetration'][0]:.1%} pre → {x['penetration'][1]:.1%} post")
            print(f"  sale-like copies spikes: {[(str(a), str(b), round(k, 1)) for a, b, k in x['sale_spans']]}")
            print(f"  DAU spikes (patch/event?): {[(str(a), str(b), round(k, 2)) for a, b, k in x['dau_spans']]}")
            print("  break-even: " + ", ".join(f"{k}={v:,.2f}" for k, v in (A['break_even'] or {}).items()))
            print(f"  reach check failures: {A['implausible'] or 'none'}")
            print(f"  whole-game shock: {A['dau_shock'] or 'none'}")
            if x["weekly"] is not None:
                print("\n  Weekly: studio metric vs projected trend, next to Medal auto-clip volume")
                print(x["weekly"].to_string(float_format=lambda v: f"{v:+.0%}" if abs(v) < 5 else f"{v:,.0f}"))
        print(f"\nCalendar events / spikes inside POST window: {A['events_in_post'] or 'none'}")
        print(f"\nDRAFT CLOSE\n{A['close']}")
        closes.append(A["close"])
        for name, fn in (("composition", mv.fig_composition), ("rates", mv.fig_rates), ("quality", mv.fig_quality),
                         ("return", mv.fig_return), ("external", mv.fig_external)):
            f = fn(A)
            if f is not None:
                f.savefig(out / "figs" / f"{g}_{name}.png")
        plt.close("all")
    (out / "close.md").write_text("\n\n---\n\n".join(closes) + "\n")
    print(f"\nwrote {out / 'close.md'}, scorecards, figs/")

    if not a.no_nb:
        build_notebook(Path(a.packet).resolve(), out.resolve(), P.games())


def build_notebook(packet, out, games):
    from monaco import viz as dv
    nb = dv.new_notebook()
    nb.cells += [
        dv.md("# Medal auto-clipping — live analysis\n" + mv.__doc__.split("\n", 1)[1]),
        dv.code(f"import sys; sys.path.insert(0, {str(HERE)!r})\n"
                "import pandas as pd, matplotlib.pyplot as plt\n"
                "import medal_parse as mp, medal_views as mv\n"
                "from IPython.display import Markdown, display\n"
                "pd.set_option('display.width', 200); pd.set_option('display.max_columns', 20)\n"
                f"P = mp.load_packet({str(packet)!r})\nP.report()"),
        dv.md("## Platform: where RL and GJ sit, and what auto-clipping does to per-clip rates"),
        dv.code("pv = mv.platform(P.get('platform', 'platform'))\n"
                "if pv:\n    mv.fig_platform(pv); plt.show()\n"
                "    display(pv['table'][['rank','game','clips_total','auto_share','delete_ev_per_clip','share_ev_per_clip']].head(20))"),
    ]
    for g in games:
        name = mp.GAMES[g]["name"]
        nb.cells += [
            dv.md(f"## {name}"),
            dv.code(f"A = mv.analyze_game(P, {g!r}); {g.upper()} = A\n"
                    "display(mv.fmt_scorecard(A['sc']))\nprint('deletion spikes excluded:', A['purge_spans'])"),
            dv.code("mv.fig_composition(A); plt.show()"),
            dv.code("mv.fig_rates(A); plt.show()"),
            dv.code("mv.fig_quality(A); plt.show()\n"
                    "if A['o14'] is not None: display(A['o14']['post'].round(3))\n"
                    "if A['trig'] is not None: display(A['trig']['table'].round(3))"),
            dv.code("if A['rr'] is not None:\n    mv.fig_return(A); plt.show(); display(A['rr']['table'])"),
            dv.code("if A['ext']:\n    mv.fig_external(A); plt.show()\n"
                    "    print('penetration (pre, post):', A['ext']['penetration'])\n"
                    "    print('sale spikes:', A['ext']['sale_spans'], '| DAU spikes:', A['ext']['dau_spans'])\n"
                    "    print('break-even:', A['break_even']); print('reach check failures:', A['implausible'])\n"
                    "    display(A['ext']['weekly'])\n"
                    "print('events in POST window:', A['events_in_post'])"),
            dv.md(f"### {name} — draft close (edit live)"),
            dv.code("display(Markdown(A['close']))"),
        ]
    nb.cells += [dv.md("## Scratch — follow-ups the interviewer asks for"),
                 dv.code("# RL['d'] / GJ['d'] = derived daily frames; P.get(game, kind) = raw tables; P.ext('gj')")]
    dv.build_and_execute(nb, str(out / "medal_live.ipynb"), workdir=str(out))


if __name__ == "__main__":
    main()
