"""Does a detector trained on one fault type find another one?
Trains on the flights whose names start with the TRAIN prefixes and reports, for every flight that starts with a TEST prefix:
detected or not, delay, and false-alarm seconds before the fault. Same model settings and alarm rule as detect_eval.py.
Example (train on normal + engine cut, test on elevator): python cross_fault.py table.csv n,f e out_prefix
Normal flights in TRAIN are never tested here. To measure false alarms on normal flights use detect_eval.py."""
import sys, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier

K = 3
tab = pd.read_csv(sys.argv[1]); train_p = tuple(sys.argv[2].split(",")); test_p = tuple(sys.argv[3].split(","))
feat = [c for c in tab.columns if "__" in c]
tr = tab[tab.flight.str.startswith(train_p)]; te_all = tab[tab.flight.str.startswith(test_p)]
if tr["label"].nunique() < 2 or te_all.empty:
    sys.exit(f"need both normal and fault seconds in the training flights ({sorted(tr.flight.unique())}) and at least one test flight ({sorted(te_all.flight.unique())})")
m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                           random_state=0, n_jobs=2).fit(tr[feat], tr["label"])
rows, probs = [], []
for f, te in te_all.groupby("flight"):
    te = te.copy(); te["prob"] = m.predict_proba(te[feat])[:, 1]
    te["alarm"] = (te["prob"] >= 0.5).astype(int).rolling(K, min_periods=K).min().fillna(0).astype(bool)
    probs.append(te); fs = te["fault_sec"].iloc[0]
    pre = te[te["label"] == 0]; first = te.loc[te["alarm"], "t"]
    det = first[first + 1 > fs] if fs == fs else first[:0]
    rows.append(dict(flight=f, fault_sec=None if fs != fs else round(fs, 1), detected=bool(len(det)) if fs == fs else None,
                     delay_s=round(float(det.iloc[0] - fs), 1) if len(det) else None,
                     false_alarm_seconds_before_fault=int(pre["alarm"].sum()), seconds_before=len(pre)))
res = pd.DataFrame(rows); print("trained on:", ", ".join(sorted(tr.flight.unique()))); print(res.to_string(index=False))
fl = res[res.fault_sec.notna()]
if len(fl):
    print("\nfault flights detected: %d / %d" % (int(fl.detected.sum()), len(fl))); print("median delay (s):", fl.delay_s.dropna().median())
if len(sys.argv) > 4:
    pd.concat(probs).to_csv(sys.argv[4] + "_probs.csv", index=False); res.to_csv(sys.argv[4] + "_summary.csv", index=False)
