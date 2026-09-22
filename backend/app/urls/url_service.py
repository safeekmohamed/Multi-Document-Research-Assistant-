import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.database.mongodb import documents_collection
from app.documents.splitter import split_text
from app.rag.vector_store import add_chunks


def fetch_url_content(url: str):
    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            )
        },
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
            "header",
            "footer",
            "nav",
        ]
    ):
        element.decompose()

    title = (
        soup.title.get_text(strip=True)
        if soup.title
        else urlparse(url).netloc
    )

    text = soup.get_text(
        separator="\n",
        strip=True,
    )

    return {
        "title": title,
        "text": text,
    }


def add_url_source(
    user_id: str,
    url: str,
):
    url = url.strip()

    if not url.startswith(
        ("http://", "https://")
    ):
        raise ValueError(
            "URL must start with http:// or https://"
        )

    page = fetch_url_content(url)

    text = page["text"]

    if not text.strip():
        raise ValueError(
            "No readable text was found on this URL"
        )

    chunks = split_text(text)

    if not chunks:
        raise ValueError(
            "The URL did not contain enough readable text"
        )

    metadatas = []

    for chunk in chunks:
        metadatas.append(
            {
                "url": url,
                "title": page["title"],
                "source_type": "url",
                "filename": page["title"],
                "page": 0,
            }
        )

    vector_ids = add_chunks(
        user_id=user_id,
        chunks=chunks,
        metadatas=metadatas,
    )

    document = {
        "user_id": user_id,
        "filename": page["title"],
        "file_type": "url",
        "source_type": "url",
        "source_url": url,
        "stored_path": None,
        "created_at": datetime.now(
            timezone.utc
        ),
    }

    result = documents_collection.insert_one(
        document
    )

    return {
        "id": str(result.inserted_id),
        "filename": page["title"],
        "file_type": "url",
        "source_type": "url",
        "source_url": url,
        "chunk_count": len(vector_ids),
    }


def list_user_urls(
    user_id: str,
):
    documents = documents_collection.find(
        {
            "user_id": user_id,
            "source_type": "url",
        }
    ).sort(
        "created_at",
        -1,
    )

    return [
        {
            "id": str(document["_id"]),
            "filename": document.get(
                "filename",
                "Website",
            ),
            "file_type": "url",
            "source_type": "url",
            "source_url": document.get(
                "source_url"
            ),
        }
        for document in documents
    ]


def search_web(query: str):
    return {
        "message": (
            "Web search is currently handled "
            "through the indexed URL sources."
        ),
        "query": query,
        "results": [],
    }