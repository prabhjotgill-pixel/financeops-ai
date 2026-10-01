from sqlalchemy import text

from backend.app.db.session import make_engine, make_session_factory


def test_session_factory_connects_to_sqlite() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    try:
        factory = make_session_factory(engine)
        with factory() as session:
            assert session.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()
