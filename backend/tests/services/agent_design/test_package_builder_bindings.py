from app.services.agent_design.package_builder import build_design_package_from_context


def test_design_package_uses_validated_metadata_bindings_as_source_of_truth():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-1",
                "title": "Closed-Won Handoff Agent",
                "automation_type": "hybrid",
                "agent_opportunity": {
                    "agent_name": "Closed-Won Handoff Agent",
                    "agent_type": "hybrid",
                    "description": "Handles closed won handoff.",
                    "topics": [
                        {
                            "topic_name": "Closed-Won Detection",
                            "description": "Validate Opportunity status.",
                            "reasoning_type": "deterministic",
                            "actions_needed": ["Read Opportunity stage", "Update Opportunity handoff status"],
                        }
                    ],
                    "data_requirements": ["Opportunity record with all deal fields"],
                    "metadata_bindings_v1": {
                        "schema_version": "metadata_bindings_v1",
                        "bindings": [
                            {
                                "ref_type": "object",
                                "api_name": "Opportunity",
                                "object_api_name": "Opportunity",
                                "operation": "read",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-1"],
                            }
                        ],
                        "unresolved_bindings": [],
                        "telemetry": {"bindings_from_process_touchpoints": 1},
                    },
                },
            },
            "salesforce_metadata": {"objects": [{"api_name": "Opportunity", "label": "Opportunity"}]},
        }
    )

    assert package["metadata_grounding"]["binding_model_version"] == "metadata_bindings_v1"
    assert package["metadata_grounding"]["legacy_adapter_used"] is False
    assert package["metadata_grounding"]["mapped"][0]["api_name"] == "Opportunity"
    assert package["permission_requirements"] == [
        {
            "object": "Opportunity",
            "operations": ["read"],
            "reason": "Required by validated metadata bindings for generated Agentforce action contracts.",
        }
    ]
    assert package["action_contracts"][0]["salesforce_objects"] == ["Opportunity"]
    assert package["blockers"] == []


def test_design_package_does_not_use_legacy_string_adapter_for_source_dependencies():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-legacy",
                "title": "Legacy Recommendation",
                "agent_opportunity": {
                    "agent_name": "Legacy Agent",
                    "agent_type": "hybrid",
                    "topics": [
                        {
                            "topic_name": "Opportunity Review",
                            "description": "Review Opportunity records.",
                            "reasoning_type": "hybrid",
                            "actions_needed": ["Read Opportunity record"],
                        }
                    ],
                    "data_requirements": ["Opportunity record"],
                },
            },
            "salesforce_metadata": {"objects": [{"api_name": "Opportunity", "label": "Opportunity"}]},
        }
    )

    assert package["metadata_grounding"]["legacy_adapter_used"] is True
    assert package["metadata_grounding"]["legacy_suggestions"][0]["api_name"] == "Opportunity"
    assert package["metadata_grounding"]["mapped"] == []
    assert package["permission_requirements"] == []
    assert package["action_contracts"][0]["salesforce_objects"] == []
    assert "legacy_binding_requires_review:Opportunity" in package["blockers"]


def test_design_package_uses_manifest_bindings_and_does_not_block_on_advisory_copy():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-closed-won",
                "title": "Closed-Won Opportunity Handoff Coordinator",
                "automation_type": "hybrid",
                "agent_opportunity": {
                    "agent_name": "Closed-Won Opportunity Handoff Coordinator",
                    "agent_type": "hybrid",
                    "description": "Coordinates closed-won handoffs.",
                    "topics": [
                        {
                            "topic_name": "Closed-Won Detection",
                            "description": "Validate Opportunity status and start handoff.",
                            "reasoning_type": "deterministic",
                            "actions_needed": [
                                "Validate Opportunity stage",
                                "Dispatch handoff event",
                            ],
                        }
                    ],
                    "data_requirements": [
                        "Opportunity record with all deal fields",
                        "Customer Onboarding team roster or queue configuration",
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "binding_model_version": "metadata_binding_manifest_v1",
                        "bindings": [
                            {
                                "ref_type": "object",
                                "api_name": "Opportunity",
                                "object_api_name": "Opportunity",
                                "operation": "write",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-1"],
                            },
                            {
                                "ref_type": "object",
                                "api_name": "Agent_Opportunity__c",
                                "object_api_name": "Agent_Opportunity__c",
                                "operation": "create",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-1"],
                            },
                            {
                                "ref_type": "flow",
                                "api_name": "Opportunity_Before_Create_Update",
                                "object_api_name": "Opportunity",
                                "operation": "trigger",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-1"],
                            },
                        ],
                        "advisory_bindings": [
                            {
                                "ref_type": "queue",
                                "raw_value": "Customer Onboarding team roster or queue configuration",
                                "source": "llm_suggestion",
                                "status": "suggested",
                            }
                        ],
                        "unresolved_bindings": [],
                        "quality_gates": {
                            "agent_ready": True,
                            "missing_evidence": [],
                            "unresolved_external_dependencies": [],
                        },
                        "telemetry": {"bindings_from_process_touchpoints": 3},
                    },
                },
            },
            "salesforce_metadata": {
                "objects": [
                    {"api_name": "Opportunity", "label": "Opportunity"},
                    {"api_name": "Agent_Opportunity__c", "label": "Agent Opportunity"},
                ],
                "automations": [
                    {
                        "api_name": "Opportunity_Before_Create_Update",
                        "type": "flow",
                        "label": "Opportunity Before Create Update",
                        "related_object": "Opportunity",
                    }
                ],
            },
        }
    )

    grounding = package["metadata_grounding"]
    assert grounding["binding_model_version"] == "metadata_binding_manifest_v1"
    assert {row["api_name"] for row in grounding["mapped"]} == {
        "Opportunity",
        "Agent_Opportunity__c",
    }
    assert grounding["validated_dependencies"][0]["ref_type"] == "flow"
    assert grounding["upstream_defects"] == []
    assert grounding["advisory_suggestions"][0]["ref_type"] == "queue"
    permission_ops = {row["object"]: row["operations"] for row in package["permission_requirements"]}
    assert permission_ops == {
        "Opportunity": ["read", "update"],
        "Agent_Opportunity__c": ["read", "create"],
    }
    assert package["blockers"] == []


def test_design_package_blocks_upstream_defects_not_mapping_tasks():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-defect",
                "title": "Broken Agent",
                "agent_opportunity": {
                    "agent_name": "Broken Agent",
                    "agent_type": "hybrid",
                    "topics": [
                        {
                            "topic_name": "Broken Topic",
                            "description": "Needs missing evidence.",
                            "reasoning_type": "hybrid",
                            "actions_needed": ["Review missing object"],
                        }
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "bindings": [],
                        "advisory_bindings": [],
                        "unresolved_bindings": [
                            {
                                "ref_type": "object",
                                "raw_value": "Legacy_Workflow__c",
                                "api_name": "Legacy_Workflow__c",
                                "object_api_name": "Legacy_Workflow__c",
                                "source": "process_touchpoint",
                                "status": "unresolved",
                                "reason": "unknown_object",
                            }
                        ],
                        "quality_gates": {
                            "agent_ready": False,
                            "missing_evidence": ["Legacy_Workflow__c"],
                            "unresolved_external_dependencies": [],
                        },
                        "telemetry": {"unresolved_binding_count": 1},
                    },
                },
            },
            "salesforce_metadata": {"objects": []},
        }
    )

    assert package["metadata_grounding"]["upstream_defects"][0]["raw"] == "Legacy_Workflow__c"
    assert package["metadata_grounding"]["unresolved"] == []
    assert "upstream_metadata_evidence_missing:Legacy_Workflow__c" in package["blockers"]
    assert not any(blocker.startswith("unresolved_metadata_binding:") for blocker in package["blockers"])


def test_case_triage_micro_actions_are_grouped_into_cohesive_contracts():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-case-triage",
                "title": "Case Triage & Routing Agent",
                "automation_type": "hybrid",
                "agent_opportunity": {
                    "agent_name": "Case Triage & Routing Agent",
                    "agent_type": "headless",
                    "description": "Classifies, prioritizes, and routes support cases.",
                    "topics": [
                        {
                            "topic_name": "Initial Case Classification",
                            "description": "Classify inbound cases.",
                            "reasoning_type": "hybrid",
                            "actions_needed": [
                                "Read Case.Subject",
                                "Read Case.Description",
                                "Apply NLP classification model",
                                "Update Case.Category__c",
                            ],
                        },
                        {
                            "topic_name": "Priority Determination",
                            "description": "Determine support priority.",
                            "reasoning_type": "hybrid",
                            "actions_needed": [
                                "Read Case.Severity__c",
                                "Read Account.Tier__c",
                                "Compute priority using business rules",
                                "Update Case.Priority",
                            ],
                        },
                        {
                            "topic_name": "Queue Assignment",
                            "description": "Assign the case to the right queue.",
                            "reasoning_type": "deterministic",
                            "actions_needed": [
                                "Read Case.Category__c",
                                "Read Case.Priority",
                                "Lookup queue mapping",
                                "Update Case.OwnerId",
                            ],
                        },
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "binding_model_version": "metadata_binding_manifest_v1",
                        "bindings": [
                            {
                                "ref_type": "object",
                                "api_name": "Case",
                                "object_api_name": "Case",
                                "operation": "create",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case"],
                            },
                            *[
                                {
                                    "ref_type": "field",
                                    "api_name": f"Case.{field}",
                                    "object_api_name": "Case",
                                    "field_api_name": field,
                                    "operation": operation,
                                    "source": "step_touchpoint",
                                    "confidence": 1.0,
                                    "status": "validated",
                                    "evidence_ids": ["process:proc-case", "step:step-case"],
                                }
                                for field, operation in [
                                    ("Subject", "read"),
                                    ("Description", "read"),
                                    ("Severity__c", "read"),
                                    ("Category__c", "update"),
                                    ("Priority", "update"),
                                    ("OwnerId", "update"),
                                ]
                            ],
                            {
                                "ref_type": "field",
                                "api_name": "Account.Tier__c",
                                "object_api_name": "Account",
                                "field_api_name": "Tier__c",
                                "operation": "read",
                                "source": "step_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case", "step:step-account"],
                            },
                        ],
                        "advisory_bindings": [],
                        "unresolved_bindings": [],
                        "quality_gates": {
                            "agent_ready": True,
                            "missing_evidence": [],
                            "unresolved_external_dependencies": [],
                        },
                        "telemetry": {"bindings_from_process_touchpoints": 1},
                    },
                },
            },
            "salesforce_metadata": {
                "objects": [
                    {
                        "api_name": "Case",
                        "label": "Case",
                        "fields": [
                            "Subject",
                            "Description",
                            "Severity__c",
                            "Category__c",
                            "Priority",
                            "OwnerId",
                        ],
                    },
                    {
                        "api_name": "Account",
                        "label": "Account",
                        "fields": ["Tier__c"],
                    },
                ]
            },
        }
    )

    action_names = {action["name"] for action in package["action_contracts"]}
    micro_action_names = {
        "ReadCaseSubject",
        "ReadCaseDescription",
        "ReadCaseSeverity",
        "ReadCaseCategory",
        "ReadCasePriority",
        "UpdateCaseCategory",
        "UpdateCasePriority",
        "UpdateCaseOwnerId",
    }

    assert len(package["action_contracts"]) <= 4
    assert action_names.isdisjoint(micro_action_names)
    assert {"LoadCaseTriageContext", "ClassifyCase", "ApplyCaseTriageDecision"} <= action_names
    assert all(action["common_name"] for action in package["action_contracts"])
    assert all(action["source_group_id"] for action in package["action_contracts"])
    assert all(action["validated_bindings"] for action in package["action_contracts"])

    context_action = next(a for a in package["action_contracts"] if a["name"] == "LoadCaseTriageContext")
    write_action = next(a for a in package["action_contracts"] if a["name"] == "ApplyCaseTriageDecision")

    assert context_action["capability_type"] == "read_context"
    assert {op["field_api_name"] for op in context_action["operations"]} >= {
        "Subject",
        "Description",
        "Severity__c",
    }
    assert write_action["capability_type"] == "writeback"
    assert {op["field_api_name"] for op in write_action["operations"]} >= {
        "Category__c",
        "Priority",
        "OwnerId",
    }
    assert set(write_action["permissions"]) == {"Case:read", "Case:update"}
    assert package["blockers"] == []


def test_read_only_contracts_do_not_inherit_create_permission_from_triggers():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-triggered-case",
                "title": "Case Development Orchestrator",
                "automation_type": "agentic",
                "agent_opportunity": {
                    "agent_name": "Case Development Orchestrator",
                    "agent_type": "headless",
                    "description": "Reviews newly created cases and decides whether development work is needed.",
                    "topics": [
                        {
                            "topic_name": "Issue Triage",
                            "description": "Evaluate new Cases.",
                            "reasoning_type": "agentic",
                            "actions_needed": ["Read Case record", "Classify Case"],
                        }
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "binding_model_version": "metadata_binding_manifest_v1",
                        "bindings": [
                            {
                                "ref_type": "object",
                                "api_name": "Case",
                                "object_api_name": "Case",
                                "operation": "create",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case"],
                            }
                        ],
                        "advisory_bindings": [],
                        "unresolved_bindings": [],
                        "quality_gates": {
                            "agent_ready": True,
                            "missing_evidence": [],
                            "unresolved_external_dependencies": [],
                        },
                    },
                },
            },
            "salesforce_metadata": {"objects": [{"api_name": "Case", "label": "Case"}]},
        }
    )

    context_action = next(a for a in package["action_contracts"] if a["capability_type"] == "read_context")
    evaluate_action = next(a for a in package["action_contracts"] if a["capability_type"] == "reasoning")

    assert context_action["target_type"] == "apex"
    assert evaluate_action["target_type"] == "apex"
    assert context_action["permissions"] == ["Case:read"]
    assert evaluate_action["permissions"] == ["Case:read"]
    assert "Case:create" not in context_action["permissions"]
    assert "Case:create" not in evaluate_action["permissions"]


def test_action_contracts_expose_field_bindings_quality_and_apex_mode():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-field-quality",
                "title": "Case Triage Agent",
                "automation_type": "agentic",
                "agent_opportunity": {
                    "agent_name": "Case Triage Agent",
                    "agent_type": "headless",
                    "description": "Classifies and updates cases.",
                    "topics": [
                        {
                            "topic_name": "Case Triage",
                            "description": "Classify and update Case fields.",
                            "reasoning_type": "agentic",
                            "actions_needed": ["Read Case.Subject", "Update Case.Priority"],
                        }
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "binding_model_version": "metadata_binding_manifest_v1",
                        "bindings": [
                            {
                                "ref_type": "object",
                                "api_name": "Case",
                                "object_api_name": "Case",
                                "operation": "read",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case"],
                            },
                            {
                                "ref_type": "field",
                                "api_name": "Case.Subject",
                                "object_api_name": "Case",
                                "field_api_name": "Subject",
                                "operation": "read",
                                "source": "step_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case", "step:step-case"],
                            },
                            {
                                "ref_type": "field",
                                "api_name": "Case.Priority",
                                "object_api_name": "Case",
                                "field_api_name": "Priority",
                                "operation": "update",
                                "source": "step_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case", "step:step-case"],
                            },
                        ],
                        "advisory_bindings": [],
                        "unresolved_bindings": [],
                        "quality_gates": {
                            "agent_ready": True,
                            "missing_evidence": [],
                            "unresolved_external_dependencies": [],
                        },
                    },
                },
            },
            "salesforce_metadata": {
                "objects": [
                    {
                        "api_name": "Case",
                        "label": "Case",
                        "fields": [
                            {"api_name": "Subject", "label": "Subject", "field_type": "string"},
                            {"api_name": "Priority", "label": "Priority", "field_type": "picklist"},
                        ],
                    }
                ]
            },
        }
    )

    context_action = next(a for a in package["action_contracts"] if a["capability_type"] == "read_context")
    write_action = next(a for a in package["action_contracts"] if a["capability_type"] == "writeback")

    assert context_action["implementation_status"] == "bounded_candidate"
    assert context_action["apex_generation_mode"] == "bounded_apex"
    assert context_action["read_fields"] == [{"object_api_name": "Case", "field_api_name": "Subject"}]
    assert context_action["write_fields"] == []
    assert context_action["quality_warnings"] == []
    assert write_action["implementation_status"] == "bounded_candidate"
    assert write_action["write_fields"] == [{"object_api_name": "Case", "field_api_name": "Priority"}]
    assert write_action["permissions"] == ["Case:read", "Case:update"]


def test_existing_flow_evidence_is_dependency_not_generated_target():
    package = build_design_package_from_context(
        {
            "recommendation": {
                "id": "rec-flow-evidence",
                "title": "Case Development Orchestrator",
                "automation_type": "agentic",
                "agent_opportunity": {
                    "agent_name": "Case Development Orchestrator",
                    "agent_type": "headless",
                    "description": "Coordinates case and development item automation.",
                    "topics": [
                        {
                            "topic_name": "Development Sync",
                            "description": "Coordinate with existing automation.",
                            "reasoning_type": "agentic",
                            "actions_needed": ["Read Case.Status", "Update Development_Items__c.Phase__c"],
                        }
                    ],
                    "metadata_binding_manifest_v1": {
                        "schema_version": "metadata_binding_manifest_v1",
                        "binding_model_version": "metadata_binding_manifest_v1",
                        "bindings": [
                            {
                                "ref_type": "field",
                                "api_name": "Case.Status",
                                "object_api_name": "Case",
                                "field_api_name": "Status",
                                "operation": "read",
                                "source": "step_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-case", "step:step-case"],
                            },
                            {
                                "ref_type": "field",
                                "api_name": "Development_Items__c.Phase__c",
                                "object_api_name": "Development_Items__c",
                                "field_api_name": "Phase__c",
                                "operation": "update",
                                "source": "step_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-dev", "step:step-dev"],
                            },
                            {
                                "ref_type": "flow",
                                "api_name": "Development_Item_Case_Status_Handler",
                                "object_api_name": "Development_Items__c",
                                "operation": "trigger",
                                "source": "process_touchpoint",
                                "confidence": 1.0,
                                "status": "validated",
                                "evidence_ids": ["process:proc-dev"],
                            },
                        ],
                        "advisory_bindings": [],
                        "unresolved_bindings": [],
                        "quality_gates": {
                            "agent_ready": True,
                            "missing_evidence": [],
                            "unresolved_external_dependencies": [],
                        },
                    },
                },
            },
            "salesforce_metadata": {
                "objects": [
                    {"api_name": "Case", "label": "Case", "fields": ["Status"]},
                    {"api_name": "Development_Items__c", "label": "Development Item", "fields": ["Phase__c"]},
                ],
                "automations": [
                    {
                        "api_name": "Development_Item_Case_Status_Handler",
                        "type": "flow",
                        "label": "Development Item Case Status Handler",
                        "related_object": "Development_Items__c",
                    }
                ],
            },
        }
    )

    assert package["metadata_grounding"]["validated_dependencies"][0]["ref_type"] == "flow"
    assert {action["target_type"] for action in package["action_contracts"]} == {"apex"}
    assert all(
        action["existing_automation_dependencies"][0]["api_name"] == "Development_Item_Case_Status_Handler"
        for action in package["action_contracts"]
    )
