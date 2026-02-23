import pytest
from python.analysis.validation import DataValidationError, validate_frames, validate_table


def test_validation_passes_on_sample_data(sample_frames) -> None:
    frames = sample_frames
    report = validate_frames(frames, mode="strict")
    assert not report.empty
    assert "severity" in report.columns


def test_validation_fails_missing_required_column(sample_frames) -> None:
    frames = sample_frames
    broken = frames["orders"].drop(columns=["order_id"])
    with pytest.raises(DataValidationError):
        validate_table("orders", broken, mode="strict")


def test_validation_fails_cross_table_fk(sample_frames) -> None:
    frames = sample_frames
    frames["orders"].loc[0, "customer_id"] = "missing_customer"
    with pytest.raises(DataValidationError):
        validate_frames(frames, mode="strict")


def test_validation_fails_clicks_gt_impressions(sample_frames) -> None:
    frames = sample_frames
    frames["marketing_spend"].loc[0, "clicks"] = 100000
    frames["marketing_spend"].loc[0, "impressions"] = 10
    with pytest.raises(DataValidationError):
        validate_frames(frames, mode="strict")


def test_validation_fails_discount_gt_gross(sample_frames) -> None:
    frames = sample_frames
    frames["orders"].loc[0, "discount"] = frames["orders"].loc[0, "gross_revenue"] + 1
    with pytest.raises(DataValidationError):
        validate_frames(frames, mode="strict")


def test_validation_fails_refund_gt_order_gross(sample_frames) -> None:
    frames = sample_frames
    target_order_id = frames["refunds"].loc[0, "order_id"]
    gross = float(frames["orders"].loc[frames["orders"]["order_id"] == target_order_id, "gross_revenue"].iloc[0])
    frames["refunds"].loc[0, "refund_amount"] = gross + 1
    with pytest.raises(DataValidationError):
        validate_frames(frames, mode="strict")
