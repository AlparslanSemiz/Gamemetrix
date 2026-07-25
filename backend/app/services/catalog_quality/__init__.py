"""Groq-backed review of suspicious catalog titles, summaries and metadata."""

from .batch import catalog_quality_batch
from .repair_batch import catalog_repair_batch
from .remediation import ResearchedGame, build_repair_plan, repair_fields
from .review import QualityVerdict, parse_quality_verdict
from .signals import catalog_quality_signals

__all__ = [
    "QualityVerdict",
    "ResearchedGame",
    "catalog_quality_batch",
    "catalog_repair_batch",
    "catalog_quality_signals",
    "build_repair_plan",
    "parse_quality_verdict",
    "repair_fields",
]
