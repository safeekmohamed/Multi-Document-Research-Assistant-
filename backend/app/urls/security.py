import ipaddress
import socket
from urllib.parse import urlparse


def validate_public_http_url(url: str) -> None:
    """Reject local/private destinations before fetching user supplied URLs."""
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("URL must be a public HTTP or HTTPS address")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL has an invalid port") from error
    if port is not None and port not in {80, 443}:
        raise ValueError("URL must use the standard HTTP or HTTPS port")

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise ValueError("URL host could not be resolved") from error
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global
        for address in addresses
    ):
        raise ValueError("URL must resolve only to public IP addresses")
