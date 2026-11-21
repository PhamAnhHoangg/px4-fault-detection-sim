"""Simple rules against the random forest, on the same table and with the same alarm rule (3 raw alarms in a row).

Each rule watches one feature (or two, joined by OR). Its threshold is learned leave-one-flight-out: the largest
absolute value the feature reached in the normal seconds of all OTHER flights (normal flights and the part of fault
flights before the fault), times a margin. So the rule is tuned to give no false alarms on what it has seen, the same
information the forest gets.

  python scripts/baseline_eval.py results/sih/table_sih_18.csv [--margin 1.2]
"""
import argparse, sys
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier

K = 3
RULES = {
    "altitude error (5 s mean)": ["alt_error__mean5"],
    "climb rate (5 s mean)": ["vel_lin_z__mean5"],
    "altitude change over 10 s": ["hud_altitude__delta10"],
    "pitch tracking spread (5 s std)": ["pitch_gap__std5"],
    "altitude error OR pitch spread": ["alt_error__mean5", "pitch_gap__std5"],
}


def alarms(raw):
    return pd.Series(raw).rolling(K, min_periods=K).min().fillna(0).astype(bool).to_numpy()


def score(te, alarm):
    fs = te["fault_sec"].iloc[0]
    if fs != fs:  # normal flight
        return dict(kind="normal", detected=None, delay=None, false_s=int(alarm.sum()))
    t = te["t"].to_numpy(); pre = te["label"].to_numpy() == 0
    hit = np.flatnonzero(alarm & (t + 1 > fs))
    return dict(kind="fault", detected=bool(len(hit)), delay=round(float(t[hit[0]] - fs), 1) if len(hit) else None,
                false_s=int((alarm & pre).sum()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("table"); ap.add_argument("--margin", type=float, default=1.2)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    tab = pd.read_csv(a.table); feat = [c for c in tab.columns if "__" in c]
    flights = sorted(tab.flight.unique())
    res = []
    for f in flights:
        tr, te = tab[tab.flight != f], tab[tab.flight == f]
        m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                                   random_state=0, n_jobs=2).fit(tr[feat], tr["label"])
        res.append(dict(flight=f, method="random forest", **score(te, alarms(m.predict_proba(te[feat])[:, 1] >= 0.5))))
        normal = tr[tr["label"] == 0]
        for name, cols in RULES.items():
            raw = np.zeros(len(te), bool)
            for c in cols:
                thr = normal[c].abs().max() * a.margin
                raw |= te[c].abs().to_numpy() > thr
            res.append(dict(flight=f, method=name, **score(te, alarms(raw))))
    r = pd.DataFrame(res)
    rows = []
    for meth, g in r.groupby("method", sort=False):
        fl, nm = g[g.kind == "fault"], g[g.kind == "normal"]
        rows.append({"method": meth, "faults detected": f"{int(fl.detected.sum())}/{len(fl)}",
                     "median delay s": fl.delay.dropna().median(),
                     "normal flights with an alarm": f"{int((nm.false_s > 0).sum())}/{len(nm)}",
                     "alarm seconds before a fault": int(fl.false_s.sum())})
    s = pd.DataFrame(rows); print(s.to_string(index=False))
    if a.out:
        s.to_csv(a.out, index=False); r.to_csv(a.out.replace(".csv", "_per_flight.csv"), index=False)


if __name__ == "__main__":
    main()
