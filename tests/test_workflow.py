from __future__ import annotations

from pathlib import Path


def test_monthly_report_workflow_contains_feishu_and_artifact_steps():
    workflow_text = Path(".github/workflows/monthly_report.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow_text
    assert "base_monthly_rmb:" in workflow_text
    assert "review_months:" in workflow_text
    assert "current_total_portfolio_value_rmb:" in workflow_text
    assert "current_gldm_shares:" in workflow_text
    assert "schedule:" in workflow_text
    assert "FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}" in workflow_text
    assert "FEISHU_KEYWORD: ${{ secrets.FEISHU_KEYWORD }}" in workflow_text
    assert "检测运行模式" in workflow_text
    assert "simulation_mode=true" in workflow_text
    assert "--base-monthly-rmb" in workflow_text
    assert "--review-months" in workflow_text
    assert "--current-total-portfolio-value-rmb" in workflow_text
    assert "--current-gldm-shares" in workflow_text
    assert "上传产物" in workflow_text
    assert "if: always()" in workflow_text
    assert "发送工作流失败告警" in workflow_text
    assert "if: failure() && steps.run_monthly_report.outcome == 'success'" in workflow_text
    assert "if: success() && steps.run_mode.outputs.simulation_mode != 'true'" in workflow_text
    assert "git add state/reserve_state.json reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-report.md" in workflow_text
