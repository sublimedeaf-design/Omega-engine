from __future__ import annotations
import numpy as np
from scipy.optimize import isotonic_regression

class IsotonicCalibrator:
    def __init__(self):
        self.x_: np.ndarray | None=None
        self.y_: np.ndarray | None=None
    def fit(self, probabilities, outcomes):
        p=np.asarray(probabilities,dtype=float); y=np.asarray(outcomes,dtype=float)
        if len(p)!=len(y) or len(p)<2: raise ValueError("need paired calibration data")
        order=np.argsort(p); x=p[order]; yy=y[order]
        fitted=isotonic_regression(yy, increasing=True).x
        # collapse duplicate x to mean fitted value
        ux=np.unique(x); uy=np.array([fitted[x==v].mean() for v in ux])
        self.x_,self.y_=ux,uy
        return self
    def predict(self, probabilities):
        if self.x_ is None: raise RuntimeError("calibrator not fitted")
        p=np.asarray(probabilities,dtype=float)
        return np.interp(p,self.x_,self.y_,left=self.y_[0],right=self.y_[-1])
