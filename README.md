# notifynl-utils

![Build](https://img.shields.io/github/actions/workflow/status/Worth-NL/notifynl-utils/merge.yml?branch=main&style=for-the-badge&label=build)
![Release](https://img.shields.io/github/v/tag/Worth-NL/notifynl-utils?style=for-the-badge&label=release)
![License](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.13-blue.svg?style=for-the-badge)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=for-the-badge)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://github.com/astral-sh/ruff)

Shared Python code for **NotifyNL** applications — the Dutch fork of GOV.UK Notify. Standardises
logging, message-template rendering, spreadsheet parsing, external-service clients, and more, across
all NotifyNL Flask/Celery services.

`notifynl-utils` is a fork of alphagov's [`notifications-utils`](https://github.com/alphagov/notifications-utils),
layered with NL-specific modules (`countries_nl/`, `recipient_validation/notifynl/`, a parallel
`tests_nl/` suite, etc.) on top of the still-present upstream structure.

## Used by

- `notifynl-api`
- `notifynl-admin`
- `document-download-api`
- `document-download-frontend`
- `notifications-antivirus`
- `notifynl-template-preview`

## Setting up

### Python version

Requires **Python 3.13+** (see `pyproject.toml`).

### uv

Dependency management uses [uv](https://github.com/astral-sh/uv). Follow the [install instructions](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) or run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Pre-commit

We use [pre-commit](https://pre-commit.com/) to ensure that committed code meets basic standards for formatting, and will make basic fixes for you to save time and aggravation.

Install pre-commit system-wide with, eg `brew install pre-commit`. Then, install the hooks in this repository with `pre-commit install --install-hooks`.

### Redis

We use a real [Redis](https://redis.io/) instance to test `notifications_utils.redis_client.RedisClient`. You can either install locally or [run inside a docker container](https://hub.docker.com/_/redis).

The unit test fixture uses `FLUSHALL` every single time it is called. To prevent this from having unexpected side effects with a locally running Redis instance, the tests expect Redis to run on port 6999. In Docker simply change the port mapping flag to `-p 6999:6379`. If running outside a container add the flag `--port 6999`.

## To test the library

```bash
# install dependencies, etc.
make bootstrap

# run the tests
make test
```

## Publishing a new version

Versioning should be done by running the `make version-[type of change]` command, following [semantic versioning](https://semver.org/). For example:

```bash
make version-patch
```

Include a short summary (sentence or two) about the changes you've made in `CHANGELOG.md`. Please do this even if you're only making a minor or patch version change.

On merge to `main`, CI (`.github/workflows/merge.yml`) builds the package and tags a GitHub release automatically. On each pull request, `.github/workflows/pr.yml` runs lint/tests and will auto-bump the patch version if it hasn't already been bumped.

## Updating utils version in apps

App repos should be updated with the latest version of `notifications-utils` where possible. The repos to update are: `notifynl-api`, `notifynl-admin`, `document-download-api`, `document-download-frontend`, `notifications-antivirus`, `notifynl-template-preview`.

To do this in the app repo:

- Ensure `uv` (and npm, where relevant) is installed and you're using Python 3.13
- Run `make bootstrap`
- Run `make bump-utils`
- Run `make freeze-requirements`
- Commit with the recommended message and raise a PR

## License & attribution

MIT licensed — see [LICENSE](LICENSE). Originally authored by the UK Government Digital Service as
part of [GOV.UK Notify](https://github.com/alphagov/notifications-utils); NL-specific work maintained
by Worth Ventures B.V. as part of the NotifyNL fork. The original upstream README is preserved at
[docs/README.old.md](docs/README.old.md).
