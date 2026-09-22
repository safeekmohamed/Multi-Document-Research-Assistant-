from pathlib import Path

from app.documents.extractor import (
    extract_docx,
    extract_pdf,
    extract_txt,
)


def load_document(file_path: str):
    extension = Path(
        file_path
    ).suffix.lower()

    if extension == ".pdf":
        return extract_pdf(
            file_path
        )

    if extension == ".docx":
        return extract_docx(
            file_path
        )

    if extension == ".txt":
        return extract_txt(
            file_path
        )

    raise ValueError(
        "Supported file types are PDF, DOCX and TXT"
    )