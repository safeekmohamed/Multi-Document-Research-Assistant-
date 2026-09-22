import requests
from bs4 import BeautifulSoup


def fetch_url(
    url: str,
):
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "ResearchAssistant/1.0"
            )
        },
        timeout=15,
    )

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