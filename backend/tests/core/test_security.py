from app.core.security import extract_clerk_org_context


def test_extract_org_id_from_top_level_claim_when_o_absent():
    org_id, org_name = extract_clerk_org_context(
        {"sub": "user_123", "org_id": "org_top", "org_name": "Top Org"}
    )

    assert org_id == "org_top"
    assert org_name == "Top Org"


def test_extract_org_id_from_nested_o_claim():
    org_id, org_name = extract_clerk_org_context(
        {"sub": "user_123", "o": {"id": "org_nested", "slug": "nested-org"}}
    )

    assert org_id == "org_nested"
    assert org_name == "nested-org"


def test_org_role_is_not_used_as_tenant_context():
    org_id, org_name = extract_clerk_org_context(
        {"sub": "user_123", "org_role": "org_wrong:admin"}
    )

    assert org_id is None
    assert org_name is None
