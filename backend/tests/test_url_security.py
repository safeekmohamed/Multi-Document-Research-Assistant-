import unittest
from unittest.mock import patch

from app.urls.security import validate_public_http_url


class PublicURLValidationTests(unittest.TestCase):
    @patch("app.urls.security.socket.getaddrinfo")
    def test_accepts_public_host(self, resolve):
        resolve.return_value = [(None, None, None, None, ("93.184.216.34", 443))]
        validate_public_http_url("https://example.com/article")

    @patch("app.urls.security.socket.getaddrinfo")
    def test_rejects_private_resolution(self, resolve):
        resolve.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        with self.assertRaisesRegex(ValueError, "public IP"):
            validate_public_http_url("http://example.com/")

    def test_rejects_non_http_and_nonstandard_ports(self):
        for url in ("file:///etc/passwd", "http://example.com:8080/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_public_http_url(url)


if __name__ == "__main__":
    unittest.main()
