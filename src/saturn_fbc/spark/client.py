"""OpenAI-compatible Spark client for structured BrowserAction JSON."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from saturn_fbc.contract import AuthorityContract, BrowserAction
from saturn_fbc.pig_stack import MODEL_ID, openai_base_url


SYSTEM_PROMPT = """You are Spark, the inner browser loop for Saturn frontier browser control.

You receive a bounded subgoal, authority contract constraints, and a numbered accessibility page digest.
Respond with exactly ONE JSON object — a BrowserAction — and nothing else.

Allowed action types come from the contract allowed_actions only.
Use index for a11y_indexed mode (preferred). Do not propose submit, send, purchase, or blocked actions.

Example:
{"type":"type","index":3,"text":"example@invalid.test"}
"""


@dataclass
class SparkResponse:
    action: BrowserAction | None
    raw: str
    parse_error: str | None = None


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


def build_user_prompt(
    contract: AuthorityContract,
    *,
    digest: str,
    url: str,
    last_steps: list[str],
    remaining_fields: dict[str, str] | None = None,
) -> str:
    history = "\n".join(last_steps[-5:]) if last_steps else "(none)"
    remaining = ""
    if remaining_fields:
        remaining = "Still need values in: " + ", ".join(
            f"{k}={v!r}" for k, v in remaining_fields.items()
        )
    return f"""Subgoal:
{contract.subgoal}

Allowed actions: {", ".join(contract.allowed_actions)}
Blocked actions: {", ".join(contract.blocked_actions)}
Max steps: {contract.max_steps}
Task data: {json.dumps(contract.task_data)}
{remaining}

Current URL: {url}

Page digest:
{digest}

Recent steps:
{history}

Task data keys map to form field names. Fill unfilled task_data values only.
Prefer typing into textbox nodes whose labels match task_data keys (custname, custtel, custemail, comments, name, email, phone).
Do not click Submit. When all task_data fields appear filled, return a harmless scroll action.
"""


class SparkClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str = "llama-server",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or openai_base_url()).rstrip("/")
        self.model = model or MODEL_ID
        self.api_key = api_key
        self.timeout = timeout

    def propose_action(
        self,
        contract: AuthorityContract,
        *,
        digest: str,
        url: str,
        last_steps: list[str],
        remaining_fields: dict[str, str] | None = None,
        temperature: float = 0.1,
    ) -> SparkResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        contract,
                        digest=digest,
                        url=url,
                        last_steps=last_steps,
                        remaining_fields=remaining_fields,
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
            return SparkResponse(action=BrowserAction.model_validate(parsed), raw=content)
        except Exception as exc:
            return SparkResponse(action=None, raw=content, parse_error=str(exc))
