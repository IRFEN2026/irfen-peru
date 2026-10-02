#!/usr/bin/env python3
"""Research-only utilities for IRFEN Independent Basin Validation."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

FORBIDDEN = {"EVENT", "NONE"}
RESEARCH_STATES = {"REMOTE_EVENT_CANDIDATE","REMOTE_NONE_CANDIDATE","INSUFFICIENT_EVIDENCE","CONFLICTING_EVIDENCE"}

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def assert_guards(contract):
    assert contract["status"] == "RESEARCH_ONLY"
    assert contract["test_only"] is True
    assert contract["production_use"] is False
    assert contract["production_ready"] is False
    assert contract["operational_alerting_enabled"] is False
    assert contract["relationship_to_v08"]["counts_toward_closeout"] is False

def validate_catalog(catalog):
    for r in catalog["records"]:
        state = r["research_state"]
        assert state in RESEARCH_STATES and state not in FORBIDDEN
        assert r.get("training_target") is None, "Target-basin records are not auto-labelled."
    return True

def fit_logistic(X, y, l2=1.0, steps=4000, lr=0.05):
    X=np.asarray(X,float); y=np.asarray(y,float)
    mu=X.mean(axis=0); sd=X.std(axis=0); sd=np.where(sd==0,1.0,sd)
    Z=(X-mu)/sd
    A=np.column_stack([np.ones(len(Z)),Z])
    w=np.zeros(A.shape[1])
    for _ in range(steps):
        p=1/(1+np.exp(-np.clip(A@w,-30,30)))
        grad=A.T@(p-y)/len(y)
        grad[1:]+=l2*w[1:]/len(y)
        w-=lr*grad
    return {"mean":mu.tolist(),"sd":sd.tolist(),"weights":w.tolist(),"l2":l2}

def predict(model, X):
    X=np.asarray(X,float)
    mu=np.asarray(model["mean"]); sd=np.asarray(model["sd"]); w=np.asarray(model["weights"])
    A=np.column_stack([np.ones(len(X)),(X-mu)/sd])
    return 1/(1+np.exp(-np.clip(A@w,-30,30)))

def roc_auc(y,p):
    y=np.asarray(y,int); p=np.asarray(p,float)
    pos=np.where(y==1)[0]; neg=np.where(y==0)[0]
    if not len(pos) or not len(neg): return None
    wins=ties=0
    for i in pos:
        for j in neg:
            wins += p[i] > p[j]
            ties += p[i] == p[j]
    return (wins+0.5*ties)/(len(pos)*len(neg))

def pr_auc(y,p):
    y=np.asarray(y,int); p=np.asarray(p,float)
    if y.sum()==0: return None
    order=np.argsort(-p); yy=y[order]
    tp=np.cumsum(yy); fp=np.cumsum(1-yy)
    precision=tp/(tp+fp); recall=tp/y.sum()
    r=np.r_[0,recall]; q=np.r_[1,precision]
    return float(np.sum((r[1:]-r[:-1])*q[1:]))

def metrics(y,p,threshold=0.5):
    y=np.asarray(y,int); p=np.asarray(p,float); pred=(p>=threshold).astype(int)
    tp=int(((pred==1)&(y==1)).sum()); tn=int(((pred==0)&(y==0)).sum())
    fp=int(((pred==1)&(y==0)).sum()); fn=int(((pred==0)&(y==1)).sum())
    div=lambda a,b: None if b==0 else a/b
    return {"n":len(y),"positives":int(y.sum()),"negatives":int((1-y).sum()),
      "roc_auc":roc_auc(y,p),"pr_auc":pr_auc(y,p),"brier":float(np.mean((p-y)**2)),
      "sensitivity_recall":div(tp,tp+fn),"specificity":div(tn,tn+fp),
      "precision":div(tp,tp+fp),"false_negatives":fn,"false_positives":fp}

def leave_one_out(samples, feature_names):
    X=np.array([[s[k] for k in feature_names] for s in samples],float)
    y=np.array([s["research_target"] for s in samples],int)
    probs=[]
    for i in range(len(samples)):
        keep=[j for j in range(len(samples)) if j!=i]
        m=fit_logistic(X[keep],y[keep])
        probs.append(float(predict(m,X[[i]])[0]))
    return probs, metrics(y,probs)
