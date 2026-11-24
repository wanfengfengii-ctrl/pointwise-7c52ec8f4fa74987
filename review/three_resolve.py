from bisect import bisect_right
from dataclasses import dataclass

from review.confirmations import BoundConfirmation
from review.resolve import NoCompatibleAlignment, _shortest_distances
from issue.three_packet import ThreeDraftEvidence


class RoundGraph:
    def __init__(self, nodes: tuple[tuple[int, int], ...], edges: tuple[tuple[int, int, int], ...]):
        self.nodes = nodes
        self.edges = edges
        self.end = len(nodes) + 1

    def solve(self, mandatory: frozenset[int]):
        end = self.end
        ordered = sorted(mandatory) + [end]
        allowed = tuple(
            (source, target, weight) for source, target, weight in self.edges
            if target <= ordered[bisect_right(ordered, source)]
        )
        forward = _shortest_distances(allowed, 0)
        if end not in forward:
            raise NoCompatibleAlignment('the confirmations cannot continue through one round')
        backward = _shortest_distances(allowed, end, reverse=True)
        cost = forward[end]
        optimal_edges = tuple(
            (source, target) for source, target, weight in allowed
            if source in forward and target in backward
            and forward[source] + weight + backward[target] == cost
        )
        return cost, optimal_edges


@dataclass(frozen=True)
class ThreeDraftAlignment:
    cost: int
    evidence: ThreeDraftEvidence
    first_usable: frozenset[int]
    second_usable: frozenset[int]
    first_edges: tuple[tuple[int, int], ...]
    second_edges: tuple[tuple[int, int], ...]


def _graphs(evidence: ThreeDraftEvidence) -> tuple[RoundGraph, RoundGraph]:
    return (RoundGraph(evidence.first_nodes, evidence.first_edges),
            RoundGraph(evidence.second_nodes, evidence.second_edges))


def _confirmation_witnesses(
    evidence: ThreeDraftEvidence,
    confirmations: tuple[BoundConfirmation, ...],
) -> tuple[tuple[int, int, frozenset[int]], ...]:
    """Each entry is (old public index, new public index, shared middle
    occurrences) for one distinct, sorted confirmation pair."""
    first_middles_by_old: dict[int, set[int]] = {}
    for i, middle in evidence.first_nodes:
        first_middles_by_old.setdefault(i, set()).add(middle)
    second_middles_by_new: dict[int, set[int]] = {}
    for j, middle in evidence.second_nodes:
        second_middles_by_new.setdefault(j, set()).add(middle)
    groups = []
    seen = set()
    for item in confirmations:
        pair = item.pair
        if pair in seen:
            continue
        seen.add(pair)
        old_i, new_j = pair
        shared = first_middles_by_old.get(old_i, set()) & second_middles_by_new.get(new_j, set())
        if not shared:
            raise NoCompatibleAlignment('a confirmed pair cannot share one middle occurrence')
        groups.append((old_i, new_j, frozenset(shared)))
    return tuple(groups)


def _unconfirmed_alignment(evidence: ThreeDraftEvidence) -> ThreeDraftAlignment:
    first, second = _graphs(evidence)
    f_cost, f_edges = first.solve(frozenset())
    s_cost, s_edges = second.solve(frozenset())
    return ThreeDraftAlignment(
        f_cost + s_cost, evidence,
        frozenset(target for _source, target in f_edges if target < first.end),
        frozenset(target for _source, target in s_edges if target < second.end),
        f_edges, s_edges,
    )


def _enumerate_chains(groups):
    """All witness chains; every chain is a tuple of (first node, second
    node, middle ordinal) with strictly increasing middle ordinals."""
    chains: list[tuple] = [()]
    for old_i, new_j, middles in groups:
        extended = []
        choices = sorted(middles)
        for chain in chains:
            floor = chain[-1][2] if chain else -1
            for middle in choices:
                if middle > floor:
                    extended.append(chain + ((old_i, new_j, middle),))
        if not extended:
            raise NoCompatibleAlignment('the confirmations cannot coexist in one complete alignment')
        chains = extended
    return chains


def _confirmed_alignment(
    evidence: ThreeDraftEvidence,
    groups: tuple[tuple[int, int, frozenset[int]], ...],
) -> ThreeDraftAlignment:
    first, second = _graphs(evidence)
    first_index = {(i, middle): node for node, (i, middle) in enumerate(evidence.first_nodes, start=1)}
    second_index = {(j, middle): node for node, (j, middle) in enumerate(evidence.second_nodes, start=1)}
    options = []
    for chain in _enumerate_chains(groups):
        f_nodes = frozenset(first_index[(old_i, middle)] for old_i, _new_j, middle in chain)
        s_nodes = frozenset(second_index[(new_j, middle)] for _old_i, new_j, middle in chain)
        f_cost, f_edges = first.solve(f_nodes)
        s_cost, s_edges = second.solve(s_nodes)
        options.append((f_cost + s_cost, f_edges, s_edges))
    minimum = min(cost for cost, _f, _s in options)
    winners = [option for option in options if option[0] == minimum]
    f_edges = tuple(sorted({edge for _cost, f_edges, _s in winners for edge in f_edges}))
    s_edges = tuple(sorted({edge for _cost, _f, s_edges in winners for edge in s_edges}))
    return ThreeDraftAlignment(
        minimum, evidence,
        frozenset(target for _source, target in f_edges if target < first.end),
        frozenset(target for _source, target in s_edges if target < second.end),
        f_edges, s_edges,
    )


def resolve_three_draft_alignment(
    evidence: ThreeDraftEvidence,
    confirmations: tuple[BoundConfirmation, ...],
) -> ThreeDraftAlignment:
    if not confirmations:
        return _unconfirmed_alignment(evidence)
    groups = _confirmation_witnesses(evidence, confirmations)
    return _confirmed_alignment(evidence, groups)


def _skippable_nodes(graph: RoundGraph, optimal_edges: tuple[tuple[int, int], ...],
                     carried: dict[int, int]) -> set[int]:
    """End nodes reachable on an optimal path without visiting any node that
    carries the annotated public word."""
    reachable = {0}
    for source, target in optimal_edges:
        if source in reachable and target not in carried:
            reachable.add(target)
    return reachable


def three_draft_landings(
    alignment: ThreeDraftAlignment,
    old_index: int,
    new_public_count: int,
) -> tuple[tuple[int, ...], bool]:
    evidence = alignment.evidence
    first, second = _graphs(evidence)
    first_carry = {
        node: middle for node, (i, middle) in enumerate(evidence.first_nodes, start=1)
        if i == old_index
    }
    # A public landing exists only when an optimal first-round path reaches an
    # anchor carrying the old word, that middle occurrence stays usable in the
    # second round, and its second-round anchor ends at a public new word.
    reachable_middles = {
        middle for node, middle in first_carry.items() if node in alignment.first_usable
    }
    second_anchor = {
        node: (j, middle) for node, (j, middle) in enumerate(evidence.second_nodes, start=1)
    }
    public_landings = set()
    for node in alignment.second_usable:
        j, middle = second_anchor[node]
        if middle in reachable_middles and j < new_public_count:
            public_landings.add(j)
    # If an optimal first-round alignment never matches the old public word,
    # the annotation cannot continue to any final word, public or private.
    first_skip = _skippable_nodes(first, alignment.first_edges, first_carry)
    can_omit = first.end in first_skip
    return tuple(sorted(public_landings)), can_omit