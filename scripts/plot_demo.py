import sys, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
# usage: python plot_demo.py probs.csv <fault_flight> <normal_flight> out.png ["title"]
probs = pd.read_csv(sys.argv[1]); fault_f, norm_f, out = sys.argv[2], sys.argv[3], sys.argv[4]
title = sys.argv[5] if len(sys.argv) > 5 else "ALFA-style detector (held-out flight) on PX4 simulated flights"
fig, ax = plt.subplots(3, 2, figsize=(11, 7.5), sharex="col")
for j, f in enumerate((fault_f, norm_f)):
    d = probs[probs.flight == f]; fs = d["fault_sec"].iloc[0]
    ax[0, j].plot(d["t"], d["hud_altitude__mean5"], color="#1f4e79"); ax[0, j].set_ylabel("altitude (m, 5 s mean)")
    ax[1, j].plot(d["t"], d["alt_error__mean5"], color="#555"); ax[1, j].set_ylabel("altitude error (m)")
    ax[2, j].plot(d["t"], d["prob"], color="#b03a2e", label="fault probability")
    ax[2, j].axhline(0.5, color="#999", ls=":", lw=1)
    a = d[d["alarm"]]
    if len(a): ax[2, j].axvline(a["t"].iloc[0], color="#b03a2e", ls="-", lw=1.5, label="alarm (3 in a row)")
    ax[2, j].set_ylabel("probability"); ax[2, j].set_xlabel("seconds since steady flight"); ax[2, j].set_ylim(-0.02, 1.02)
    if fs == fs:
        for r in ax[:, j]: r.axvline(fs, color="k", ls="--", lw=1)
        ax[0, j].set_title(f"{f}: engine cut at {fs:.0f} s (dashed)")
    else:
        ax[0, j].set_title(f"{f}: normal flight, no fault")
    ax[2, j].legend(loc="center left", fontsize=8)
for r in ax.flat: r.grid(alpha=.25)
fig.suptitle(title, fontsize=11)
fig.tight_layout(); fig.savefig(out, dpi=140); print("saved", out)
