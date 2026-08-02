def _create_document(client):
    response = client.post("/api/v1/documents", json={
        "code": "PIOS-TEST-001",
        "title": "Medication Management Master Plan",
        "document_type": "Policy",
        "lifecycle_status": "Draft",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_document_version_and_lifecycle(client):
    document = _create_document(client)
    doc_id = document["id"]

    version = client.post(f"/api/v1/documents/{doc_id}/versions", json={
        "version_label": "1.0",
        "status": "Approved",
        "prepared_by": "Pharmacy Quality",
        "reviewed_by": "P&T",
        "approved_by": "Hospital Director",
    })
    assert version.status_code == 201, version.text
    version_id = version.json()["id"]

    for status in ["Review", "Approved"]:
        transition = client.post(f"/api/v1/documents/{doc_id}/lifecycle", json={"to_status": status})
        assert transition.status_code == 200, transition.text
        assert transition.json()["lifecycle_status"] == status

    effective = client.post(f"/api/v1/documents/{doc_id}/lifecycle", json={
        "to_status": "Effective", "version_id": version_id, "comment": "Approved for controlled use"
    })
    assert effective.status_code == 200, effective.text
    assert effective.json()["lifecycle_status"] == "Effective"
    assert effective.json()["current_version_id"] == version_id

    link = client.post(f"/api/v1/documents/{doc_id}/links/measurable-elements", json={
        "me_id": "MM.4.1", "link_type": "Primary", "mandatory": True
    })
    assert link.status_code == 201

    detail = client.get(f"/api/v1/documents/{doc_id}")
    assert detail.status_code == 200
    assert detail.json()["versions"][0]["version_label"] == "1.0"
    assert detail.json()["me_links"][0]["me_id"] == "MM.4.1"


def test_invalid_document_transition_is_rejected(client):
    document = _create_document(client)
    response = client.post(f"/api/v1/documents/{document['id']}/lifecycle", json={"to_status": "Effective"})
    assert response.status_code == 409


def test_document_write_rbac(client):
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": "Bearer dev:collector:EvidenceCollector"},
        json={"code": "DENIED", "title": "Denied", "document_type": "Policy"},
    )
    assert response.status_code == 403
