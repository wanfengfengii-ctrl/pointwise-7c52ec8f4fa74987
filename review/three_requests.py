from issue.three_packet import ThreeDraftPacket
from review.confirmations import BoundConfirmation, Confirmation
from review.requests import OldAnnotation, ReviewRequest


def bind_three_draft_request(packet: ThreeDraftPacket, request: ReviewRequest):
    if request.packet_id != packet.packet_id:
        raise ValueError('request names a different packet')
    if not isinstance(request.annotations, (tuple, list)) or len(request.annotations) != 1:
        raise ValueError('a three-draft review requires exactly one old annotation')
    annotation = request.annotations[0]
    if not isinstance(annotation, OldAnnotation) or not isinstance(annotation.annotation_id, str) \
            or not annotation.annotation_id.strip():
        raise ValueError('old annotation must have an identifier')
    lookup = {word.word_id: i for i, word in enumerate(packet.old.words)}
    if not isinstance(annotation.word_id, str) or annotation.word_id not in lookup:
        raise ValueError('old annotation does not refer to this packet’s public old side')
    return annotation, lookup[annotation.word_id]


def bind_three_draft_confirmations(
    packet: ThreeDraftPacket,
    confirmations: tuple[Confirmation, ...] | list[Confirmation],
):
    if not isinstance(confirmations, (tuple, list)):
        raise ValueError('confirmations must be a sequence, which may be empty')
    old = {word.word_id: i for i, word in enumerate(packet.old.words)}
    new = {word.word_id: i for i, word in enumerate(packet.new.words)}
    by_pair = {}
    for confirmation in confirmations:
        if not isinstance(confirmation, Confirmation):
            raise ValueError('expected a confirmation with two public word identifiers')
        old_id, new_id = confirmation.old_word_id, confirmation.new_word_id
        if not isinstance(old_id, str) or not isinstance(new_id, str) or old_id not in old or new_id not in new:
            raise ValueError('confirmation does not refer to this packet’s public sides')
        by_pair[old[old_id], new[new_id]] = confirmation
    return tuple(BoundConfirmation(by_pair[pair], pair) for pair in sorted(by_pair))
