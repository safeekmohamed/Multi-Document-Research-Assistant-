
import re
from functools import lru_cache

from langchain_text_splitters import RecursiveCharacterTextSplitter


SECTION_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)*)(?:[.)])?\s+(.+?)\s*$"
)


@lru_cache(maxsize=1)
def _get_splitter():
    return RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=[
            "\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""
        ],
    )


def detect_section_heading(line: str) -> tuple[str | None, str | None]:
    if not line:
        return None, None

    match = SECTION_PATTERN.match(line.strip())
    if not match:
        return None, None

    number, title = match.group(1).strip(), match.group(2).strip()
    return (number, title) if title else (None, None)


def get_parent_section(section_number: str | None) -> str | None:
    if not section_number:
        return None

    parts = section_number.split(".")
    return section_number if len(parts) == 1 else ".".join(parts[:-1])


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _make_chunks(text: str, page_number, section=None,
                 section_title=None, parent_section=None,
                 hierarchy_level=0) -> list[dict]:
    result = []

    for chunk in _get_splitter().split_text(text):
        chunk = chunk.strip()
        if chunk:
            result.append({
                "text": chunk,
                "page": page_number,
                "section": section,
                "section_title": section_title,
                "parent_section": parent_section,
                "hierarchy_level": hierarchy_level,
            })

    return result


def split_document_pages(pages: list[dict]) -> list[dict]:
    chunks = []

    for page in pages:
        text = clean_text(page.get("text", ""))
        if not text:
            continue

        page_number = page.get("page")
        blocks = []
        current_lines = []
        current_section = None
        current_title = None

        for line in text.splitlines():
            stripped = line.strip()
            number, title = detect_section_heading(stripped)

            if number:
                if current_lines:
                    blocks.append((
                        "\n".join(current_lines),
                        current_section,
                        current_title,
                    ))

                current_section = number
                current_title = title
                current_lines = [stripped]

            elif stripped:
                current_lines.append(stripped)

        if current_lines:
            blocks.append((
                "\n".join(current_lines),
                current_section,
                current_title,
            ))

        if not blocks:
            chunks.extend(_make_chunks(text, page_number))
            continue

        for block_text, section, title in blocks:
            parent = get_parent_section(section)
            level = len(section.split(".")) if section else 0

            chunks.extend(_make_chunks(
                block_text,
                page_number,
                section,
                title,
                parent,
                level,
            ))

    return chunks


def split_text(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []

    return [
        chunk.strip()
        for chunk in _get_splitter().split_text(text)
        if chunk.strip()
    ]
