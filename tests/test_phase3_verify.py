"""Phase 3: verifier and escalation tests."""

from __future__ import annotations

from saturn_fbc.contract import AuthorityContract, ContractMode, StepRecord
from saturn_fbc.escalate import EscalationPacket, build_packet, write_escalation
from saturn_fbc.verify import VerificationResult, check_success


def _contract(**kwargs) -> AuthorityContract:
    base = dict(
        task_id="v",
        mode=ContractMode.DRAFT,
        subgoal="x",
        origin_allowlist=["httpbin.org"],
        allowed_actions=["type"],
        success_checks=[
            "custname visible value is Saturn Test",
            "Submit was not activated",
        ],
        task_data={"custname": "Saturn Test"},
    )
    base.update(kwargs)
    return AuthorityContract(**base)


class FakeLocator:
    def __init__(self, value: str):
        self._value = value

    def count(self):
        return 1

    @property
    def first(self):
        return self

    def input_value(self, timeout=1000):
        return self._value

    def inner_text(self, timeout=1000):
        return self._value


class FakePage:
    def __init__(self, values: dict[str, str]):
        self.url = "https://httpbin.org/forms/post"
        self._values = values

    def locator(self, sel: str):
        for name, value in self._values.items():
            if name in sel:
                return FakeLocator(value)
        return FakeLocator("")


def test_check_success_passes_when_values_match():
    page = FakePage({"custname": "Saturn Test"})
    result = check_success(_contract(), page)
    assert result.ok


def test_check_success_fails_wrong_value():
    page = FakePage({"custname": "Wrong"})
    result = check_success(_contract(), page)
    assert not result.ok
    assert result.failed_checks


def test_build_escalation_packet(tmp_path):
    contract = _contract()
    packet = build_packet(
        contract,
        url="https://httpbin.org/forms/post",
        failed_checks=["custname mismatch"],
        steps=[StepRecord(step=1, result="typed")],
        a11y_snippet="[1] textbox",
        screenshot_path="/tmp/x.png",
        message="verify failed",
    )
    path = write_escalation(tmp_path, packet)
    assert path.is_file()
    assert isinstance(packet, EscalationPacket)
    assert "custname mismatch" in packet.to_prompt()
