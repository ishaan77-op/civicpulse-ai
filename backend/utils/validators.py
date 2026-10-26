import math


class ValidationError(ValueError):
    """Input validation failure with a message safe for API clients."""


def parse_optional_coordinates(latitude_raw, longitude_raw):
    """Return a validated ``(latitude, longitude)`` pair or ``(None, None)``.

    Coordinates are a pair: accepting only one produces ambiguous field
    evidence, so partial input is always rejected.  ``NaN`` and infinities
    are explicitly rejected because ``float()`` otherwise accepts them.
    """
    latitude_supplied = latitude_raw not in (None, "")
    longitude_supplied = longitude_raw not in (None, "")
    if latitude_supplied != longitude_supplied:
        raise ValidationError("Latitude and longitude must be provided together")
    if not latitude_supplied:
        return None, None

    try:
        latitude = float(latitude_raw)
        longitude = float(longitude_raw)
    except (TypeError, ValueError):
        raise ValidationError("GPS coordinates are invalid") from None

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValidationError("GPS coordinates must be finite numbers")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValidationError("GPS coordinates are outside the valid range")
    return latitude, longitude
