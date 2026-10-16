from pathlib import Path

from app.documents.extractor import (
    extract_csv,
    extract_docx,
    extract_excel,
    extract_pdf,
    extract_pptx,
    extract_txt,
)


LOADERS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".txt": extract_txt,
    ".csv": extract_csv,
    ".xlsx": extract_excel,
    ".pptx": extract_pptx,
}


def load_document(
    file_path: str,
) -> list[dict]:
    extension = Path(
        file_path
    ).suffix.lower()

    loader = LOADERS.get(extension)

    if loader is None:
        raise ValueError(
            "Supported file types are PDF, DOCX, TXT, CSV, XLSX and PPTX"
        )

    return loader(file_path)