import hashlib
import hmac
import json
from dataclasses import asdict

from issue.envelope import (
    EnvelopeMismatch, _fields, _read_excerpt, _text, canonical_json,
)
from issue.packet import Packet
from issue.three_packet import ThreeDraftEvidence, ThreeDraftPacket


def _digest(body: str) -> str:
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def three_draft_declaration(packet: ThreeDraftPacket) -> dict:
    return {
        'packet_id': packet.packet_id,
        'old': asdict(packet.old.identity),
        'middle_revision_id': packet.middle_revision_id,
        'new': asdict(packet.new.identity),
    }


def seal_three_draft_packet(packet: ThreeDraftPacket) -> str:
    body = canonical_json(asdict(packet))
    return canonical_json({
        'version': 2,
        'declaration': three_draft_declaration(packet),
        'body': body,
        'sha256': _digest(body),
    })


def _integer_rows(rows: object, width: int) -> tuple:
    if type(rows) is not list:
        raise EnvelopeMismatch('invalid evidence rows')
    if any(type(row) is not list or len(row) != width or
           any(type(value) is not int or value < 0 for value in row) for row in rows):
        raise EnvelopeMismatch('invalid evidence coordinate or cost')
    return tuple(tuple(row) for row in rows)


def _expected_nodes(public_values: tuple[str, ...], middle_values: tuple[str, ...]):
    positions: dict[str, list[int]] = {}
    for ordinal, value in enumerate(middle_values):
        positions.setdefault(value, []).append(ordinal)
    return tuple(
        (i, ordinal)
        for i, value in enumerate(public_values)
        for ordinal in positions.get(value, ())
    )


def _read_round_evidence(nodes, edges, public_values, middle_values, public_size, middle_size):
    expected = _expected_nodes(public_values, middle_values)
    if nodes != expected:
        raise EnvelopeMismatch('evidence nodes do not identify the round matches')
    positions = ((-1, -1),) + tuple(
        (public_index, other_ordinal) for public_index, other_ordinal in nodes
    ) + ((public_size, middle_size),)
    expected_arcs = []
    for source, (start_i, start_j) in enumerate(positions[:-1]):
        for target in range(source + 1, len(positions)):
            end_i, end_j = positions[target]
            if start_i < end_i and start_j < end_j:
                expected_arcs.append((source, target))
    for edge, arc in zip(edges, expected_arcs, strict=True):
        if edge[:2] != arc:
            raise EnvelopeMismatch('invalid evidence edge order or endpoints')


def _read_three_draft_evidence(data: dict, packet: ThreeDraftPacket) -> ThreeDraftEvidence:
    _fields(data, 'middle_size', 'middle_values', 'first_nodes', 'first_edges',
            'second_nodes', 'second_edges')
    middle_size = data['middle_size']
    if type(middle_size) is not int or middle_size < 0:
        raise EnvelopeMismatch('invalid middle revision size')
    middle_values = data['middle_values']
    if type(middle_values) is not list or len(middle_values) != middle_size:
        raise EnvelopeMismatch('middle values do not match the middle revision size')
    if any(not isinstance(value, str) or not value for value in middle_values):
        raise EnvelopeMismatch('middle values must be nonempty strings')
    middle_values = tuple(middle_values)
    first_nodes = _integer_rows(data['first_nodes'], 2)
    first_edges = _integer_rows(data['first_edges'], 3)
    second_nodes = _integer_rows(data['second_nodes'], 2)
    second_edges = _integer_rows(data['second_edges'], 3)
    _read_round_evidence(first_nodes, first_edges,
                         tuple(word.value for word in packet.old.words), middle_values,
                         len(packet.old.words), middle_size)
    _read_round_evidence(second_nodes, second_edges,
                         tuple(word.value for word in packet.new.words), middle_values,
                         len(packet.new.words), middle_size)
    return ThreeDraftEvidence(middle_size, middle_values, first_nodes, first_edges,
                              second_nodes, second_edges)


def _read_three_draft_packet(data: dict) -> ThreeDraftPacket:
    _fields(data, 'packet_id', 'old', 'middle_revision_id', 'new', 'evidence')
    _text(data['packet_id'])
    _text(data['middle_revision_id'])
    old, new = _read_excerpt(data['old']), _read_excerpt(data['new'])
    if old.identity.manuscript_id != new.identity.manuscript_id:
        raise EnvelopeMismatch('packet sides name different manuscripts')
    if (old.identity.revision_id == new.identity.revision_id
            or old.identity.revision_id == data['middle_revision_id']
            or new.identity.revision_id == data['middle_revision_id']
            or old.identity.excerpt_id == new.identity.excerpt_id):
        raise EnvelopeMismatch('packet requires three distinct revisions and two distinct excerpts')
    packet = ThreeDraftPacket(data['packet_id'], old, data['middle_revision_id'], new, None)
    evidence = _read_three_draft_evidence(data['evidence'], packet)
    return ThreeDraftPacket(packet.packet_id, old, packet.middle_revision_id, new, evidence)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise EnvelopeMismatch('duplicate JSON object key')
    return result


def open_three_draft_envelope(envelope: str) -> ThreeDraftPacket:
    try:
        if not isinstance(envelope, str):
            raise EnvelopeMismatch('envelope must be JSON text')
        outer = json.loads(envelope, object_pairs_hook=_unique_json_object)
        _fields(outer, 'version', 'declaration', 'body', 'sha256')
        if type(outer['version']) is not int or outer['version'] != 2:
            raise EnvelopeMismatch('unsupported envelope version')
        body, digest = outer['body'], outer['sha256']
        if not isinstance(body, str) or not isinstance(digest, str) or not digest.isascii():
            raise EnvelopeMismatch('missing packet body or digest')
        if not hmac.compare_digest(_digest(body), digest):
            raise EnvelopeMismatch('packet body digest does not match')
        packet = _read_three_draft_packet(json.loads(body))
        if body != canonical_json(asdict(packet)):
            raise EnvelopeMismatch('packet body is not in canonical form')
        if outer['declaration'] != three_draft_declaration(packet):
            raise EnvelopeMismatch('packet declaration does not match its body')
        return packet
    except EnvelopeMismatch:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise EnvelopeMismatch('malformed packet envelope') from exc


def open_any_envelope(envelope: str) -> Packet | ThreeDraftPacket:
    try:
        outer = json.loads(envelope)
    except (ValueError, TypeError) as exc:
        raise EnvelopeMismatch('malformed packet envelope') from exc
    if not isinstance(outer, dict) or 'version' not in outer:
        raise EnvelopeMismatch('malformed packet envelope')
    if outer['version'] == 1:
        from issue.envelope import open_envelope
        return open_envelope(envelope)
    if outer['version'] == 2:
        return open_three_draft_envelope(envelope)
    raise EnvelopeMismatch('unsupported envelope version')
