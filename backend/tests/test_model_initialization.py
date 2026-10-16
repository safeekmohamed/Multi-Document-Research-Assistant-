import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from fastapi import HTTPException

from app.embeddings import embedding_model
from app.rag import retriever
from app.rag import model_runtime
from app.routes import chat as chat_route
from app.schemas.chat import ChatRequest
from app.core.model_cache import synchronized_lru_cache


class ModelInitializationTests(unittest.TestCase):
    def tearDown(self):
        embedding_model.get_embedding_model.cache_clear()
        retriever.get_reranker.cache_clear()
        model_runtime._warmup_error = None

    def test_embedding_model_is_initialized_once_and_reused(self):
        model = Mock()
        with (
            patch.dict("os.environ", {"EMBEDDING_MODEL": "test-embedding"}),
            patch.object(embedding_model, "SentenceTransformer", return_value=model) as factory,
        ):
            first = embedding_model.get_embedding_model()
            second = embedding_model.get_embedding_model()

        self.assertIs(first, second)
        factory.assert_called_once_with("test-embedding")

    def test_reranker_is_initialized_once_and_reused(self):
        model = Mock()
        with (
            patch.dict("os.environ", {"RERANKER_MODEL": "test-reranker"}),
            patch.object(retriever, "CrossEncoder", return_value=model) as factory,
        ):
            first = retriever.get_reranker()
            second = retriever.get_reranker()

        self.assertIs(first, second)
        factory.assert_called_once_with("test-reranker")

    def test_concurrent_cache_misses_construct_the_model_once(self):
        calls = []
        start = threading.Barrier(6)

        @synchronized_lru_cache(maxsize=1)
        def load_model():
            calls.append(1)
            time.sleep(0.03)
            return object()

        def get_model(_):
            start.wait()
            return load_model()

        with ThreadPoolExecutor(max_workers=6) as pool:
            models = list(pool.map(get_model, range(6)))

        self.assertEqual(len(calls), 1)
        self.assertTrue(all(model is models[0] for model in models))

    def test_startup_warms_both_retrieval_models(self):
        with (
            patch.object(model_runtime, "get_embedding_model") as embedding_loader,
            patch.object(model_runtime, "get_reranker") as reranker_loader,
        ):
            model_runtime.warmup_rag_models()

        embedding_loader.assert_called_once_with()
        reranker_loader.assert_called_once_with()

    def test_warmup_failure_is_retained_to_avoid_repeated_download_attempts(self):
        with (
            patch.object(model_runtime, "get_embedding_model", side_effect=OSError("offline")),
            patch.object(model_runtime, "get_reranker") as reranker_loader,
            self.assertLogs(model_runtime.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(RuntimeError, "embedding model did not initialize"):
                model_runtime.warmup_rag_models()

        self.assertIn("embedding model did not initialize", model_runtime.get_model_warmup_error())
        reranker_loader.assert_not_called()

    def test_chat_fails_fast_if_startup_warmup_failed(self):
        with (
            patch.object(
                chat_route,
                "get_model_warmup_error",
                return_value="The embedding model did not initialize during backend startup.",
            ),
            patch.object(chat_route, "answer_question") as answer_question,
        ):
            with self.assertRaises(HTTPException) as raised:
                chat_route.chat(
                    ChatRequest(question="Summarize my research sources."),
                    current_user={"_id": "test-user"},
                )

        self.assertEqual(raised.exception.status_code, 503)
        answer_question.assert_not_called()


if __name__ == "__main__":
    unittest.main()
