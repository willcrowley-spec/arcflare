"""Filtering logic for platform connector results.

Applies configurable rules to remove noise from the data model:
managed packages, zero-record objects, inactive automations, etc.
"""
from dataclasses import dataclass, field
import logging

from app.services.connectors.base import AutomationMeta, PlatformObjectMeta

logger = logging.getLogger(__name__)


@dataclass
class FilterConfig:
    """Configuration for filtering platform metadata."""
    exclude_managed_packages: bool = True
    allowed_namespaces: list[str] = field(default_factory=list)
    exclude_zero_records: bool = True
    exclude_inactive_automations: bool = True
    min_record_count: int = 1
    recency_days: int = 365


def filter_objects(
    objects: list[PlatformObjectMeta],
    config: FilterConfig,
) -> list[PlatformObjectMeta]:
    """Filter objects based on config rules."""
    original_count = len(objects)
    kept: list[PlatformObjectMeta] = []

    for obj in objects:
        if config.exclude_managed_packages and obj.is_managed_package:
            if obj.namespace_prefix not in config.allowed_namespaces:
                continue

        if config.exclude_zero_records and obj.record_count < config.min_record_count:
            continue

        kept.append(obj)

    logger.info(
        "filter_objects_complete original=%d kept=%d removed=%d",
        original_count, len(kept), original_count - len(kept),
    )
    return kept


def filter_automations(
    automations: list[AutomationMeta],
    config: FilterConfig,
) -> list[AutomationMeta]:
    """Filter automations, removing inactive ones if configured."""
    if not config.exclude_inactive_automations:
        return automations

    original_count = len(automations)
    kept = [a for a in automations if a.is_active]

    logger.info(
        "filter_automations_complete original=%d kept=%d removed=%d",
        original_count, len(kept), original_count - len(kept),
    )
    return kept
