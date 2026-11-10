import pytest

from backend import auth


@pytest.fixture(autouse=True)
def fresh_discord_limiter():
    """The shared Discord limiter and the server-roles memory are process-wide: one test's 429 must not pause the next."""
    auth.discord_limiter.reset()
    auth._server_roles.clear()
    yield
    auth.discord_limiter.reset()
    auth._server_roles.clear()
