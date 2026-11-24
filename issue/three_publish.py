from uuid import uuid4

from excerpts.store import ExcerptStore
from issue.publish import _published_excerpt
from issue.three_envelope import seal_three_draft_packet
from issue.three_evidence import build_three_draft_evidence
from issue.three_packet import ThreeDraftPacket
from revisions.model import require_identifier
from revisions.store import RevisionStore


def publish_three_draft_packet(
    revisions: RevisionStore,
    excerpts: ExcerptStore,
    old_excerpt_id: str,
    middle_revision_id: str,
    new_excerpt_id: str,
    *,
    packet_id: str | None = None,
) -> str:
    require_identifier(old_excerpt_id)
    require_identifier(middle_revision_id)
    require_identifier(new_excerpt_id)
    if packet_id is None:
        packet_id = uuid4().hex
    require_identifier(packet_id)
    old_excerpt, new_excerpt = excerpts.get(old_excerpt_id), excerpts.get(new_excerpt_id)
    if old_excerpt is None or new_excerpt is None:
        raise ValueError('unknown excerpt')
    middle_revision = revisions.get(middle_revision_id)
    if middle_revision is None:
        raise ValueError('middle revision is unavailable')
    old_revision, new_revision = revisions.get(old_excerpt.revision_id), revisions.get(new_excerpt.revision_id)
    if old_revision is None or new_revision is None:
        raise ValueError('excerpt revision is unavailable')
    manuscript_id = old_revision.manuscript_id
    revision_ids = {old_revision.revision_id, middle_revision.revision_id, new_revision.revision_id}
    if len(revision_ids) != 3 or middle_revision.manuscript_id != manuscript_id or new_revision.manuscript_id != manuscript_id:
        raise ValueError('select three distinct revisions of the same manuscript')
    if old_excerpt_id == new_excerpt_id:
        raise ValueError('select two distinct excerpts')
    old = _published_excerpt(old_revision, old_excerpt)
    new = _published_excerpt(new_revision, new_excerpt)
    evidence = build_three_draft_evidence(old_revision, middle_revision, new_revision, old, new)
    packet = ThreeDraftPacket(packet_id, old, middle_revision_id, new, evidence)
    return seal_three_draft_packet(packet)
