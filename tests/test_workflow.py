from __future__ import annotations

from pathlib import Path


def test_monthly_report_workflow_contains_feishu_and_artifact_steps():
    workflow_text = Path(".github/workflows/monthly_report.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow_text
    assert "schedule:" in workflow_text
    assert "FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}" in workflow_text
    assert "FEISHU_KEYWORD: ${{ secrets.FEISHU_KEYWORD }}" in workflow_text
    assert "Upload artifacts" in workflow_text
    assert "if: always()" in workflow_text
    assert "Send workflow failure alert" in workflow_text
    assert "if: failure() && steps.run_monthly_report.outcome == 'success'" in workflow_text
    assert "git add state/reserve_state.json reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-report.md" in workflow_text
