from unittest.mock import MagicMock, patch

from app.services.salesforce.metadata import pull_permission_sets


def test_pull_permission_sets_namespaces_api_names_to_avoid_collisions():
    """Managed package permission set names can collide with local permission set names."""
    sf = MagicMock()

    def fake_query(_sf, soql: str):
        if "FROM PermissionSet" in soql:
            assert "NamespacePrefix" in soql
            return [
                {
                    "Id": "0PS1",
                    "Name": "DevOps_Center",
                    "Label": "DevOps Center",
                    "Description": None,
                    "IsCustom": True,
                    "NamespacePrefix": "sf_devops",
                },
                {
                    "Id": "0PS2",
                    "Name": "DevOps_Center",
                    "Label": "DevOps Center",
                    "Description": None,
                    "IsCustom": True,
                    "NamespacePrefix": None,
                },
            ]
        if "FROM ObjectPermissions" in soql:
            return []
        raise AssertionError(f"Unexpected SOQL: {soql}")

    with patch("app.services.salesforce.metadata._rest_query_all", side_effect=fake_query):
        results = pull_permission_sets(sf)

    assert [p.api_name for p in results] == ["sf_devops__DevOps_Center", "DevOps_Center"]
    assert len({p.api_name for p in results}) == 2
