import logging
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))
load_dotenv()

logger = logging.getLogger(__name__)

# Insecure built-in secrets. They are only ever used when APP_ENV=development
# is set explicitly, and are rejected as values in any other environment.
DEV_SECRET_KEY = "civicpulse_secret_key_default_dev"
DEV_JWT_SECRET_KEY = "super_secret_jwt_key_default_dev"

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigurationError(RuntimeError):
    """The environment is missing or has unsafe required settings."""


def is_development(environ):
    """True only when APP_ENV is explicitly 'development' (or 'dev').
    Unset or any other value (including typos) is treated as production,
    so a misconfigured deployment fails closed."""
    return (environ.get("APP_ENV") or "").strip().lower() in {"development", "dev"}


def resolve_secrets(environ):
    """Return (SECRET_KEY, JWT_SECRET_KEY).

    Development: blank/missing values fall back to the dev defaults.
    Anything else: both must be set, non-blank and not the dev defaults,
    otherwise ConfigurationError is raised. Messages name the variables
    only and never include secret values."""
    development = is_development(environ)
    required = (
        ("SECRET_KEY", DEV_SECRET_KEY),
        ("JWT_SECRET_KEY", DEV_JWT_SECRET_KEY),
    )
    resolved = {}
    problems = []

    for name, dev_default in required:
        value = environ.get(name) or ""
        if value.strip():
            if not development and value == dev_default:
                problems.append(f"{name} is set to the built-in development default")
            resolved[name] = value
        elif development:
            logger.warning("%s is not set; using the insecure development default", name)
            resolved[name] = dev_default
        else:
            problems.append(f"{name} is missing or blank")

    if problems:
        raise ConfigurationError(
            "Invalid configuration (APP_ENV="
            f"{(environ.get('APP_ENV') or '').strip() or 'unset'}): "
            + "; ".join(problems)
            + ". Set real values in backend/.env, or set APP_ENV=development "
            "for local development only."
        )

    return resolved["SECRET_KEY"], resolved["JWT_SECRET_KEY"]


def resolve_server_options(environ):
    """Return (host, port, debug) for `python app.py`.

    Defaults: 127.0.0.1, port 5001, debug off. LAN access needs an explicit
    HOST=0.0.0.0. Debug (FLASK_DEBUG=1) is honoured only in development AND
    when bound to a loopback address, so the Werkzeug debugger can never be
    exposed to the network."""
    host = (environ.get("HOST") or "").strip() or "127.0.0.1"

    port_text = (environ.get("PORT") or "").strip() or "5001"
    try:
        port = int(port_text)
    except ValueError:
        raise ConfigurationError("PORT must be a number") from None
    if not 0 < port < 65536:
        raise ConfigurationError("PORT must be between 1 and 65535")

    debug_requested = (environ.get("FLASK_DEBUG") or "").strip().lower() in {"1", "true", "yes", "on"}
    debug = debug_requested

    if debug_requested and not is_development(environ):
        logger.warning("FLASK_DEBUG ignored: debug mode requires APP_ENV=development")
        debug = False
    elif debug_requested and host not in LOOPBACK_HOSTS:
        logger.warning("FLASK_DEBUG ignored: debug mode is never enabled on a non-loopback HOST")
        debug = False

    return host, port, debug


def _positive_int_env(name, default):
    """Integer env var; blank, non-numeric or non-positive values fall back."""
    try:
        value = int(os.getenv(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


# Largest accepted complaint photo. The request cap adds headroom for the
# other form fields and multipart framing.
MAX_UPLOAD_MB = _positive_int_env("MAX_UPLOAD_MB", 10)

_SECRET_KEY, _JWT_SECRET_KEY = resolve_secrets(os.environ)


# Blank values (e.g. `DATABASE_URL=` copied from .env.example) are treated as
# unset, so they fall back to the defaults instead of becoming empty strings.
class Config:
    SECRET_KEY = _SECRET_KEY
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"sqlite:///{os.path.join(basedir, 'instance', 'civicpulse.db')}"
    )
    # Where complaint photos are stored and served from. Defaults to
    # backend/uploads; override with UPLOAD_FOLDER (tests use a temp dir).
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(basedir, "uploads")
    MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = _JWT_SECRET_KEY
