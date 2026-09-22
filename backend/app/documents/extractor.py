from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


def extract_pdf(file_path: str):
    reader = PdfReader(file_path)

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        if text.strip():
            pages.append(
                {
                    "text": text,
                    "page": page_number,
                }
            )

    return pages


def extract_docx(file_path: str):
    document = DocxDocument(
        file_path
    )

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    text = "\n".join(paragraphs)

    return [
        {
            "text": text,
            "page": None,
        }
    ]


def extract_txt(file_path: str):
    text = Path(
        file_path
    ).read_text(
        encoding="utf-8",
        errors="ignore",
    )

    return [
        {
            "text": text,
            "page": None,
        }
    ]