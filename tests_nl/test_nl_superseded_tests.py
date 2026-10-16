import pytest

TESTS = """
import pytest

def test_upstream(): assert False
def test_kept(): pass

@pytest.mark.parametrize("x", [1, 2])
def test_param(x): assert x == 1

class TestUpstream:
    def test_a(self): assert False
    def test_b(self): assert False
"""

TWIN_TESTS = """
def test_upstream(): pass
def test_param(): pass
"""


@pytest.fixture
def project(pytester):
    pytester.makeconftest('pytest_plugins = ["notifications_utils.testing_nl.superseded_tests"]')
    pytester.makepyfile(test_foo=TESTS, test_foo_nl=TWIN_TESTS)
    return pytester


def write_manifest(pytester, body):
    pytester.path.joinpath("superseded_tests_nl.toml").write_text(body)


HIDE_ALL = """
[[test]]
nodeid = "test_foo.py::test_upstream"
reason = "Translation issue"
twin = ["test_foo_nl.py::test_upstream"]

[[test]]
nodeid = "test_foo.py::test_param[2]"
reason = "NL deliberately differs"
counterpart = ["test_foo_nl.py::test_param"]

[[test]]
nodeid = "test_foo.py::TestUpstream"
reason = "NHS features"
not_applicable = "NHS doesn't exist in NL"
"""


@pytest.mark.parametrize("args", [(), ("-n", "2")], ids=["serial", "xdist"])
def test_superseded_tests_are_not_reported(project, args):
    write_manifest(project, HIDE_ALL)

    result = project.runpytest_subprocess("--junitxml=junit.xml", *args)

    result.assert_outcomes(passed=4)
    result.stdout.no_fnmatch_line("*skipped*")
    result.stdout.no_fnmatch_line("*deselected*")
    junit = project.path.joinpath("junit.xml").read_text()
    assert 'skipped="0"' in junit
    assert 'tests="4"' in junit


def test_tests_without_twin_are_still_skipped(project):
    write_manifest(
        project,
        """
        [[test]]
        nodeid = "test_foo.py::test_upstream"
        reason = "Dutch phone numbers"

        [[test]]
        nodeid = "test_foo.py::TestUpstream::test_a"
        reason = "Spryng breaks MMG"
        xfail = true
        """,
    )

    result = project.runpytest("-rsx", "-k", "not test_param and not test_b")

    result.assert_outcomes(passed=2, skipped=1, xfailed=1)
    result.stdout.fnmatch_lines(["*[[]NOTIFYNL] Dutch phone numbers (no NL twin or counterpart yet)*"])


def test_show_superseded_reports_hidden_tests_as_skipped(project):
    write_manifest(project, HIDE_ALL)

    result = project.runpytest("-rs", "--nl-show-superseded")

    result.assert_outcomes(passed=4, skipped=4)
    result.stdout.fnmatch_lines(
        [
            "*superseded by twin test_foo_nl.py::test_upstream*",
            "*superseded by counterpart test_foo_nl.py::test_param*",
            "*not applicable in NL*",
        ]
    )


def test_without_manifest_nothing_changes(project):
    result = project.runpytest()

    result.assert_outcomes(passed=4, failed=4)


@pytest.mark.parametrize(
    "manifest, error",
    [
        ('[[test]]\nnodeid = "test_foo.py::test_upstream"\nreason = "x"\ncandidates = []', "unknown keys"),
        ('[[test]]\nnodeid = "test_foo.py::test_upstream"', "required strings"),
        (
            '[[test]]\nnodeid = "test_foo.py::test_upstream"\nreason = "x"\n'
            'twin = ["a_nl.py::b"]\nnot_applicable = "y"',
            "`not_applicable` can't be combined with `twin` or `counterpart`",
        ),
        (
            '[[test]]\nnodeid = "test_foo.py::test_upstream"\nreason = "x"\n'
            '[[test]]\nnodeid = "test_foo.py::test_upstream"\nreason = "x"',
            "duplicate nodeids",
        ),
    ],
)
def test_invalid_manifest_is_a_usage_error(project, manifest, error):
    write_manifest(project, manifest)

    result = project.runpytest()

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([f"*superseded_tests_nl.toml:*{error}*"])


def test_verify_passes_for_a_correct_manifest(project):
    write_manifest(project, HIDE_ALL)

    result = project.runpytest("--collect-only", "--nl-verify")

    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        ["*1 with an NL twin, 1 with only an NL counterpart, 1 not applicable, 0 without an NL replacement yet*"]
    )


@pytest.mark.parametrize(
    "entry, error",
    [
        ('nodeid = "test_foo.py::test_renamed"\nreason = "x"', "matches no collected test"),
        ('nodeid = "test_gone.py::test_upstream"\nreason = "x"', "file no longer exists"),
        (
            'nodeid = "test_foo.py::test_upstream"\nreason = "x"\ntwin = ["test_foo_nl.py::test_missing"]',
            "twin test_foo_nl.py::test_missing does not exist",
        ),
        (
            'nodeid = "test_foo.py::test_upstream"\nreason = "x"\ntwin = ["test_foo.py::test_kept"]',
            "is not an NL test",
        ),
        (
            'nodeid = "test_foo.py::test_upstream"\nreason = "x"\ncounterpart = ["test_foo_nl.py::test_missing"]',
            "counterpart test_foo_nl.py::test_missing does not exist",
        ),
    ],
)
def test_verify_fails_for_a_broken_manifest(project, entry, error):
    write_manifest(project, f"[[test]]\n{entry}")

    result = project.runpytest("--collect-only", "--nl-verify")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines([f"ERROR *{error}*"])


def test_verify_fails_when_a_twin_is_itself_superseded(project):
    write_manifest(
        project,
        """
        [[test]]
        nodeid = "test_foo.py::test_upstream"
        reason = "x"
        twin = ["test_foo_nl.py::test_upstream"]

        [[test]]
        nodeid = "test_foo_nl.py::test_upstream"
        reason = "y"
        """,
    )

    result = project.runpytest("--collect-only", "--nl-verify")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["ERROR *twin test_foo_nl.py::test_upstream is itself listed*"])


def test_verify_fails_for_tests_still_skipped_inline(project):
    project.makepyfile(
        test_inline="""
        import pytest

        @pytest.mark.skip(reason="[NOTIFYNL] Translation issue")
        def test_a(): pass

        @pytest.mark.skip(reason="upstream's own skip")
        def test_b(): pass
        """
    )

    result = project.runpytest("--collect-only", "--nl-verify")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["ERROR test_inline.py::test_a: still skipped inline with @pytest.mark.skip*"])
    result.stdout.no_fnmatch_line("*test_inline.py::test_b: still skipped*")


def test_verify_refuses_test_paths(project):
    result = project.runpytest("--collect-only", "--nl-verify", "test_foo.py")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*--nl-verify checks the whole suite*"])


RUN_SUPERSEDED = """
[[test]]
nodeid = "test_foo.py::test_kept"
reason = "Was broken, fixed since"

[[test]]
nodeid = "test_foo.py::test_param"
reason = "Only some cases pass"

[[test]]
nodeid = "test_foo.py::test_upstream"
reason = "Translation issue"
twin = ["test_foo_nl.py::test_upstream"]
"""


@pytest.mark.parametrize("args", [(), ("-n", "2")], ids=["serial", "xdist"])
def test_run_superseded_lists_the_entries_that_pass_now(project, args):
    write_manifest(project, RUN_SUPERSEDED)

    result = project.runpytest_subprocess("--nl-run-superseded", *args)

    # only the listed tests run, ignoring the manifest: test_kept, test_param[1], test_param[2], test_upstream
    result.assert_outcomes(passed=2, failed=2)
    result.stdout.fnmatch_lines(
        [
            "*NL superseded tests that pass now*",
            "test_foo.py::test_kept  (Was broken, fixed since)",
            "1 of 3 entries pass now",
        ]
    )
    result.stdout.no_fnmatch_line("test_foo.py::test_param  *")
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_run_superseded_exits_0_when_nothing_passes(project):
    write_manifest(project, HIDE_ALL)

    result = project.runpytest("--nl-run-superseded")

    result.assert_outcomes(failed=4)
    result.stdout.fnmatch_lines(["0 of 3 entries pass now"])
    assert result.ret == pytest.ExitCode.OK


def test_run_superseded_cant_be_combined_with_show_superseded(project):
    result = project.runpytest("--nl-run-superseded", "--nl-show-superseded")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
