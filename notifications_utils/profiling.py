import logging
import os

logger = logging.getLogger(__name__)


def configure_pyroscope() -> None:
    """Configures Grafana Pyroscope continuous profiling for the current process.

    Safe to call unconditionally from any process (Flask/gunicorn worker, Celery worker/beat):
    a no-op if PYROSCOPE_SERVER_ADDRESS isn't set, and never raises if the SDK itself fails (e.g.
    the Pyroscope server being briefly unreachable), so a flaky/misconfigured profiler can never
    take down app or worker startup.

    Fork-based concurrency (gunicorn, Celery prefork workers) means this must be called inside a
    post-fork hook in each actual worker process, not once at import time - see
    notifications_utils.gunicorn.defaults.post_fork and
    notifications_utils.logging.celery.set_up_logging for the equivalent existing pattern this
    mirrors for Celery.

    Application name is PYROSCOPE_APPLICATION_NAME if set, falling back to OTEL_SERVICE_NAME.
    Deliberately not gated on OTEL_SERVICE_NAME being set - most processes in this fork don't have
    it set yet (see notifynl-full's own README), and profiling shouldn't depend on tracing being
    configured. When both happen to be set to the same value, Grafana's tracesToProfiles link on
    the Tempo datasource can jump from a trace span straight to its profile.
    """
    server_address = os.environ.get("PYROSCOPE_SERVER_ADDRESS", "")
    if not server_address:
        return

    application_name = os.environ.get("PYROSCOPE_APPLICATION_NAME") or os.environ.get("OTEL_SERVICE_NAME")
    if not application_name:
        logger.warning(
            "PYROSCOPE_SERVER_ADDRESS is set but neither PYROSCOPE_APPLICATION_NAME nor "
            "OTEL_SERVICE_NAME is - skipping profiling setup"
        )
        return

    try:
        import pyroscope

        pyroscope.configure(application_name=application_name, server_address=server_address)
    except Exception:
        logger.exception("Failed to configure Pyroscope profiling - continuing without it")


def set_up_profiling_for_celery() -> None:
    """Connects Pyroscope configuration to Celery's worker_process_init signal.

    Call once from a Celery-consuming app's run_celery.py, mirroring
    notifications_utils.logging.celery.set_up_logging - Celery's prefork worker model forks
    child processes after this module is imported, so profiling must be (re-)initialised inside
    each actual worker process, not just once at import time.
    """
    from celery.signals import worker_process_init

    worker_process_init.connect(_worker_process_init_connect)


def _worker_process_init_connect(*args, **kwargs) -> None:
    configure_pyroscope()
