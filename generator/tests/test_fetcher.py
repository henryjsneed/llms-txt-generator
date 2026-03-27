from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llms_txt_generator.crawler.fetcher import SSRFError, safe_fetch


# ---------------------------------------------------------------------------
# Helpers for mocking httpx responses
# ---------------------------------------------------------------------------

def _mock_response(
    status_code: int = 200,
    text: str = "",
    content_type: str = "text/html",
    url: str = "https://example.com",
    is_redirect: bool = False,
    next_request_url: str | None = None,
    content_length: str | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    headers: dict[str, str] = {"content-type": content_type}
    if content_length is not None:
        headers["content-length"] = content_length
    resp.headers = headers
    resp.url = url
    resp.is_redirect = is_redirect
    if next_request_url:
        next_req = MagicMock()
        next_req.url = next_request_url
        resp.next_request = next_req
    else:
        resp.next_request = None
    return resp


@pytest.fixture
def _skip_dns():
    """Patch resolve_and_validate to bypass real DNS resolution."""
    with patch(
        "llms_txt_generator.crawler.fetcher.resolve_and_validate",
        new_callable=AsyncMock,
    ):
        yield


# ---------------------------------------------------------------------------
# safe_fetch integration tests
# ---------------------------------------------------------------------------


class TestSafeFetchSuccess:
    async def test_returns_html_content(self, _skip_dns):
        client = AsyncMock()
        client.get.return_value = _mock_response(
            status_code=200,
            text="<html><title>Hello</title></html>",
            url="https://example.com/page",
        )

        result = await safe_fetch("https://example.com/page", client)
        assert result.status_code == 200
        assert "<title>Hello</title>" in result.body
        assert result.url == "https://example.com/page"

    async def test_follows_normal_redirect(self, _skip_dns):
        redirect_resp = _mock_response(
            status_code=301,
            is_redirect=True,
            next_request_url="https://example.com/new-page",
        )
        final_resp = _mock_response(
            status_code=200,
            text="<html><title>New Page</title></html>",
            url="https://example.com/new-page",
        )
        client = AsyncMock()
        client.get.side_effect = [redirect_resp, final_resp]

        result = await safe_fetch("https://example.com/old-page", client)
        assert result.status_code == 200
        assert "New Page" in result.body


class TestSafeFetchBlockedRedirect:
    async def test_redirect_to_blocked_returns_403(self, _skip_dns):
        redirect_resp = _mock_response(
            status_code=302,
            is_redirect=True,
            next_request_url="https://example.com/blocked?url=orig",
        )
        client = AsyncMock()
        client.get.return_value = redirect_resp

        result = await safe_fetch("https://example.com/page", client)
        assert result.status_code == 403
        assert "Robot or human" in result.body


class TestSafeFetchContentType:
    async def test_rejects_non_html(self, _skip_dns):
        client = AsyncMock()
        client.get.return_value = _mock_response(
            status_code=200,
            text='{"key": "value"}',
            content_type="application/json",
        )

        with pytest.raises(SSRFError, match="Blocked content-type"):
            await safe_fetch("https://example.com/api/data", client)


class TestSafeFetchSizeLimit:
    async def test_rejects_large_content_length(self, _skip_dns):
        client = AsyncMock()
        client.get.return_value = _mock_response(
            status_code=200,
            text="<html>small body</html>",
            content_length="999999999",
        )

        with pytest.raises(SSRFError, match="too large"):
            await safe_fetch("https://example.com/huge", client)


class TestSafeFetchRedirectLimit:
    async def test_stops_after_five_redirects(self, _skip_dns):
        redirect = _mock_response(
            status_code=302,
            is_redirect=True,
            next_request_url="https://example.com/loop",
        )
        final = _mock_response(
            status_code=200,
            text="<html>ok</html>",
            url="https://example.com/final",
        )
        client = AsyncMock()
        client.get.side_effect = [redirect] * 5 + [final]

        result = await safe_fetch("https://example.com/start", client)
        assert result.status_code == 200
        assert client.get.call_count == 6

    async def test_exceeds_redirect_limit_stops_at_six_requests(self, _skip_dns):
        redirect = _mock_response(
            status_code=302,
            is_redirect=True,
            next_request_url="https://example.com/loop",
        )
        client = AsyncMock()
        client.get.return_value = redirect

        result = await safe_fetch("https://example.com/start", client)
        assert client.get.call_count == 6  # 1 initial + 5 redirects
        assert result.status_code == 302


class TestSafeFetchBodySizeLimit:
    async def test_rejects_large_decoded_body(self, _skip_dns):
        client = AsyncMock()
        oversized_body = "x" * (6 * 1024 * 1024)
        client.get.return_value = _mock_response(
            status_code=200,
            text=oversized_body,
            url="https://example.com/huge",
        )

        with pytest.raises(SSRFError, match="size limit"):
            await safe_fetch("https://example.com/huge", client)


class TestSafeFetchSSRF:
    async def test_rejects_file_scheme(self):
        client = AsyncMock()
        with pytest.raises(SSRFError, match="Blocked scheme"):
            await safe_fetch("file:///etc/passwd", client)

    async def test_rejects_private_ip(self):
        client = AsyncMock()
        with pytest.raises(SSRFError, match="Blocked IP"):
            await safe_fetch("http://127.0.0.1/admin", client)
