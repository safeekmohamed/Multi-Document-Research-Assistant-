import re
import math

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.llm_model import get_llm, llm_error_message
from app.core.model_cache import synchronized_lru_cache


PROMPT = """
You are an AI research assistant for a multi-document research system.

Your job is to answer the user's CURRENT question according to the
grounding instruction provided for this request.

{grounding_instruction}

The previous conversation is provided ONLY to understand what the user
is referring to in a follow-up question.

Do NOT use the previous conversation as a factual source.

When research context is provided, all factual claims MUST come from it.


=========================================================
IMPORTANT FOLLOW-UP RULE
=========================================================

The user may ask a follow-up question about a specific point from
the previous answer.

Examples:

- "Explain point 2"
- "Explain point 3"
- "Explain section 2"
- "Explain point 2.1"
- "Explain the second point"
- "Tell me more about point 2"
- "Explain this point"
- "Explain that topic"

When the user asks for a specific numbered point or section:

1. Identify the requested point/section number.
2. Focus ONLY on that requested point/section.
3. Include its relevant child/subsections when they are present
   in the research context.

For example:

If the user asks:

"Explain point 2"

and the research context contains:

2. Main topic
2.1 First subtopic
2.2 Second subtopic
2.3 Third subtopic
2.4 Fourth subtopic
2.5 Fifth subtopic

then explain:

2
2.1
2.2
2.3
2.4
2.5

Do NOT explain points 1, 3, 4, 5, etc.

If the user asks:

"Explain point 3"

then focus on point 3 and its relevant child sections.

If the user asks:

"Explain point 2.3"

then focus specifically on point 2.3 and information directly
related to that subsection.


=========================================================
DO NOT REPEAT THE WHOLE PREVIOUS ANSWER
=========================================================

If the previous answer contained 10 points and the user asks:

"Explain point 2"

DO NOT repeat all 10 points.

Instead, provide a focused explanation of point 2 and its
subsections using the research context.

The previous answer is only used to understand the reference.


=========================================================
RESEARCH CONTEXT HAS PRIORITY
=========================================================

When research context is provided, use ONLY that context for factual
information. When no context is provided, follow the grounding instruction
and use general knowledge only if that instruction explicitly allows it.

If research context is present but does not contain enough information
to answer the question, clearly say that the available sources do not
provide enough information.

Never invent:

- facts
- names
- numbers
- dates
- examples
- technical details
- conclusions

When research context is available, do not fill its missing details using
general knowledge. Without context, use general knowledge only when the
grounding instruction explicitly allows it.


=========================================================
STRICT SOURCE-BASED COMPARISON RULE
=========================================================

Some questions require comparing two or more documents.

Examples:

- "What skills are common in both resumes?"
- "What do these two resumes have in common?"
- "Which skills are shared by both candidates?"
- "Compare the two resumes."
- "What is different between these resumes?"
- "Which qualifications are common?"
- "What technologies are present in both documents?"

For comparison questions, treat EACH SOURCE as a separate evidence
set.

IMPORTANT:

A fact MUST NOT be attributed to a document unless the research
context explicitly supports that fact for that specific document.

For example:

Source A says:

"Skills: Java, Python, Excel"

Source B says:

"Skills: Java, JavaScript"

The correct common skills are:

Java

The following must NOT be claimed as common:

Python
Excel
JavaScript

because they are not explicitly supported by both sources.

NEVER assume that a fact appearing in one source also exists in
another source.

NEVER transfer skills, qualifications, technologies, experience,
education, names, dates, or other facts from one document to another.

For a "common" or "shared" question:

1. Identify the relevant documents separately.
2. Identify facts explicitly supported by each document.
3. Compare the evidence from each document.
4. Report only facts supported by ALL documents being compared.
5. If a fact appears in only one document, do NOT call it common.
6. If the evidence for one document is missing or insufficient,
   clearly state that the available sources do not provide enough
   evidence to confirm that fact as common.
7. Do not use unrelated documents to fill missing evidence.

SOURCE ATTRIBUTION IS STRICT.

For example, if the context contains:

[Source 1: Anis Resume]

Java
Python
Excel

[Source 2: Safeek Resume]

Java
JavaScript

You may say:

"Java is listed in both resumes."

You must NOT say:

"Python is listed in both resumes."

You must NOT say:

"Excel is listed in both resumes."

You must NOT assume that Safeek has Python or Excel.

If the user asks about only one document, use evidence from that
document and do not transfer information from other documents.


=========================================================
COMPARISON: DIFFERENCES
=========================================================

When the user asks for differences:

- Keep each document separate.
- Report what is explicitly supported by each source.
- Do not treat information from one source as information from
  another source.
- Do not invent missing information.

Example:

Resume A:

Java, Python

Resume B:

Java, JavaScript

Correct:

Common:

- Java

Resume A only:

- Python

Resume B only:

- JavaScript


=========================================================
COMPARISON: MULTIPLE DOCUMENTS
=========================================================

If more than two documents are being compared:

A fact is considered common ONLY when the research context explicitly
supports that fact in every document being compared.

For example:

Document A:

Java, Python

Document B:

Java, Python, React

Document C:

Java, React

Common:

- Java

Python is NOT common because Document C does not explicitly support it.

React is NOT common because Document A does not explicitly support it.


=========================================================
SOURCE HANDLING
=========================================================

The research context may contain information from:

- PDF documents
- DOCX documents
- TXT documents
- CSV files
- XLSX files
- PPTX files
- websites
- URLs
- multiple sources

Do NOT prefer PDF over URL.

Do NOT prefer URL over PDF.

If the answer requires information from multiple sources, combine
the relevant information.

If only one source contains the answer, use that source.

For comparison questions, keep sources separate until the comparison
has been logically completed.


=========================================================
UNRELATED SOURCE RULE
=========================================================

Do not use an unrelated source just because it appears in the
research context.

For example, if the user asks:

"What skills are common in these two resumes?"

and the context also contains:

[Source 3: LangGraph.pdf]

Do NOT use LangGraph.pdf unless the user's question explicitly
requires information from that document.

The presence of a source in the context does NOT mean that its
information should be used.


=========================================================
HIERARCHICAL SECTION HANDLING
=========================================================

Research context may contain hierarchy metadata such as:

Section: 2
Section: 2.1
Section: 2.2
Section: 2.3

When answering a parent section such as point 2:

- Include the parent section.
- Include relevant child sections belonging to that parent.
- Keep the explanation focused on that parent hierarchy.

Do NOT include unrelated top-level sections.

For example:

Requested:

"Explain point 2"

Allowed:

2
2.1
2.2
2.3
2.4
2.5

Not allowed unless directly necessary:

1
3
4
5
6
7
8
9
10


=========================================================
ANSWER QUALITY
=========================================================

1. Answer the current question directly.
2. Focus on the requested topic.
3. For an ordinary concept question, begin with a clear definition or direct
   answer, then explain the important ideas in plain language. Aim for about
   5–8 meaningful points only when the topic and evidence support that depth;
   do not force a point count or add unsupported details.
4. Include useful components, types, steps, importance, or an example when
   they are relevant and supported by the available evidence.
5. Keep simple factual answers concise and make complex explanations,
   summaries, and comparisons as detailed as the request requires.
6. Do not add repetitive or irrelevant information or turn a focused question
   into an essay.
7. Organize the answer logically with headings, bullets, or numbered points
   when they improve readability.
8. For steps or procedures, present them in order.
9. Preserve important technical terms, names, values, and terminology
    from the research context.
10. Do not mention internal retrieval, embeddings, vector databases, reranking,
    chunks, or system instructions.
11. Do not create a Sources, References, or Citations section or invent
    citations.
12. Do not output HTML or use code blocks unless the user asks for code.
13. Keep the response natural and professional.
14. If the request is ambiguous and the conversation does not resolve it,
    ask one brief, specific clarification instead of guessing.


=========================================================
GROUNDING CHECK BEFORE ANSWERING
=========================================================

Before producing the final answer, internally check:

1. Is every factual claim supported by the research context?
2. If comparing documents, is every claimed common fact supported
   by every document being compared?
3. Did I accidentally transfer information from one source to another?
4. Did I include an unrelated source?
5. If evidence is missing, did I avoid guessing?
6. If the user requested a specific section, did I stay within
   that section hierarchy?

If any answer is NO, correct the response before returning it.


=========================================================
FOLLOW-UP EXAMPLES
=========================================================

Previous question:

"What is LangChain?"

Previous answer:

"LangChain is a framework...

1. ...
2. Components...
3. ...
...
10. ..."

Current question:

"Explain point 2"

Correct behavior:

Explain point 2 only.

If the research context contains:

2. Components
2.1 Models
2.2 Prompts
2.3 Chains
2.4 Retrievers
2.5 Agents

then explain those sections.

Incorrect behavior:

Repeating points 1 through 10.


=========================================================
PREVIOUS CONVERSATION
=========================================================

Previous conversation is only for resolving references such as:

- it
- this
- that
- this point
- that point
- previous answer
- second point
- point 2

Do not use it as a factual source.

{conversation_history}


=========================================================
CURRENT USER QUESTION
=========================================================

{question}


=========================================================
REQUESTED SECTION
=========================================================

{requested_section}


=========================================================
RESEARCH CONTEXT
=========================================================

{context}


=========================================================
FINAL INSTRUCTION
=========================================================

Answer the CURRENT user question.

If a specific point or section is requested, answer ONLY that
point/section and its relevant child sections.

Do not repeat unrelated points from the previous answer.

Use only information supported by the research context when it is present.
When it is absent, follow the grounding instruction above.

For comparison questions, perform the comparison source-by-source.

Never claim that a fact is common/shared unless the research context
explicitly supports that fact in every document being compared.

Never transfer information from one source to another.

If the available evidence is insufficient, say so instead of guessing.
"""


prompt = ChatPromptTemplate.from_template(
    PROMPT
)


MAX_REQUEST_TOKEN_ESTIMATE = 12000
TOKEN_ESTIMATE_OVERHEAD = 128
MAX_HISTORY_CHARACTERS = 2500


def _request_token_estimate(
    question: str,
    context: str,
    history_text: str,
    requested_section: str | None,
    grounding_instruction: str | None = None,
) -> int:
    rendered_prompt = PROMPT.format(
        question=question,
        context=context,
        conversation_history=history_text,
        requested_section=(
            requested_section
            or "No specific numbered section requested."
        ),
        grounding_instruction=(
            grounding_instruction
            or "Use only the provided research context for factual claims."
        ),
    )

    byte_estimate = math.ceil(
        len(rendered_prompt.encode("utf-8")) / 3
    )

    lexical_estimate = sum(
        math.ceil(len(piece) / 4)
        if piece.isalnum() or "_" in piece
        else 1
        for piece in re.findall(
            r"\w+|[^\w\s]",
            rendered_prompt,
            flags=re.UNICODE,
        )
    )

    return (
        math.ceil(
            max(
                byte_estimate,
                lexical_estimate,
            )
            * 1.25
        )
        + TOKEN_ESTIMATE_OVERHEAD
    )


def _extract_source_blocks(
    context: str,
) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"\[Source\s+(\d+):\s*([^\]]+)\]",
        re.IGNORECASE,
    )

    matches = list(
        pattern.finditer(context)
    )

    if not matches:
        return [
            (
                "1",
                context.strip(),
            )
        ]

    sources: list[tuple[str, str]] = []

    for index, match in enumerate(matches):
        source_number = match.group(1)
        source_name = match.group(2).strip()

        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(context)

        body = context[start:end].strip()

        if body:
            sources.append(
                (
                    source_number,
                    f"[Source {source_number}: {source_name}]\n{body}",
                )
            )

    return sources


def _is_comparison_question(
    question: str,
) -> bool:
    q = question.lower()

    comparison_terms = (
        "common",
        "shared",
        "both",
        "compare",
        "comparison",
        "difference",
        "differences",
        "similar",
        "similarities",
        "same",
        "versus",
        "vs",
        "between",
    )

    return any(
        term in q
        for term in comparison_terms
    )


def _score_source_block(
    question: str,
    source_block: str,
) -> int:
    question_words = set(
        re.findall(
            r"[a-zA-Z0-9]+",
            question.lower(),
        )
    )

    if not question_words:
        return 0

    block_words = set(
        re.findall(
            r"[a-zA-Z0-9]+",
            source_block.lower(),
        )
    )

    score = len(
        question_words.intersection(
            block_words
        )
    )

    q = question.lower()

    if "skill" in q and "skill" in source_block.lower():
        score += 10

    if (
        "technology" in q
        and any(
            word in source_block.lower()
            for word in (
                "technology",
                "technologies",
                "tech stack",
            )
        )
    ):
        score += 10

    if (
        "qualification" in q
        and "qualification" in source_block.lower()
    ):
        score += 10

    if (
        "experience" in q
        and "experience" in source_block.lower()
    ):
        score += 10

    if (
        "education" in q
        and "education" in source_block.lower()
    ):
        score += 10

    return score


def _select_relevant_source_blocks(
    question: str,
    context: str,
) -> list[str]:
    sources = _extract_source_blocks(
        context
    )

    if not sources:
        return []

    comparison = _is_comparison_question(
        question
    )

    if comparison and len(sources) > 1:
        selected_sources: list[str] = []

        ranked_sources = sorted(
            sources,
            key=lambda item: _score_source_block(
                question,
                item[1],
            ),
            reverse=True,
        )

        for source_number, source_block in ranked_sources:
            selected_sources.append(
                source_block
            )

        return selected_sources

    grouped_sources: dict[str, list[str]] = {}
    for source_number, block in sources:
        grouped_sources.setdefault(source_number, []).append(block)

    ranked_groups = []
    for source_number, blocks in grouped_sources.items():
        ranked_groups.append(
            (
                sorted(
                    blocks,
                    key=lambda block: _score_source_block(
                        question,
                        block,
                    ),
                    reverse=True,
                ),
                source_number,
            )
        )
    ranked_groups.sort(
        key=lambda item: _score_source_block(
            question,
            item[0][0],
        ),
        reverse=True,
    )

    ranked_blocks = [
        blocks[0]
        for blocks, _ in ranked_groups
        if blocks
    ]
    maximum_chunks = max(
        (len(blocks) for blocks, _ in ranked_groups),
        default=1,
    )
    for chunk_index in range(1, maximum_chunks):
        ranked_blocks.extend(
            blocks[chunk_index]
            for blocks, _ in ranked_groups
            if chunk_index < len(blocks)
        )

    return ranked_blocks
def _trim_block_to_fit(
    question: str,
    block: str,
    selected_context: str,
    history_text: str,
    requested_section: str | None,
) -> str:
    """
    Trim a source block so that the complete request stays within
    the configured token budget.

    The source header is preserved whenever possible.
    """

    if not block.strip():
        return ""

    candidate_context = (
        f"{selected_context}\n\n{block}".strip()
        if selected_context.strip()
        else block.strip()
    )

    if (
        _request_token_estimate(
            question=question,
            context=candidate_context,
            history_text=history_text,
            requested_section=requested_section,
        )
        <= MAX_REQUEST_TOKEN_ESTIMATE
    ):
        return block.strip()

    header_match = re.match(
        r"(\[Source\s+\d+:\s*[^\]]+\])",
        block.strip(),
        flags=re.IGNORECASE,
    )

    if header_match:
        header = header_match.group(1)
        body = block[
            header_match.end():
        ].strip()
    else:
        header = ""
        body = block.strip()

    if not body:
        return header

    # Try to keep the most relevant portion of the source block.
    question_lower = question.lower()

    priority_terms: list[str] = []

    if "skill" in question_lower:
        priority_terms.extend(
            [
                "skills",
                "skill",
                "technical skills",
                "technologies",
                "technology",
                "tools",
                "programming",
                "frameworks",
                "languages",
                "expertise",
            ]
        )

    if "experience" in question_lower:
        priority_terms.extend(
            [
                "experience",
                "work experience",
                "professional experience",
                "internship",
            ]
        )

    if "education" in question_lower:
        priority_terms.extend(
            [
                "education",
                "degree",
                "qualification",
                "academic",
            ]
        )

    if "project" in question_lower:
        priority_terms.extend(
            [
                "project",
                "projects",
            ]
        )

    body_lower = body.lower()

    positions: list[int] = []

    for term in priority_terms:
        position = body_lower.find(
            term.lower()
        )

        if position >= 0:
            positions.append(position)

    # Start with a conservative character limit.
    low = 300
    high = len(body)

    # If we found a relevant keyword, center the excerpt around it.
    if positions:
        target_position = min(positions)
        start = max(
            0,
            target_position - 600,
        )
    else:
        start = 0

    best_body = ""

    while low <= high:
        middle = (low + high) // 2

        end = min(
            len(body),
            start + middle,
        )

        excerpt = body[
            start:end
        ].strip()

        candidate_body = (
            f"{header}\n{excerpt}"
            if header
            else excerpt
        )

        candidate_context = (
            f"{selected_context}\n\n"
            f"{candidate_body}".strip()
            if selected_context.strip()
            else candidate_body
        )

        estimated_tokens = _request_token_estimate(
            question=question,
            context=candidate_context,
            history_text=history_text,
            requested_section=requested_section,
        )

        if (
            estimated_tokens
            <= MAX_REQUEST_TOKEN_ESTIMATE
        ):
            best_body = excerpt
            low = middle + 1
        else:
            high = middle - 1

    if not best_body:
        # Very small fallback.
        excerpt = body[:300].strip()

        candidate_body = (
            f"{header}\n{excerpt}"
            if header
            else excerpt
        )

        candidate_context = (
            f"{selected_context}\n\n"
            f"{candidate_body}".strip()
            if selected_context.strip()
            else candidate_body
        )

        if (
            _request_token_estimate(
                question=question,
                context=candidate_context,
                history_text=history_text,
                requested_section=requested_section,
            )
            <= MAX_REQUEST_TOKEN_ESTIMATE
        ):
            best_body = excerpt

    if not best_body:
        return ""

    return (
        f"{header}\n{best_body}".strip()
        if header
        else best_body
    )


def fit_generation_context(
    question: str,
    context: str,
    conversation_history: list[dict] | None = None,
) -> tuple[str, str, str]:
    """
    Prepare question, context and conversation history so the final
    LLM request stays safely below the model request limit.

    Comparison questions receive special treatment:

    - Each source is considered independently.
    - At least one useful block from each source is prioritized.
    - Relevant skill/experience/education blocks are preferred.
    - Additional blocks are added only when token budget allows.
    """

    conversation_history = (
        conversation_history or []
    )

    requested_section = (
        extract_requested_section(
            question
        )
    )

    formatted_history = build_history_text(
        conversation_history=conversation_history,
        requested_section=requested_section,
    )

    # Keep conversation history under a predictable size.
    if len(formatted_history) > MAX_HISTORY_CHARACTERS:
        formatted_history = formatted_history[
            -MAX_HISTORY_CHARACTERS:
        ]

    prepared_question = question.strip()
    prepared_context = context.strip()

    if not prepared_context:
        return (
            prepared_question,
            "",
            formatted_history,
        )

    # First check whether the complete request already fits.
    if (
        _request_token_estimate(
            question=prepared_question,
            context=prepared_context,
            history_text=formatted_history,
            requested_section=requested_section,
        )
        <= MAX_REQUEST_TOKEN_ESTIMATE
    ):
        return (
            prepared_question,
            prepared_context,
            formatted_history,
        )

    # If the request is too large, progressively shorten history.
    if formatted_history:
        shortened_history = formatted_history

        while (
            len(shortened_history)
            > 500
        ):
            shortened_history = shortened_history[
                len(shortened_history) // 10:
            ]

            if (
                _request_token_estimate(
                    question=prepared_question,
                    context=prepared_context,
                    history_text=shortened_history,
                    requested_section=requested_section,
                )
                <= MAX_REQUEST_TOKEN_ESTIMATE
            ):
                formatted_history = shortened_history
                break

        else:
            formatted_history = (
                "No previous conversation."
            )

    # If the question itself is unusually large, keep its beginning
    # and end so the user's actual request is not completely lost.
    if (
        _request_token_estimate(
            question=prepared_question,
            context="",
            history_text=formatted_history,
            requested_section=requested_section,
        )
        > MAX_REQUEST_TOKEN_ESTIMATE
    ):
        if len(prepared_question) > 4000:
            prepared_question = (
                prepared_question[:2000]
                + "\n...\n"
                + prepared_question[-2000:]
            )

    source_blocks = _extract_source_blocks(
        prepared_context
    )

    if not source_blocks:
        return (
            prepared_question,
            prepared_context,
            formatted_history,
        )

    comparison = _is_comparison_question(
        prepared_question
    )

    selected_blocks: list[str] = []
    selected_source_numbers: set[str] = set()

    # ---------------------------------------------------------
    # COMPARISON MODE
    # ---------------------------------------------------------
    #
    # This is the important fix for questions such as:
    #
    # "What skills are common in Anis Fathima and Safeek Mohamed?"
    #
    # We first guarantee useful evidence from every source.
    # ---------------------------------------------------------

    if comparison:
        grouped_sources: dict[
            str,
            list[tuple[int, str]]
        ] = {}

        for index, (
            source_number,
            source_block,
        ) in enumerate(
            source_blocks
        ):
            grouped_sources.setdefault(
                source_number,
                [],
            ).append(
                (
                    index,
                    source_block,
                )
            )

        # Preserve source order.
        source_order = list(
            grouped_sources.keys()
        )

        # First pass:
        # choose the most relevant block from every source.
        for source_number in source_order:
            blocks = grouped_sources[
                source_number
            ]

            best_block = max(
                blocks,
                key=lambda item: (
                    _score_source_block(
                        prepared_question,
                        item[1],
                    ),
                    -item[0],
                ),
            )

            selected = _trim_block_to_fit(
                question=prepared_question,
                block=best_block[1],
                selected_context="\n\n".join(
                    selected_blocks
                ),
                history_text=formatted_history,
                requested_section=requested_section,
            )

            if selected:
                selected_blocks.append(
                    selected
                )
                selected_source_numbers.add(
                    source_number
                )

        # Second pass:
        # add additional relevant blocks in a fair round-robin
        # manner so one resume cannot consume the entire context.
        remaining_by_source: dict[
            str,
            list[tuple[int, str]]
        ] = {}

        for source_number in source_order:
            ranked = sorted(
                grouped_sources[
                    source_number
                ],
                key=lambda item: (
                    _score_source_block(
                        prepared_question,
                        item[1],
                    ),
                    -item[0],
                ),
                reverse=True,
            )

            # Skip the block already selected.
            remaining_by_source[
                source_number
            ] = ranked[1:]

        added = True

        while added:
            added = False

            for source_number in source_order:
                remaining = remaining_by_source.get(
                    source_number,
                    [],
                )

                if not remaining:
                    continue

                _, candidate_block = (
                    remaining.pop(0)
                )

                selected_context = (
                    "\n\n".join(
                        selected_blocks
                    )
                )

                selected = _trim_block_to_fit(
                    question=prepared_question,
                    block=candidate_block,
                    selected_context=selected_context,
                    history_text=formatted_history,
                    requested_section=requested_section,
                )

                if selected:
                    selected_blocks.append(
                        selected
                    )
                    added = True

    # ---------------------------------------------------------
    # NORMAL QUESTION MODE
    # ---------------------------------------------------------
    else:
        ranked_blocks = _select_relevant_source_blocks(
            prepared_question,
            prepared_context,
        )

        for source_block in ranked_blocks:

            selected_context = (
                "\n\n".join(
                    selected_blocks
                )
            )

            selected = _trim_block_to_fit(
                question=prepared_question,
                block=source_block,
                selected_context=selected_context,
                history_text=formatted_history,
                requested_section=requested_section,
            )

            if selected:
                selected_blocks.append(
                    selected
                )

    final_context = "\n\n".join(
        selected_blocks
    ).strip()

    # Absolute fallback:
    # if context selection somehow failed, use a small excerpt from
    # the original context instead of sending an empty context.
    if not final_context:
        fallback = _trim_block_to_fit(
            question=prepared_question,
            block=prepared_context,
            selected_context="",
            history_text=formatted_history,
            requested_section=requested_section,
        )

        final_context = fallback.strip()

    # Final safety check.
    #
    # If the request is still too large, remove the least important
    # context blocks from the end until it fits.
    while (
        len(selected_blocks) > 1
        and _request_token_estimate(
            question=prepared_question,
            context="\n\n".join(
                selected_blocks
            ),
            history_text=formatted_history,
            requested_section=requested_section,
        )
        > MAX_REQUEST_TOKEN_ESTIMATE
    ):
        selected_blocks.pop()

    final_context = "\n\n".join(
        selected_blocks
    ).strip()

    return (
        prepared_question,
        final_context,
        formatted_history,
    )


@synchronized_lru_cache(maxsize=1)
def get_answer_chain():
    llm = get_llm()

    return (
        prompt
        | llm
        | StrOutputParser()
    )


def extract_requested_section(
    question: str,
) -> str | None:
    """
    Detect numbered section/point references in follow-up questions.

    Examples:

    "Explain point 2" -> "2"
    "Explain section 2.3" -> "2.3"
    "Explain the 3rd point" -> "3"
    "Explain point number 4" -> "4"
    """

    if not question:
        return None

    patterns = [
        re.compile(
            r"\b(?:point|section|topic|item|part)"
            r"\s+(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),

        re.compile(
            r"\b(?:explain|describe|elaborate|"
            r"expand|discuss)"
            r"\s+(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),

        re.compile(
            r"\b(\d+)(?:st|nd|rd|th)"
            r"\s+(?:point|section|topic|item|part)\b",
            re.IGNORECASE,
        ),

        re.compile(
            r"\b(?:point|section|topic|item)"
            r"\s+(?:no\.?|number)\s+"
            r"(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),

        re.compile(
            r"\b(?:point|section|topic|item)"
            r"\s+number\s+"
            r"(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(
            question
        )

        if match:
            return match.group(1)

    return None
def clean_answer(
    answer: str,
) -> str:
    """
    Clean the final LLM response before returning it to the API.

    Removes accidental markdown wrappers, internal retrieval
    language, duplicated headings and empty responses while
    preserving useful answer formatting.
    """

    if not answer:
        return (
            "The available sources do not provide "
            "enough information to answer this question."
        )

    text = str(answer).strip()

    # Remove accidental code fences around the entire answer.
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()

        if len(lines) >= 2:
            text = "\n".join(
                lines[1:-1]
            ).strip()

    # Remove common model-generated prefixes.
    prefixes = [
        "Answer:",
        "Final Answer:",
        "Response:",
        "Assistant:",
    ]

    changed = True

    while changed:
        changed = False

        for prefix in prefixes:
            if text.lower().startswith(
                prefix.lower()
            ):
                text = text[
                    len(prefix):
                ].strip()

                changed = True
                break

    # Remove internal RAG/retrieval language that should never
    # appear in the user-facing answer.
    forbidden_phrases = [
        "according to the retrieved chunks",
        "according to the retrieved context",
        "based on the retrieved chunks",
        "based on the retrieved context",
        "from the vector database",
        "from the vector db",
        "the retriever found",
        "the retrieval system found",
        "the embedding search found",
        "the reranker selected",
        "the chunks indicate",
        "the retrieved documents indicate",
        "the context contains",
    ]

    for phrase in forbidden_phrases:
        text = re.sub(
            re.escape(phrase),
            "",
            text,
            flags=re.IGNORECASE,
        )

    # Remove duplicate blank lines.
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    # Remove accidental leading/trailing whitespace.
    text = text.strip()

    if not text:
        return (
            "The available sources do not provide "
            "enough information to answer this question."
        )

    return text


def build_history_text(
    conversation_history: list[dict] | None = None,
    requested_section: str | None = None,
) -> str:
    """
    Convert previous conversation messages into a compact,
    model-friendly history block.

    Conversation history is used only for resolving follow-up
    references. It is NOT treated as a source of factual
    information for the current answer.
    """

    if not conversation_history:
        return (
            "No previous conversation is available."
        )

    lines: list[str] = []

    # Keep only the most recent messages.
    recent_messages = conversation_history[
        -20:
    ]

    for message in recent_messages:
        if not isinstance(
            message,
            dict,
        ):
            continue

        role = str(
            message.get(
                "role",
                "",
            )
        ).strip().lower()

        content = str(
            message.get(
                "content",
                "",
            )
        ).strip()

        if not content:
            continue

        if role == "user":
            label = "User"

        elif role == "assistant":
            label = "Assistant"

        else:
            label = role.title() or "Message"

        lines.append(
            f"{label}: {content}"
        )

    if not lines:
        return (
            "No previous conversation is available."
        )

    history = "\n".join(
        lines
    )

    if requested_section:
        history = (
            f"{history}\n\n"
            f"Follow-up section requested: "
            f"{requested_section}"
        )

    # Hard character safety limit.
    if len(history) > MAX_HISTORY_CHARACTERS:
        history = history[
            -MAX_HISTORY_CHARACTERS:
        ]

        history = (
            "Earlier conversation was shortened "
            "for context safety.\n"
            + history
        )

    return history


def _normalise_source_name(
    source_name: str,
) -> str:
    """
    Normalize a source name for comparison.

    Page information is removed because pages are not separate
    documents. The actual filename remains the source identity.
    """

    if not source_name:
        return ""

    value = source_name.strip()

    # Remove page information from source labels.
    value = re.sub(
        r"\s*\|\s*Page\s+\d+\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s*\|\s*Pages?\s+[\d,\-\s]+$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return value.strip()


def _source_identity(
    source_name: str,
) -> str:
    """
    Produce a stable source identity.

    This is intentionally conservative so two different files
    are not accidentally merged.
    """

    value = _normalise_source_name(
        source_name
    )

    value = value.lower().strip()

    # Remove surrounding quotes.
    value = value.strip(
        "\"'"
    )

    # Normalize repeated whitespace.
    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def _group_source_blocks(
    source_blocks: list[
        tuple[str, str]
    ],
) -> dict[
    str,
    list[str],
]:
    """
    Group retrieved blocks by actual source name.

    Example:

        Resume A - page 1
        Resume A - page 2
        Resume B - page 1

    becomes:

        Resume A -> [block1, block2]
        Resume B -> [block3]

    This is important for multi-document comparison because
    [Source 1], [Source 2], etc. are retrieval-result numbers,
    not necessarily document identities.
    """

    grouped: dict[
        str,
        list[str],
    ] = {}

    for source_number, block in source_blocks:
        match = re.match(
            r"\[Source\s+\d+:\s*([^\]]+)\]",
            block.strip(),
            flags=re.IGNORECASE,
        )

        if match:
            source_name = (
                match.group(1).strip()
            )
        else:
            source_name = source_number

        identity = _source_identity(
            source_name
        )

        if not identity:
            identity = source_number

        grouped.setdefault(
            identity,
            [],
        ).append(
            block
        )

    return grouped


def _rank_source_groups(
    question: str,
    grouped_sources: dict[
        str,
        list[str],
    ],
) -> list[
    tuple[
        str,
        list[str],
    ]
]:
    """
    Rank complete documents by the strongest evidence found
    in their retrieved blocks.
    """

    ranked = []

    for source_name, blocks in grouped_sources.items():
        if not blocks:
            continue

        scores = [
            _score_source_block(
                question,
                block,
            )
            for block in blocks
        ]

        strongest_score = max(
            scores
        )

        total_score = sum(
            scores
        )

        ranked.append(
            (
                source_name,
                blocks,
                strongest_score,
                total_score,
            )
        )

    ranked.sort(
        key=lambda item: (
            item[2],
            item[3],
        ),
        reverse=True,
    )

    return [
        (
            source_name,
            blocks,
        )
        for (
            source_name,
            blocks,
            _,
            _,
        ) in ranked
    ]


def _select_comparison_blocks(
    question: str,
    context: str,
    history_text: str,
    requested_section: str | None,
) -> list[str]:
    """
    Select context specifically for comparison questions.

    Important rule:

    If the question asks for a fact common to multiple named
    documents, evidence from every compared document must remain
    available to the LLM.

    We therefore select the strongest relevant evidence from
    each distinct document before filling remaining budget.
    """

    source_blocks = _extract_source_blocks(
        context
    )

    if not source_blocks:
        return []

    grouped_sources = _group_source_blocks(
        source_blocks
    )

    ranked_sources = _rank_source_groups(
        question,
        grouped_sources,
    )

    selected: list[str] = []

    # ---------------------------------------------------------
    # PASS 1
    # One strongest relevant block from EVERY document.
    # ---------------------------------------------------------

    for source_name, blocks in ranked_sources:
        ranked_blocks = sorted(
            blocks,
            key=lambda block: _score_source_block(
                question,
                block,
            ),
            reverse=True,
        )

        if not ranked_blocks:
            continue

        candidate = ranked_blocks[0]

        trimmed = _trim_block_to_fit(
            question=question,
            block=candidate,
            selected_context="\n\n".join(
                selected
            ),
            history_text=history_text,
            requested_section=requested_section,
        )

        if trimmed:
            selected.append(
                trimmed
            )

    # ---------------------------------------------------------
    # PASS 2
    # Add additional evidence from each document.
    # ---------------------------------------------------------

    used_blocks = set(
        selected
    )

    remaining = []

    for source_name, blocks in ranked_sources:
        for block in blocks:
            if block in used_blocks:
                continue

            remaining.append(
                (
                    _score_source_block(
                        question,
                        block,
                    ),
                    source_name,
                    block,
                )
            )

    remaining.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    for _, source_name, candidate in remaining:
        trimmed = _trim_block_to_fit(
            question=question,
            block=candidate,
            selected_context="\n\n".join(
                selected
            ),
            history_text=history_text,
            requested_section=requested_section,
        )

        if not trimmed:
            continue

        selected.append(
            trimmed
        )

    return selected


def _select_normal_blocks(
    question: str,
    context: str,
    history_text: str,
    requested_section: str | None,
) -> list[str]:
    """
    Select the highest-value source blocks for ordinary
    single-document or general questions.
    """

    source_blocks = _extract_source_blocks(
        context
    )

    if not source_blocks:
        return []

    ranked_blocks = _select_relevant_source_blocks(
        question,
        context,
    )

    selected: list[str] = []

    for block in ranked_blocks:
        trimmed = _trim_block_to_fit(
            question=question,
            block=block,
            selected_context="\n\n".join(
                selected
            ),
            history_text=history_text,
            requested_section=requested_section,
        )

        if not trimmed:
            continue

        selected.append(
            trimmed
        )

    return selected
def generate_answer(
    question: str,
    context: str,
    conversation_history: list[dict] | None = None,
    prepared_history: str | None = None,
    allow_general_knowledge: bool = False,
) -> str:
    """
    Generate the final answer using only the retrieved research
    context.

    The context is fitted before the LLM call so that:
    - comparison questions keep evidence from every document
    - relevant source blocks are prioritized
    - request size stays within the configured token budget
    - conversation history remains bounded
    """

    if not question.strip():
        return ""

    if not context.strip() and not allow_general_knowledge:
        return (
            "The available sources do not provide "
            "enough information to answer this question."
        )

    conversation_history = (
        conversation_history or []
    )
    grounding_instruction = (
        "No relevant uploaded source was found. Answer using general knowledge, "
        "do not imply that the answer came from the user's documents, and state "
        "clearly that it is not grounded in their sources."
        if allow_general_knowledge and not context.strip()
        else "Use only the supplied research context for factual claims. "
        "If it does not contain the answer, say so instead of guessing."
    )

    requested_section = (
        extract_requested_section(
            question
        )
    )

    # If the caller already prepared history, preserve it.
    # Otherwise fit the complete request here.
    if prepared_history is not None:
        formatted_history = (
            prepared_history
        )

        prepared_question = (
            question.strip()
        )

        prepared_context = (
            context.strip()
        )

    else:
        (
            prepared_question,
            prepared_context,
            formatted_history,
        ) = fit_generation_context(
            question=question,
            context=context,
            conversation_history=conversation_history,
        )

        requested_section = (
            extract_requested_section(
                prepared_question
            )
        )

    # ---------------------------------------------------------
    # Extra comparison-aware context selection
    # ---------------------------------------------------------
    #
    # This second selection is useful when the caller passes a
    # large context that has already been partially prepared.
    #
    # For comparison questions, every distinct source gets
    # representation before additional evidence is added.
    # ---------------------------------------------------------

    if prepared_history is None and _is_comparison_question(
        prepared_question
    ):
        comparison_blocks = (
            _select_comparison_blocks(
                question=prepared_question,
                context=prepared_context,
                history_text=formatted_history,
                requested_section=requested_section,
            )
        )

        if comparison_blocks:
            prepared_context = (
                "\n\n".join(
                    comparison_blocks
                ).strip()
            )

    elif prepared_history is None:
        normal_blocks = (
            _select_normal_blocks(
                question=prepared_question,
                context=prepared_context,
                history_text=formatted_history,
                requested_section=requested_section,
            )
        )

        if normal_blocks:
            prepared_context = (
                "\n\n".join(
                    normal_blocks
                ).strip()
            )

    # ---------------------------------------------------------
    # Final token-budget safety check
    # ---------------------------------------------------------

    if (
        _request_token_estimate(
            question=prepared_question,
            context=prepared_context,
            history_text=formatted_history,
            requested_section=requested_section,
        )
        > MAX_REQUEST_TOKEN_ESTIMATE
    ):
        (
            prepared_question,
            prepared_context,
            formatted_history,
        ) = fit_generation_context(
            question=prepared_question,
            context=prepared_context,
            conversation_history=conversation_history,
        )

        requested_section = (
            extract_requested_section(
                prepared_question
            )
        )

    chain = get_answer_chain()

    try:
        answer = chain.invoke(
            {
                "question": prepared_question,
                "context": prepared_context,
                "conversation_history": (
                    formatted_history
                ),
                "requested_section": (
                    requested_section
                    if requested_section
                    else (
                        "No specific numbered "
                        "section requested."
                    )
                ),
                "grounding_instruction": grounding_instruction,
            }
        )

    except Exception as error:
        # Do not silently convert an LLM failure into a false
        # factual answer.
        message = llm_error_message(error)
        if message:
            raise RuntimeError(message) from error
        raise

    return clean_answer(
        answer
    )
