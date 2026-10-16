import re

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
            "",
        ],
    )

SECTION_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)*)[\.\)]?\s+(.+?)\s*$"
)

def detect_section_heading(
    line: str,
) -> tuple[str | None, str | None]:
    """
    Detect numbered headings such as:

        1. Introduction
        2. Components
        2.1 Models
        2.2 Prompts
        2.3 Chains
        3. Applications

    Returns:

        ("2", "Components")
        ("2.1", "Models")
        ("2.2", "Prompts")

    If the line is not a numbered heading,
    returns (None, None).
    """

    if not line:
        return None, None

    line = line.strip()

    match = SECTION_PATTERN.match(line)

    if not match:
        return None, None

    section_number = match.group(1).strip()
    section_title = match.group(2).strip()

    if not section_title:
        return None, None

    return section_number, section_title

def get_parent_section(
    section_number: str | None,
) -> str | None:
    """
    Convert:

        2       -> 2
        2.1     -> 2
        2.2     -> 2
        2.3.1   -> 2.3
        3       -> 3

    This allows the retriever to understand
    parent-child section relationships.
    """

    if not section_number:
        return None

    parts = section_number.split(".")

    if len(parts) == 1:
        return section_number

    return ".".join(parts[:-1])

def clean_text(
    text: str,
) -> str:
    """
    Remove unnecessary whitespace while preserving
    meaningful paragraph separation.
    """

    if not text:
        return ""

    text = text.replace(
        "\x00",
        " ",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()

def split_document_pages(
    pages: list[dict],
) -> list[dict]:
    """
    Split extracted document pages into RAG chunks
    while preserving:

        - page metadata
        - section number
        - section title
        - parent section
        - hierarchy level

    Example:

        2. Components
        2.1 Models
        2.2 Prompts
        2.3 Chains

    Chunks belonging to 2.1, 2.2 and 2.3
    will all carry:

        parent_section = "2"

    This allows later retrieval to expand a
    parent question into its child sections.
    """

    chunks = []

    for page in pages:

        text = clean_text(
            page.get("text", "")
        )

        if not text:
            continue

        page_number = page.get("page")

        current_section = None
        current_section_title = None
        current_parent_section = None
        current_hierarchy_level = 0

        lines = text.splitlines()

        section_blocks = []

        current_block_lines = []

        block_section = None
        block_section_title = None
        block_parent_section = None
        block_hierarchy_level = 0

        for line in lines:

            stripped_line = line.strip()

            section_number, section_title = (
                detect_section_heading(
                    stripped_line
                )
            )

            if section_number:

                if current_block_lines:

                    section_blocks.append(
                        {
                            "text": "\n".join(
                                current_block_lines
                            ).strip(),
                            "section": block_section,
                            "section_title": (
                                block_section_title
                            ),
                            "parent_section": (
                                block_parent_section
                            ),
                            "hierarchy_level": (
                                block_hierarchy_level
                            ),
                        }
                    )

                current_section = section_number
                current_section_title = section_title

                current_parent_section = (
                    get_parent_section(
                        current_section
                    )
                )

                current_hierarchy_level = (
                    len(
                        current_section.split(".")
                    )
                )

                block_section = current_section
                block_section_title = (
                    current_section_title
                )
                block_parent_section = (
                    current_parent_section
                )
                block_hierarchy_level = (
                    current_hierarchy_level
                )

                current_block_lines = [
                    stripped_line
                ]

            else:

                if stripped_line:
                    current_block_lines.append(
                        stripped_line
                    )

        if current_block_lines:

            section_blocks.append(
                {
                    "text": "\n".join(
                        current_block_lines
                    ).strip(),
                    "section": block_section,
                    "section_title": (
                        block_section_title
                    ),
                    "parent_section": (
                        block_parent_section
                    ),
                    "hierarchy_level": (
                        block_hierarchy_level
                    ),
                }
            )

        if not section_blocks:

            split_texts = _get_splitter().split_text(
                text
            )

            for chunk in split_texts:

                chunk = chunk.strip()

                if not chunk:
                    continue

                chunks.append(
                    {
                        "text": chunk,
                        "page": page_number,
                        "section": None,
                        "section_title": None,
                        "parent_section": None,
                        "hierarchy_level": 0,
                    }
                )

            continue

        for block in section_blocks:

            block_text = block["text"]

            if not block_text:
                continue

            split_texts = _get_splitter().split_text(
                block_text
            )

            for chunk in split_texts:

                chunk = chunk.strip()

                if not chunk:
                    continue

                chunks.append(
                    {
                        "text": chunk,
                        "page": page_number,
                        "section": block[
                            "section"
                        ],
                        "section_title": block[
                            "section_title"
                        ],
                        "parent_section": block[
                            "parent_section"
                        ],
                        "hierarchy_level": block[
                            "hierarchy_level"
                        ],
                    }
                )

    return chunks

def split_text(
    text: str,
) -> list[str]:
    """
    Split plain text such as URL content.

    Kept as list[str] for compatibility with the
    existing URL processing code.

    Hierarchy-aware URL metadata can be added at
    the URL service layer without breaking the
    current interface.
    """

    text = clean_text(
        text
    )

    if not text:
        return []

    return [
        chunk.strip()
        for chunk in _get_splitter().split_text(
            text
        )
        if chunk.strip()
    ]
