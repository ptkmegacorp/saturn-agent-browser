"""OpenAI-compatible visual specialist (UI-Venus 2) — screenshot + instruction → BrowserAction."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from saturn_fbc.contract import AuthorityContract, BrowserAction
from saturn_fbc.pig_stack import MODEL_ID, openai_base_url, health_json


SYSTEM_PROMPT = """You are the visual specialist for Saturn frontier browser control.

You receive a browser screenshot, a bounded subgoal, and contract constraints.
Respond with exactly ONE JSON object — a BrowserAction — and nothing else.

For clicks on visible elements, prefer pixel coordinates:
{"type":"click","x":640,"y":320}

You may also use indexed actions when an a11y digest is provided.
Allowed action types come from the contract allowed_actions only.
Do not propose submit, send, purchase, or blocked actions.
Never type into password or passphrase fields.
"""


@dataclass
class VisualSpecialistResponse:
    action: BrowserAction | None
    raw: str
    parse_error: str | None = None


def specialist_configured() -> bool:
    health = health_json()
    return "error" not in health


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model response")
    return json.loads(text[start : end + 1])


def _encode_image(path: Path) -> str:
    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    return f"data:image/{mime};base64,{b64}"


def build_user_prompt(
    contract: AuthorityContract,
    *,
    url: str,
    screenshot_path: str,
    a11y_digest: str | None = None,
    last_steps: list[str] | None = None,
) -> list[dict]:
    history = "\n".join((last_steps or [])[-5:]) if last_steps else "(none)"
    digest_block = ""
    if a11y_digest:
        digest_block = f"\n\nAccessibility digest (optional hint):\n{a11y_digest}\n"
    text = f"""Subgoal:
{contract.subgoal}

Allowed actions: {", ".join(contract.allowed_actions)}
Blocked actions: {", ".join(contract.blocked_actions)}
Task data: {json.dumps(contract.task_data)}

Current URL: {url}
Recent steps:
{history}
{digest_block}
Use the screenshot to choose the next single browser action."""
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": _encode_image(Path(screenshot_path))},
        },
    ]


class VisualSpecialistClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str = "llama-server",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or openai_base_url()).rstrip("/")
        self.model = model or MODEL_ID
        self.api_key = api_key
        self.timeout = timeout

    def propose_action(
        self,
        contract: AuthorityContract,
        *,
        url: str,
        screenshot_path: str,
        a11y_digest: str | None = None,
        last_steps: list[str] | None = None,
        temperature: float = 0.1,
    ) -> VisualSpecialistResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        contract,
                        url=url,
                        screenshot_path=screenshot_path,
                        a11y_digest=a11y_digest,
                        last_steps=last_steps,
                    ),
                },
            ],
            "temperature": temperature,
            "max_tokens": 256,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        try:
            parsed = _extract_json(content)
            return VisualSpecialistResponse(
                action=BrowserAction.model_validate(parsed), raw=content
            )
        except Exception as exc:
            return VisualSpecialistResponse(action=None, raw=content, parse_error=str(exc))
