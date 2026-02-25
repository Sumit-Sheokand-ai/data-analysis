import json
import threading
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pandas as pd
import pytest

from python.webapp.server import WebAppConfig, create_webapp_http_server


def _seed_raw_contract(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"date": "2026-01-01", "channel": "meta", "campaign": "Prospecting", "spend": 1000, "clicks": 200, "impressions": 20000, "sales_cost": 100}
        ]
    ).to_csv(raw_dir / "raw_marketing_spend.csv", index=False)
    pd.DataFrame(
        [
            {
                "session_id": "s1",
                "session_ts": "2026-01-01T10:00:00Z",
                "customer_id": "c1",
                "utm_source": "meta",
                "utm_medium": "paid",
                "utm_campaign": "Prospecting",
                "channel": "meta",
                "is_direct": False,
            }
        ]
    ).to_csv(raw_dir / "raw_sessions.csv", index=False)
    pd.DataFrame([{"customer_id": "c1", "acquired_at": "2026-01-01T11:00:00Z", "acquisition_channel": "meta", "region": "ca"}]).to_csv(
        raw_dir / "raw_customers.csv", index=False
    )
    pd.DataFrame(
        [{"order_id": "o1", "customer_id": "c1", "order_ts": "2026-01-02T12:00:00Z", "gross_revenue": 1200, "discount": 50, "cogs": 400, "status": "completed"}]
    ).to_csv(raw_dir / "raw_orders.csv", index=False)
    pd.DataFrame([{"refund_id": "r1", "order_id": "o1", "refund_amount": 0, "refund_ts": "2026-01-03T12:00:00Z", "status": "processed"}]).to_csv(
        raw_dir / "raw_refunds.csv", index=False
    )


def _seed_processed_outputs(processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"metric": "total_net_revenue", "value": 1150},
            {"metric": "total_contribution_margin", "value": 750},
            {"metric": "avg_cac", "value": 55.25},
            {"metric": "avg_ltv_cac_ratio", "value": 3.1},
        ]
    ).to_csv(processed_dir / "kpi_overview.csv", index=False)
    pd.DataFrame([{"channel": "meta", "spend": 1000, "sales_cost": 100, "total_cost": 1100, "new_customers": 20, "cac": 55}]).to_csv(
        processed_dir / "cac_by_channel.csv", index=False
    )
    pd.DataFrame([{"cohort_month": "2026-01-01", "month_index": 0, "active_customers": 20, "cohort_size": 20, "retention_rate": 1.0}]).to_csv(
        processed_dir / "retention_monthly.csv", index=False
    )
    pd.DataFrame([{"customer_id": "c1", "realized_ltv": 750, "predicted_ltv": 820, "prediction_method": "fallback_proxy", "order_count": 1}]).to_csv(
        processed_dir / "ltv_by_customer.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "channel": "meta",
                "customers": 20,
                "avg_realized_ltv": 750,
                "avg_predicted_ltv": 820,
                "avg_order_count": 1.0,
                "cac": 55,
                "ltv_cac_ratio": 14.9,
                "payback_months_est": 0.7,
            }
        ]
    ).to_csv(processed_dir / "channel_profitability.csv", index=False)
    pd.DataFrame([{"table": "orders", "row_count": 1, "duplicate_rows": 0, "null_cells": 0}]).to_csv(
        processed_dir / "data_quality.csv", index=False
    )
    pd.DataFrame([{"check": "anomaly_monitoring_passed", "severity": "info", "date": "all", "channel": "all", "metric": "n/a", "value": 0, "threshold": 0, "detail": "No anomaly spikes detected."}]).to_csv(
        processed_dir / "anomaly_report.csv", index=False
    )


def _seed_previous_snapshots(processed_dir: Path) -> None:
    previous_dir = processed_dir / "previous"
    previous_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"metric": "total_net_revenue", "value": 1000},
            {"metric": "total_contribution_margin", "value": 700},
            {"metric": "avg_cac", "value": 60.0},
            {"metric": "avg_ltv_cac_ratio", "value": 2.9},
        ]
    ).to_csv(previous_dir / "kpi_overview.csv", index=False)
    pd.DataFrame([{"channel": "meta", "cac": 60}]).to_csv(previous_dir / "cac_by_channel.csv", index=False)
    pd.DataFrame([{"channel": "meta", "ltv_cac_ratio": 12.0}]).to_csv(previous_dir / "channel_profitability.csv", index=False)


def _make_config(tmp_path: Path, *, require_auth: bool) -> WebAppConfig:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _seed_raw_contract(raw_dir)
    _seed_processed_outputs(processed_dir)
    users = (
        {
            "admin": {
                "password": "secret-pass",
                "user_id": "admin",
                "workspace_id": "default",
                "role": "owner",
                "plan_slug": "pro",
            }
        }
        if require_auth
        else {}
    )
    return WebAppConfig(
        app_env="test",
        data_source="csv",
        raw_data_dir=raw_dir,
        processed_data_dir=processed_dir,
        database_url="",
        default_validation_mode="warn",
        allow_proxy_spend=False,
        pipeline_service_url="",
        pipeline_timeout_seconds=10,
        policy_service_url="",
        policy_timeout_seconds=10,
        policy_state_file=tmp_path / "policy_state.json",
        service_token="",
        disable_local_pipeline_fallback=False,
        require_auth=require_auth,
        auth_mode="basic" if require_auth else "disabled",
        default_workspace="default",
        default_role="viewer",
        default_plan="starter",
        workspace_plan_overrides={},
        basic_auth_users=users,
        static_dir=Path(__file__).resolve().parents[1] / "web",
    )


def _start_server(config: WebAppConfig) -> tuple:
    server = create_webapp_http_server(host="127.0.0.1", port=0, config=config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, thread, base_url


def test_webapp_server_serves_index_and_css(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    server, thread, base_url = _start_server(config)
    try:
        with urllib_request.urlopen(f"{base_url}/", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert "Syntellia" in body
        with urllib_request.urlopen(f"{base_url}/styles.css", timeout=5) as response:
            css = response.read().decode("utf-8")
        assert "--bg" in css
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_dashboard_endpoint_returns_core_payload(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    server, thread, base_url = _start_server(config)
    try:
        with urllib_request.urlopen(f"{base_url}/api/dashboard", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        dashboard = payload["dashboard"]
        assert dashboard["readiness"]["status"] == "ready"
        assert dashboard["overview"]["total_net_revenue"] == pytest.approx(1150.0)
        assert len(dashboard["channel_performance"]) >= 1
        assert len(dashboard["retention"]) >= 1
        assert len(dashboard["ltv_customers"]) >= 1
        assert isinstance(dashboard["what_changed"], dict)
        assert isinstance(dashboard["recommendations"], list)
        assert dashboard["optimizer_defaults"]["total_budget"] == pytest.approx(1100.0)
        assert dashboard["optimizer_defaults"]["reserve_pct"] == pytest.approx(10.0)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_dashboard_what_changed_uses_previous_snapshots(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    _seed_previous_snapshots(config.processed_data_dir)
    server, thread, base_url = _start_server(config)
    try:
        with urllib_request.urlopen(f"{base_url}/api/dashboard", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        changed = payload["dashboard"]["what_changed"]
        assert len(changed["overview_deltas"]) >= 1
        assert len(changed["cac_deltas"]) >= 1
        assert len(changed["ltv_cac_deltas"]) >= 1
        first_overview_delta = changed["overview_deltas"][0]
        assert "delta" in first_overview_delta
        assert "delta_pct" in first_overview_delta
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_auth_login_flow_for_protected_mode(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=True)
    server, thread, base_url = _start_server(config)
    try:
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(f"{base_url}/api/dashboard", timeout=5)
        assert exc_info.value.code == 401

        cookie_jar = CookieJar()
        opener = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(cookie_jar))
        login_request = urllib_request.Request(
            url=f"{base_url}/api/auth/login",
            data=json.dumps({"username": "admin", "password": "secret-pass"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login_request, timeout=5) as login_response:
            login_payload = json.loads(login_response.read().decode("utf-8"))
        assert login_payload["authenticated"] is True
        assert login_payload["plan"]["slug"] == "pro"

        with opener.open(f"{base_url}/api/auth/me", timeout=5) as me_response:
            me_payload = json.loads(me_response.read().decode("utf-8"))
        assert me_payload["authenticated"] is True
        assert me_payload["user_id"] == "admin"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_pipeline_run_rejects_invalid_validation_mode(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    server, thread, base_url = _start_server(config)
    try:
        request = urllib_request.Request(
            url=f"{base_url}/api/pipeline/run",
            data=json.dumps({"validation_mode": "invalid-mode"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(request, timeout=5)
        assert exc_info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_optimizer_endpoint_returns_allocations(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    server, thread, base_url = _start_server(config)
    try:
        request = urllib_request.Request(
            url=f"{base_url}/api/optimizer/run",
            data=json.dumps({"total_budget": 10000, "target_max_cac": 80, "reserve_pct": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        optimizer = payload["optimizer"]
        assert payload["status"] == "ok"
        assert optimizer["summary"]["usable_budget"] == pytest.approx(9000.0)
        assert optimizer["summary"]["projected_customers"] > 0
        assert len(optimizer["allocations"]) >= 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_webapp_optimizer_endpoint_validates_reserve_pct(tmp_path: Path) -> None:
    config = _make_config(tmp_path, require_auth=False)
    server, thread, base_url = _start_server(config)
    try:
        request = urllib_request.Request(
            url=f"{base_url}/api/optimizer/run",
            data=json.dumps({"total_budget": 10000, "target_max_cac": 80, "reserve_pct": 99}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib_error.HTTPError) as exc_info:
            urllib_request.urlopen(request, timeout=5)
        assert exc_info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
