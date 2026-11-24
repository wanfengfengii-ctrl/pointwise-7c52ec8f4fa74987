from issue.alignment_evidence import _gap_matches
from issue.packet import PublishedExcerpt
from issue.three_packet import ThreeDraftEvidence
from revisions.model import Revision


def _ordered_arcs(positions: tuple[tuple[int, int], ...]):
    for source, (start_i, start_j) in enumerate(positions[:-1]):
        for target in range(source + 1, len(positions)):
            end_i, end_j = positions[target]
            if start_i < end_i and start_j < end_j:
                yield source, target


def _node_pairs(public_values: tuple[str, ...], other_values: tuple[str, ...]):
    other_positions: dict[str, list[int]] = {}
    for ordinal, value in enumerate(other_values):
        other_positions.setdefault(value, []).append(ordinal)
    return tuple(
        (public_index, ordinal)
        for public_index, value in enumerate(public_values)
        for ordinal in other_positions.get(value, ())
    )


def _round_graph(
    left_revision_values: tuple[str, ...],
    excerpt: PublishedExcerpt,
    other_values: tuple[str, ...],
):
    """One round's shortest-path graph in full-revision ordinal space.

    Nodes pair a public excerpt word (by excerpt index) with a matching
    full-revision ordinal on the other side. Gap weights reuse the two-draft
    DP; matches that start on a public excerpt occurrence are excluded from
    gaps because they appear as graph nodes instead.
    """
    public_ordinals = tuple(word.ordinal for word in excerpt.words)
    public_values = tuple(word.value for word in excerpt.words)
    blocked = set(public_ordinals)
    indexed_nodes = _node_pairs(public_values, other_values)
    positions = ((-1, -1),) + tuple(
        (public_ordinals[public_index], other_ordinal)
        for public_index, other_ordinal in indexed_nodes
    ) + ((len(left_revision_values), len(other_values)),)
    edges = []
    last_source = None
    for source, target in _ordered_arcs(positions):
        i, j = positions[source]
        if source != last_source:
            best = _gap_matches(left_revision_values, other_values, i, j, blocked, set())
            last_source = source
        end_i, end_j = positions[target]
        rows, cols = end_i - i - 1, end_j - j - 1
        weight = rows + cols - 2 * best[rows][cols]
        edges.append((source, target, weight))
    return indexed_nodes, tuple(edges)


def build_three_draft_evidence(
    old_revision: Revision,
    middle_revision: Revision,
    new_revision: Revision,
    old_excerpt: PublishedExcerpt,
    new_excerpt: PublishedExcerpt,
) -> ThreeDraftEvidence:
    old = tuple(word.value for word in old_revision.words)
    middle = tuple(word.value for word in middle_revision.words)
    new = tuple(word.value for word in new_revision.words)
    first_nodes, first_edges = _round_graph(old, old_excerpt, middle)
    second_nodes, second_edges = _round_graph(new, new_excerpt, middle)
    return ThreeDraftEvidence(len(middle), middle, first_nodes, first_edges,
                              second_nodes, second_edges)
