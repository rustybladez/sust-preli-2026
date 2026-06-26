from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def generate_text_fields(
    *,
    settings: Any,
    context: dict[str, Any],
    fallback: tuple[str, str, str],
) -> tuple[str, str, str] | None:
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        return await _gemini_generate(settings, context, fallback)
    if provider == "openai":
        return await _openai_generate(settings, context, fallback)
    return None


async def _gemini_generate(
    settings: Any,
    context: dict[str, Any],
    fallback: tuple[str, str, str],
) -> tuple[str, str, str] | None:
    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    prompt = _build_prompt(context)
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(model.generate_content, prompt),
            timeout=settings.llm_timeout_seconds,
        )
        text = response.text or ""
        data = _parse_json_block(text)
        if not data:
            return None
        return (
            str(data.get("agent_summary", fallback[0])),
            str(data.get("recommended_next_action", fallback[1])),
            str(data.get("customer_reply", fallback[2])),
        )
    except Exception:
        logger.exception("Gemini call failed")
        return None


async def _openai_generate(
    settings: Any,
    context: dict[str, Any],
    fallback: tuple[str, str, str],
) -> tuple[str, str, str] | None:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return None

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = _build_prompt(context)
    try:
        completion = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You draft support copilot text only. Never ask for PIN/OTP/password. "
                            "Never promise refunds. Return JSON with agent_summary, "
                            "recommended_next_action, customer_reply."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            ),
            timeout=settings.llm_timeout_seconds,
        )
        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)
        return (
            str(data.get("agent_summary", fallback[0])),
            str(data.get("recommended_next_action", fallback[1])),
            str(data.get("customer_reply", fallback[2])),
        )
    except Exception:
        logger.exception("OpenAI call failed")
        return None


def _build_prompt(context: dict[str, Any]) -> str:
    return (
        "Draft three support fields as JSON.\n"
        "Rules: never request PIN/OTP/password; never promise refund/reversal; "
        "use official-channel language only.\n"
        f"Reply language: {context.get('reply_language', 'en')}\n"
        f"Locked case_type: {context.get('case_type')}\n"
        f"Locked department: {context.get('department')}\n"
        f"Locked evidence_verdict: {context.get('evidence_verdict')}\n"
        f"Locked relevant_transaction_id: {context.get('relevant_transaction_id')}\n"
        f"Complaint: {context.get('complaint')}\n"
        f"Transaction summary: {context.get('txn_summary')}\n"
        'Return: {"agent_summary":"...", "recommended_next_action":"...", "customer_reply":"..."}'
    )


def _parse_json_block(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None
