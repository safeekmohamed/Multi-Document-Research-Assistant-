from contextlib import ExitStack
import unittest
from unittest.mock import patch

from app.rag import rag_service, retriever


class SourceRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.documents = [
            {"source_id": "llm-source", "filename": "llm.pdf"},
            {"source_id": "resume-source", "filename": "safeekmohamedresume (4).pdf"},
        ]
        self.semantic = {
            "ids": [["llm-1", "resume-1"]],
            "documents": [["LLM architecture evidence", "resume employment history"]],
            "metadatas": [[
                {"source_id": "llm-source", "filename": "llm.pdf", "page": 1},
                {"source_id": "resume-source", "filename": "safeekmohamedresume (4).pdf", "page": 1},
            ]],
            "distances": [[0.1, 0.2]],
        }
        self.lexical = {
            "ids": ["llm-1", "resume-1"],
            "documents": ["LLM architecture evidence", "resume employment history"],
            "metadatas": [
                {"source_id": "llm-source", "filename": "llm.pdf", "page": 1},
                {"source_id": "resume-source", "filename": "safeekmohamedresume (4).pdf", "page": 1},
            ],
        }

    def _identity_ranking_patches(self):
        return [
            patch.object(retriever, "select_rerank_candidates", side_effect=lambda items: items),
            patch.object(retriever, "rerank_candidates", side_effect=lambda query, candidates: candidates),
            patch.object(retriever, "apply_final_relevance_score", side_effect=lambda items: items),
            patch.object(retriever, "filter_relevant_sources", side_effect=lambda candidates: candidates),
            patch.object(retriever, "apply_preferred_source_boost", side_effect=lambda candidates, preferred_sources: candidates),
            patch.object(retriever, "diversify_sources", side_effect=lambda candidates, limit, max_chunks_per_source: candidates),
            patch.object(retriever, "sort_final_candidates", side_effect=lambda candidates: candidates),
            patch.object(retriever, "cleanup_candidates", side_effect=lambda candidates, limit: candidates),
        ]

    def test_named_pdf_is_hard_source_boundary_and_excludes_resume(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(retriever, "get_user_file_metadata", return_value=self.documents))
            semantic_search = stack.enter_context(patch.object(retriever, "search_semantic_by_sources", return_value=self.semantic))
            unrestricted_search = stack.enter_context(patch.object(retriever, "search_semantic"))
            lexical_search = stack.enter_context(patch.object(retriever, "get_all_user_chunks", return_value=self.lexical))
            for mocked in self._identity_ranking_patches():
                stack.enter_context(mocked)
            results = retriever.hybrid_retrieve(
                user_id="owner-a", query="Explain the concepts in llm.pdf", limit=None
            )
        self.assertEqual([item["metadata"]["filename"] for item in results], ["llm.pdf"])
        self.assertEqual(semantic_search.call_args.kwargs["source_filters"], [{"source_id": "llm-source"}])
        self.assertEqual(lexical_search.call_args.kwargs["source_filters"], [{"source_id": "llm-source"}])
        unrestricted_search.assert_not_called()

    def test_missing_named_pdf_returns_no_evidence_without_general_search(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(retriever, "get_user_file_metadata", return_value=[]))
            semantic_search = stack.enter_context(patch.object(retriever, "search_semantic"))
            restricted_search = stack.enter_context(patch.object(retriever, "search_semantic_by_sources"))
            results = retriever.hybrid_retrieve(
                user_id="owner-a", query="Summarize missing.pdf", limit=None
            )
        self.assertEqual(results, [])
        semantic_search.assert_not_called()
        restricted_search.assert_not_called()

    def test_attached_source_is_allowlisted_in_semantic_and_lexical_retrieval(self):
        attachment = {"source_id": "llm-source", "filename": "llm.pdf"}
        with ExitStack() as stack:
            semantic_search = stack.enter_context(patch.object(retriever, "search_semantic_by_sources", return_value=self.semantic))
            unrestricted_search = stack.enter_context(patch.object(retriever, "search_semantic"))
            lexical_search = stack.enter_context(patch.object(retriever, "get_all_user_chunks", return_value=self.lexical))
            for mocked in self._identity_ranking_patches():
                stack.enter_context(mocked)
            results = retriever.hybrid_retrieve(
                user_id="owner-a", query="Explain these materials", limit=None,
                attached_sources=[attachment],
            )
        self.assertEqual({item["metadata"]["filename"] for item in results}, {"llm.pdf"})
        self.assertEqual(semantic_search.call_args.kwargs["source_filters"], [{"source_id": "llm-source"}])
        self.assertEqual(lexical_search.call_args.kwargs["source_filters"], [{"source_id": "llm-source"}])
        unrestricted_search.assert_not_called()

    def test_generation_timeout_is_logged_with_stage_timing_and_propagated(self):
        evidence = [{"id": "chunk-1", "content": "evidence", "metadata": {"filename": "paper.pdf"}}]
        with (
            patch.object(rag_service, "hybrid_retrieve", return_value=evidence),
            patch.object(rag_service, "build_context", return_value="internal evidence"),
            patch.object(rag_service, "fit_generation_context", return_value=("question", "context", "")),
            patch.object(rag_service, "generate_answer", side_effect=TimeoutError("model timed out")),
            self.assertLogs("app.rag.rag_service", level="INFO") as captured,
        ):
            with self.assertRaisesRegex(TimeoutError, "model timed out"):
                rag_service.answer_question(user_id="owner-a", question="Explain this material")
        combined = "\n".join(captured.output)
        self.assertIn("RAG generation failed:", combined)
        self.assertIn("elapsed_seconds=", combined)
        self.assertNotIn("internal evidence", combined)

    def test_missing_requested_source_does_not_fall_back_to_general_llm(self):
        with (
            patch.object(rag_service, "hybrid_retrieve", return_value=[]),
            patch.object(rag_service, "generate_answer") as generation,
        ):
            result = rag_service.answer_question(
                user_id="owner-a", question="What does missing.pdf say?"
            )
        self.assertIn("could not find retrievable indexed content", result["answer"])
        self.assertEqual(result["citations"], [])
        generation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
