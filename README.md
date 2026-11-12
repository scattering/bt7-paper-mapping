# BT-7 Paper Mapping

Deterministic paper-to-experiment mapping heuristics for the TAS co-pilot.

This repository owns record-linkage logic between BT-7 corpus records and BT-7 experiment/data catalogs. It does not parse raw BT-7 files, group scans, reduce data, or own the co-pilot registry. Those remain separate responsibilities.

## Plugin

The package exposes a TAS co-pilot plugin entry point:

- namespace: `tas.paper_mapping`
- tool: `map_paper_to_experiments`
- permission: `read_only`
- output: `PaperExperimentLink` records

The first implementation is deterministic. It scores explicit proposal IDs, experiment IDs, dates, sample/material names, fuzzy author/participant overlap, and experiment-title/content overlap, then returns candidate mappings with evidence and provenance.

The author/date/text-overlap heuristics were moved from the legacy BT-7 `paper_matcher.py` workflow. Small golden fixtures derived from the generated `paper_data_matches.json` report live under `tests/fixtures/`; the full generated report is not copied into this repo.

## Example

```bash
TAS_COPILOT_PLUGIN_MODULES=bt7_paper_mapping.copilot_plugin python -m tas_copilot_core.cli compare-paper-to-data paper-1
```

For direct plugin testing:

```python
from tas_copilot_contracts import ToolCall
from bt7_paper_mapping.copilot_plugin import run_tool

result = run_tool(ToolCall(
    tool_namespace="tas.paper_mapping",
    tool_name="map_paper_to_experiments",
    arguments={
        "paper": {"paper_id": "paper-1", "title": "BT-7 study", "year": 2019, "text": "Proposal 25860 on Ho2Ti2O7"},
        "experiments": [{"experiment_id": "exp-25860", "proposal_id": "25860", "sample": "Ho2Ti2O7"}],
    },
))
```

## Boundary

This package treats paper text, catalog metadata, and snippets as untrusted data. It does not execute retrieved content and does not call instrument-control software.

## Next Data Step

Move additional reviewed mappings into `tests/fixtures/golden_mappings.json` as compact paper/experiment examples with expected top candidates. Keep raw generated reports outside the repository unless they are intentionally curated and small.

## Reproducibility Tests

Install the shared contracts from the
[TASCopilot paper repository](https://github.com/scattering/tascopilot-paper)
and this package into a Python 3.11 or newer environment:

```sh
TASCOPILOT_PAPER=/absolute/path/to/tascopilot-paper
python -m pip install -e "$TASCOPILOT_PAPER/packages/tas_copilot_contracts"
python -m pip install -e . pytest
python -m pytest -q -rs
```

Tests use local fixtures. Optional upstream runtimes or explicitly supplied
archive fixtures are reported as skipped when unavailable. No instrument
connection is required. No full papers, private corpus, or development
handoff documents are included.
