from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)


splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=[
        "\n\n",
        "\n",
        ". ",
        " ",
        "",
    ],
)


def split_document_pages(
    pages: list[dict],
):
    chunks = []

    for page in pages:
        text = page["text"]
        page_number = page.get(
            "page"
        )

        split_texts = splitter.split_text(
            text
        )

        for chunk in split_texts:
            chunks.append(
                {
                    "text": chunk,
                    "page": page_number,
                }
            )

    return chunks


def split_text(
    text: str,
):
    return splitter.split_text(
        text
    )