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
            "operations": ["read", "update"],
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
