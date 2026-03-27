from unittest.mock import AsyncMock, MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

from llms_txt_generator.crawler.robots import USER_AGENT, fetch_robots, is_allowed


def _mock_response(status_code: int = 200, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture
def _skip_dns():
    with patch(
        "llms_txt_generator.crawler.robots.resolve_and_validate",
        new_callable=AsyncMock,
    ):
        yield


class TestFetchRobots:
    async def test_parses_valid_robots_txt(self, _skip_dns):
        robots_body = "User-agent: *\nDisallow: /secret\n"
        client = AsyncMock()
        client.get.return_value = _mock_response(200, robots_body)

        parser = await fetch_robots("https://example.com", client)
        assert not parser.can_fetch(USER_AGENT, "https://example.com/secret")
        assert parser.can_fetch(USER_AGENT, "https://example.com/public")

    async def test_allows_all_on_404(self, _skip_dns):
        client = AsyncMock()
        client.get.return_value = _mock_response(404)

        parser = await fetch_robots("https://example.com", client)
        assert parser.can_fetch(USER_AGENT, "https://example.com/anything")

    async def test_allows_all_on_network_error(self, _skip_dns):
        client = AsyncMock()
        client.get.side_effect = Exception("connection refused")

        parser = await fetch_robots("https://example.com", client)
        assert parser.can_fetch(USER_AGENT, "https://example.com/anything")


class TestIsAllowed:
    def test_respects_disallow(self):
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /admin"])
        assert is_allowed(parser, "https://example.com/admin") is False

    def test_allows_unlisted_path(self):
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /admin"])
        assert is_allowed(parser, "https://example.com/docs") is True

    def test_wildcard_disallow(self):
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /"])
        assert is_allowed(parser, "https://example.com/anything") is False
