from __future__ import annotations

from ai_local_video_mixer.information_flow_copy import scan_copy_compliance


def test_absolute_and_income_claims_are_flagged() -> None:
    findings = scan_copy_compliance("保证百分之百有效，轻松日入一千")
    codes = {item.code for item in findings}
    assert "absolute_guarantee" in codes
    assert "income_claim" in codes
    assert any(item.level == "high" for item in findings)


def test_compliant_hook_is_not_flagged() -> None:
    findings = scan_copy_compliance("做信息流投放的人，先检查素材前三秒有没有给结果")
    assert findings == []


def test_fake_system_message_is_high_risk() -> None:
    findings = scan_copy_compliance("系统警告：你的账户异常，立即点击领取")
    codes = {item.code for item in findings}
    assert "fake_system_message" in codes
    assert "forced_click" in codes
