"""Authority contract and step record schemas."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ContractMode(str, Enum):
    READ_ONLY = "read-only"
    DRAFT = "draft"


class StopReason(str, Enum):
    SUCCESS = "success"
    MAX_STEPS = "max_steps"
    DOMAIN_CHANGE = "domain_change"
    CAPTCHA = "captcha"
    ESCALATE = "escalate"
    POLICY_VIOLATION = "policy_violation"
    CREDENTIAL_REQUIRED = "credential_required"
    USER_ABORT = "user_abort"
    PRE_SUBMIT_BOUNDARY = "pre_submit_boundary"


class CredentialSpec(BaseModel):
    """Signup/login credential metadata for the broker (secrets stay in KeePass)."""

    domain: str | None = None
    username: str
    label: str
    handle: str | None = None


class BrowserAction(BaseModel):
    """Structured Playwright action proposed by the visual specialist or a script."""

    type: str
    index: int | None = None
    x: int | None = None
    y: int | None = None
    selector: str | None = None
    url: str | None = None
    text: str | None = None
    value: str | None = None
    direction: Literal["up", "down"] | None = None
    amount: int | None = None

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower()


class AuthorityContract(BaseModel):
    task_id: str
    run_id: str | None = None
    mode: ContractMode
    subgoal: str
    origin_allowlist: list[str]
    allowed_actions: list[str]
    blocked_actions: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=18, ge=1)
    credential_policy: str = "request_only"
    credential_spec: CredentialSpec | None = None
    start_url: str | None = None
    task_data: dict[str, Any] = Field(default_factory=dict)
    success_checks: list[str] = Field(default_factory=list)

    @field_validator("allowed_actions", "blocked_actions", mode="before")
    @classmethod
    def normalize_action_lists(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value]

    @field_validator("origin_allowlist", mode="before")
    @classmethod
    def normalize_allowlist(cls, value: list[str]) -> list[str]:
        return [item.strip().lower() for item in value]


class StepRecord(BaseModel):
    step: int
    action: BrowserAction | None = None
    observation_mode: str | None = None
    url: str | None = None
    title: str | None = None
    screenshot_path: str | None = None
    a11y_digest: str | None = None
    result: str | None = None
    error: str | None = None
    stop_reason: StopReason | None = None


def load_contract(path: str | Path) -> AuthorityContract:
    """Validate and load an authority contract from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AuthorityContract.model_validate(data)


def contract_to_json(contract: AuthorityContract) -> str:
    return contract.model_dump_json(indent=2)
