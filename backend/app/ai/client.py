"""LLM clients behind one small interface (AI-01, 07 §2, §8, §9).

* :class:`LlmClient` — ``create(LlmRequest) -> LlmResponse``. Items in ``LlmRequest.input``
  use the Responses API shapes (``{"role": "user", "content": …}``,
  ``{"type": "function_call", …}``, ``{"type": "function_call_output", …}``) so the OpenAI
  client passes them through unchanged.
* :class:`FakeClient` — scripted steps for tests / offline eval (no network).
* :class:`OpenAIClient` — ``openai`` SDK, Responses API + strict function calling; model
  names come from ``OPENAI_MODEL_REASONING / FAST / EMBED`` (never hard-coded, 01 §6).
  **Not exercised against the real API yet** (no key): see docs/quyet-dinh/M4-ai.md.
* :class:`RecordReplayClient` — ``AI_MODE=record|replay`` (07 §9): record writes every LLM
  step of a turn to ``backend/eval/ai_recordings/<flow>/<key>.json``; replay serves them
  back by key (question + data fingerprint + prompt version) and marks them ``replayed``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import AiUnavailable
from app.core.timeutil import utcnow

ModelTask = Literal["reasoning", "fast", "embed"]
RECORDINGS_DIR = BACKEND_DIR / "eval" / "ai_recordings"
_CALL_SEQ = itertools.count(1)


def model_for(task: ModelTask, settings: Settings) -> str:
    """07 §8: model per task from env. Missing → ``AiUnavailable`` (no hard-coded name)."""
    name = {
        "reasoning": settings.openai_model_reasoning,
        "fast": settings.openai_model_fast or settings.openai_model_reasoning,
        "embed": settings.openai_model_embed,
    }[task]
    if not name:
        env = {"reasoning": "OPENAI_MODEL_REASONING", "fast": "OPENAI_MODEL_FAST"}.get(
            task, "OPENAI_MODEL_EMBED"
        )
        raise AiUnavailable(f"Chưa cấu hình {env}.", task=task)
    return name


# ---------------------------------------------------------------------- data shapes
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class LlmRequest:
    model: str
    instructions: str
    input: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    temperature: float | None = 0.2
    text_format: dict[str, Any] | None = None  # structured output json_schema
    max_output_tokens: int | None = 1500
    flow: str = "chat"


@dataclass
class LlmResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    # items to append to ``input`` for the next step (reasoning + function_call items for
    # the Responses API; ``None`` → the agent builds them from ``tool_calls``/``text``)
    output_items: list[dict[str, Any]] | None = None
    replayed: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tool_calls": [c.__dict__ for c in self.tool_calls],
            "usage": self.usage.__dict__,
            "model": self.model,
            "output_items": self.output_items,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> LlmResponse:
        return cls(
            text=d.get("text"),
            tool_calls=[ToolCall(**c) for c in d.get("tool_calls", [])],
            usage=Usage(**d.get("usage", {})),
            model=d.get("model", ""),
            output_items=d.get("output_items"),
        )


def user_item(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def assistant_item(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


def developer_item(text: str) -> dict[str, Any]:
    return {"role": "developer", "content": text}


def call_item(call: ToolCall) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": call.id,
        "name": call.name,
        "arguments": call.arguments,
    }


def output_item(call_id: str, output: str) -> dict[str, Any]:
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def json_schema_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """``text.format`` for strict structured outputs (Responses API)."""
    return {"type": "json_schema", "name": name, "schema": schema, "strict": True}


# ---------------------------------------------------------------------- clients
class LlmClient(ABC):
    name = "abstract"

    @abstractmethod
    def create(self, req: LlmRequest) -> LlmResponse: ...

    def start_turn(self, key: str, meta: dict[str, Any]) -> None:  # noqa: B027
        """Called by the agent before the first step of a turn (record/replay key)."""

    def finish_turn(self, ok: bool) -> None:  # noqa: B027
        """Called after the last step of a turn."""


Step = LlmResponse | Callable[[LlmRequest], LlmResponse]


class FakeClient(LlmClient):
    """Scripted client. Each step is an ``LlmResponse`` or a function of the request (so a
    test can answer with numbers read from the real tool outputs)."""

    name = "fake"

    def __init__(self, steps: Sequence[Step] = (), *, default_text: str | None = None) -> None:
        self.steps: list[Step] = list(steps)
        self.requests: list[LlmRequest] = []
        self.default_text = default_text

    def create(self, req: LlmRequest) -> LlmResponse:
        self.requests.append(req)
        if not self.steps:
            if self.default_text is None:
                raise AiUnavailable("FakeClient hết kịch bản.")
            return LlmResponse(text=self.default_text, model="fake")
        step = self.steps.pop(0)
        resp = step(req) if callable(step) else step
        if not resp.model:
            resp.model = "fake"
        if resp.usage.total == 0:
            size = len(json.dumps(req.input, ensure_ascii=False, default=str)) + len(
                req.instructions
            )
            resp.usage = Usage(size // 4, len(resp.text or "") // 4 + 20 * len(resp.tool_calls))
        return resp

    # helpers -----------------------------------------------------------
    @staticmethod
    def call(
        name: str, args: dict[str, Any] | None = None, call_id: str | None = None
    ) -> LlmResponse:
        cid = call_id or f"call_{name}_{next(_CALL_SEQ)}"
        return LlmResponse(tool_calls=[ToolCall(cid, name, json.dumps(args or {}))])

    @staticmethod
    def calls(*items: tuple[str, dict[str, Any]]) -> LlmResponse:
        return LlmResponse(
            tool_calls=[
                ToolCall(f"call_{i}_{n}", n, json.dumps(a, ensure_ascii=False))
                for i, (n, a) in enumerate(items)
            ]
        )

    @staticmethod
    def say(text: str) -> LlmResponse:
        return LlmResponse(text=text)


def tool_outputs(req: LlmRequest) -> dict[str, dict[str, Any]]:
    """``{tool name: parsed output}`` of the function calls in a request (last wins); for
    FakeClient steps that write answers from the real tool results."""
    names = {i["call_id"]: i["name"] for i in req.input if i.get("type") == "function_call"}
    out: dict[str, dict[str, Any]] = {}
    for i in req.input:
        if i.get("type") == "function_call_output":
            try:
                out[names.get(i["call_id"], i["call_id"])] = json.loads(i["output"])
            except (ValueError, KeyError):
                continue
    return out


def all_tool_outputs(req: LlmRequest) -> list[tuple[str, dict[str, Any]]]:
    names = {i["call_id"]: i["name"] for i in req.input if i.get("type") == "function_call"}
    out = []
    for i in req.input:
        if i.get("type") == "function_call_output":
            try:
                out.append((names.get(i["call_id"], ""), json.loads(i["output"])))
            except (ValueError, KeyError):
                continue
    return out


class OpenAIClient(LlmClient):
    """Responses API + function calling (``openai`` ≥ 1.40). Not run in CI (no key)."""

    name = "openai"

    def __init__(self, settings: Settings, *, timeout: float = 60.0) -> None:
        if not settings.openai_api_key:
            raise AiUnavailable("Chưa có OPENAI_API_KEY.")
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key, timeout=timeout, max_retries=2)

    def create(self, req: LlmRequest) -> LlmResponse:
        import openai

        kwargs: dict[str, Any] = {
            "model": req.model,
            "instructions": req.instructions,
            "input": req.input,
        }
        if req.tools:
            kwargs["tools"] = req.tools
            kwargs["parallel_tool_calls"] = True
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        if req.text_format is not None:
            kwargs["text"] = {"format": req.text_format}
        if req.max_output_tokens:
            kwargs["max_output_tokens"] = req.max_output_tokens
        try:
            resp = self._client.responses.create(**kwargs)
        except openai.BadRequestError as e:
            # reasoning models reject ``temperature``: retry once without it
            if "temperature" in str(e) and "temperature" in kwargs:
                kwargs.pop("temperature")
                resp = self._client.responses.create(**kwargs)
            else:
                raise AiUnavailable(f"OpenAI từ chối yêu cầu: {e}") from e
        except openai.OpenAIError as e:
            raise AiUnavailable(f"Không gọi được OpenAI: {type(e).__name__}") from e
        calls: list[ToolCall] = []
        texts: list[str] = []
        items: list[dict[str, Any]] = []
        for item in resp.output:
            d = item.model_dump(exclude_none=True)
            items.append(d)
            if item.type == "function_call":
                calls.append(ToolCall(d["call_id"], d["name"], d.get("arguments") or "{}"))
            elif item.type == "message":
                for c in d.get("content", []):
                    if c.get("type") == "output_text":
                        texts.append(c.get("text", ""))
        u = resp.usage
        usage = Usage(
            int(getattr(u, "input_tokens", 0) or 0), int(getattr(u, "output_tokens", 0) or 0)
        )
        return LlmResponse(
            text="".join(texts) if texts else None,
            tool_calls=calls,
            usage=usage,
            model=str(resp.model),
            output_items=items,
        )


# ---------------------------------------------------------------------- record / replay
class ReplayMiss(AiUnavailable):
    default_message = "Trợ lý đang ngoại tuyến (chưa có bản ghi cho câu hỏi này)."


def recording_key(flow: str, question: str, data_fp: str, prompt_version: str) -> str:
    raw = json.dumps([flow, normalize_question(question), data_fp, prompt_version])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_question(q: str) -> str:
    return " ".join(q.lower().split()).rstrip(" ?.!")


class RecordReplayClient(LlmClient):
    """``record``: wraps a live client and saves each turn; ``replay``: serves saved turns."""

    def __init__(
        self,
        mode: Literal["record", "replay"],
        inner: LlmClient | None,
        root: Path = RECORDINGS_DIR,
    ) -> None:
        if mode == "record" and inner is None:
            raise ValueError("record mode needs a live client")
        self.mode = mode
        self.inner = inner
        self.root = root
        self.name = f"{mode}:{inner.name if inner else 'none'}"
        self._key: str | None = None
        self._meta: dict[str, Any] = {}
        self._steps: list[dict[str, Any]] = []
        self._cursor = 0

    def _path(self, key: str, flow: str) -> Path:
        return self.root / flow / f"{key}.json"

    def start_turn(self, key: str, meta: dict[str, Any]) -> None:
        self._key, self._meta, self._cursor = key, dict(meta), 0
        self._steps = []
        if self.mode == "replay":
            p = self._path(key, str(meta.get("flow", "chat")))
            if p.exists():
                self._steps = json.loads(p.read_text(encoding="utf-8")).get("steps", [])

    def create(self, req: LlmRequest) -> LlmResponse:
        if self.mode == "replay":
            if self._cursor >= len(self._steps):
                raise ReplayMiss()
            step = self._steps[self._cursor]
            self._cursor += 1
            resp = LlmResponse.from_json(step["response"])
            resp.replayed = True
            return resp
        assert self.inner is not None
        resp = self.inner.create(req)
        self._steps.append(
            {
                "request": {
                    "model": req.model,
                    "n_items": len(req.input),
                    "tools": [t.get("name") for t in req.tools],
                    "last_item": _item_kind(req.input[-1]) if req.input else None,
                },
                "response": resp.to_json(),
            }
        )
        return resp

    def finish_turn(self, ok: bool) -> None:
        if self.mode != "record" or self._key is None or not self._steps:
            return
        flow = str(self._meta.get("flow", "chat"))
        p = self._path(self._key, flow)
        p.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "key": self._key,
            **self._meta,
            "ok": ok,
            "recorded_at": utcnow().isoformat(),
            "steps": self._steps,
        }
        p.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def _item_kind(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("role") or "?")


def make_client(settings: Settings, live: LlmClient | None = None) -> LlmClient:
    """Client for ``AI_MODE`` (07 §9). ``live`` overrides the OpenAI client (tests)."""
    if not settings.ai_enabled:
        raise AiUnavailable("AI đang tắt (AI_ENABLED=false).")
    if settings.ai_mode == "replay":
        return RecordReplayClient("replay", None)
    inner = live or OpenAIClient(settings)
    if settings.ai_mode == "record":
        return RecordReplayClient("record", inner)
    return inner
