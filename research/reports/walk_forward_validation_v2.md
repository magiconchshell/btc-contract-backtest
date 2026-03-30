# Walk-Forward Validation v2

- folds: 8
- avg test return: 0.05%
- avg test drawdown: -0.62%
- profitable test folds: 2/8
- overfit warning: True
- strategy selection counts: {'long_only_regime': 3, 'regime_filtered': 5}

| fold | strategy | test return | test dd | test win rate | trades |
|---|---|---:|---:|---:|---:|
| 1 | long_only_regime | 2.23% | -0.82% | 100.00% | 2 |
| 2 | regime_filtered | -0.15% | -0.15% | 0.00% | 0 |
| 3 | long_only_regime | 0.00% | 0.00% | 0.00% | 0 |
| 4 | regime_filtered | -1.07% | -1.65% | 0.00% | 2 |
| 5 | long_only_regime | 0.00% | 0.00% | 0.00% | 0 |
| 6 | regime_filtered | 0.29% | -1.27% | 66.67% | 3 |
| 7 | regime_filtered | -0.90% | -1.03% | 0.00% | 2 |
| 8 | regime_filtered | 0.00% | 0.00% | 0.00% | 0 |