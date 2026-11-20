"""Fig22: selective prediction (risk-coverage) on TRAIN, nested cluster CV."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from v5_style import *

A = pd.read_csv(RES / 'selective/selective_summary.csv')
SC = {'LOCAL_ERROR': ('Local error of neighbours', C['train']), 'AD_DISTANCE': ('Distance to TRAIN (AD)', C['purple']),
      'DISAGREEMENT': ('|Ridge − mean|', C['test']), 'RANDOM': ('Random (control)', C['grey'])}


def main():
    fig, ax = plt.subplots(2, 3, figsize=(W, 5.4))
    for row, ep in enumerate(['yield', 'biomass']):
        a = ax[row, 0]
        for s, (lab, col) in SC.items():
            d = A[(A.endpoint == ep) & (A.score == s)].sort_values('retained_frac')
            a.plot(d.retained_frac, d.RMSE_ridge, 'o-', color=col, ms=3, lw=1, label=f'Ridge, {lab}')
            if s == 'LOCAL_ERROR':
                a.plot(d.retained_frac, d.RMSE_mean, 's--', color=col, ms=3, lw=0.8, mfc='white', label='Mean on the same rows')
        a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('RMSE (lnRR)')
        if row == 0:
            a.legend(frameon=False, fontsize=4.9)
        panel(a, 'ad'[row], f'{ep.title()}: error vs share')
        a = ax[row, 1]
        for s, (lab, col) in SC.items():
            d = A[(A.endpoint == ep) & (A.score == s)].sort_values('retained_frac')
            a.plot(d.retained_frac, d.d_ridge_vs_mean, 'o-', color=col, ms=3, lw=1)
            if s == 'LOCAL_ERROR':
                a.fill_between(d.retained_frac, d.d_ridge_vs_mean_ci_lo, d.d_ridge_vs_mean_ci_hi, color=col, alpha=0.15)
                for x, yv, n in zip(d.retained_frac, d.d_ridge_vs_mean, d.retained_studies):
                    a.text(x, yv, f'{n:.0f}', fontsize=4.8, ha='center', va='bottom', color=col)
        a.axhline(0, color='#555', lw=0.6); a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('RMSE Ridge − RMSE mean')
        panel(a, 'be'[row], 'Ridge − mean, same rows')
        a = ax[row, 2]
        for s, (lab, col) in SC.items():
            d = A[(A.endpoint == ep) & (A.score == s)].sort_values('retained_frac')
            a.plot(d.retained_frac, d.coverage_ridge, 'o-', color=col, ms=3, lw=1)
        a.axhline(0.95, color='#555', ls='--', lw=0.6); a.axhline(0.90, color=C['red'], ls=':', lw=0.6)
        a.set_xlabel('Share of contrasts predicted'); a.set_ylabel('95 % interval coverage'); panel(a, 'cf'[row], 'Interval coverage')
    fig.tight_layout()
    save(fig, 'Fig22_selective_prediction', 'Fig. 22. Selective prediction on TRAIN (nested CV by dependency cluster, seeds 11/22/33; TEST not used). Abstention thresholds are '
         'r-quantiles of scores learnt on the outer training fold only (local error = mean |inner out-of-fold Ridge residual| of the 15 nearest training contrasts; '
         'AD = mean distance to the 5 nearest; disagreement = |Ridge − training mean|; random = control). (a, d) RMSE of Ridge on the retained contrasts and of '
         'the mean on the same contrasts. (b, e) Difference Ridge − mean on the retained contrasts, band = 95 % cluster-bootstrap CI (local error), numbers = '
         'retained studies. (c, f) Coverage of the Ridge 95 % interval (constant half-width ≈ 0.86 yield / 0.83 biomass, set on inner OOF residuals).')


if __name__ == '__main__':
    main()
