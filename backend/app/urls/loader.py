from app.urls.extractor import (
    fetch_url,
)


def load_url(url: str):
    return fetch_url(url)