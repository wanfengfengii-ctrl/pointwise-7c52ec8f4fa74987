"""Run this project's full unittest suite and the three-draft handoff checks."""
import sys
import unittest

import three_draft_cases


def main():
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    tests_ok = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if tests_ok else "FAIL"}')
    if not tests_ok:
        return 1
    try:
        three_draft_cases.main()
    except Exception as exc:  # pragma: no cover - surfaced as a nonzero exit
        print(f'THREE-DRAFT FIXTURE CHECK FAILED: {exc!r}', file=sys.stderr)
        return 1
    print('THREE-DRAFT FIXTURE CHECK result=PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
