def test_seeded_registry_and_workspace(client):
    standards = client.get("/api/v1/standards")
    assert standards.status_code == 200
    assert len(standards.json()) == 41
    assert standards.json()[0]["code"] == "MM.1"
    assert standards.json()[-1]["code"] == "MM.41"

    standard = client.get("/api/v1/standards/MM.5")
    assert standard.status_code == 200
    assert standard.json()["me_count"] == 4
    assert standard.json()["esr_me_count"] == 4

    mes = client.get("/api/v1/measurable-elements")
    assert mes.status_code == 200
    assert len(mes.json()) == 266
    assert mes.json()[0]["me_id"] == "MM.1.1"
    assert mes.json()[-1]["me_id"] == "MM.41.12"

    workspace = client.get("/api/v1/measurable-elements/MM.5.2/workspace")
    assert workspace.status_code == 200
    body = workspace.json()
    assert body["workspace_state"]["nested_clause_count"] == 9
    assert body["workspace_state"]["document_candidate_count"] >= 1
