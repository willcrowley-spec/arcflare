"""Classify Salesforce User records into human / system / external tiers."""
from app.services.salesforce.licensing import EXTERNAL_LICENSE_KEYS

SYSTEM_LICENSE_KEYS = {
    "SFDC_INTL",
    "AUL_EINSTEIN_ACTIVITY",
    "AUL_LINKEDIN_SALES_NAVIGATOR",
    "PID_Chatter_Only_Integration",
    "SFDC_PLATFORM_INTL",
}

_SYSTEM_NAME_PATTERNS = {
    "integration",
    "einstein",
    "automated",
    "coach",
    "agent user",
    "insights",
}


def classify_user(user: dict) -> str:
    """Return 'system', 'external', or 'human'.

    Classification hierarchy (first match wins):
    1. System — license key in SYSTEM_LICENSE_KEYS or (noreply@salesforce email + name pattern)
    2. External — license key in EXTERNAL_LICENSE_KEYS
    3. Human — everything else
    """
    profile = user.get("Profile") or {}
    user_license = profile.get("UserLicense") or {}
    lic_key = user_license.get("LicenseDefinitionKey", "")

    if lic_key in SYSTEM_LICENSE_KEYS:
        return "system"

    email = (user.get("Email") or "").lower()
    name = (user.get("Name") or "").lower()
    if email.endswith("@salesforce.com") and any(p in name for p in _SYSTEM_NAME_PATTERNS):
        return "system"

    if lic_key in EXTERNAL_LICENSE_KEYS:
        return "external"

    user_type = user.get("UserType", "")
    if user_type not in ("Standard", ""):
        return "external"

    return "human"
