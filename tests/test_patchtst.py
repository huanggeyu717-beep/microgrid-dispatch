"""PatchTST model tests (task 05 phase 3).

The [B, H, Q] output-shape contract is also enforced by the parametrised
test_model_contract_output_shape in tests/test_forecast.py, which picks up
configs/model/patchtst.yaml automatically; the tests here cover what that one
cannot: fusion-width agnosticism, the revin flag actually doing something,
zero-variance stability, the patching compatibility error, and the parameter
budget.
"""

from pathlib import Path

import pytest
import torch
from omegaconf import OmegaConf

from microgrid.assemble import build_model

PATCHTST_YAML = Path(__file__).resolve().parents[1] / "configs" / "model" / "patchtst.yaml"


def _model(n_hist=3, n_fut=7, n_quantiles=3, horizon=96, **overrides):
    mcfg = OmegaConf.load(PATCHTST_YAML)
    for k, v in overrides.items():
        mcfg[k] = v
    return build_model(
        mcfg, n_hist=n_hist, n_fut=n_fut, n_quantiles=n_quantiles, horizon=horizon
    )


@pytest.mark.parametrize("n_fut", [7, 11])  # standalone (7 calendar) and +NWP widths
def test_output_shape_for_both_future_widths(n_fut):
    """The fusion layer must be width-agnostic: the same architecture serves
    the standalone configuration (7 calendar columns) and a later NWP one."""
    torch.manual_seed(0)
    model = _model(n_fut=n_fut)
    out = model(torch.randn(4, 96, 3), torch.randn(4, 96, n_fut))
    assert out.shape == (4, 96, 3)


def test_eval_quantiles_do_not_cross():
    torch.manual_seed(0)
    model = _model().eval()
    out = model(torch.randn(4, 96, 3), torch.randn(4, 96, 7))
    assert (out[..., 1:] >= out[..., :-1]).all()


def test_revin_flag_changes_the_output():
    """revin adds no parameters, so the same state_dict loads into both
    variants — a flag that silently does nothing would produce identical
    outputs here."""
    torch.manual_seed(0)
    off = _model(revin=False).eval()
    on = _model(revin=True).eval()
    on.load_state_dict(off.state_dict())
    x_hist = torch.randn(4, 96, 3) * 3.0 + 5.0  # non-zero per-window mean/std
    x_fut = torch.randn(4, 96, 7)
    out_off, out_on = off(x_hist, x_fut), on(x_hist, x_fut)
    assert out_off.shape == out_on.shape == (4, 96, 3)
    assert not torch.allclose(out_off, out_on)


def test_revin_constant_channel_stays_finite():
    """A zero-standard-deviation history channel divides by (0 + eps); the
    output must contain no NaN or inf."""
    torch.manual_seed(0)
    model = _model(revin=True).eval()
    x_hist = torch.randn(4, 96, 3)
    x_hist[..., 0] = 2.5  # exactly constant channel
    out = model(x_hist, torch.randn(4, 96, 7))
    assert torch.isfinite(out).all()


def test_incompatible_context_length_raises_naming_the_keys():
    """(C - patch_len) % patch_stride != 0 would make unfold silently drop the
    tail of the context; it must raise instead, naming all three config keys."""
    torch.manual_seed(0)
    model = _model()
    with pytest.raises(ValueError) as e:
        model(torch.randn(2, 30, 3), torch.randn(2, 96, 7))  # (30-16) % 8 != 0
    msg = str(e.value)
    for key in ("forecast.context_steps", "model.patch_len", "model.patch_stride"):
        assert key in msg


def test_parameter_count_within_budget():
    """Guards against an accidental all-channel flatten head, which alone
    would be several million parameters."""
    model = _model(n_hist=3, n_fut=7, n_quantiles=3, horizon=96)
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params < 1_000_000, f"{n_params} parameters — head likely flattens channels"
