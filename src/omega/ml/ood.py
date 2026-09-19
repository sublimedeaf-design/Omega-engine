from __future__ import annotations
import numpy as np

class MahalanobisOOD:
    def fit(self,X):
        X=np.asarray(X,float); self.mean_=X.mean(0); cov=np.cov(X,rowvar=False)
        cov=np.atleast_2d(cov)+np.eye(X.shape[1])*1e-6; self.inv_=np.linalg.pinv(cov)
        d=self.score_samples(X); self.threshold_=float(np.quantile(d,.99)); return self
    def score_samples(self,X):
        X=np.asarray(X,float); z=X-self.mean_; return np.sqrt(np.einsum('ij,jk,ik->i',z,self.inv_,z))
    def is_ood(self,X): return self.score_samples(X)>self.threshold_

class ErrorPredictor:
    """Predicts absolute forecast error using ridge regression; output is clipped to [0,1]."""
    def __init__(self,l2=1.0): self.l2=l2
    def fit(self,X,p,y):
        X=np.asarray(X,float); target=np.abs(np.asarray(p)-np.asarray(y)); A=np.c_[np.ones(len(X)),X]
        reg=np.eye(A.shape[1])*self.l2; reg[0,0]=0; self.w_=np.linalg.solve(A.T@A+reg,A.T@target); return self
    def predict(self,X):
        A=np.c_[np.ones(len(X)),np.asarray(X,float)]; return np.clip(A@self.w_,0,1)
