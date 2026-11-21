"""Which features the random forest relies on (impurity importance of a model trained on all flights of a table).
One panel per table, top 8 features, one hue. Writes a PNG.

  python scripts/feature_chart.py docs/feature_importance.png "SIH" results/sih/table_sih_18.csv "Gazebo" results/gazebo/table_gz_18.csv
"""
import sys
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, INK, INK2, GRID, SURF = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SIG = {"alt_error": "altitude error", "hud_altitude": "altitude", "vel_lin_z": "climb rate", "xtrack_error": "distance to circle",
       "roll_gap": "roll tracking", "pitch_gap": "pitch tracking", "yaw_gap": "yaw tracking"}
STAT = {"mean5": "5 s mean", "std5": "5 s spread", "delta10": "10 s change"}


def nice(c):
    s, st = c.split("__"); return f"{SIG.get(s, s)}, {STAT.get(st, st)}"


out = sys.argv[1]; pairs = list(zip(sys.argv[2::2], sys.argv[3::2]))
fig, axs = plt.subplots(1, len(pairs), figsize=(5.2 * len(pairs), 3.6), facecolor=SURF)
axs = [axs] if len(pairs) == 1 else axs
for ax, (title, path) in zip(axs, pairs):
    t = pd.read_csv(path); feat = [c for c in t.columns if "__" in c]
    m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample", random_state=0,
                               n_jobs=2).fit(t[feat], t["label"])
    imp = pd.Series(m.feature_importances_, feat).sort_values().tail(8)
    ax.set_facecolor(SURF)
    ax.barh([nice(c) for c in imp.index], imp.values, color=BLUE, height=0.6)
    for y, v in enumerate(imp.values):
        ax.text(v + 0.003, y, f"{v:.2f}", va="center", fontsize=8, color=INK)
    ax.set_title(f"{title}: top 8 of {len(feat)} features", loc="left", fontsize=10, color=INK)
    ax.set_xlabel("share of the model's splits (importance)", fontsize=8, color=INK2)
    ax.grid(axis="x", color=GRID, lw=0.6); ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.set_xlim(0, imp.max() * 1.18)
fig.tight_layout(); fig.savefig(out, dpi=130, facecolor=SURF)
print("saved", out)
