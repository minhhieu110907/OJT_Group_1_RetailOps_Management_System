"""Integration tests against a dedicated MySQL test database."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, Engine

pytestmark = pytest.mark.integration


def test_mysql_select_one(integration_engine: Engine) -> None:
    with integration_engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1


def test_session_is_closed_after_use(
    integration_database_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETAILOPS_DB_HOST", integration_database_url.host or "")
    monkeypatch.setenv("RETAILOPS_DB_PORT", str(integration_database_url.port or 3306))
    monkeypatch.setenv("RETAILOPS_DB_NAME", integration_database_url.database or "")
    monkeypatch.setenv("RETAILOPS_DB_USER", integration_database_url.username or "")
    monkeypatch.setenv("RETAILOPS_DB_PASSWORD", integration_database_url.password or "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.db.session as session_module

    session_module = importlib.reload(session_module)
    baseline = session_module.engine.pool.checkedout()
    dependency = session_module.get_db_session()
    session = next(dependency)
    assert session.scalar(text("SELECT 1")) == 1
    dependency.close()

    assert not session.in_transaction()
    assert session_module.engine.pool.checkedout() == baseline
    session_module.engine.dispose()
    get_settings.cache_clear()


def test_session_rolls_back_and_closes_after_exception(
    integration_database_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETAILOPS_DB_HOST", integration_database_url.host or "")
    monkeypatch.setenv("RETAILOPS_DB_PORT", str(integration_database_url.port or 3306))
    monkeypatch.setenv("RETAILOPS_DB_NAME", integration_database_url.database or "")
    monkeypatch.setenv("RETAILOPS_DB_USER", integration_database_url.username or "")
    monkeypatch.setenv("RETAILOPS_DB_PASSWORD", integration_database_url.password or "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.db.session as session_module

    session_module = importlib.reload(session_module)
    baseline = session_module.engine.pool.checkedout()
    dependency = session_module.get_db_session()
    session = next(dependency)
    session.execute(text("SELECT 1"))

    with pytest.raises(RuntimeError, match="expected test failure"):
        dependency.throw(RuntimeError("expected test failure"))

    assert not session.in_transaction()
    assert session_module.engine.pool.checkedout() == baseline
    session_module.engine.dispose()
    get_settings.cache_clear()


def test_temporary_probe_survives_new_connection(
    integration_engine: Engine,
) -> None:
    probe_table = f"task02_probe_{uuid4().hex}"
    probe_created = False
    try:
        with integration_engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE TABLE `{probe_table}` "
                    "(id INT PRIMARY KEY, value VARCHAR(32) NOT NULL) ENGINE=InnoDB"
                )
            )
            probe_created = True
            connection.execute(
                text(f"INSERT INTO `{probe_table}` (id, value) VALUES (1, 'persisted')")
            )

        integration_engine.dispose()
        with integration_engine.connect() as connection:
            value = connection.scalar(
                text(f"SELECT value FROM `{probe_table}` WHERE id = 1")
            )
            assert value == "persisted"
    finally:
        if probe_created:
            with integration_engine.begin() as connection:
                connection.execute(text(f"DROP TABLE `{probe_table}`"))


def test_session_factory_initializes_once_under_concurrency(
    integration_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.db.session as session_module

    calls = 0
    calls_lock = Lock()

    def counted_engine_factory() -> Engine:
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.05)
        return integration_engine

    monkeypatch.setattr(session_module, "engine", None)
    monkeypatch.setattr(session_module, "SessionLocal", None)
    monkeypatch.setattr(session_module, "_create_engine", counted_engine_factory)

    with ThreadPoolExecutor(max_workers=8) as executor:
        factories = list(
            executor.map(lambda _index: session_module.get_session_factory(), range(8))
        )

    assert calls == 1
    assert len({id(factory) for factory in factories}) == 1
