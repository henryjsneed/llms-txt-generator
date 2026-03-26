import pytest

from llms_txt_worker.crawler.fetcher import SSRFError, _is_blocked_ip, validate_url


class TestIsBlockedIP:
    def test_loopback(self):
        assert _is_blocked_ip("127.0.0.1") is True
        assert _is_blocked_ip("127.0.0.2") is True

    def test_private_10(self):
        assert _is_blocked_ip("10.0.0.1") is True
        assert _is_blocked_ip("10.255.255.255") is True

    def test_private_172(self):
        assert _is_blocked_ip("172.16.0.1") is True
        assert _is_blocked_ip("172.31.255.255") is True

    def test_private_192(self):
        assert _is_blocked_ip("192.168.0.1") is True
        assert _is_blocked_ip("192.168.255.255") is True

    def test_link_local(self):
        assert _is_blocked_ip("169.254.169.254") is True
        assert _is_blocked_ip("169.254.0.1") is True

    def test_multicast(self):
        assert _is_blocked_ip("224.0.0.1") is True
        assert _is_blocked_ip("239.255.255.255") is True

    def test_ipv6_loopback(self):
        assert _is_blocked_ip("::1") is True

    def test_ipv6_ula(self):
        assert _is_blocked_ip("fd00::1") is True

    def test_public_ips_allowed(self):
        assert _is_blocked_ip("8.8.8.8") is False
        assert _is_blocked_ip("1.1.1.1") is False
        assert _is_blocked_ip("93.184.216.34") is False

    def test_invalid_ip(self):
        assert _is_blocked_ip("not-an-ip") is True


class TestValidateUrl:
    def test_http_allowed(self):
        validate_url("http://example.com")

    def test_https_allowed(self):
        validate_url("https://example.com")

    def test_ftp_blocked(self):
        with pytest.raises(SSRFError, match="Blocked scheme"):
            validate_url("ftp://example.com")

    def test_file_blocked(self):
        with pytest.raises(SSRFError, match="Blocked scheme"):
            validate_url("file:///etc/passwd")

    def test_javascript_blocked(self):
        with pytest.raises(SSRFError, match="Blocked scheme"):
            validate_url("javascript:alert(1)")

    def test_private_ip_literal(self):
        with pytest.raises(SSRFError, match="Blocked IP"):
            validate_url("http://127.0.0.1/admin")

    def test_metadata_ip(self):
        with pytest.raises(SSRFError, match="Blocked IP"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_missing_hostname(self):
        with pytest.raises(SSRFError, match="Missing hostname"):
            validate_url("http:///path")

    def test_normal_url_passes(self):
        validate_url("https://docs.stripe.com/api")
