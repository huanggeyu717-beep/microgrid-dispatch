# Task 02 — Day-ahead quantile forecasting (LSTM baseline)

**Status**: ✅ done

## Archive summary

Delivered: seq2seq LSTM (encoder: 24h of all three measured series;
decoder: calendar encodings + Elia's own day-ahead forecast) emitting
q=0.1/0.5/0.9 quantiles for a 96-step day-ahead horizon, trained with
pinball loss. Test set (Nov–Dec 2024) MAE: load 260 MW (+49% vs seasonal
persistence, −1.4% vs TSO), wind 225 MW (+79% / −22%), solar 106 MW
(+39% / −11%). Checkpoints are self-contained (state_dict + scaler +
configs) in `models/<target>_lstm/best.pt`.

## Leakage discipline (binding for every future model)

- Chronological splits; a sample belongs to the split containing its
  *horizon*; contexts may reach back across the boundary (past data is not
  leakage), labels never cross.
- Scalers fit on the train slice only, stored inside the checkpoint.
- All engineered features causal; rolling stats use explicit shift(1).
- Guarded by tests in tests/test_forecast.py (exact-shift lag, poisoned-
  value causality check, scaler-fit-on-train). Never weaken these.
- Every model is compared against seasonal persistence AND the TSO
  day-ahead forecast on identical windows, in MW.

Also delivered: time-boxed resumable trainer (last.pt + DONE marker),
originally built for a 45s-per-command sandbox, kept as a feature.
Honest finding: without NWP weather inputs the wind gap vs TSO (−22%) is
expected; NWP features are the named improvement path (task 05).
