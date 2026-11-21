"""How the alarm settings trade speed against false alarms. Leave-one-flight-out probabilities from the same random
forest, then for each threshold (0.2 to 0.9) and each K (raw alarms in a row: 1, 3, 5): faults found, median delay,
and false-alarm seconds (normal flights plus the part of fault flights before the fault). Writes a CSV and a PNG.

  python scripts/threshold_curve.py results/gazebo/table_gz_18.csv docs/threshold_gazebo [--title "Gazebo, 18 flights"]
"""
import argparse
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

SERIES = {1: "#2a78d6", 3: "#eb6834", 5: "#1baf7a"}          # categorical slots 1-3, fixed order
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def loo_probs(tab):
    feat = [c for c in tab.columns if "__" in c]; out = []
    for f in sorted(tab.flight.unique()):
        tr, te = tab[tab.flight != f], tab[tab.flight == f].copy()
        m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                                   random_state=0, n_jobs=2).fit(tr[feat], tr["label"])
        te["prob"] = m.predict_proba(te[feat])[:, 1]; out.append(te)
    return pd.concat(out)


def sweep(p):
    rows = []
    for k in SERIES:
        for thr in np.round(np.arange(0.2, 0.91, 0.05), 2):
            found = n_fault = false_s = 0; delays = []
            for f, te in p.groupby("flight"):
                al = (te["prob"] >= thr).astype(int).rolling(k, min_periods=k).min().fillna(0).astype(bool).to_numpy()
                t = te["t"].to_numpy(); fs = te["fault_sec"].iloc[0]
                if fs != fs:
                    false_s += int(al.sum()); continue
                n_fault += 1; false_s += int((al & (te["label"].to_numpy() == 0)).sum())
                hit = np.flatnonzero(al & (t + 1 > fs))
                if len(hit):
                    found += 1; delays.append(t[hit[0]] - fs)
            rows.append(dict(K=k, threshold=thr, found=found, faults=n_fault,
                             median_delay_s=float(np.median(delays)) if delays else np.nan, false_alarm_s=false_s))
    return pd.DataFrame(rows)


def chart(s, path, title):
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.6), facecolor=SURF)
    panels = [("found", "faults found"), ("median_delay_s", "median delay (s)"), ("false_alarm_s", "false-alarm seconds")]
    for ax, (col, lab) in zip(axs, panels):
        ax.set_facecolor(SURF)
        for k, c in SERIES.items():
            d = s[s.K == k]
            ax.plot(d.threshold, d[col], color=c, lw=2, label=f"K = {k}")
            ax.plot(d.threshold.iloc[-1], d[col].iloc[-1], "o", ms=8, color=c, mec=SURF, mew=2)
        cur = s[(s.K == 3) & (s.threshold == 0.5)][col].iloc[0]
        ax.plot(0.5, cur, "o", ms=9, mfc="none", mec=INK, mew=1.5)
        ax.annotate("used: 0.5, K = 3", (0.5, cur), xytext=(6, 8), textcoords="offset points", fontsize=8, color=INK2)
        ax.set_title(lab, loc="left", fontsize=10, color=INK)
        ax.set_xlabel("probability threshold", fontsize=8, color=INK2)
        ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, labelsize=8, length=0)
        if col == "found":
            ax.set_ylim(0, s.faults.max() + 0.5)
    axs[0].legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(); fig.savefig(path, dpi=130, facecolor=SURF); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("table"); ap.add_argument("out"); ap.add_argument("--title", default="")
    a = ap.parse_args()
    s = sweep(loo_probs(pd.read_csv(a.table)))
    s.to_csv(a.out + ".csv", index=False); chart(s, a.out + ".png", a.title)
    print(s[s.K == 3].to_string(index=False))
