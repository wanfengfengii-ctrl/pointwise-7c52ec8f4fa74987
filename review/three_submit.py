from archive.records import ArchiveEntry
from archive.sign import sign_decision
from issue.receipts import ReceiptStore
from issue.three_packet import ThreeDraftPacket
from archive.transactions import ArchiveStore
from review.requests import ReviewRequest
from review.three_requests import bind_three_draft_confirmations, bind_three_draft_request
from review.three_resolve import resolve_three_draft_alignment
from review.three_results import build_three_draft_decision


def submit_three_draft_review(
    receipts: ReceiptStore,
    archive: ArchiveStore,
    request: ReviewRequest,
) -> ArchiveEntry:
    if not isinstance(request, ReviewRequest) or not isinstance(request.packet_id, str) or not request.packet_id.strip():
        raise ValueError('review requires a packet identifier')
    received = receipts.get_received(request.packet_id)
    if received is None:
        raise ValueError('packet has not been received')
    packet = received.packet
    if not isinstance(packet, ThreeDraftPacket):
        raise ValueError('this review entry only accepts three-draft packets')
    annotation, old_index = bind_three_draft_request(packet, request)
    confirmations = bind_three_draft_confirmations(packet, request.confirmations)
    alignment = resolve_three_draft_alignment(packet.evidence, confirmations)
    decision = build_three_draft_decision(
        packet, received.receipt.body_digest, received.receipt.receipt_id,
        annotation, old_index, confirmations, alignment,
    )
    return sign_decision(archive, decision)
