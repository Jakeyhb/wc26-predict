"""LLM services — DeepSeek V4 Pro integration for WC26 business intelligence.

Sub-packages:
- deepseek_client: Unified DeepSeek V4 Pro client with retry logic
- signal_extraction: Structured signal extraction from news articles
- schemas: ExtractedSignal dataclass and JSON schema
- prompts/: Prompt templates for extraction, report writing, etc.
"""
from app.services.llm.schemas import ExtractedSignal, SignalType, ImpactDirection, Severity
from app.services.llm.deepseek_client import DeepSeekClient
from app.services.llm.signal_extraction import SignalExtractionService

__all__ = [
    "DeepSeekClient",
    "SignalExtractionService",
    "ExtractedSignal",
    "SignalType",
    "ImpactDirection",
    "Severity",
]
