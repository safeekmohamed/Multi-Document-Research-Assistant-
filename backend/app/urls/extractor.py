import requests
from bs4 import BeautifulSoup
from app.urls.security import validate_public_http_url


def fetch_url(
    url: str,
):
    validate_public_http_url(url)
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "ResearchAssistant/1.0"
            )
        },
        timeout=15,
        allow_redirects=False,
    )

    if 300 <= response.status_code < 400:
        raise ValueError("Website redirected. Submit its final public URL instead.")

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        element.decompose()

    title = (
        soup.title.get_text(
            strip=True
        )
        if soup.title
        else url
    )

    text = soup.get_text(
        separator="\n",
        strip=True,
    )

    return {
        "title": title,
        "text": text,
        "url": url,
    }
