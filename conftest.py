# NotifyNL: upstream (alphagov) tests that don't hold for NL are listed in superseded_tests_nl.toml instead of being
# skipped inline, so upstream test files stay identical to alphagov's. This plugin reads that manifest: tests with an NL
# twin or counterpart are left out of the run, tests without one still show as skipped. See
# notifications_utils/testing_nl/superseded_tests.py for the options
# (--nl-verify, --nl-show-superseded, --nl-run-superseded).
#
# pytester is only needed by tests_nl/test_nl_superseded_tests.py, which tests that plugin.
pytest_plugins = ["notifications_utils.testing_nl.superseded_tests", "pytester"]
