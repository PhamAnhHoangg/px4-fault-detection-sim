"""Train the detector on ALL flights of a feature table and save it for the live script.
Same settings as detect_eval.py (random forest 300 trees, min_samples_leaf=5, balanced_subsample, seed 0).
Note: a model trained on all flights has seen every flight, so its score on those flights means nothing.
The honest numbers are the leave-one-flight-out ones from detect_eval.py.
Usage: python train_model.py table.csv model.joblib"""
import sys, joblib, pandas as pd
from sklearn.ensemble import RandomForestClassifier

tab = pd.read_csv(sys.argv[1])
feat = [c for c in tab.columns if "__" in c]
m = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                           random_state=0, n_jobs=2).fit(tab[feat], tab["label"])
joblib.dump({"model": m, "features": feat, "trained_on": sorted(tab["flight"].unique())}, sys.argv[2])
print("saved", sys.argv[2], "| flights:", ", ".join(sorted(tab["flight"].unique())), "| features:", len(feat))
