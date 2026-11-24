from dataclasses import dataclass

from issue.packet import PacketWord
from issue.three_packet import ThreeDraftPacket, ThreeDraftProvenance
from review.confirmations import BoundConfirmation, Confirmation
from review.requests import OldAnnotation
from review.three_resolve import ThreeDraftAlignment, three_draft_landings


@dataclass(frozen=True)
class ThreeDraftAnnotationOutcome:
    annotation_id: str
    old_word: PacketWord
    targets: tuple[PacketWord, ...]
    can_have_no_public_landing: bool


@dataclass(frozen=True)
class ThreeDraftReviewDecision:
    packet: ThreeDraftProvenance
    cost: int
    annotations: tuple[OldAnnotation, ...]
    confirmations: tuple[Confirmation, ...]
    outcomes: tuple[ThreeDraftAnnotationOutcome, ...]


def build_three_draft_decision(
    packet: ThreeDraftPacket,
    body_digest: str,
    receipt_id: str,
    annotation: OldAnnotation,
    old_index: int,
    confirmations: tuple[BoundConfirmation, ...],
    alignment: ThreeDraftAlignment,
) -> ThreeDraftReviewDecision:
    targets, can_omit = three_draft_landings(
        alignment, old_index, len(packet.new.words))
    outcome = ThreeDraftAnnotationOutcome(
        annotation.annotation_id,
        packet.old.words[old_index],
        tuple(packet.new.words[j] for j in targets),
        can_omit,
    )
    provenance = ThreeDraftProvenance(
        packet.packet_id, body_digest, packet.old.identity, packet.new.identity,
        packet.middle_revision_id, receipt_id,
    )
    return ThreeDraftReviewDecision(
        provenance, alignment.cost, (annotation,),
        tuple(item.confirmation for item in confirmations), (outcome,),
    )
