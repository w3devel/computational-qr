"""Integration helpers – convert a DependencyGraph into visual payloads.

This module bridges the dependency-intersection engine and the existing colour
geometry / 3D graph modules so that spreadsheet dependency structure can be
immediately rendered using the existing :class:`~computational_qr.core.color_geometry.ColorGeometry`
and :class:`~computational_qr.graphs.graph_3d.Graph3D` infrastructure.

Public helpers
--------------
- :func:`dependency_to_color_geometry` – build ``ColorGeometry`` +
  ``GeometryKey`` entries from a ``DependencyGraph``.
- :func:`dependency_to_graph3d` – build a semantic ``Graph3D`` from a
  ``DependencyGraph`` (source group count → z, dependency depth → y).
- :func:`build_visualization_payload` – combine both into a single JSON-safe
  dict ready for a renderer.
"""

from __future__ import annotations

import math
from typing import Iterable

from computational_qr.core.color_geometry import ColorGeometry, ColorShape, GeometryKey
from computational_qr.core.grouping_policy import DefaultTableGroupingPolicy, ShapePolicy
from computational_qr.graphs.dependency_graph import DependencyGraph, Reference
from computational_qr.graphs.graph_3d import Graph3D


# ---------------------------------------------------------------------------
# Colour geometry conversion
# ---------------------------------------------------------------------------

def dependency_to_color_geometry(
    graph: DependencyGraph,
    outputs: Iterable[Reference] | None = None,
    *,
    policy: DefaultTableGroupingPolicy | None = None,
    shape_policy: ShapePolicy | None = None,
) -> ColorGeometry:
    """Build a :class:`~computational_qr.core.color_geometry.ColorGeometry`
    from a :class:`~computational_qr.graphs.dependency_graph.DependencyGraph`.

    Each *output* reference in the graph becomes a
    :class:`~computational_qr.core.color_geometry.ColorShape` whose shape type
    and side count are determined by how many distinct source groups feed into
    it.  Each source group receives its own
    :class:`~computational_qr.core.color_geometry.GeometryKey` (legend entry).

    Parameters
    ----------
    graph:
        The dependency graph to convert.
    outputs:
        The output references to visualise.  Defaults to all outputs that have
        at least one registered formula node.
    policy:
        Grouping policy.  Defaults to :class:`~computational_qr.core.grouping_policy.DefaultTableGroupingPolicy`.
    shape_policy:
        Shape selection policy.  Defaults to :class:`~computational_qr.core.grouping_policy.ShapePolicy`.

    Returns
    -------
    ColorGeometry
        Populated with one dimension per unique source group and one shape per
        output reference.
    """
    policy = policy or DefaultTableGroupingPolicy()
    shape_policy = shape_policy or ShapePolicy()

    cg = ColorGeometry()

    # Determine outputs to process
    if outputs is None:
        # All refs that appear as outputs in formula nodes
        all_outputs: list[Reference] = list({
            node.output.ref_id: node.output
            for node in graph.formula_nodes()
        }.values())
    else:
        all_outputs = list(outputs)

    # Collect all unique source groups across all outputs and assign dimensions
    group_to_dim: dict[str, int] = {}
    for out_ref in all_outputs:
        inputs = graph.get_inputs(out_ref)
        groups = policy.group_ids(inputs)
        for gid in sorted(groups):
            if gid not in group_to_dim:
                dim_idx = cg.add_dimension(gid, unit="", min_value=0.0, max_value=1.0)
                group_to_dim[gid] = dim_idx

    # Assign a shape to each output reference
    for i, out_ref in enumerate(all_outputs):
        inputs = graph.get_inputs(out_ref)
        groups = sorted(policy.group_ids(inputs))
        k = len(groups)
        shape_type, n_sides = shape_policy.shape_for(k)

        # Position shapes evenly on a unit circle (XY plane, z=depth)
        angle = 2 * math.pi * i / max(len(all_outputs), 1)
        x = math.cos(angle)
        y = math.sin(angle)
        z = float(k)  # z encodes source group count (semantic depth)

        # Use the first source group's dimension index for colour
        dim_idx = group_to_dim[groups[0]] if groups else 0

        cg.add_shape(
            out_ref.ref_id,
            value=float(k),
            x=x,
            y=y,
            z=z,
            dimension=dim_idx,
            weight=1.0,
            shape_type=shape_type,
        )

    return cg


# ---------------------------------------------------------------------------
# Graph3D conversion
# ---------------------------------------------------------------------------

def dependency_to_graph3d(
    graph: DependencyGraph,
    outputs: Iterable[Reference] | None = None,
    *,
    policy: DefaultTableGroupingPolicy | None = None,
    tolerance: float = 1.0,
) -> Graph3D:
    """Build a semantic :class:`~computational_qr.graphs.graph_3d.Graph3D`
    from a :class:`~computational_qr.graphs.dependency_graph.DependencyGraph`.

    Axis semantics
    --------------
    - **x**: hash-based spread so nodes from different source groups separate
      horizontally.
    - **y**: dependency depth (number of hops from raw sources).
    - **z**: number of distinct source groups (*k*).

    Each output reference becomes a :class:`~computational_qr.graphs.graph_3d.DataPoint`
    with ``dimension`` = index of its primary source group.

    Parameters
    ----------
    graph:
        The dependency graph to convert.
    outputs:
        Output references to include.  Defaults to all formula outputs.
    policy:
        Grouping policy.  Defaults to :class:`~computational_qr.core.grouping_policy.DefaultTableGroupingPolicy`.
    tolerance:
        Passed through to :class:`~computational_qr.graphs.graph_3d.Graph3D`.

    Returns
    -------
    Graph3D
        Populated with one data point per output reference.
    """
    policy = policy or DefaultTableGroupingPolicy()
    g3d = Graph3D(tolerance=tolerance)

    if outputs is None:
        all_outputs: list[Reference] = list({
            node.output.ref_id: node.output
            for node in graph.formula_nodes()
        }.values())
    else:
        all_outputs = list(outputs)

    # Collect all unique source groups → dimension mapping
    all_groups: list[str] = []
    group_to_dim: dict[str, int] = {}
    for out_ref in all_outputs:
        inputs = graph.get_inputs(out_ref)
        for gid in sorted(policy.group_ids(inputs)):
            if gid not in group_to_dim:
                group_to_dim[gid] = len(all_groups)
                all_groups.append(gid)
                g3d.register_dimension(group_to_dim[gid], gid)

    for out_ref in all_outputs:
        inputs = graph.get_inputs(out_ref)
        groups = sorted(policy.group_ids(inputs))
        k = len(groups)

        # x: a deterministic spread based on primary group
        primary_group = groups[0] if groups else out_ref.ref_id
        x = float(hash(primary_group) % 1000) / 100.0

        # y: dependency depth (transitive input count as a proxy)
        all_inputs = graph.get_all_inputs(out_ref)
        y = float(len(all_inputs))

        # z: source group count
        z = float(k)

        dim_idx = group_to_dim.get(primary_group, 0)

        g3d.add_point(
            out_ref.ref_id,
            x=x,
            y=y,
            z=z,
            value=float(k),
            dimension=dim_idx,
            metadata={"source_groups": groups, "ref_type": out_ref.ref_type},
        )

    return g3d


# ---------------------------------------------------------------------------
# Combined payload
# ---------------------------------------------------------------------------

def build_visualization_payload(
    graph: DependencyGraph,
    outputs: Iterable[Reference] | None = None,
    *,
    policy: DefaultTableGroupingPolicy | None = None,
    shape_policy: ShapePolicy | None = None,
    graph3d_tolerance: float = 1.0,
) -> dict:
    """Produce a combined JSON-safe visualisation payload.

    The payload contains:

    - ``"dependency_graph"`` – serialised dependency graph.
    - ``"color_geometry"``   – :meth:`~computational_qr.core.color_geometry.ColorGeometry.to_dict` output.
    - ``"graph_3d"``         – :meth:`~computational_qr.graphs.graph_3d.Graph3D.to_dict` output.

    Parameters
    ----------
    graph:
        The dependency graph to visualise.
    outputs:
        Output references to include.  Defaults to all formula outputs.
    policy:
        Grouping policy.
    shape_policy:
        Shape-selection policy.
    graph3d_tolerance:
        Tolerance passed to the ``Graph3D`` instance.

    Returns
    -------
    dict
        JSON-safe dictionary suitable for serialisation with :func:`json.dumps`.
    """
    policy = policy or DefaultTableGroupingPolicy()
    shape_policy = shape_policy or ShapePolicy()

    outputs_list = list(outputs) if outputs is not None else None

    cg = dependency_to_color_geometry(
        graph, outputs_list, policy=policy, shape_policy=shape_policy
    )
    g3d = dependency_to_graph3d(
        graph, outputs_list, policy=policy, tolerance=graph3d_tolerance
    )

    return {
        "dependency_graph": graph.to_dict(),
        "color_geometry": cg.to_dict(),
        "graph_3d": g3d.to_dict(),
    }
