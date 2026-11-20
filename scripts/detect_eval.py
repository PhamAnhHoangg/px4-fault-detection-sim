"""Leave-one-flight-out evaluation of the ALFA-style detector on PX4 simulated flights.
Same settings as the ALFA final model: random forest 300 trees, min_samples_leaf=5,
class_weight=balanced_subsample, threshold 0.5, alarm after K=3 raw alarms in a row."""
import sys, numpy as np, pandas as pd, json
from sklearn.ensemble import RandomForestClassifier

K = 3
tab = pd.read_csv(sys.argv[1]); outprefix = sys.argv[2]
feat = [c for c in tab.columns if "__" in c]
flights = sorted(tab["flight"].unique())
rows = []; probs = []
for f in flights:
    tr, te = tab[tab.flight != f], tab[tab.flight == f].copy()
    m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                               random_state=0, n_jobs=2).fit(tr[feat], tr["label"])
    te["prob"] = m.predict_proba(te[feat])[:, 1]
    te["raw"] = (te["prob"] >= 0.5).astype(int)
    te["alarm"] = te["raw"].rolling(K, min_periods=K).min().fillna(0).astype(bool)
    probs.append(te)
    is_fault = te["label"].max() == 1
    first = te.loc[te["alarm"], "t"]
    if is_fault:
        fs = te["fault_sec"].iloc[0]
        pre = te[te["label"] == 0]
        det = first[first + 1 > fs]
        rows.append(dict(flight=f, kind="fault", fault_sec=round(fs, 1),
                         detected=bool(len(det)), delay_s=round(float(det.iloc[0] - fs), 1) if len(det) else None,
                         false_alarm_seconds_before_fault=int(pre["alarm"].sum()), seconds_before=len(pre)))
    else:
        rows.append(dict(flight=f, kind="normal", fault_sec=None, detected=None, delay_s=None,
                         false_alarm_seconds_before_fault=int(te["alarm"].sum()), seconds_before=len(te)))
res = pd.DataFrame(rows); print(res.to_string(index=False))
pd.concat(probs).to_csv(outprefix + "_probs.csv", index=False); res.to_csv(outprefix + "_summary.csv", index=False)
fl = res[res.kind == "fault"]
print("\nfault flights detected: %d / %d" % (int(fl.detected.sum()), len(fl)))
print("median delay (s):", fl.delay_s.dropna().median())
nm = res[res.kind == "normal"]
print("normal flights with any alarm: %d / %d" % (int((nm.false_alarm_seconds_before_fault > 0).sum()), len(nm)))
