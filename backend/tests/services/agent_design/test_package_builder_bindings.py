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
