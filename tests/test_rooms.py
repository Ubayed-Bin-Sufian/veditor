from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.db import Base
from app.routes.talks import _ensure_event_room

engine = create_engine(settings.database_url)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _event(db, name):
    event = models.Event(name=name)
    db.add(event)
    db.flush()
    return event


def test_room_names_are_event_scoped_and_case_insensitive(db_session):
    first = _event(db_session, "Rooms event one")
    second = _event(db_session, "Rooms event two")
    db_session.add(models.Room(event_id=first.id, name="Hall A"))
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(models.Room(event_id=first.id, name="hall a"))
        db_session.flush()

    db_session.add(models.Room(event_id=second.id, name="hall a"))
    db_session.flush()


def test_room_rename_and_delete_keep_talk_assignments_consistent(db_session):
    event = _event(db_session, "Room assignment event")
    room = models.Room(event_id=event.id, name="Hall A")
    db_session.add(room)
    db_session.flush()
    talks = [
        models.Talk(
            event_id=event.id,
            title=f"Talk {index}",
            room="Hall A",
            start=datetime(2026, 1, 1, index, tzinfo=UTC),
            end=datetime(2026, 1, 1, index + 1, tzinfo=UTC),
        )
        for index in (1, 2)
    ]
    db_session.add_all(talks)
    db_session.flush()

    room.name = "Main Hall"
    db_session.query(models.Talk).filter(
        models.Talk.event_id == event.id, models.Talk.room == "Hall A"
    ).update({models.Talk.room: room.name}, synchronize_session=False)
    db_session.flush()
    db_session.expire_all()
    assert {
        talk.room
        for talk in db_session.query(models.Talk).filter(
            models.Talk.event_id == event.id
        )
    } == {"Main Hall"}

    db_session.query(models.Talk).filter(
        models.Talk.event_id == event.id, models.Talk.room == room.name
    ).update({models.Talk.room: None}, synchronize_session=False)
    db_session.delete(room)
    db_session.flush()
    db_session.expire_all()
    assert all(talk.room is None for talk in db_session.query(models.Talk).all())


def test_room_assignment_normalizes_blank_and_reuses_pending_room(db_session):
    event = _event(db_session, "Room normalization event")
    assert _ensure_event_room(db_session, event.id, "   ") is None
    assert _ensure_event_room(db_session, event.id, None) is None

    first = _ensure_event_room(db_session, event.id, "  Hall A  ")
    second = _ensure_event_room(db_session, event.id, "hall a")
    assert first == "Hall A"
    assert second == "Hall A"
    assert db_session.query(models.Room).filter_by(event_id=event.id).count() == 1
