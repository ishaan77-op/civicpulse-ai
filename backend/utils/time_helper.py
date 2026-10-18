from datetime import datetime, timezone


def utc_now():
    """Timezone-aware "now" in UTC. Use this instead of the deprecated,
    naive `datetime.utcnow()` for every timestamp written to the database -
    every stored timestamp in this app is a UTC instant."""
    return datetime.now(timezone.utc)


def to_iso8601(value):
    """Serializes a stored timestamp as an unambiguous ISO-8601 UTC
    instant (e.g. "...+00:00"), never a bare, timezone-less string.

    SQLite/SQLAlchemy strips tzinfo on the way into the DB, so a value
    read back out is naive-but-UTC. Serializing that naive value directly
    with `.isoformat()` produces a string with no timezone designator,
    which browsers may parse as local time instead of UTC - shifting the
    displayed clock time by the reader's UTC offset. Reattaching UTC here
    fixes that at the source, once, instead of in every route."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
