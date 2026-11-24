from contextlib import closing, contextmanager
from dataclasses import dataclass
import sqlite3

from archive.transactions import ArchiveStore
from excerpts.policy import PublicationPermission
from excerpts.selection import select_excerpt
from excerpts.store import ExcerptStore
from issue.receipts import ReceiptStore
from revisions.importer import import_revision
from revisions.model import SourceSegment
from revisions.store import RevisionStore


CASES = {
    "split-middle": (("A X", "A X A", "X A"), ((0, 0), (1, 1))),
    "shared-middle": (("A X", "X A X", "X A"), ((0, 0), (1, 1))),
    "one-slot": (("A A", "A", "A A"), ((0, 1), (0, 1))),
    "different-witnesses": (("A B C", "B C A B", "A B C"), ((0, 2), (0, 2))),
    "empty-middle": (("A", "", "A"), ((0, 0), (0, 0))),
}


@dataclass(frozen=True)
class ThreeDraftInputs:
    old_excerpt_id: str
    middle_revision_id: str
    new_excerpt_id: str
    old_word_ids: tuple[str, ...]
    new_word_ids: tuple[str, ...]


@contextmanager
def source_desk(database, case_name):
    texts, bounds = CASES[case_name]
    with closing(sqlite3.connect(database)) as connection:
        revisions = RevisionStore(connection)
        excerpts = ExcerptStore(connection)
        revisions.initialize()
        excerpts.initialize()
        ordered = []
        for role, text in zip(("initial", "hearing", "final"), texts, strict=True):
            revision = import_revision(
                revisions,
                case_name,
                f"{case_name}-{role}",
                (SourceSegment(f"{role}-source-segment", 5, tuple(text.split())),),
            )
            ordered.append(revision)
        initial, middle, final = ordered
        selected = []
        for revision, (lo, hi) in zip((initial, final), bounds, strict=True):
            first, last = revision.words[lo].word_id, revision.words[hi].word_id
            permit = PublicationPermission(f"{revision.revision_id}-permit", revision.revision_id, first, last)
            selected.append(select_excerpt(revisions, excerpts, f"{revision.revision_id}-excerpt",
                                           revision.revision_id, permit, first, last))
        old, new = selected
        inputs = ThreeDraftInputs(old.excerpt_id, middle.revision_id, new.excerpt_id,
                                  tuple(word.word_id for word in old.words),
                                  tuple(word.word_id for word in new.words))
        yield revisions, excerpts, inputs


@contextmanager
def offline_desk(database):
    with closing(sqlite3.connect(database)) as connection:
        receipts = ReceiptStore(connection)
        archive = ArchiveStore(connection)
        receipts.initialize()
        archive.initialize()
        yield receipts, archive


def main():
    for name, (texts, bounds) in CASES.items():
        with source_desk(":memory:", name) as (revisions, excerpts, inputs):
            middle = revisions.get(inputs.middle_revision_id)
            old = excerpts.get(inputs.old_excerpt_id)
            new = excerpts.get(inputs.new_excerpt_id)
            if middle is None or old is None or new is None:
                raise RuntimeError(f"{name}: expected fixed revisions and permitted excerpts")
            public = [[word.value for word in item.words] for item in (old, new)]
            expected = [text.split()[lo:hi + 1] for text, (lo, hi) in zip((texts[0], texts[2]), bounds, strict=True)]
            if public != expected or [word.value for word in middle.words] != texts[1].split():
                raise RuntimeError(f"{name}: source fixture differs from the published sample")
            print(name, inputs.middle_revision_id, public)
        with offline_desk(":memory:") as (receipts, archive):
            if receipts.get_received(name) is not None or archive.get_signed(name) is not None:
                raise RuntimeError(f"{name}: expected an empty offline desk")


if __name__ == "__main__":
    main()
