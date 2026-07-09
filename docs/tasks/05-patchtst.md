# Task 05 — PatchTST forecaster + NWP features

**Status**: ⬜ pending (spec to be written when activated)

## Goal (placeholder)

Add a PatchTST-style transformer forecaster through the existing model
contract (`configs/model/patchtst.yaml` + one module under
`forecast/models/` — the assembler makes this a one-yaml-line plug-in),
compare against the LSTM baseline on identical windows, and evaluate
whether open NWP weather features close the wind gap vs the TSO forecast
(currently −22%). SHAP-based feature attribution for the AI-interview
story. Spec, data source for NWP, and acceptance criteria to be defined
when this task becomes active.
