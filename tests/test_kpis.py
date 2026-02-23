from python.analysis.kpis import run_all_kpis


def test_kpi_outputs_exist(sample_frames) -> None:
    frames = sample_frames
    outputs = run_all_kpis(frames)

    required = {
        "cac_by_channel",
        "retention_monthly",
        "ltv_by_customer",
        "channel_profitability",
        "kpi_overview",
        "data_quality",
    }
    assert required.issubset(set(outputs.keys()))


def test_cac_computation_positive_for_known_channels(sample_frames) -> None:
    frames = sample_frames
    outputs = run_all_kpis(frames)
    cac = outputs["cac_by_channel"]
    meta = cac[cac["channel"] == "Meta"]
    assert not meta.empty
    assert float(meta["cac"].iloc[0]) > 0


def test_retention_has_cohort_zero(sample_frames) -> None:
    frames = sample_frames
    outputs = run_all_kpis(frames)
    retention = outputs["retention_monthly"]
    assert (retention["month_index"] == 0).any()
