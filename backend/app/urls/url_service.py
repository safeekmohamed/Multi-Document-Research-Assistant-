from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.database.mongodb import (
    documents_collection,
)
from app.documents.splitter import split_document_pages
from app.rag.vector_store import add_chunks
from app.urls.security import validate_public_http_url

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


def fetch_url_content(
    url: str,
):
    validate_public_http_url(url)
    response = requests.get(
        url,
        timeout=15,
        allow_redirects=False,
        headers={
            "User-Agent": USER_AGENT
        },
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
            "header",
            "footer",
            "nav",
            "form",
            "svg",
        ]
    ):
        element.decompose()

    title = (
        soup.title.get_text(
            " ",
            strip=True,
        )
        if soup.title
        else urlparse(url).netloc
    )

    main_content = soup.find(
        "main"
    )

    if main_content:
        text = main_content.get_text(
            separator="\n",
            strip=True,
        )
    else:
        text = soup.get_text(
            separator="\n",
            strip=True,
        )

    cleaned_lines = []

    for line in text.splitlines():
        line = " ".join(
            line.split()
        )

        if line:
            cleaned_lines.append(line)

    return {
        "title": title,
        "text": "\n".join(
            cleaned_lines
        ),
    }

def add_url_source(
    user_id: str,
    url: str,
):
    url = url.strip()

    validate_public_http_url(url)

    page = fetch_url_content(url)

    text = page["text"]

    if not text.strip():
        raise ValueError(
            "No readable text was found on this URL"
        )

    pages = [
        {
            "page": 0,
            "text": text,
        }
    ]

    chunks = split_document_pages(
        pages
    )

    if not chunks:
        raise ValueError(
            "The URL did not contain enough readable text"
        )

    source_id = uuid4().hex

    metadatas = []

    for chunk in chunks:

        hierarchy_level = chunk.get(
            "hierarchy_level",
            0,
        )

        try:
            hierarchy_level = int(
                hierarchy_level
            )
        except (
            TypeError,
            ValueError,
        ):
            hierarchy_level = 0

        metadatas.append(
            {
                "source_id": source_id,
                "url": url,
                "title": page["title"],
                "source_type": "url",
                "filename": page["title"],
                "page": chunk.get(
                    "page",
                    0,
                ),

                "section": chunk.get(
                    "section"
                ),
                "section_title": chunk.get(
                    "section_title"
                ),
                "parent_section": chunk.get(
                    "parent_section"
                ),
                "hierarchy_level": hierarchy_level,
            }
        )

    chunk_texts = [
        chunk["text"]
        for chunk in chunks
    ]

    vector_ids = add_chunks(
        user_id=user_id,
        chunks=chunk_texts,
        metadatas=metadatas,
    )

    document = {
        "user_id": user_id,
        "source_id": source_id,
        "filename": page["title"],
        "file_type": "url",
        "source_type": "url",
        "source_url": url,
        "chunk_count": len(
            vector_ids
        ),
        "created_at": datetime.now(
            timezone.utc
        ),
    }

    result = documents_collection.insert_one(
        document
    )

    return {
        "id": str(
            result.inserted_id
        ),
        "filename": page["title"],
        "file_type": "url",
        "source_type": "url",
        "source_url": url,
        "chunk_count": len(
            vector_ids
        ),
    }

def list_user_urls(
    user_id: str,
):
    documents = (
        documents_collection.find(
            {
                "user_id": user_id,
                "source_type": "url",
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return [
        {
            "id": str(
                document["_id"]
            ),
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

def search_web(
    query: str,
):
    query = query.strip()

    if not query:
        raise ValueError(
            "Search query cannot be empty"
        )

    try:
        search_results = []

        with DDGS() as search_client:
            results = search_client.text(
                query,
                max_results=5,
            )

            for result in results:
                search_results.append(
                    {
                        "title": result.get(
                            "title",
                            "",
                        ),
                        "url": result.get(
                            "href",
                            "",
                        ),
                        "snippet": result.get(
                            "body",
                            "",
                        ),
                    }
                )

        return {
            "query": query,
            "results": search_results,
        }

    except Exception as error:
        raise RuntimeError(
            f"Web search failed: {error}"
        )
