"""
Pytest plugin for upstream (alphagov) tests that don't hold for NotifyNL.

Instead of skipping those tests inline - which turns every upstream test file into a merge conflict - they are listed
in ``superseded_tests_nl.toml`` at the repo root, each with the NL test(s) that replace it::

    [[test]]
    nodeid = "tests/test_foo.py::test_bar"
    reason = "Translation issue"
    twin = ["tests/test_foo_nl.py::test_bar"]

* ``twin``: NL tests that check the same behaviour, adapted to NL (Dutch text, NL data). When upstream changes the
  test, the twin probably needs the same change.
* ``counterpart``: NL tests for behaviour NL deliberately does differently (e.g. hides the SMS cost upstream shows).
  Upstream changes to the test usually don't apply to NL.
* ``not_applicable``: why the tested feature doesn't exist in NL (e.g. NHS organisation types).

An entry with any of these is dropped from the run; the summary line only counts it (``12 passed, 4 superseded``). An
entry with none is still shown as a skip (or a strict xfail with ``xfail = true``), so the skipped count is the number
of upstream tests that have no NL replacement yet.

Load it from a root ``conftest.py`` with ``pytest_plugins = ["notifications_utils.testing_nl.superseded_tests"]``.

``--nl-show-superseded`` reports the hidden tests as skips. ``--nl-verify`` (run on the whole suite, e.g. with
``--collect-only``) fails when the manifest is stale, a twin or counterpart doesn't exist or a test is still skipped
inline.
``--nl-run-superseded`` runs only the listed tests, ignoring the manifest, and lists the entries whose tests all pass
now and can be removed (exit code 1 if there are any).
"""

import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest
from _pytest import terminal

MANIFEST_NAME = "superseded_tests_nl.toml"
NL_TAG = "[NOTIFYNL]"
SUPERSEDED_STAT = "superseded"

_ALLOWED_KEYS = {"nodeid", "reason", "twin", "counterpart", "not_applicable", "xfail"}


@dataclass(frozen=True)
class Entry:
    nodeid: str
    reason: str
    twin: tuple[str, ...] = ()
    counterpart: tuple[str, ...] = ()
    not_applicable: str = ""
    xfail: bool = False

    @property
    def replacements(self) -> list[tuple[str, str]]:
        """(kind, nodeid) of every NL test that replaces this one."""
        return [("twin", t) for t in self.twin] + [("counterpart", c) for c in self.counterpart]

    @property
    def hidden(self) -> bool:
        return bool(self.twin or self.counterpart or self.not_applicable)

    @property
    def path(self) -> str:
        return self.nodeid.split("::", 1)[0]


def matches(pattern: str, nodeid: str) -> bool:
    """A nodeid also covers the tests of a class and every case of a parametrized test."""
    return nodeid == pattern or nodeid.startswith((pattern + "::", pattern + "["))


def _parse_entry(raw: dict, position: int) -> Entry:
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"entry {position}: unknown keys {sorted(unknown)}")
    if not isinstance(raw.get("nodeid"), str) or not isinstance(raw.get("reason"), str):
        raise ValueError(f"entry {position}: `nodeid` and `reason` are required strings")
    for key in ("twin", "counterpart"):
        value = raw.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"entry {position} ({raw['nodeid']}): `{key}` must be a list of nodeids")
    if (raw.get("twin") or raw.get("counterpart")) and raw.get("not_applicable"):
        raise ValueError(
            f"entry {position} ({raw['nodeid']}): `not_applicable` can't be combined with `twin` or `counterpart`"
        )
    return Entry(
        nodeid=raw["nodeid"],
        reason=raw["reason"],
        twin=tuple(raw.get("twin", [])),
        counterpart=tuple(raw.get("counterpart", [])),
        not_applicable=str(raw.get("not_applicable", "")),
        xfail=bool(raw.get("xfail", False)),
    )


def load_manifest(path: Path) -> list[Entry]:
    with path.open("rb") as f:
        raw_entries = tomllib.load(f).get("test", [])
    entries = [_parse_entry(raw, position) for position, raw in enumerate(raw_entries, start=1)]
    duplicates = [nodeid for nodeid, count in Counter(e.nodeid for e in entries).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate nodeids: {duplicates}")
    return entries


class Manifest:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self._by_path: dict[str, list[Entry]] = {}
        for entry in entries:
            self._by_path.setdefault(entry.path, []).append(entry)

    def entry_for(self, nodeid: str) -> Entry | None:
        """The most specific entry covering this nodeid, if any."""
        candidates = [e for e in self._by_path.get(nodeid.split("::", 1)[0], []) if matches(e.nodeid, nodeid)]
        return max(candidates, key=lambda e: len(e.nodeid), default=None)


def inline_nl_reason(item: pytest.Item) -> str | None:
    for mark in item.iter_markers():
        if mark.name not in ("skip", "skipif", "xfail"):
            continue
        texts = [mark.kwargs.get("reason"), *mark.args]
        if any(isinstance(text, str) and text.startswith(NL_TAG) for text in texts):
            return f"@pytest.mark.{mark.name}"
    return None


def find_problems(manifest: Manifest, items: list[pytest.Item], rootpath: Path) -> list[str]:
    nodeids = [item.nodeid for item in items]
    collected_paths = {nodeid.split("::", 1)[0] for nodeid in nodeids}
    problems = []

    for item in items:
        if mark := inline_nl_reason(item):
            problems.append(f"{item.nodeid}: still skipped inline with {mark}, move it to {MANIFEST_NAME}")

    for entry in manifest.entries:
        if not (rootpath / entry.path).exists():
            problems.append(f"{entry.nodeid}: file no longer exists (renamed upstream?)")
        elif entry.path in collected_paths and not any(matches(entry.nodeid, nodeid) for nodeid in nodeids):
            problems.append(f"{entry.nodeid}: matches no collected test (renamed upstream?)")
        for kind, nl_test in entry.replacements:
            problems.extend(_replacement_problems(entry, kind, nl_test, manifest, nodeids))
    return problems


def _replacement_problems(entry: Entry, kind: str, nl_test: str, manifest: Manifest, nodeids: list[str]) -> list[str]:
    if "_nl" not in nl_test.split("::", 1)[0]:
        return [f"{entry.nodeid}: {kind} {nl_test} is not an NL test"]
    if manifest.entry_for(nl_test):
        return [f"{entry.nodeid}: {kind} {nl_test} is itself listed in {MANIFEST_NAME}"]
    if not any(matches(nl_test, nodeid) for nodeid in nodeids):
        return [f"{entry.nodeid}: {kind} {nl_test} does not exist"]
    return []


class RunSuperseded:
    """--nl-run-superseded: run the listed tests as plain tests and report the entries that pass now."""

    def __init__(self, manifest: Manifest):
        self.manifest = manifest
        self.outcomes: dict[str, str] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.outcome != "passed":
            self.outcomes[report.nodeid] = report.outcome  # a failure or skip in any phase wins
        elif report.when == "call":
            self.outcomes.setdefault(report.nodeid, "passed")

    def passing_entries(self) -> list[Entry]:
        """Entries whose tests ran and all passed - with parametrize, every case has to pass."""
        results = defaultdict(list)
        for nodeid, outcome in self.outcomes.items():
            if entry := self.manifest.entry_for(nodeid):
                results[entry.nodeid].append(outcome)
        return [e for e in self.manifest.entries if results[e.nodeid] and set(results[e.nodeid]) == {"passed"}]

    def pytest_terminal_summary(self, terminalreporter) -> None:
        passing = self.passing_entries()
        terminalreporter.section(f"NL superseded tests that pass now (remove them from {MANIFEST_NAME})")
        for entry in passing:
            terminalreporter.line(f"{entry.nodeid}  ({entry.reason})", green=True)
        terminalreporter.line(f"{len(passing)} of {len(self.manifest.entries)} entries pass now")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        # failures of the listed tests are expected here, only a passing entry is news
        if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED if self.passing_entries() else pytest.ExitCode.OK


_manifest_key = pytest.StashKey[Manifest]()
_problems_key = pytest.StashKey[list[str]]()
_superseded_key = pytest.StashKey[list[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("notifynl", "NotifyNL superseded upstream tests")
    group.addoption(
        "--nl-show-superseded",
        action="store_true",
        help=f"Report the upstream tests hidden by {MANIFEST_NAME} as skipped.",
    )
    group.addoption(
        "--nl-verify",
        action="store_true",
        help=f"Fail if {MANIFEST_NAME} is stale, a twin or counterpart is missing or a test is still skipped inline.",
    )
    group.addoption(
        "--nl-run-superseded",
        action="store_true",
        help=f"Run only the tests listed in {MANIFEST_NAME}, as plain tests, and list the entries that pass now.",
    )


def pytest_configure(config: pytest.Config) -> None:
    path = config.rootpath / MANIFEST_NAME
    try:
        entries = load_manifest(path) if path.exists() else []
    except (ValueError, tomllib.TOMLDecodeError) as e:
        raise pytest.UsageError(f"{MANIFEST_NAME}: {e}") from e
    config.stash[_manifest_key] = Manifest(entries)
    _register_superseded_stat()
    if config.getoption("nl_verify") and config.args_source == pytest.Config.ArgsSource.ARGS:
        raise pytest.UsageError("--nl-verify checks the whole suite, run it without test paths")
    if config.getoption("nl_run_superseded"):
        if config.getoption("nl_show_superseded"):
            raise pytest.UsageError("--nl-run-superseded and --nl-show-superseded can't be combined")
        # most listed tests are expected to fail: drop their tracebacks and the short summary, which would bury the list
        # of entries that pass now. Run a test without this option to see why it fails.
        config.option.tbstyle = "no"
        config.option.reportchars = ""
        config.pluginmanager.register(RunSuperseded(config.stash[_manifest_key]), "nl-run-superseded")


def _register_superseded_stat() -> None:
    # pytest turns the summary line of a clean run yellow when it holds a stat pytest doesn't know, so add "superseded"
    # to its own stats. These names are private: if a pytest upgrade renames them, the count still shows, in yellow.
    if SUPERSEDED_STAT not in getattr(terminal, "KNOWN_TYPES", (SUPERSEDED_STAT,)):
        terminal.KNOWN_TYPES = (*terminal.KNOWN_TYPES, SUPERSEDED_STAT)
    getattr(terminal, "_color_for_type", {}).setdefault(SUPERSEDED_STAT, "green")


@pytest.hookimpl(tryfirst=True)  # see the full collection, before -k/-m deselect anything
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    manifest = config.stash[_manifest_key]
    if config.getoption("nl_verify"):
        config.stash[_problems_key] = find_problems(manifest, items, config.rootpath)

    if config.getoption("nl_run_superseded"):
        items[:] = [item for item in items if manifest.entry_for(item.nodeid)]
        return

    show_superseded = config.getoption("nl_show_superseded")
    kept, superseded = [], []
    for item in items:
        entry = manifest.entry_for(item.nodeid)
        if entry is None:
            kept.append(item)
        elif not entry.hidden:
            item.add_marker(_gap_marker(entry))
            kept.append(item)
        elif show_superseded:
            item.add_marker(pytest.mark.skip(reason=_superseded_reason(entry)))
            kept.append(item)
        else:
            # dropped without calling pytest_deselected, so it's neither skipped nor deselected: only counted
            superseded.append(item.nodeid)
    items[:] = kept
    config.stash[_superseded_key] = superseded


def _gap_marker(entry: Entry) -> pytest.MarkDecorator:
    reason = f"{NL_TAG} {entry.reason} (no NL twin or counterpart yet)"
    return pytest.mark.xfail(reason=reason, strict=True) if entry.xfail else pytest.mark.skip(reason=reason)


def _superseded_reason(entry: Entry) -> str:
    if entry.replacements:
        return f"{NL_TAG} {entry.reason}, superseded by " + ", ".join(f"{k} {t}" for k, t in entry.replacements)
    return f"{NL_TAG} {entry.reason}, not applicable in NL: {entry.not_applicable}"


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    if not config.getoption("nl_verify"):
        return
    manifest = config.stash[_manifest_key]
    problems = config.stash.get(_problems_key, [])
    gaps = Counter(entry.reason for entry in manifest.entries if not entry.hidden)

    terminalreporter.section(f"NL superseded tests ({MANIFEST_NAME})")
    terminalreporter.line(
        f"{sum(bool(e.twin) for e in manifest.entries)} with an NL twin, "
        f"{sum(bool(e.counterpart and not e.twin) for e in manifest.entries)} with only an NL counterpart, "
        f"{sum(bool(e.not_applicable) for e in manifest.entries)} not applicable, "
        f"{gaps.total()} without an NL replacement yet"
    )
    for reason, count in gaps.most_common():
        terminalreporter.line(f"  {count:4}  {reason}")
    for problem in problems:
        terminalreporter.line(f"ERROR {problem}", red=True)


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    superseded = config.stash.get(_superseded_key, [])
    if hasattr(config, "workeroutput"):  # xdist worker: the controller prints the summary line
        config.workeroutput["nl_superseded"] = superseded
    elif superseded and (terminalreporter := config.pluginmanager.get_plugin("terminalreporter")):
        terminalreporter.stats.setdefault(SUPERSEDED_STAT, []).extend(superseded)

    if config.stash.get(_problems_key, []):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error) -> None:
    # xdist controller: every worker collects the whole suite, so any worker's list is the full one
    if (superseded := getattr(node, "workeroutput", {}).get("nl_superseded")) is not None:
        node.config.stash[_superseded_key] = superseded
