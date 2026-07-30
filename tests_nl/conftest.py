"""
Conftest for tests_nl directory with required fixtures.
"""

import logging

import pytest
from flask import Flask


def _create_app(extra_config=None):
    flask_app = Flask(__name__)
    flask_app.config.update(extra_config or {})
    ctx = flask_app.app_context()
    ctx.push()

    yield flask_app

    ctx.pop()


@pytest.fixture
def app_with_mocked_logger(mocker, tmpdir):
    """Patch `create_logger` to return a mock logger that is made accessible on `app.logger`"""
    mocker.patch(
        "flask.sansio.app.create_logger",
        return_value=mocker.Mock(spec=logging.Logger("flask.app"), handlers=[]),
    )
    yield from _create_app()
