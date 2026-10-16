import os
import unittest
import logging
from unittest.mock import Mock, patch
import requests
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.llm import llm_model
from app import main
from app.rag import chain as rag_chain


def ollama_tags_response(model_names):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"models": [{"name": name} for name in model_names]}
    return response


class LLMProviderTests(unittest.TestCase):
    def test_backend_env_file_is_resolved_from_module_location(self):
        self.assertEqual(llm_model.BACKEND_ENV_PATH.name, ".env")
        self.assertEqual(llm_model.BACKEND_ENV_PATH.parent.name, "backend")

    def test_blank_key_is_treated_as_missing(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "  "}, clear=True):
            self.assertFalse(llm_model.is_gemini_configured())

    def test_default_provider_is_ollama_without_gemini_or_groq_keys(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                llm_model.requests,
                "get",
                return_value=ollama_tags_response(["llama3.2:latest"]),
            ),
            patch.object(llm_model, "ChatOllama", return_value="local-client") as ollama_model,
        ):
            llm_model.get_llm.cache_clear()
            try:
                self.assertEqual(llm_model.get_llm_provider(), "ollama")
                self.assertEqual(llm_model.get_llm(), "local-client")
            finally:
                llm_model.get_llm.cache_clear()

        ollama_model.assert_called_once_with(
            model="llama3.2:latest",
            base_url="http://127.0.0.1:11434",
            temperature=0.2,
            streaming=False,
            keep_alive="30m",
            sync_client_kwargs={"timeout": 180.0},
            async_client_kwargs={"timeout": 180.0},
        )

    def test_ollama_timeout_is_configurable_and_reported_clearly(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "ollama", "OLLAMA_REQUEST_TIMEOUT_SECONDS": "42"},
            clear=True,
        ):
            self.assertEqual(llm_model.get_ollama_request_timeout(), 42.0)
            message = llm_model.llm_error_message(TimeoutError("request timed out"))

        self.assertIn("within 42 seconds", message)

    def test_invalid_ollama_timeout_is_rejected(self):
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "ollama", "OLLAMA_REQUEST_TIMEOUT_SECONDS": "0"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "must be a positive number"):
                llm_model.get_ollama_request_timeout()

    def test_unreachable_ollama_service_has_clear_error(self):
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True),
            patch.object(llm_model.requests, "get", side_effect=requests.ConnectionError("offline")),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ollama is not reachable"):
                llm_model.validate_llm_configuration()

    def test_missing_ollama_model_has_safe_install_instruction(self):
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "missing-model"}, clear=True),
            patch.object(llm_model.requests, "get", return_value=ollama_tags_response(["llama3.2:latest"])),
        ):
            with self.assertRaisesRegex(RuntimeError, "ollama pull missing-model"):
                llm_model.validate_llm_configuration()

    def test_gemini_is_available_only_when_explicitly_selected(self):
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "unit-test-key"}, clear=True),
            patch.object(llm_model, "ChatGoogleGenerativeAI", return_value="gemini-client") as factory,
        ):
            llm_model.get_llm.cache_clear()
            try:
                result = llm_model.get_llm()
            finally:
                llm_model.get_llm.cache_clear()
        self.assertEqual(result, "gemini-client")
        factory.assert_called_once_with(
            model="gemini-3.8-flash",
            api_key="unit-test-key",
            temperature=0.2,
            streaming=False,
        )

    def test_groq_is_available_only_when_explicitly_selected(self):
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test-groq-key", "GROQ_MODEL": "configured-groq-model"}, clear=True),
            patch.object(llm_model, "ChatGroq", return_value="groq-client") as factory,
        ):
            llm_model.get_llm.cache_clear()
            try:
                result = llm_model.get_llm()
            finally:
                llm_model.get_llm.cache_clear()
        self.assertEqual(result, "groq-client")
        factory.assert_called_once_with(
            model="configured-groq-model",
            api_key="test-groq-key",
            temperature=0.2,
        )

    def test_startup_warns_without_logging_a_key_when_unconfigured(self):
        async def exercise_lifespan():
            with (
                patch.object(main, "llm_configuration_warning", return_value="Ollama model is not installed."),
                patch.object(main, "warmup_rag_models"),
                patch.object(main, "initialize_database"),
                self.assertLogs(main.logger, level=logging.WARNING) as captured,
            ):
                async with main.lifespan(main.app):
                    pass
            self.assertTrue(any("Ollama model is not installed" in line for line in captured.output))

        import asyncio

        asyncio.run(exercise_lifespan())

    def test_mocked_ollama_runs_through_existing_rag_answer_chain(self):
        fake_model = FakeListChatModel(responses=["Mocked comparison answer with source-grounded content."])
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True),
            patch.object(rag_chain, "get_llm", return_value=fake_model),
        ):
            rag_chain.get_answer_chain.cache_clear()
            try:
                answer = rag_chain.generate_answer(
                    question="Compare llm.pdf and LangChain.pdf.",
                    context=(
                        "Source: llm.pdf, page 2\nLarge language models learn patterns.\n\n"
                        "Source: LangChain.pdf, page 4\nLangChain connects language model components."
                    ),
                    conversation_history=[],
                )
            finally:
                rag_chain.get_answer_chain.cache_clear()

        self.assertEqual(answer, "Mocked comparison answer with source-grounded content.")

    def test_ollama_research_question_never_initializes_gemini_without_key(self):
        fake_model = FakeListChatModel(responses=["Ollama grounded answer."])
        with (
            patch.dict(
                os.environ,
                {
                    "LLM_PROVIDER": "ollama",
                    "OLLAMA_MODEL": "llama3.2:latest",
                    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                },
                clear=True,
            ),
            patch.object(
                llm_model.requests,
                "get",
                return_value=ollama_tags_response(["llama3.2:latest"]),
            ),
            patch.object(llm_model, "ChatOllama", return_value=fake_model) as ollama_factory,
            patch.object(
                llm_model,
                "ChatGoogleGenerativeAI",
                side_effect=AssertionError("Gemini must not initialize for Ollama"),
            ) as gemini_factory,
        ):
            llm_model.get_llm.cache_clear()
            rag_chain.get_answer_chain.cache_clear()
            try:
                answer = rag_chain.generate_answer(
                    question="Compare the two attached research papers.",
                    context=(
                        "Source: llm.pdf, page 2\\nLLMs learn patterns.\\n\\n"
                        "Source: LangChain.pdf, page 4\\nLangChain connects model components."
                    ),
                    conversation_history=[],
                )
            finally:
                rag_chain.get_answer_chain.cache_clear()
                llm_model.get_llm.cache_clear()

        self.assertEqual(answer, "Ollama grounded answer.")
        ollama_factory.assert_called_once_with(
            model="llama3.2:latest",
            base_url="http://127.0.0.1:11434",
            temperature=0.2,
            streaming=False,
            keep_alive="30m",
            sync_client_kwargs={"timeout": 180.0},
            async_client_kwargs={"timeout": 180.0},
        )
        gemini_factory.assert_not_called()

    def test_missing_gemini_key_errors_only_when_gemini_is_selected(self):
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True),
            patch.object(llm_model, "ChatGoogleGenerativeAI") as gemini_factory,
        ):
            llm_model.get_llm.cache_clear()
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "GEMINI_API_KEY is not configured",
                ):
                    llm_model.get_llm()
            finally:
                llm_model.get_llm.cache_clear()

        gemini_factory.assert_not_called()

    def test_provider_errors_are_classified_without_hiding_detail(self):
        cases = (
            (
                401,
                "API_KEY_INVALID: key rejected",
                "authentication or permission",
            ),
            (
                404,
                "model gemini-3.8-flash was not found",
                "unavailable or unsupported",
            ),
            (
                403,
                "model gemini-3.8-flash is not supported for this project",
                "unavailable or unsupported",
            ),
            (
                429,
                "rate limit exceeded",
                "rate limit was reached",
            ),
            (
                429,
                "quota exceeded for this project",
                "API quota is exhausted",
            ),
            (
                400,
                "input token count exceeds the maximum number of tokens",
                "exceeds the model's context window",
            ),
        )

        for status_code, detail, expected_message in cases:
            with self.subTest(detail=detail):
                error = RuntimeError(detail)
                error.status_code = status_code

                message = llm_model.gemini_error_message(error)

                self.assertIn(expected_message, message)
                self.assertIn(detail, message)

    def test_unrecognized_provider_error_is_not_rewritten(self):
        error = RuntimeError("unexpected provider failure")

        self.assertIsNone(llm_model.gemini_error_message(error))


if __name__ == "__main__":
    unittest.main()
