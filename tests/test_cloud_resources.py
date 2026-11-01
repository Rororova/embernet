import pytest

from embernet.cloud_resources import credit_reserve, rendering_resources, require_free_credits


def test_render_profiles_preserve_bounded_free_credit_spend():
    assert rendering_resources("RTX-PRO-6000")["memory"] == 65536
    assert credit_reserve("RTX-PRO-6000", 600) >= 1.5
    require_free_credits({"billed_cost": "0", "adjustments": {"credits": "-21.22"}}, 1.5)
    with pytest.raises(RuntimeError):
        require_free_credits({"billed_cost": "0", "adjustments": {"credits": "-29"}}, 1.5)
    with pytest.raises(RuntimeError):
        require_free_credits({"billed_cost": "1", "adjustments": {"credits": "-1"}}, 1.5)
    with pytest.raises(ValueError):
        require_free_credits({"billed_cost": "nan", "adjustments": {"credits": "-1"}}, 1.5)
    with pytest.raises(ValueError):
        rendering_resources("H100")
