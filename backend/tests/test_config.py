import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET, MIN_PRODUCTION_SECRET_LENGTH, Settings

GOOD_SECRET = "a" * MIN_PRODUCTION_SECRET_LENGTH


def settings(**overrides):
    # _env_file=None and explicit values keep the developer's own .env and environment out of it.
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_plain_database_urls_from_hosting_platforms_use_the_async_driver(scheme):
    s = settings(database_url=f"{scheme}://user:pw@db.internal:5432/app")
    assert s.database_url == "postgresql+asyncpg://user:pw@db.internal:5432/app"


def test_a_url_that_already_names_the_driver_is_left_alone():
    url = "postgresql+asyncpg://user:pw@db:5432/app"
    assert settings(database_url=url).database_url == url


def test_the_development_defaults_work_without_any_configuration():
    s = settings()
    assert s.environment == "development"
    assert s.jwt_secret == DEV_JWT_SECRET


def test_production_refuses_the_built_in_development_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET must be set in production"):
        settings(environment="production")


def test_production_refuses_a_short_secret():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        settings(environment="production", jwt_secret="short")
    with pytest.raises(ValidationError, match="at least 32 characters"):
        settings(environment="production", jwt_secret="a" * (MIN_PRODUCTION_SECRET_LENGTH - 1))


def test_production_accepts_a_proper_secret():
    assert settings(environment="production", jwt_secret=GOOD_SECRET).environment == "production"


def test_the_secret_rules_do_not_get_in_the_way_of_development():
    assert settings(environment="development", jwt_secret="short").jwt_secret == "short"


def test_a_rejected_secret_is_never_echoed_into_the_error():
    almost = "almost-a-real-secret"  # long enough to be plausible, too short to be accepted
    with pytest.raises(ValidationError) as caught:
        settings(environment="production", jwt_secret=almost)
    # What a crash prints into the logs. (.errors() still carries the input for code that asks.)
    assert almost not in str(caught.value)
