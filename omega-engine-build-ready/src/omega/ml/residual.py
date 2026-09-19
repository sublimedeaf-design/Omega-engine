from __future__ import annotations
import numpy as np
from scipy.optimize import minimize

class ResidualLogit:
    """Regularized logistic residual learner with market logit as an explicit offset feature."""
    def __init__(self,l2:float=1.0): self.l2=l2; self.coef_=None
    def fit(self,X,y):
        X=np.asarray(X,float); y=np.asarray(y,float); X=np.c_[np.ones(len(X)),X]
        def loss(w):
            z=np.clip(X@w,-30,30); p=1/(1+np.exp(-z))
            nll=-np.sum(y*np.log(p+1e-12)+(1-y)*np.log(1-p+1e-12))
            return nll+self.l2*np.sum(w[1:]**2)
        self.coef_=minimize(loss,np.zeros(X.shape[1]),method='L-BFGS-B').x; return self
    def predict_proba(self,X):
        if self.coef_ is None: raise RuntimeError('not fitted')
        X=np.asarray(X,float); X=np.c_[np.ones(len(X)),X]; z=np.clip(X@self.coef_,-30,30)
        return 1/(1+np.exp(-z))
