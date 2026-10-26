import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Apply SQLite foreign-key enforcement to every SQLAlchemy connection.

    SQLite leaves this disabled by default per connection.  The workflow has
    audit records that must never become detached from their issue, complaint,
    or review, so the setting belongs in the shared engine lifecycle rather
    than in an individual request handler.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
