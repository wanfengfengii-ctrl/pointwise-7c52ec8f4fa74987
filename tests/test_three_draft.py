import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from archive.read import read_report
from issue.envelope import EnvelopeMismatch
from issue.three_envelope import open_any_envelope, open_three_draft_envelope, seal_three_draft_packet
from issue.three_publish import publish_three_draft_packet
from review.confirmations import Confirmation
from review.requests import OldAnnotation, ReviewRequest
from review.submit import submit_review
from review.three_resolve import NoCompatibleAlignment
from review.three_submit import submit_three_draft_review
from three_draft_cases import CASES, offline_desk, source_desk


def _outcome(details):
    outcome = details['outcomes'][0]
    return (details['cost'],
            [target['ordinal'] for target in outcome['targets']],
            outcome['can_have_no_public_landing'])


class ThreeDraftFixtureTests(unittest.TestCase):
    def test_all_handoff_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in CASES:
                with self.subTest(case=name):
                    source_path, offline_path = Path(tmp, f'{name}-s.sqlite'), Path(tmp, f'{name}-o.sqlite')
                    with source_desk(source_path, name) as (revisions, excerpts, inputs):
                        envelope = publish_three_draft_packet(
                            revisions, excerpts, inputs.old_excerpt_id,
                            inputs.middle_revision_id, inputs.new_excerpt_id, packet_id=name)
                    with offline_desk(offline_path) as (receipts, archive):
                        receipts.accept(envelope)
                        results = []
                        for old_id in inputs.old_word_ids:
                            entry = submit_three_draft_review(
                                receipts, archive,
                                ReviewRequest(name, (OldAnnotation(f'note-{old_id}', old_id),)))
                            results.append(_outcome(entry.report.details))
                        expected_cost = {
                            'split-middle': 2, 'shared-middle': 2, 'one-slot': 2,
                            'different-witnesses': 6, 'empty-middle': 2,
                        }[name]
                        self.assertTrue(all(result[0] == expected_cost for result in results))
                        if name == 'split-middle':
                            self.assertEqual(results, [(2, [], True)])
                        elif name == 'shared-middle':
                            self.assertEqual(results, [(2, [1], True)])
                        elif name == 'one-slot':
                            self.assertEqual(results, [(2, [0, 1], True), (2, [0, 1], True)])
                        elif name == 'different-witnesses':
                            # Each old public word can reach its same-order new
                            # position in some optimum, and every annotation can
                            # also end without a public landing.
                            self.assertEqual([targets for _, targets, _ in results], [[0], [1], [2]])
                            self.assertTrue(all(can_omit for _, _, can_omit in results))
                        elif name == 'empty-middle':
                            self.assertEqual(results, [(2, [], True)])

    def test_split_middle_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'split-middle') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='split-middle')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                confirmed = submit_three_draft_review(
                    receipts, archive,
                    ReviewRequest('split-middle', (annotation,),
                                  (Confirmation(inputs.old_word_ids[0], inputs.new_word_ids[0]),)))
                self.assertEqual(_outcome(confirmed.report.details), (4, [1], False))

    def test_shared_middle_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'shared-middle') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='shared-middle')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                confirmed = submit_three_draft_review(
                    receipts, archive,
                    ReviewRequest('shared-middle', (annotation,),
                                  (Confirmation(inputs.old_word_ids[0], inputs.new_word_ids[0]),)))
                self.assertEqual(_outcome(confirmed.report.details), (2, [1], False))

    def test_one_slot_pair_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'one-slot') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='one-slot')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                # Either same-order pair alone is feasible at cost two.
                for old_id, new_id in ((inputs.old_word_ids[0], inputs.new_word_ids[0]),
                                       (inputs.old_word_ids[1], inputs.new_word_ids[1])):
                    entry = submit_three_draft_review(
                        receipts, archive,
                        ReviewRequest('one-slot', (annotation,), (Confirmation(old_id, new_id),)))
                    self.assertEqual(entry.report.details['cost'], 2)
                # Both pairs together are incompatible.
                both = (Confirmation(inputs.old_word_ids[0], inputs.new_word_ids[0]),
                        Confirmation(inputs.old_word_ids[1], inputs.new_word_ids[1]))
                with self.assertRaises(NoCompatibleAlignment):
                    submit_three_draft_review(receipts, archive,
                                              ReviewRequest('one-slot', (annotation,), both))

    def test_different_witnesses_group_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'different-witnesses') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='different-witnesses')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                feasible = ((inputs.old_word_ids[0], inputs.new_word_ids[0]),
                            (inputs.old_word_ids[1], inputs.new_word_ids[1]))
                for old_id, new_id in feasible:
                    entry = submit_three_draft_review(
                        receipts, archive,
                        ReviewRequest('different-witnesses', (annotation,), (Confirmation(old_id, new_id),)))
                    self.assertEqual(entry.report.details['cost'], 6)
                all_pairs = tuple(Confirmation(o, n)
                                  for o in inputs.old_word_ids for n in inputs.new_word_ids)
                with self.assertRaises(NoCompatibleAlignment):
                    submit_three_draft_review(receipts, archive,
                                              ReviewRequest('different-witnesses', (annotation,), all_pairs))

    def test_empty_middle_rejects_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'empty-middle') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='empty-middle')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                with self.assertRaises(NoCompatibleAlignment):
                    submit_three_draft_review(
                        receipts, archive,
                        ReviewRequest('empty-middle', (annotation,),
                                      (Confirmation(inputs.old_word_ids[0], inputs.new_word_ids[0]),)))


class ThreeDraftEnvelopeTests(unittest.TestCase):
    def _publish(self, name='split-middle'):
        self.tmp = tempfile.TemporaryDirectory()
        directory = Path(self.tmp.name)
        source_path = directory / 'source.sqlite'
        with source_desk(source_path, name) as (revisions, excerpts, inputs):
            envelope = publish_three_draft_packet(
                revisions, excerpts, inputs.old_excerpt_id,
                inputs.middle_revision_id, inputs.new_excerpt_id, packet_id=name)
        return envelope, inputs

    def setUp(self):
        self.envelope, self.inputs = self._publish()

    def tearDown(self):
        self.tmp.cleanup()

    def test_version_two_shape_and_station_holdback(self):
        outer = json.loads(self.envelope)
        self.assertEqual(outer['version'], 2)
        self.assertEqual(set(outer), {'version', 'declaration', 'body', 'sha256'})
        body = json.loads(outer['body'])
        self.assertEqual(set(body), {'packet_id', 'old', 'middle_revision_id', 'new', 'evidence'})
        self.assertEqual(set(body['evidence']),
                         {'middle_size', 'middle_values', 'first_nodes', 'first_edges',
                          'second_nodes', 'second_edges'})
        packet = open_three_draft_envelope(self.envelope)
        self.assertEqual(packet.packet_id, 'split-middle')
        # Only anonymous middle values travel; no middle word identifiers or
        # provenance codes may appear in the sealed body.
        for word_id in (f'{packet.middle_revision_id}:{i}' for i in range(packet.evidence.middle_size)):
            self.assertNotIn(word_id, outer['body'])
        # Public excerpts keep the original word position and provenance shape.
        for side in (packet.old, packet.new):
            self.assertTrue(all(type(word.ordinal) is int and word.segment_id for word in side.words))

    def test_dispatch_and_round_trip(self):
        packet = open_any_envelope(self.envelope)
        self.assertEqual(packet.middle_revision_id, self.inputs.middle_revision_id)
        self.assertEqual(open_any_envelope(self.envelope), packet)

    def test_corrupt_and_rebound_envelopes_rejected(self):
        outer = json.loads(self.envelope)
        corrupted = dict(outer)
        corrupted['body'] = outer['body'] + ' '
        with self.assertRaises(EnvelopeMismatch):
            open_any_envelope(json.dumps(corrupted))
        rebound = dict(outer)
        rebound['declaration'] = dict(outer['declaration'], packet_id='someone-else')
        with self.assertRaises(EnvelopeMismatch):
            open_any_envelope(json.dumps(rebound))
        with self.assertRaises(EnvelopeMismatch):
            open_any_envelope('not-json')

    def test_tampered_evidence_rejected(self):
        outer = json.loads(self.envelope)
        body = json.loads(outer['body'])
        body['evidence']['first_edges'][0] = [99, 1, 1]
        canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        import hashlib
        tampered = {**outer, 'body': canonical,
                    'sha256': hashlib.sha256(canonical.encode('utf-8')).hexdigest()}
        with self.assertRaises(EnvelopeMismatch):
            open_three_draft_envelope(json.dumps(tampered))


class ThreeDraftReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        directory = Path(self.tmp.name)
        self.source_path, self.offline_path = directory / 's.sqlite', directory / 'o.sqlite'
        with source_desk(self.source_path, 'split-middle') as (revisions, excerpts, inputs):
            self.inputs = inputs
            self.envelope = publish_three_draft_packet(
                revisions, excerpts, inputs.old_excerpt_id,
                inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='split-middle')

    def tearDown(self):
        self.tmp.cleanup()

    def test_accept_reaccept_and_reopen(self):
        with offline_desk(self.offline_path) as (receipts, archive):
            first = receipts.accept(self.envelope)
            self.assertEqual(receipts.accept(self.envelope), first)
            received = receipts.get_received('split-middle')
            self.assertEqual(received.receipt, first)
            self.assertEqual(received.receipt.body_digest, first.body_digest)
        with offline_desk(self.offline_path) as (receipts, archive):
            self.assertEqual(receipts.accept(self.envelope).receipt_id, first.receipt_id)
            self.assertIsNotNone(receipts.get_received('split-middle'))

    def test_same_identifier_different_body_rejected(self):
        with offline_desk(self.offline_path) as (receipts, archive):
            receipts.accept(self.envelope)
            packet = open_three_draft_envelope(self.envelope)
            changed_values = ['CHANGED'] * packet.evidence.middle_size
            changed = replace(packet,
                              evidence=replace(packet.evidence, middle_values=tuple(changed_values)))
            with self.assertRaises(EnvelopeMismatch):
                receipts.accept(seal_three_draft_packet(changed))
            self.assertEqual(
                receipts.connection.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 1)

    def test_mixed_packet_types_share_identifier_space(self):
        from tests.fixtures import DeskCase
        case = DeskCase()
        case.setUp()
        try:
            exchange = case.exchange(('A', 'X'), ('X', 'A'), name='shared-id')
            case.close_source()
            # Sealing a v2 packet under an already received v1 identifier must
            # be refused as a different body rather than overwriting the ledger.
            import tempfile as _tempfile
            v2_path = Path(_tempfile.mkdtemp()) / 'three.sqlite'
            with source_desk(v2_path, 'empty-middle') as (revisions, excerpts, inputs):
                v2 = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='shared-id')
            with self.assertRaises(EnvelopeMismatch):
                case.receipts.accept(v2)
            self.assertEqual(case.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 1)
            self.assertEqual(case.receipts.get_received('shared-id').envelope, exchange.envelope)
        finally:
            case.doCleanups()


class ThreeDraftSubmitGuardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        directory = Path(self.tmp.name)
        self.source_path, self.offline_path = directory / 's.sqlite', directory / 'o.sqlite'
        with source_desk(self.source_path, 'split-middle') as (revisions, excerpts, inputs):
            self.inputs = inputs
            self.envelope = publish_three_draft_packet(
                revisions, excerpts, inputs.old_excerpt_id,
                inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='split-middle')

    def tearDown(self):
        self.tmp.cleanup()

    def test_entry_rejects_wrong_packet_type_and_unknown_id(self):
        with offline_desk(self.offline_path) as (receipts, archive):
            receipts.accept(self.envelope)
            annotation = OldAnnotation('note', self.inputs.old_word_ids[0])
            # Unknown packet.
            with self.assertRaises(ValueError):
                submit_three_draft_review(receipts, archive, ReviewRequest('missing', (annotation,)))
            # Three-draft entry rejects nothing here; now check v1 entry refusal
            # is covered by the mixed fixture test below.

    def test_invalid_annotation_and_confirmation_references(self):
        with offline_desk(self.offline_path) as (receipts, archive):
            receipts.accept(self.envelope)
            good_word = self.inputs.old_word_ids[0]
            invalid_requests = (
                ReviewRequest('split-middle', ()),
                ReviewRequest('split-middle', (OldAnnotation('note', good_word), OldAnnotation('note-2', good_word))),
                ReviewRequest('split-middle', (OldAnnotation('note', 'not-a-word'),)),
                ReviewRequest('split-middle', (OldAnnotation('', good_word),)),
                ReviewRequest('split-middle', (OldAnnotation('note', good_word),), None),
                ReviewRequest('split-middle', (OldAnnotation('note', good_word),),
                              (Confirmation(good_word, 'not-a-word'),)),
                ReviewRequest('split-middle', (OldAnnotation('note', good_word),),
                              (Confirmation('not-a-word', self.inputs.new_word_ids[0]),)),
            )
            before = archive.connection.execute('SELECT COUNT(*) FROM archive_reports').fetchone()[0]
            for request in invalid_requests:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    submit_three_draft_review(receipts, archive, request)
            after = archive.connection.execute('SELECT COUNT(*) FROM archive_reports').fetchone()[0]
            self.assertEqual(before, after)

    def test_duplicate_confirmations_merge(self):
        with offline_desk(self.offline_path) as (receipts, archive):
            receipts.accept(self.envelope)
            annotation = OldAnnotation('note', self.inputs.old_word_ids[0])
            pair = Confirmation(self.inputs.old_word_ids[0], self.inputs.new_word_ids[0])
            entry = submit_three_draft_review(
                receipts, archive, ReviewRequest('split-middle', (annotation,), (pair, pair)))
            self.assertEqual(entry.report.details['confirmations'],
                             [{'old_word_id': pair.old_word_id, 'new_word_id': pair.new_word_id}])


class ThreeDraftArchiveTests(unittest.TestCase):
    def test_two_reviews_after_source_close_and_reopen_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'split-middle') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='split-middle')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                first = submit_three_draft_review(receipts, archive,
                                                  ReviewRequest('split-middle', (annotation,)))
                second = submit_three_draft_review(
                    receipts, archive,
                    ReviewRequest('split-middle', (annotation,),
                                  (Confirmation(inputs.old_word_ids[0], inputs.new_word_ids[0]),)))
                self.assertEqual(first.report.details['cost'], 2)
                self.assertEqual(second.report.details['cost'], 4)
                provenance = second.report.details['packet']
                self.assertEqual(provenance['middle_revision_id'], inputs.middle_revision_id)
                self.assertEqual(provenance['receipt_id'], receipts.get_received('split-middle').receipt.receipt_id)
                self.assertEqual(provenance['old']['excerpt_id'], inputs.old_excerpt_id)
                self.assertEqual(provenance['new']['excerpt_id'], inputs.new_excerpt_id)
                report_ids = [first.report.report_id, second.report.report_id]
            # Reopen the offline library and retrieve both by report id.
            with offline_desk(offline_path) as (receipts, archive):
                recovered = [read_report(archive, report_id) for report_id in report_ids]
                self.assertEqual([entry.report.details for entry in recovered],
                                 [first.report.details, second.report.details])
                self.assertEqual([entry.receipt.receipt_id for entry in recovered],
                                 [first.receipt.receipt_id, second.receipt.receipt_id])

    def test_sign_failure_leaves_no_half_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path, offline_path = Path(tmp, 's.sqlite'), Path(tmp, 'o.sqlite')
            with source_desk(source_path, 'split-middle') as (revisions, excerpts, inputs):
                envelope = publish_three_draft_packet(
                    revisions, excerpts, inputs.old_excerpt_id,
                    inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='split-middle')
            with offline_desk(offline_path) as (receipts, archive):
                receipts.accept(envelope)
                annotation = OldAnnotation('note', inputs.old_word_ids[0])
                existing = submit_three_draft_review(receipts, archive,
                                                     ReviewRequest('split-middle', (annotation,)))
                connection = archive.connection
                connection.execute('CREATE TABLE failure_parent (id TEXT PRIMARY KEY)')
                connection.execute('''CREATE TABLE failure_child (
                    id TEXT REFERENCES failure_parent(id) DEFERRABLE INITIALLY DEFERRED)''')
                connection.execute('''CREATE TRIGGER fail_archive_commit AFTER INSERT ON archive_receipts
                    BEGIN INSERT INTO failure_child VALUES (NEW.report_id); END''')
                before = (connection.execute('SELECT COUNT(*) FROM archive_reports').fetchone()[0],
                          connection.execute('SELECT COUNT(*) FROM archive_receipts').fetchone()[0])
                with self.assertRaises(sqlite3.IntegrityError):
                    submit_three_draft_review(receipts, archive,
                                              ReviewRequest('split-middle', (annotation,)))
                self.assertFalse(connection.in_transaction)
                after = (connection.execute('SELECT COUNT(*) FROM archive_reports').fetchone()[0],
                         connection.execute('SELECT COUNT(*) FROM archive_receipts').fetchone()[0])
                self.assertEqual(before, after)
            with offline_desk(offline_path) as (receipts, archive):
                self.assertEqual(read_report(archive, existing.report.report_id), existing)


class MixedPacketEntryTests(unittest.TestCase):
    def test_each_entry_only_accepts_its_packet_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # Build a v1 packet through the standard test fixture.
            from tests.fixtures import DeskCase
            case = DeskCase()
            case.setUp()
            try:
                exchange = case.exchange(('A', 'X'), ('X', 'A'))
                case.close_source()
                # Publish a v2 packet into the same offline store under another id.
                source_path = directory / 'three.sqlite'
                with source_desk(source_path, 'empty-middle') as (revisions, excerpts, inputs):
                    v2 = publish_three_draft_packet(
                        revisions, excerpts, inputs.old_excerpt_id,
                        inputs.middle_revision_id, inputs.new_excerpt_id, packet_id='three')
                case.receipts.accept(v2)
                with self.assertRaises(ValueError):
                    submit_three_draft_review(case.receipts, case.archive, exchange.request())
                with self.assertRaises(ValueError):
                    submit_review(case.receipts, case.archive,
                                  ReviewRequest('three', (OldAnnotation('note', inputs.old_word_ids[0]),)))
            finally:
                case.doCleanups()


if __name__ == '__main__':
    unittest.main()
