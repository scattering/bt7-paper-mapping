"""TAS co-pilot plugin entry points for BT-7 paper mapping."""

from __future__ import annotations


def get_tool_specs():
    from tas_copilot_contracts import Availability, ImplementationType, PermissionLevel, SideEffectLevel, ToolSpec

    return [
        ToolSpec(
            name="map_paper_to_experiments",
            namespace="tas.paper_mapping",
            version="0.1.0",
            description="Map a paper or source chunks to candidate BT-7 experiments using deterministic record-linkage heuristics.",
            input_schema={
                "type": "object",
                "required": ["paper"],
                "properties": {
                    "paper": {"type": "object"},
                    "experiments": {"type": "array", "items": {"type": "object"}},
                    "threshold": {"type": "number"},
                },
            },
            output_schema={"type": "object"},
            side_effect_level=SideEffectLevel.none,
            availability=Availability.available,
            implementation_type=ImplementationType.python_entrypoint,
            required_dependencies=["bt7-paper-mapping"],
            preconditions=["Paper metadata or text and candidate experiment records are supplied."],
            postconditions=["No files or instrument state are modified."],
            provenance_policy="Record matched paper fields, experiment fields, score contributions, and source record identifiers.",
            permissions_required=[PermissionLevel.read_only],
            enabled_by_default=True,
            owner_repo="git@github.com:scattering/bt7-paper-mapping.git",
            documentation_url="https://github.com/scattering/bt7-paper-mapping",
            maintainer="William Ratcliff",
        )
    ]


def run_tool(call):
    from tas_copilot_contracts import ToolError, ToolResult, ToolResultStatus

    if (call.tool_namespace, call.tool_name) != ("tas.paper_mapping", "map_paper_to_experiments"):
        return ToolResult(
            status=ToolResultStatus.validation_failed,
            errors=[ToolError(code="unknown_tool", message=f"Unknown paper mapping tool {call.tool_namespace}.{call.tool_name}")],
            tool_name=call.tool_name,
            tool_namespace=call.tool_namespace,
            tool_version="0.1.0",
        )

    try:
        from .heuristics import map_paper_to_experiments

        paper = call.arguments.get("paper") or {}
        experiments = call.arguments.get("experiments") or []
        threshold = float(call.arguments.get("threshold", 0.2))
        links = map_paper_to_experiments(paper, experiments, threshold=threshold)
        return ToolResult(
            status=ToolResultStatus.success,
            output={
                "paper_id": str(paper.get("paper_id") or paper.get("id") or ""),
                "links": [link.model_dump(mode="json") for link in links],
                "link_count": len(links),
                "mapping_method": "deterministic_bt7_record_linkage_v0",
            },
            provenance=[prov for link in links for prov in link.provenance],
            tool_name="map_paper_to_experiments",
            tool_namespace="tas.paper_mapping",
            tool_version="0.1.0",
        )
    except Exception as exc:
        return ToolResult(
            status=ToolResultStatus.error,
            errors=[ToolError(code=exc.__class__.__name__, message=str(exc))],
            tool_name="map_paper_to_experiments",
            tool_namespace="tas.paper_mapping",
            tool_version="0.1.0",
        )
