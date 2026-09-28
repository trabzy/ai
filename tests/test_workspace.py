import pytest

from jarvis.tools import builtin, registry, workspace


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtin, "DATA_DIR", tmp_path)
    yield


def test_workspace_tools_are_registered():
    names = {spec["name"] for spec in registry.specs()}
    assert {"create_project", "add_tasks", "complete_task", "save_brief"} <= names


def test_project_lifecycle():
    assert "Created business P001" in workspace.create_project("Coffee Cart", "business", "Mobile espresso.")
    workspace.add_tasks("coffee", [{"text": "Price a cart", "priority": "high"}, {"text": "Get permit"}])
    workspace.complete_task("P001", "T1")
    workspace.log_decision("Coffee Cart", "Start at farmers markets", "Low rent, high foot traffic")
    workspace.save_brief("P001", "SWOT", "## Strengths\n- Low overhead")

    detail = workspace.get_project("P001")
    assert "[x] T1 [high] Price a cart" in detail
    assert "[ ] T2 [medium] Get permit" in detail
    assert "Start at farmers markets" in detail
    assert "SWOT" in workspace.read_brief("coffee", "swot")

    snap = workspace.snapshot()["projects"][0]
    assert (snap["tasks_done"], snap["tasks_total"]) == (1, 2)


def test_ideas_default_to_idea_status_and_listing_filters():
    workspace.create_project("AI tutor", "idea", "Personal tutor for kids.")
    workspace.create_project("Website", "project", "Rebuild the site.")
    assert "idea" in workspace.list_projects(kind="idea")
    assert "Website" not in workspace.list_projects(status="idea")


def test_ambiguous_and_missing_references_error():
    workspace.create_project("Alpha app", "project", "a")
    workspace.create_project("Alpha site", "project", "b")
    with pytest.raises(ValueError, match="ambiguous"):
        workspace.get_project("alpha")
    with pytest.raises(ValueError, match="No project"):
        workspace.get_project("zeta")


def test_duplicate_names_rejected():
    workspace.create_project("Dup", "project", "x")
    with pytest.raises(ValueError):
        workspace.create_project("dup", "idea", "y")


def test_errors_surface_through_registry():
    out = registry.execute("get_project", {"project": "nothing"})
    assert out.startswith("Error")
