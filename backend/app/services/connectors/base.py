"""Abstract base class and shared dataclasses for platform connectors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PlatformObjectMeta:
    """Metadata for a single platform object (e.g. Salesforce SObject)."""
    api_name: str
    label: str
    record_count: int = 0
    recent_record_count: int = 0
    field_count: int = 0
    is_managed_package: bool = False
    namespace_prefix: Optional[str] = None
    is_custom: bool = False
    fields: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)


@dataclass
class AutomationMeta:
    """Metadata for an automation component."""
    api_name: str
    label: str
    automation_type: str  # "flow", "workflow_rule", "trigger", "process_builder", "approval_process"
    is_active: bool = True
    description: Optional[str] = None
    related_objects: list[str] = field(default_factory=list)


@dataclass
class UIComponentMeta:
    """Metadata for a UI component."""
    api_name: str
    label: str
    component_type: str  # "page_layout", "lightning_page", "app", "report", "dashboard"
    related_object: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PermissionMeta:
    """Metadata for a permission/security configuration."""
    api_name: str
    label: str
    permission_type: str  # "profile", "permission_set", "role"
    description: Optional[str] = None
    object_permissions: list[dict] = field(default_factory=list)


@dataclass
class UsageData:
    """Record-count usage data for platform objects."""
    object_record_counts: dict[str, int] = field(default_factory=dict)
    object_recent_counts: dict[str, int] = field(default_factory=dict)
    active_user_count: Optional[int] = None


@dataclass
class PlatformPullResult:
    """Complete result of pulling all data from a platform."""
    platform_name: str
    objects: list[PlatformObjectMeta]
    automations: list[AutomationMeta]
    ui_components: list[UIComponentMeta]
    permissions: list[PermissionMeta]
    usage: UsageData
    summary: dict


class PlatformConnector(ABC):
    """Abstract base class for platform connectors.

    Subclasses must implement all abstract methods. The pull_all template
    method orchestrates a full pull: authenticate, fetch data model, usage,
    automations, UI components, and permissions.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @abstractmethod
    def authenticate(self, credentials: dict) -> None:
        ...

    @abstractmethod
    def pull_data_model(self) -> list[PlatformObjectMeta]:
        ...

    @abstractmethod
    def pull_automations(self) -> list[AutomationMeta]:
        ...

    @abstractmethod
    def pull_ui_components(self, object_names: list[str]) -> list[UIComponentMeta]:
        ...

    @abstractmethod
    def pull_permissions(self) -> list[PermissionMeta]:
        ...

    @abstractmethod
    def pull_usage_data(self, object_names: list[str]) -> UsageData:
        ...

    @abstractmethod
    def pull_records(
        self,
        object_name: str,
        fields: list[str] | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        ...

    def pull_all(
        self,
        credentials: dict,
        filter_config: "FilterConfig | None" = None,
        include_records: bool = False,
    ) -> PlatformPullResult:
        """Template method: pull everything from the platform."""
        from app.services.connectors.filtering import FilterConfig, filter_automations, filter_objects

        if filter_config is None:
            filter_config = FilterConfig()

        logger.info("pull_all_start platform=%s", self.platform_name)

        self.authenticate(credentials)

        objects = self.pull_data_model()
        logger.info("pull_all_data_model platform=%s objects=%d", self.platform_name, len(objects))

        object_names = [obj.api_name for obj in objects]
        usage = self.pull_usage_data(object_names)

        for obj in objects:
            obj.record_count = usage.object_record_counts.get(obj.api_name, 0)
            obj.recent_record_count = usage.object_recent_counts.get(obj.api_name, 0)

        objects = filter_objects(objects, filter_config)

        automations = self.pull_automations()
        automations = filter_automations(automations, filter_config)

        ui_components = self.pull_ui_components(object_names)
        permissions = self.pull_permissions()

        summary = {
            "objects": len(objects),
            "automations": len(automations),
            "ui_components": len(ui_components),
            "permissions": len(permissions),
            "total_records": sum(usage.object_record_counts.values()),
            "active_users": usage.active_user_count,
        }

        logger.info("pull_all_complete platform=%s summary=%s", self.platform_name, summary)

        return PlatformPullResult(
            platform_name=self.platform_name,
            objects=objects,
            automations=automations,
            ui_components=ui_components,
            permissions=permissions,
            usage=usage,
            summary=summary,
        )
