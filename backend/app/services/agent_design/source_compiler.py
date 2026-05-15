from __future__ import annotations

import json
import re
from html import escape
from textwrap import indent

from app.services.agent_design.validators import validate_design_package

_NON_WORD_RE = re.compile(r"[^A-Za-z0-9_]+")


def safe_identifier(value: str, *, fallback: str = "GeneratedAgent") -> str:
    cleaned = _NON_WORD_RE.sub(" ", str(value or "")).strip()
    parts = [p for p in re.split(r"\s+", cleaned) if p]
    ident = "".join(p[:1].upper() + p[1:] for p in parts)
    ident = re.sub(r"[^A-Za-z0-9_]", "", ident)
    if not ident:
        ident = fallback
    if ident[0].isdigit():
        ident = f"Generated{ident}"
    return ident


def _field_type(raw: object) -> str:
    value = str(raw or "String").strip()
    mapping = {
        "id": "Id",
        "string": "String",
        "text": "String",
        "boolean": "Boolean",
        "bool": "Boolean",
        "integer": "Integer",
        "int": "Integer",
        "number": "Decimal",
        "decimal": "Decimal",
        "date": "Date",
        "datetime": "Datetime",
    }
    return mapping.get(value.lower(), safe_identifier(value, fallback="String"))


def _var_name(raw: object, *, fallback: str = "value") -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "", str(raw or "").strip())
    if not name:
        name = fallback
    name = name[:1].lower() + name[1:]
    if name[0].isdigit():
        name = f"v{name}"
    return name


def _files_key(file: dict) -> str:
    return str(file["path"])


def _class_name(action: dict) -> str:
    target_name = str(action.get("target_name") or "").strip()
    if target_name:
        return safe_identifier(target_name, fallback="GeneratedAction")
    action_name = safe_identifier(action.get("name") or "Generated", fallback="Generated")
    return f"{action_name}Action"


def _apex_literal(raw_type: object, fallback: str = "REVIEW_REQUIRED") -> str:
    apex_type = _field_type(raw_type)
    if apex_type == "Boolean":
        return "false"
    if apex_type in {"Integer", "Decimal"}:
        return "0"
    if apex_type == "Date":
        return "Date.today()"
    if apex_type == "Datetime":
        return "Datetime.now()"
    return f"'{fallback}'"


def _primary_object(action: dict) -> str | None:
    for obj in action.get("salesforce_objects") or []:
        value = str(obj or "").strip()
        if value:
            return value
    return None


def _agent_script(bundle_name: str, design_package: dict) -> str:
    agent = design_package.get("agent") or {}
    lines = [
        f"agent {bundle_name} {{",
        f'  label "{agent.get("name") or bundle_name}"',
        f'  description "{str(agent.get("summary") or "").replace(chr(34), chr(39))}"',
        f'  trigger "{str(agent.get("trigger") or "Manual review").replace(chr(34), chr(39))}"',
        "",
    ]
    for topic in design_package.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        topic_name = safe_identifier(topic.get("name") or "Topic", fallback="Topic")
        lines.extend(
            [
                f"  topic {topic_name} {{",
                f'    description "{str(topic.get("description") or "").replace(chr(34), chr(39))}"',
                f'    reasoning "{topic.get("reasoning_type") or "hybrid"}"',
            ]
        )
        for action in topic.get("actions") or []:
            action_name = safe_identifier(str(action), fallback="Action")
            lines.append(f"    action {action_name}Action")
        lines.append("  }")
        lines.append("")
    lines.append("}")
    lines.append("")
    lines.append("// Draft Agent Script generated from an approved Arcflare Agent Design Package.")
    lines.append("// Review in Agentforce DX before deploying to any customer org.")
    return "\n".join(lines)


def _apex_action(action: dict) -> str:
    action_name = safe_identifier(action.get("name") or "Generated", fallback="Generated")
    class_name = _class_name(action)
    label = str(action.get("common_name") or action.get("label") or action_name)
    description = str(action.get("description") or "Generated action contract")
    inputs = [i for i in (action.get("inputs") or []) if isinstance(i, dict)]
    outputs = [o for o in (action.get("outputs") or []) if isinstance(o, dict)]
    primary_object = _primary_object(action)

    input_fields = []
    for item in inputs:
        req = "true" if item.get("required") is not False else "false"
        input_fields.append(
            f"        @InvocableVariable(required={req})\n"
            f"        public {_field_type(item.get('type'))} {_var_name(item.get('name'))};"
        )

    output_fields = []
    output_assignments = []
    for item in outputs:
        var_name = _var_name(item.get("name"))
        output_fields.append(
            f"        @InvocableVariable\n"
            f"        public {_field_type(item.get('type'))} {var_name};"
        )
        output_assignments.append(f"            response.{var_name} = {_apex_literal(item.get('type'))};")

    security_lines = [
        "        // Security baseline: enforce object access, sharing, and FLS before returning data to Agentforce.",
        "        // Replace this scaffold with concrete SOQL/DML that uses WITH USER_MODE or AccessLevel.USER_MODE.",
    ]
    if primary_object:
        security_lines.extend(
            [
                f"        Schema.SObjectType objectType = Schema.getGlobalDescribe().get('{primary_object}');",
                "        if (objectType == null || !objectType.getDescribe().isAccessible()) {",
                "            throw new AgentActionException('MISSING_ACCESS');",
                "        }",
                "        SObjectAccessDecision readableDecision = Security.stripInaccessible(",
                "            AccessType.READABLE,",
                "            new List<SObject>()",
                "        );",
                "        readableDecision.getRecords();",
            ]
        )
    else:
        security_lines.append(
            "        Security.stripInaccessible(AccessType.READABLE, new List<SObject>()).getRecords();"
        )

    assignment_body = "\n".join(output_assignments) if output_assignments else "            response.result = 'REVIEW_REQUIRED';"
    return f"""public with sharing class {class_name} {{
    public class AgentActionException extends Exception {{}}

    public class Request {{
{indent(chr(10).join(input_fields) if input_fields else "        @InvocableVariable(required=true)\n        public Id recordId;", "        ").strip()}
    }}

    public class Response {{
{indent(chr(10).join(output_fields) if output_fields else "        @InvocableVariable\n        public String result;", "        ").strip()}
    }}

    @InvocableMethod(label='{label}' description='{description.replace("'", "\\'")}')
    public static List<Response> invoke(List<Request> requests) {{
{chr(10).join(security_lines)}

        List<Response> responses = new List<Response>();
        for (Request request : requests) {{
            Response response = new Response();
            // TODO: Implement bounded business logic from the approved Arcflare action contract.
{assignment_body}
            responses.add(response);
        }}
        return responses;
    }}
}}
"""


def _apex_test(action: dict) -> str:
    class_name = _class_name(action)
    assignments = []
    for item in [i for i in (action.get("inputs") or []) if isinstance(i, dict)]:
        if item.get("required") is False:
            continue
        assignments.append(
            f"        request.{_var_name(item.get('name'))} = {_apex_literal(item.get('type'), '001000000000001AAA')};"
        )
    assignment_body = "\n".join(assignments)
    return f"""@IsTest
private class {class_name}Test {{
    @IsTest
    static void invokesGeneratedActionStub() {{
        {class_name}.Request request = new {class_name}.Request();
{assignment_body}
        List<{class_name}.Response> responses = {class_name}.invoke(new List<{class_name}.Request>{{ request }});
        System.assertEquals(1, responses.size(), 'The generated action should return one response per request.');
        System.assertNotEquals(null, responses[0], 'The generated action should return a reviewable response.');
    }}
}}
"""


def _apex_meta() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>66.0</apiVersion>
    <status>Active</status>
</ApexClass>
"""


def _permission_set(bundle_name: str, design_package: dict) -> str:
    object_perms = []
    for req in design_package.get("permission_requirements") or []:
        if not isinstance(req, dict):
            continue
        obj = str(req.get("object") or "").strip()
        if not obj:
            continue
        ops = {str(op).lower() for op in (req.get("operations") or [])}
        object_perms.append(
            f"""    <objectPermissions>
        <allowCreate>{str("create" in ops).lower()}</allowCreate>
        <allowDelete>false</allowDelete>
        <allowEdit>{str("update" in ops or "edit" in ops).lower()}</allowEdit>
        <allowRead>{str("read" in ops or not ops).lower()}</allowRead>
        <modifyAllRecords>false</modifyAllRecords>
        <object>{escape(obj)}</object>
        <viewAllRecords>false</viewAllRecords>
    </objectPermissions>"""
        )
    body = "\n".join(object_perms)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Draft permissions for the {escape(bundle_name)} Agentforce artifact bundle. Review before deploy.</description>
    <hasActivationRequired>false</hasActivationRequired>
    <label>{escape(bundle_name)} Agent Permissions</label>
{body}
</PermissionSet>
"""


def _package_xml(bundle_name: str, action_class_names: list[str]) -> str:
    apex_members = "\n".join(
        f"        <members>{escape(name)}</members>"
        for name in sorted({*action_class_names, *[f"{name}Test" for name in action_class_names]})
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{apex_members}
        <name>ApexClass</name>
    </types>
    <types>
        <members>{escape(bundle_name)}</members>
        <name>AiAuthoringBundle</name>
    </types>
    <types>
        <members>{escape(bundle_name)}</members>
        <name>PermissionSet</name>
    </types>
    <version>66.0</version>
</Package>
"""


def _artifact_groups(bundle_name: str, design_package: dict, files_by_path: dict[str, dict]) -> list[dict]:
    groups = [
        {
            "id": "readme",
            "kind": "documentation",
            "display_name": "Review README",
            "common_name": "Review README",
            "files": {"readme": "README.md"},
        },
        {
            "id": "agent_script",
            "kind": "agent_script",
            "display_name": f"{bundle_name} Agent Script",
            "common_name": f"{bundle_name} Agent Script",
            "files": {
                "agent_script": f"force-app/main/default/aiAuthoringBundles/{bundle_name}/{bundle_name}.agent"
            },
        },
        {
            "id": "permissions",
            "kind": "permission_set",
            "display_name": f"{bundle_name} permissions",
            "common_name": f"{bundle_name} permissions",
            "files": {
                "permission_set": f"force-app/main/default/permissionsets/{bundle_name}.permissionset-meta.xml"
            },
        },
        {
            "id": "project_config",
            "kind": "project_config",
            "display_name": "Salesforce DX project config",
            "common_name": "Salesforce DX project config",
            "files": {
                "sfdx_project": "sfdx-project.json",
                "scratch_def": "config/project-scratch-def.json",
                "manifest": "manifest/package.xml",
            },
        },
    ]

    for action in design_package.get("action_contracts") or []:
        if not isinstance(action, dict):
            continue
        action_name = safe_identifier(action.get("name") or "Generated", fallback="Generated")
        class_name = _class_name(action)
        file_map = {
            "apex_class": f"force-app/main/default/classes/{class_name}.cls",
            "apex_meta": f"force-app/main/default/classes/{class_name}.cls-meta.xml",
            "apex_test": f"force-app/main/default/classes/{class_name}Test.cls",
            "apex_test_meta": f"force-app/main/default/classes/{class_name}Test.cls-meta.xml",
        }
        groups.append(
            {
                "id": action.get("source_group_id") or f"action:{action_name}",
                "kind": "action_contract",
                "display_name": str(action.get("common_name") or action.get("label") or action_name),
                "common_name": str(action.get("common_name") or action.get("label") or action_name),
                "action_name": action_name,
                "target_type": action.get("target_type") or "apex",
                "target_name": class_name,
                "capability_type": action.get("capability_type") or "action",
                "implementation_status": action.get("implementation_status") or "scaffold",
                "salesforce_objects": action.get("salesforce_objects") or [],
                "source_topics": action.get("source_topics") or [],
                "files": {key: value for key, value in file_map.items() if value in files_by_path},
                "contract": action,
            }
        )
    return groups


def _scratch_def() -> str:
    return json.dumps(
        {
            "orgName": "Arcflare Agent Validation",
            "edition": "Developer",
            "features": ["Einstein1AIPlatform"],
            "settings": {
                "einsteinGptSettings": {"enableEinsteinGptPlatform": True},
                "agentforceSettings": {"enableAgentforcePlatform": True},
            },
        },
        indent=2,
    )


def _readme(bundle_name: str, design_package: dict) -> str:
    blockers = design_package.get("blockers") or []
    checks = "\n".join(f"- {b}" for b in blockers) if blockers else "- No design blockers at generation time."
    return f"""# {bundle_name} Agentforce Draft

This Salesforce DX project was generated from an approved Arcflare Agent Design Package.

## Review Checklist

{checks}

## Suggested Commands

```bash
sf project deploy start --manifest manifest/package.xml --target-org <scratch-or-sandbox-alias>
sf apex run test --target-org <scratch-or-sandbox-alias> --test-level RunLocalTests
```

Generated Apex actions are safe stubs unless the action contract contains enough bounded implementation detail. Review CRUD/FLS, sharing, tests, and Agentforce topic behavior before customer deployment.
"""


def compile_source_bundle(design_package: dict) -> dict:
    validation = validate_design_package(design_package)
    if not validation["ok"]:
        raise ValueError(f"Design package has blockers: {', '.join(validation['blockers'])}")

    agent = design_package.get("agent") if isinstance(design_package.get("agent"), dict) else {}
    bundle_name = safe_identifier(str(agent.get("name") or "Generated Agent"), fallback="GeneratedAgent")
    actions = [a for a in (design_package.get("action_contracts") or []) if isinstance(a, dict)]
    action_class_names = [_class_name(action) for action in actions]
    files = [
        {
            "path": "sfdx-project.json",
            "kind": "project_config",
            "language": "json",
            "content": json.dumps(
                {
                    "packageDirectories": [{"path": "force-app", "default": True}],
                    "name": f"{bundle_name}-arcflare-draft",
                    "namespace": "",
                    "sourceApiVersion": "66.0",
                },
                indent=2,
            ),
        },
        {
            "path": "manifest/package.xml",
            "kind": "manifest",
            "language": "xml",
            "content": _package_xml(bundle_name, action_class_names),
        },
        {
            "path": "config/project-scratch-def.json",
            "kind": "scratch_org_definition",
            "language": "json",
            "content": _scratch_def(),
        },
        {
            "path": f"force-app/main/default/aiAuthoringBundles/{bundle_name}/{bundle_name}.agent",
            "kind": "agent_script",
            "language": "agentscript",
            "content": _agent_script(bundle_name, design_package),
        },
        {
            "path": f"force-app/main/default/permissionsets/{bundle_name}.permissionset-meta.xml",
            "kind": "permission_set",
            "language": "xml",
            "content": _permission_set(bundle_name, design_package),
        },
        {
            "path": "README.md",
            "kind": "readme",
            "language": "markdown",
            "content": _readme(bundle_name, design_package),
        },
    ]

    for action in actions:
        class_name = _class_name(action)
        files.append(
            {
                "path": f"force-app/main/default/classes/{class_name}.cls",
                "kind": "apex_action",
                "language": "apex",
                "content": _apex_action(action),
            }
        )
        files.append(
            {
                "path": f"force-app/main/default/classes/{class_name}.cls-meta.xml",
                "kind": "apex_metadata",
                "language": "xml",
                "content": _apex_meta(),
            }
        )
        files.append(
            {
                "path": f"force-app/main/default/classes/{class_name}Test.cls",
                "kind": "apex_test",
                "language": "apex",
                "content": _apex_test(action),
            }
        )
        files.append(
            {
                "path": f"force-app/main/default/classes/{class_name}Test.cls-meta.xml",
                "kind": "apex_metadata",
                "language": "xml",
                "content": _apex_meta(),
            }
        )

    files = sorted(files, key=_files_key)
    files_by_path = {str(file["path"]): file for file in files}
    artifact_groups = _artifact_groups(bundle_name, design_package, files_by_path)
    return {
        "schema_version": "agent_source_bundle_v1",
        "source_api_version": "66.0",
        "compiler_version": "agentforce_source_compiler_v1",
        "bundle_name": bundle_name,
        "files": files,
        "artifact_groups": artifact_groups,
        "checks": {
            "validation": validation,
            "generated_file_count": len(files),
            "artifact_group_count": len(artifact_groups),
            "requires_review": True,
        },
    }
