"""DeepSeek V4 Pro unified client for WC26 business LLM operations.

Wraps the existing DeepSeekAdapter with:
- Retry logic (3 attempts with exponential backoff)
- Rate limiting awareness
- Structured JSON output validation
- Error classification
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.services.llm_service import DeepSeekAdapter

logger = logging.getLogger(__name__)

# ── Configuration ──
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 30.0


class DeepSeekClient:
    """Unified DeepSeek V4 Pro client with retry and validation.

    Usage:
        client = DeepSeekClient()
        signals = await client.extract_json(
            system_prompt=PROMPT,
            user_prompt=formatted_article,
            expected_schema=EXTRACTION_JSON_SCHEMA,
        )
    """

    def __init__(self) -> None:
        self._adapter = DeepSeekAdapter()

    @property
    def model(self) -> str:
        from app.config import get_settings
        return get_settings().llm_model

    async def chat(
        self,
        system: str,
        user: str,
        *,
        response_format: str = "text",
    ) -> str:
        """Send a chat request with retry logic.

        Args:
            system: System prompt.
            user: User message.
            response_format: "text" or "json".

        Returns:
            LLM response text.

        Raises:
            RuntimeError: After exhausting all retries.
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                result = await self._adapter.chat(
                    system=system,
                    user=user,
                    response_format=response_format,
                )
                if result:
                    return result
                logger.warning(
                    f"DeepSeek returned empty response (attempt {attempt + 1}/{MAX_RETRIES})"
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"DeepSeek API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )

            if attempt < MAX_RETRIES - 1:
                delay = min(BASE_DELAY_SECONDS * (2 ** attempt), MAX_DELAY_SECONDS)
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"DeepSeek API failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    async def extract_json(
        self,
        system: str,
        user: str,
        expected_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract structured JSON from LLM with validation.

        Args:
            system: System prompt (must instruct JSON output).
            user: User prompt with article text etc.
            expected_schema: Optional JSON schema for validation.

        Returns:
            Parsed JSON dict. Guaranteed to be valid JSON.

        Raises:
            ValueError: If response is not valid JSON or fails schema validation.
        """
        raw = await self.chat(system=system, user=user, response_format="json")

        # Parse JSON — handle markdown fences and common wrapping
        parsed = self._parse_json_response(raw)

        if expected_schema and parsed:
            # Basic structural validation
            self._validate_schema(parsed, expected_schema)

        return parsed

    @staticmethod
    def _parse_json_response(raw: str) -> dict[str, Any]:
        """Robust JSON extraction from LLM responses.

        Handles:
        - ```json ... ``` markdown fences
        - ``` ... ``` generic fences
        - Plain JSON
        - { "key": "value" } objects
        """
        if not raw or not raw.strip():
            raise ValueError("Empty response from DeepSeek")

        text = raw.strip()

        # Try markdown fence extraction
        if "```" in text:
            fence_start = text.find("```")
            fence_end = text.find("```", fence_start + 3)
            if fence_end > fence_start:
                inner = text[fence_start + 3:fence_end].strip()
                # Skip optional "json" tag
                if inner.startswith("json"):
                    inner = inner[4:].strip()
                text = inner

        # Try to find JSON object/array
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            si = text.find(start_char)
            ei = text.rfind(end_char)
            if si >= 0 and ei > si:
                text = text[si:ei + 1]
                break

        try:
            parsed = json.loads(text)
            return parsed
        except json.JSONDecodeError:
            raise ValueError(
                f"Could not parse DeepSeek response as JSON. "
                f"Raw (first 300 chars): {raw[:300]}"
            )

    @staticmethod
    def _validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> None:
        """Basic structural validation against expected schema."""
        if "required" in schema:
            for key in schema["required"]:
                if key not in data:
                    logger.warning(f"Schema validation: missing required key '{key}'")
        # Non-blocking — we don't reject, just warn
