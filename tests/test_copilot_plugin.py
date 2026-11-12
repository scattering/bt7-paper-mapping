import json
from pathlib import Path

from tas_copilot_contracts import ToolCall, ToolResultStatus

from bt7_paper_mapping.copilot_plugin import get_tool_specs, run_tool
from bt7_paper_mapping.heuristics import map_paper_to_experiments


def _paper():
    return {
        "paper_id": "paper-ho2ti2o7",
        "title": "BT-7 measurements of Ho2Ti2O7",
        "year": 2020,
        "text": "NCNR BT-7 proposal 26983 measured Ho2Ti2O7 in September 2020.",
        "authors": ["A. Scientist", "B. User"],
    }


def _experiments():
    return [
        {
            "experiment_id": "exp-26983",
            "proposal_id": "26983",
            "sample": "Ho2Ti2O7",
            "principal_investigator": "Scientist",
            "start_date": "2020-09-01",
        },
        {
            "experiment_id": "exp-other",
            "proposal_id": "11111",
            "sample": "MnO",
            "start_date": "2011-01-01",
        },
    ]


def test_tool_spec_exposes_mapping_tool():
    specs = get_tool_specs()
    assert [(spec.namespace, spec.name) for spec in specs] == [("tas.paper_mapping", "map_paper_to_experiments")]
    assert specs[0].permissions_required[0].value == "read_only"


def test_heuristics_return_paper_experiment_link():
    links = map_paper_to_experiments(_paper(), _experiments())

    assert len(links) == 1
    assert links[0].paper_id == "paper-ho2ti2o7"
    assert links[0].experiment_id == "exp-26983"
    assert links[0].confidence > 0.6
    assert links[0].status == "candidate"
    assert links[0].evidence


def test_plugin_returns_typed_tool_result():
    result = run_tool(
        ToolCall(
            tool_namespace="tas.paper_mapping",
            tool_name="map_paper_to_experiments",
            arguments={"paper": _paper(), "experiments": _experiments()},
            caller_workflow="test",
        )
    )

    assert result.status == ToolResultStatus.success
    assert result.output["link_count"] == 1
    assert result.output["links"][0]["experiment_id"] == "exp-26983"


def test_legacy_generated_golden_mapping_fixture_ranks_expected_experiment():
    fixtures = json.loads((Path(__file__).parent / "fixtures" / "golden_mappings.json").read_text())

    assert len(fixtures) >= 10
    for fixture in fixtures:
        links = map_paper_to_experiments(fixture["paper"], fixture["experiments"], threshold=0.01)

        assert links
        assert links[0].experiment_id == fixture["expected_top_experiment_id"]
        assert any("author/participant overlap" in item for item in links[0].evidence)
