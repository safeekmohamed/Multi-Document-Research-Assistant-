from pathlib import Path

import pandas as pd
from docx import Document as DocxDocument
from pptx import Presentation
from pypdf import PdfReader

MAX_PDF_PAGES = 5_000
MAX_PDF_TEXT_CHARACTERS = 5_000_000


def extract_pdf(
    file_path: str,
) -> list[dict]:
    reader = PdfReader(file_path)
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("The PDF exceeds the 5,000 page processing limit")

    pages = []
    extracted_characters = 0

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        text = text.strip()

        if not text:
            continue

        extracted_characters += len(text)
        if extracted_characters > MAX_PDF_TEXT_CHARACTERS:
            raise ValueError(
                "The extracted document text exceeds the 5 million character processing limit"
            )

        pages.append(
            {
                "text": text,
                "page": page_number,
            }
        )

    return pages


def extract_docx(
    file_path: str,
) -> list[dict]:
    document = DocxDocument(file_path)

    paragraphs = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if text:
            paragraphs.append(text)

    text = "\n".join(paragraphs)

    if not text.strip():
        return []

    return [
        {
            "text": text,
            "page": None,
        }
    ]


def extract_txt(
    file_path: str,
) -> list[dict]:
    text = Path(file_path).read_text(
        encoding="utf-8",
        errors="ignore",
    )

    text = text.strip()

    if not text:
        return []

    return [
        {
            "text": text,
            "page": None,
        }
    ]


def extract_csv(
    file_path: str,
) -> list[dict]:
    dataframe = pd.read_csv(file_path)

    text = dataframe.to_string(
        index=False
    ).strip()

    if not text:
        return []

    return [
        {
            "text": text,
            "page": None,
        }
    ]


def extract_excel(
    file_path: str,
) -> list[dict]:
    sheets = pd.read_excel(
        file_path,
        sheet_name=None,
    )

    sheet_texts = []

    for sheet_name, dataframe in sheets.items():

        if dataframe.empty:
            continue

        text = dataframe.to_string(
            index=False
        ).strip()

        if text:
            sheet_texts.append(
                f"Sheet: {sheet_name}\n{text}"
            )

    text = "\n\n".join(
        sheet_texts
    ).strip()

    if not text:
        return []

    return [
        {
            "text": text,
            "page": None,
        }
    ]


def extract_pptx(
    file_path: str,
) -> list[dict]:
    presentation = Presentation(file_path)

    slides = []

    for slide_number, slide in enumerate(
        presentation.slides,
        start=1,
    ):
        slide_texts = []

        for shape in slide.shapes:

            if not hasattr(
                shape,
                "text",
            ):
                continue

            text = shape.text.strip()

            if text:
                slide_texts.append(text)

        text = "\n".join(
            slide_texts
        ).strip()

        if not text:
            continue

        slides.append(
            {
                "text": text,
                "page": slide_number,
            }
        )

    return slides
