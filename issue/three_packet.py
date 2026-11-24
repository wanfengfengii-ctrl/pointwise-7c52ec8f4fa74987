from dataclasses import dataclass

from issue.packet import ExcerptIdentity, PublishedExcerpt


@dataclass(frozen=True)
class ThreeDraftEvidence:
    # Each round keeps a v1-style shortest-path graph. The first-round graph
    # joins a public old position to a middle occurrence; the second joins a
    # middle occurrence to a public new position. A continuation is valid only
    # when both rounds name the same middle occurrence. The anonymous middle
    # word values travel inside this evidence payload, while middle word
    # identifiers, codes and provenance remain at the source desk.
    middle_size: int
    middle_values: tuple[str, ...]
    first_nodes: tuple[tuple[int, int], ...]
    first_edges: tuple[tuple[int, int, int], ...]
    second_nodes: tuple[tuple[int, int], ...]
    second_edges: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class ThreeDraftPacket:
    packet_id: str
    old: PublishedExcerpt
    middle_revision_id: str
    new: PublishedExcerpt
    evidence: ThreeDraftEvidence


@dataclass(frozen=True)
class ThreeDraftProvenance:
    packet_id: str
    body_digest: str
    old: ExcerptIdentity
    new: ExcerptIdentity
    middle_revision_id: str
    receipt_id: str
