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


def _field_rows(action: dict, key: str) -> list[dict]:
    rows = []
    for item in action.get(key) or []:
        if not isinstance(item, dict):
            continue
        object_api_name = str(item.get("object_api_name") or "").strip()
        field_api_name = str(item.get("field_api_name") or "").strip()
        if object_api_name and field_api_name:
            rows.append({"object_api_name": object_api_name, "field_api_name": field_api_name})
    return rows


def _field_names_for_object(fields: list[dict], object_api_name: str | None) -> list[str]:
    if not object_api_name:
        return []
    names = {
        str(field.get("field_api_name") or "").strip()
        for field in fields
        if str(field.get("object_api_name") or "").strip() == object_api_name
    }
    return sorted(name for name in names if name)


def _record_id_input(action: dict, primary_object: str | None) -> dict | None:
    inputs = [i for i in (action.get("inputs") or []) if isinstance(i, dict)]
    for item in inputs:
        if str(item.get("type") or "").lower() == "id" and (
            not primary_object or str(item.get("object") or "") == primary_object
        ):
            return item
    for item in inputs:
        if str(item.get("type") or "").lower() == "id":
            return item
    return None


def _has_output(action: dict, name: str) -> bool:
    return any(
        isinstance(item, dict) and _var_name(item.get("name")) == name
        for item in action.get("outputs") or []
    )


def _response_assignment(var_name: str, value: str) -> str:
    return f"            response.{var_name} = {value};"


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
    capability_type = str(action.get("capability_type") or "")
    bounded = action.get("apex_generation_mode") == "bounded_apex"
    read_fields = _field_rows(action, "read_fields")
    write_fields = _field_rows(action, "write_fields")
    record_id_input = _record_id_input(action, primary_object)
    record_id_var = _var_name(record_id_input.get("name")) if record_id_input else "recordId"

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
    bounded_body = None
    if bounded and capability_type in {"read_context", "reasoning"} and primary_object and read_fields:
        field_names = _field_names_for_object(read_fields, primary_object)
        select_fields = ", ".join(["Id", *[name for name in field_names if name != "Id"]])
        response_lines = []
        if _has_output(action, "contextJson"):
            response_lines.append(_response_assignment("contextJson", "JSON.serialize(record)"))
        if _has_output(action, "classification"):
            response_lines.append(_response_assignment("classification", "'REVIEW_REQUIRED'"))
        if _has_output(action, "priority"):
            response_lines.append(_response_assignment("priority", "'REVIEW_REQUIRED'"))
        if _has_output(action, "confidence"):
            response_lines.append(_response_assignment("confidence", "0"))
        if _has_output(action, "rationale"):
            response_lines.append(_response_assignment("rationale", "'Review the generated action contract before deployment.'"))
        if _has_output(action, "status"):
            response_lines.append(_response_assignment("status", "'LOADED'"))
        bounded_body = f"""
        Schema.SObjectType objectType = Schema.getGlobalDescribe().get('{primary_object}');
        if (objectType == null || !objectType.getDescribe().isAccessible()) {{
            List<Response> responses = new List<Response>();
            for (Request request : requests) {{
                Response response = new Response();
{_response_assignment("status", "'MISSING_ACCESS'") if _has_output(action, "status") else ""}
                responses.add(response);
            }}
            return responses;
        }}

        Set<Id> recordIds = new Set<Id>();
        for (Request request : requests) {{
            if (request.{record_id_var} != null) {{
                recordIds.add(request.{record_id_var});
            }}
        }}

        Map<Id, {primary_object}> recordsById = new Map<Id, {primary_object}>([
            SELECT {select_fields}
            FROM {primary_object}
            WHERE Id IN :recordIds
            WITH USER_MODE
        ]);

        List<Response> responses = new List<Response>();
        for (Request request : requests) {{
            Response response = new Response();
            try {{
                {primary_object} record = recordsById.get(request.{record_id_var});
                if (record == null) {{
{_response_assignment("status", "'RECORD_NOT_FOUND'") if _has_output(action, "status") else ""}
                }} else {{
{indent(chr(10).join(response_lines), "                ")}
                }}
            }} catch (Exception ex) {{
{_response_assignment("status", "'ERROR'") if _has_output(action, "status") else ""}
{_response_assignment("rationale", "ex.getMessage()") if _has_output(action, "rationale") else ""}
            }}
            responses.add(response);
        }}
        return responses;"""
    elif bounded and capability_type == "writeback" and primary_object and write_fields:
        field_names = _field_names_for_object(write_fields, primary_object)
        update_lines = []
        for field_name in field_names:
            input_name = _var_name(field_name.removesuffix("__c"))
            if any(_var_name(item.get("name")) == input_name for item in inputs):
                update_lines.append(
                    f"                if (request.{input_name} != null) {{\n"
                    f"                    record.{field_name} = request.{input_name};\n"
                    "                }"
                )
        bounded_body = f"""
        Schema.SObjectType objectType = Schema.getGlobalDescribe().get('{primary_object}');
        if (objectType == null || !objectType.getDescribe().isUpdateable()) {{
            List<Response> responses = new List<Response>();
            for (Request request : requests) {{
                Response response = new Response();
{_response_assignment("status", "'MISSING_ACCESS'") if _has_output(action, "status") else ""}
                responses.add(response);
            }}
            return responses;
        }}

        List<Response> responses = new List<Response>();
        List<{primary_object}> pendingUpdates = new List<{primary_object}>();
        for (Request request : requests) {{
            Response response = new Response();
            try {{
                {primary_object} record = new {primary_object}(Id = request.{record_id_var});
{chr(10).join(update_lines) if update_lines else "                // No writable fields were included in the request contract."}
                pendingUpdates.add(record);
{_response_assignment("status", "'UPDATED'") if _has_output(action, "status") else ""}
            }} catch (Exception ex) {{
{_response_assignment("status", "'ERROR'") if _has_output(action, "status") else ""}
{_response_assignment("rationale", "ex.getMessage()") if _has_output(action, "rationale") else ""}
            }}
            responses.add(response);
        }}

        if (!pendingUpdates.isEmpty()) {{
            SObjectAccessDecision updateDecision = Security.stripInaccessible(AccessType.UPDATABLE, pendingUpdates);
            List<SObject> sanitizedRecords = updateDecision.getRecords();
            Database.SaveResult[] saveResults = Database.update(sanitizedRecords, false, AccessLevel.USER_MODE);
            for (Integer i = 0; i < saveResults.size(); i++) {{
                if (!saveResults[i].isSuccess() && i < responses.size()) {{
                    responses[i].status = saveResults[i].getErrors()[0].getMessage();
                }}
            }}
        }}
        return responses;"""

    method_body = bounded_body or f"""
{chr(10).join(security_lines)}

        List<Response> responses = new List<Response>();
        for (Request request : requests) {{
            Response response = new Response();
            // TODO: Implement bounded business logic from the approved Arcflare action contract.
{assignment_body}
            responses.add(response);
        }}
        return responses;"""
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
{method_body}
    }}
}}
"""


def _apex_test(action: dict) -> str:
    class_name = _class_name(action)
    primary_object = _primary_object(action)
    bounded = action.get("apex_generation_mode") == "bounded_apex"
    capability_type = str(action.get("capability_type") or "")
    record_id_input = _record_id_input(action, primary_object)
    record_id_var = _var_name(record_id_input.get("name")) if record_id_input else "recordId"
    assignments = []
    for item in [i for i in (action.get("inputs") or []) if isinstance(i, dict)]:
        if item.get("required") is False:
            continue
        assignments.append(
            f"        request.{_var_name(item.get('name'))} = {_apex_literal(item.get('type'), '001000000000001AAA')};"
        )
    assignment_body = "\n".join(assignments)
    if bounded and primary_object:
        optional_assignments = []
        for item in [i for i in (action.get("inputs") or []) if isinstance(i, dict)]:
            if item.get("required") is not False:
                continue
            if item.get("field"):
                optional_assignments.append(
                    f"        request.{_var_name(item.get('name'))} = {_apex_literal(item.get('type'), 'High')};"
                )
        status_assertion = (
            "        System.assertEquals('UPDATED', responses[0].status, 'The generated writeback should report an update.');"
            if capability_type == "writeback"
            else "        System.assertNotEquals(null, responses[0], 'The generated action should return a reviewable response.');"
        )
        return f"""@IsTest
private class {class_name}Test {{
    @IsTest
    static void invokesGeneratedActionWithRecordEvidence() {{
        {primary_object} caseRecord = new {primary_object}();
        insert caseRecord;

        {class_name}.Request request = new {class_name}.Request();
        request.{record_id_var} = caseRecord.Id;
{chr(10).join(optional_assignments)}
        List<{class_name}.Response> responses = {class_name}.invoke(new List<{class_name}.Request>{{ request }});
        System.assertEquals(1, responses.size(), 'The generated action should return one response per request.');
{status_assertion}
    }}
}}
"""
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
    field_perms = []
    seen_fields: set[tuple[str, str]] = set()
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
        for field in req.get("fields") or []:
            if not isinstance(field, dict):
                continue
            field_api_name = str(field.get("field_api_name") or "").strip()
            if not field_api_name:
                continue
            seen_fields.add((obj, field_api_name))
            field_ops = {str(op).lower() for op in (field.get("operations") or [])}
            field_perms.append(
                f"""    <fieldPermissions>
        <editable>{str("update" in field_ops or "edit" in field_ops).lower()}</editable>
        <field>{escape(obj)}.{escape(field_api_name)}</field>
        <readable>{str("read" in field_ops or not field_ops).lower()}</readable>
    </fieldPermissions>"""
            )
    for action in design_package.get("action_contracts") or []:
        if not isinstance(action, dict):
            continue
        for field in _field_rows(action, "read_fields"):
            obj = field["object_api_name"]
            field_api_name = field["field_api_name"]
            if (obj, field_api_name) in seen_fields:
                continue
            seen_fields.add((obj, field_api_name))
            field_perms.append(
                f"""    <fieldPermissions>
        <editable>false</editable>
        <field>{escape(obj)}.{escape(field_api_name)}</field>
        <readable>true</readable>
    </fieldPermissions>"""
            )
        for field in _field_rows(action, "write_fields"):
            obj = field["object_api_name"]
            field_api_name = field["field_api_name"]
            if (obj, field_api_name) in seen_fields:
                continue
            seen_fields.add((obj, field_api_name))
            field_perms.append(
                f"""    <fieldPermissions>
        <editable>true</editable>
        <field>{escape(obj)}.{escape(field_api_name)}</field>
        <readable>true</readable>
    </fieldPermissions>"""
            )
    body = "\n".join(object_perms)
    field_body = "\n".join(field_perms)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <description>Draft permissions for the {escape(bundle_name)} Agentforce artifact bundle. Review before deploy.</description>
    <hasActivationRequired>false</hasActivationRequired>
    <label>{escape(bundle_name)} Agent Permissions</label>
{field_body}
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
                "apex_generation_mode": action.get("apex_generation_mode") or "scaffold_apex",
                "salesforce_objects": action.get("salesforce_objects") or [],
                "source_topics": action.get("source_topics") or [],
                "quality": {
                    "implementation_status": action.get("implementation_status") or "scaffold",
                    "apex_generation_mode": action.get("apex_generation_mode") or "scaffold_apex",
                    "warnings": action.get("quality_warnings") or [],
                },
                "files": {key: value for key, value in file_map.items() if value in files_by_path},
                "contract": action,
            }
        )
    return groups


def _implementation_quality(actions: list[dict]) -> dict:
    counts = {"deployable_candidate": 0, "bounded_candidate": 0, "scaffold": 0}
    warnings: list[str] = []
    for action in actions:
        status = str(action.get("implementation_status") or "scaffold")
        counts[status] = counts.get(status, 0) + 1
        for warning in action.get("quality_warnings") or []:
            value = str(warning)
            if value not in warnings:
                warnings.append(value)
    return {**counts, "warnings": warnings}


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
            "implementation_quality": _implementation_quality(actions),
            "requires_review": True,
        },
    }
