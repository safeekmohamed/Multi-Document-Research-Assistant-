import re

from langchain_core.output_parsers import (
    StrOutputParser,
)
from langchain_core.prompts import (
    ChatPromptTemplate,
)

from app.llm.llm_model import get_llm


prompt = ChatPromptTemplate.from_template(
    """
You are an AI research assistant.

Answer the user's question using ONLY the
provided research context.

If the context does not contain enough information,
clearly say that the available sources do not
provide enough information.

Do not invent facts.

IMPORTANT ANSWER FORMATTING RULES:

1. Return only the final answer for the user.

2. Do NOT output HTML tags such as:
   <p>, </p>, <br>, <div>, <ul>, <li>, etc.

3. Do NOT output internal source labels such as:
   [Source 1], [Source 2], [Source 3], etc.

4. Do NOT create a:
   Sources
   References
   Citations
   section.

5. Do NOT use Markdown formatting.

6. Do NOT use:
   **bold**
   *italic*
   ## headings
   Markdown tables
   backticks

7. Use plain text only.

8. You may use simple headings followed by a colon.

9. You may use simple numbered points:
   1. First point
   2. Second point
   3. Third point

10. For comparison questions, clearly separate
    the information about each source.

11. For comparison questions, include a short
    "Key Differences:" section.

12. Keep the answer clear, natural, and easy to read.

13. Do not mention internal source numbers.

14. Do not mention that you are using a research
    context or retrieval system.

15. The application displays the source information
    separately below the answer. Therefore, do not
    write source names, source numbers, URLs,
    citations, or a Sources section inside the answer
    unless the user specifically asks for them.

User question:
{question}

Research context:
{context}

Provide the final answer in clean plain text.
"""
)


def clean_answer(answer: str) -> str:
    """
    Clean unwanted formatting from the LLM response.
    """

    answer = re.sub(
        r"<[^>]+>",
        "",
        answer,
    )

  
    answer = re.sub(
        r"\[\s*Source\s+\d+(?::[^\]]*)?\s*\]",
        "",
        answer,
        flags=re.IGNORECASE,
    )

    answer = re.sub(
        r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]",
        "",
        answer,
    )


    answer = re.sub(
        r"(?im)^\s*(sources|references|citations)\s*:?\s*$",
        "",
        answer,
    )

    answer = answer.replace(
        "**",
        "",
    )

    answer = answer.replace(
        "*",
        "",
    )

   
    answer = re.sub(
        r"(?m)^\s*#{1,6}\s*",
        "",
        answer,
    )

 

    answer = answer.replace(
        "```",
        "",
    )

  
    answer = re.sub(
        r"\n{3,}",
        "\n\n",
        answer,
    )

    answer = "\n".join(
        line.strip()
        for line in answer.splitlines()
    )

    return answer.strip()


def generate_answer(
    question: str,
    context: str,
) -> str:

    llm = get_llm()

    chain = (
        prompt
        | llm
        | StrOutputParser()
    )

    answer = chain.invoke(
        {
            "question": question,
            "context": context,
        }
    )

    return clean_answer(
        answer
    )