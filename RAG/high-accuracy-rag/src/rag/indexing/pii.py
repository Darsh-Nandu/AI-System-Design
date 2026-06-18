"""PII detection and anonymization using Microsoft Presidio.

Runs before indexing to replace personal data with typed placeholders.
Falls back to a no-op if Presidio is not installed (useful in test environments).
"""

from __future__ import annotations

from rag.logging import get_logger

logger = get_logger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    _analyzer = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
    _PRESIDIO_AVAILABLE = True
except ImportError:
    _PRESIDIO_AVAILABLE = False
    logger.warning("presidio_not_installed", note="PII detection disabled; install presidio-analyzer")


def detect_and_anonymize(text: str, language: str = "en") -> tuple[str, int]:
    """Return (anonymized_text, pii_entity_count).

    Replaces names, emails, phone numbers, and similar PII with
    placeholders like <PERSON>, <EMAIL_ADDRESS>, <PHONE_NUMBER>.
    """
    if not _PRESIDIO_AVAILABLE:
        return text, 0

    results = _analyzer.analyze(text=text, language=language)
    if not results:
        return text, 0

    anonymized = _anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text, len(results)
