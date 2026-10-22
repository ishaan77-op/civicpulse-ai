import pytest

from config import (
    DEV_JWT_SECRET_KEY,
    DEV_SECRET_KEY,
    ConfigurationError,
    resolve_secrets,
    resolve_server_options,
)

REAL = {"SECRET_KEY": "real-flask-secret-value", "JWT_SECRET_KEY": "real-jwt-secret-value"}


# ---- secrets: development ----------------------------------------------

@pytest.mark.parametrize("env_value", ["development", "dev", "Development", " DEV "])
def test_development_blank_or_missing_secrets_use_dev_defaults(env_value):
    assert resolve_secrets({"APP_ENV": env_value}) == (DEV_SECRET_KEY, DEV_JWT_SECRET_KEY)
    assert resolve_secrets({"APP_ENV": env_value, "SECRET_KEY": "", "JWT_SECRET_KEY": "   "}) == (
        DEV_SECRET_KEY,
        DEV_JWT_SECRET_KEY,
    )


def test_development_uses_real_secrets_when_provided():
    assert resolve_secrets({"APP_ENV": "development", **REAL}) == (
        REAL["SECRET_KEY"],
        REAL["JWT_SECRET_KEY"],
    )


# ---- secrets: production / unidentified --------------------------------

def test_production_with_real_secrets_works():
    assert resolve_secrets({"APP_ENV": "production", **REAL}) == (
        REAL["SECRET_KEY"],
        REAL["JWT_SECRET_KEY"],
    )


@pytest.mark.parametrize("app_env", ["production", "staging", "devlopment", "", None])
def test_non_development_missing_secrets_fail_clearly(app_env):
    environ = {} if app_env is None else {"APP_ENV": app_env}

    with pytest.raises(ConfigurationError) as excinfo:
        resolve_secrets(environ)

    message = str(excinfo.value)
    assert "SECRET_KEY is missing or blank" in message
    assert "JWT_SECRET_KEY is missing or blank" in message
    assert "APP_ENV=development" in message  # tells the developer how to fix it


@pytest.mark.parametrize("blank", ["", "   "])
def test_production_blank_secret_fails(blank):
    with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY is missing or blank"):
        resolve_secrets({"APP_ENV": "production", "SECRET_KEY": "real-value", "JWT_SECRET_KEY": blank})


def test_production_rejects_builtin_dev_defaults():
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_secrets({
            "APP_ENV": "production",
            "SECRET_KEY": DEV_SECRET_KEY,
            "JWT_SECRET_KEY": DEV_JWT_SECRET_KEY,
        })
    assert "built-in development default" in str(excinfo.value)


def test_configuration_errors_never_contain_secret_values():
    environ = {"APP_ENV": "production", "SECRET_KEY": DEV_SECRET_KEY, "JWT_SECRET_KEY": ""}

    with pytest.raises(ConfigurationError) as excinfo:
        resolve_secrets(environ)

    assert DEV_SECRET_KEY not in str(excinfo.value)
    assert DEV_JWT_SECRET_KEY not in str(excinfo.value)


# ---- host / port / debug -------------------------------------------------

def test_server_defaults_are_loopback_with_debug_off():
    assert resolve_server_options({}) == ("127.0.0.1", 5001, False)
    assert resolve_server_options({"HOST": "", "PORT": "", "FLASK_DEBUG": ""}) == ("127.0.0.1", 5001, False)


def test_lan_access_requires_explicit_host():
    assert resolve_server_options({"HOST": "0.0.0.0", "PORT": "5050"}) == ("0.0.0.0", 5050, False)


def test_debug_is_opt_in_in_development_on_loopback_only():
    base = {"APP_ENV": "development", "FLASK_DEBUG": "1"}
    assert resolve_server_options(base)[2] is True
    assert resolve_server_options({**base, "HOST": "localhost"})[2] is True


def test_debug_is_never_enabled_on_the_network():
    environ = {"APP_ENV": "development", "FLASK_DEBUG": "1", "HOST": "0.0.0.0"}
    assert resolve_server_options(environ) == ("0.0.0.0", 5001, False)


def test_debug_is_ignored_outside_development():
    assert resolve_server_options({"FLASK_DEBUG": "1"})[2] is False
    assert resolve_server_options({"APP_ENV": "production", "FLASK_DEBUG": "true"})[2] is False


@pytest.mark.parametrize("port", ["abc", "0", "70000", "-1"])
def test_invalid_port_fails_clearly(port):
    with pytest.raises(ConfigurationError, match="PORT"):
        resolve_server_options({"PORT": port})


def test_blank_env_values_fall_back_to_defaults_in_a_fresh_interpreter():
    """Regression: `cp .env.example .env` leaves SECRET_KEY=, JWT_SECRET_KEY=,
    DATABASE_URL= and UPLOAD_FOLDER= blank. They must not become empty
    strings. Runs in a subprocess so no shared module state is mutated."""
    import json
    import os
    import subprocess
    import sys

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {
        **os.environ,
        "APP_ENV": "development",
        "SECRET_KEY": "",
        "JWT_SECRET_KEY": "",
        "DATABASE_URL": "",
        "UPLOAD_FOLDER": "",
        "MAX_UPLOAD_MB": "",
    }
    code = (
        "import json, config; c = config.Config; "
        "print(json.dumps({k: getattr(c, k) for k in "
        "('SECRET_KEY', 'JWT_SECRET_KEY', 'SQLALCHEMY_DATABASE_URI', 'UPLOAD_FOLDER', 'MAX_UPLOAD_BYTES')}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=backend_dir, env=env,
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip().splitlines()[-1])
    assert values["SECRET_KEY"] == DEV_SECRET_KEY
    assert values["JWT_SECRET_KEY"] == DEV_JWT_SECRET_KEY
    assert values["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")
    assert values["SQLALCHEMY_DATABASE_URI"].endswith("civicpulse.db")
    assert values["UPLOAD_FOLDER"].endswith("uploads")
    assert values["MAX_UPLOAD_BYTES"] == 10 * 1024 * 1024


def test_app_refuses_to_start_in_production_without_secrets():
    import os
    import subprocess
    import sys

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "APP_ENV": "production", "SECRET_KEY": "", "JWT_SECRET_KEY": ""}
    result = subprocess.run(
        [sys.executable, "-c", "import config"], cwd=backend_dir, env=env,
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode != 0
    assert "SECRET_KEY is missing or blank" in result.stderr
