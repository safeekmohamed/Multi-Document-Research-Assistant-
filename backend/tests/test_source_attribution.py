import unittest
import math
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import get_current_user
from app.rag import rag_service, retriever
from app.routes import chat as chat_route


class SourceAttributionTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            {
                "id": "safeek-page-2",
                "content": "Safeek's resume lists Java in the programming languages section.",
                "metadata": {
                    "source_id": "safeek-source",
                    "filename": "Safeek Resume.pdf",
                    "source_type": "file",
                    "page": 2,
                    "section": "Technical Skills",
                },
                "final_relevance_score": 0.35,
            },
            {
                "id": "anil-page-5",
                "content": "Anil's resume discusses project management experience.",
                "metadata": {
                    "source_id": "anil-source",
                    "filename": "Anil Sathiyamoorthy Resume.pdf",
                    "source_type": "file",
                    "page": 5,
                    "section": "Experience",
                },
                "final_relevance_score": 0.72,
            },
        ]

    def _answer(self, selected_results, searched_files=None):
        searched = searched_files or [
            {
                "filename": item["metadata"]["filename"],
                "source_id": item["metadata"]["source_id"],
                "source_type": "file",
            }
            for item in self.results
        ]

        def retrieve(**kwargs):
            kwargs["retrieval_metadata"]["searched_files"] = searched
            return self.results

        complete_context = rag_service.build_context(self.results)
        selected_context = rag_service.build_context(selected_results)
        with (
            patch.object(rag_service, "hybrid_retrieve", side_effect=retrieve),
            patch.object(
                rag_service,
                "fit_generation_context",
                return_value=("Does Safeek's resume mention Java?", selected_context, ""),
            ),
            patch.object(rag_service, "generate_answer", return_value="Yes, Java is listed."),
            patch.object(rag_service.documents_collection, "find", return_value=[]),
        ):
            response = rag_service.answer_question(
                user_id="owner-a",
                question="Does Safeek's resume mention Java?",
            )
        return response, complete_context

    def test_two_resumes_searched_but_only_selected_resume_is_cited(self):
        response, _ = self._answer(self.results[:1])
        self.assertEqual(
            {item["source_id"] for item in response["searched_files"]},
            {"safeek-source", "anil-source"},
        )
        self.assertEqual(
            [(item["filename"], item["source_id"], item["pages"]) for item in response["citations"]],
            [("Safeek Resume.pdf", "safeek-source", [2])],
        )
        self.assertEqual(
            {item["source_id"] for item in response["sources"]},
            {"safeek-source", "anil-source"},
        )
        anil_source = next(
            item for item in response["sources"]
            if item["source_id"] == "anil-source"
        )
        self.assertEqual(anil_source["relevance_percentage"], 72.0)
        self.assertEqual(anil_source["pages"], [5])
        safeek_source = next(
            item for item in response["sources"]
            if item["source_id"] == "safeek-source"
        )
        self.assertEqual(safeek_source["relevance_percentage"], 35.0)
        self.assertIn("Java", safeek_source["snippets"][0]["text"])

    def test_both_files_used_in_final_context_are_cited(self):
        response, _ = self._answer(self.results)
        self.assertEqual(
            {item["source_id"] for item in response["citations"]},
            {"safeek-source", "anil-source"},
        )

    def test_retrieved_file_omitted_from_final_context_is_not_cited(self):
        response, _ = self._answer(self.results[:1])
        self.assertIn("anil-source", {item["source_id"] for item in response["searched_files"]})
        self.assertNotIn("anil-source", {item["source_id"] for item in response["citations"]})

    def test_empty_evidence_returns_no_answer_sources(self):
        with (
            patch.object(rag_service, "hybrid_retrieve", return_value=[]),
            patch.object(rag_service, "generate_answer") as generate,
        ):
            response = rag_service.answer_question(
                user_id="owner-a",
                question="Does Safeek's resume mention Java?",
            )
        self.assertEqual(response["citations"], [])
        self.assertEqual(response["searched_files"], [])
        generate.assert_not_called()

    def test_retrieval_metadata_lists_only_files_in_the_explicit_allowlist(self):
        metadata = {}
        semantic = {
            "ids": [["safeek", "anil"]],
            "documents": [["Java listed", "Unrelated resume"]],
            "metadatas": [[
                self.results[0]["metadata"],
                self.results[1]["metadata"],
            ]],
            "distances": [[0.1, 0.2]],
        }
        lexical = {
            "ids": ["safeek", "anil"],
            "documents": ["Java listed", "Unrelated resume"],
            "metadatas": [
                self.results[0]["metadata"],
                self.results[1]["metadata"],
            ],
        }
        with (
            patch.object(
                retriever,
                "get_user_file_metadata",
                return_value=[self.results[0]["metadata"]],
            ),
            patch.object(retriever, "is_resume_content_query", return_value=False),
            patch.object(retriever, "search_semantic_by_sources", return_value=semantic),
            patch.object(retriever, "get_all_user_chunks", return_value=lexical),
            patch.object(retriever, "select_rerank_candidates", side_effect=lambda items: items),
            patch.object(retriever, "rerank_candidates", side_effect=lambda query, candidates: candidates),
            patch.object(retriever, "apply_final_relevance_score", side_effect=lambda items: items),
            patch.object(retriever, "filter_relevant_sources", side_effect=lambda candidates: candidates),
            patch.object(retriever, "diversify_sources", side_effect=lambda candidates, limit, max_chunks_per_source: candidates),
            patch.object(retriever, "sort_final_candidates", side_effect=lambda items: items),
            patch.object(retriever, "cleanup_candidates", side_effect=lambda candidates, limit: candidates),
        ):
            retriever.hybrid_retrieve(
                user_id="owner-a",
                query="Describe the content in Safeek Resume.pdf",
                limit=None,
                attached_sources=[{
                    "source_id": "safeek-source",
                    "filename": "Safeek Resume.pdf",
                }],
                retrieval_metadata=metadata,
            )
        self.assertEqual(
            [item["source_id"] for item in metadata["searched_files"]],
            ["safeek-source"],
        )

    def test_unrestricted_semantic_and_bm25_scope_reports_both_resumes(self):
        metadata = {}
        semantic = {
            "ids": [["safeek", "anil"]],
            "documents": [
                [item["content"] for item in self.results]
            ],
            "metadatas": [[item["metadata"] for item in self.results]],
            "distances": [[0.1, 0.2]],
        }
        lexical = {
            "ids": [item["id"] for item in self.results],
            "documents": [item["content"] for item in self.results],
            "metadatas": [item["metadata"] for item in self.results],
        }
        with (
            patch.object(retriever, "is_resume_content_query", return_value=False),
            patch.object(retriever, "search_semantic", return_value=semantic),
            patch.object(retriever, "get_all_user_chunks", return_value=lexical),
            patch.object(retriever, "select_rerank_candidates", side_effect=lambda items: items),
            patch.object(retriever, "rerank_candidates", side_effect=lambda query, candidates: candidates),
            patch.object(retriever, "apply_final_relevance_score", side_effect=lambda items: items),
            patch.object(retriever, "filter_relevant_sources", side_effect=lambda candidates: candidates),
            patch.object(retriever, "diversify_sources", side_effect=lambda candidates, limit, max_chunks_per_source: candidates),
            patch.object(retriever, "sort_final_candidates", side_effect=lambda items: items),
            patch.object(retriever, "cleanup_candidates", side_effect=lambda candidates, limit: candidates),
        ):
            retriever.hybrid_retrieve(
                user_id="owner-a",
                query="What does each document mention?",
                limit=None,
                retrieval_metadata=metadata,
            )
        self.assertEqual(
            {item["source_id"] for item in metadata["searched_files"]},
            {"safeek-source", "anil-source"},
        )

    def test_chat_route_returns_and_persists_attribution_metadata(self):
        app = FastAPI()
        app.include_router(chat_route.router)
        user_id = str(ObjectId())
        app.dependency_overrides[get_current_user] = lambda: {"_id": ObjectId(user_id)}
        client = TestClient(app)
        conversation_id = ObjectId()
        searched_files = [{
            "filename": "Safeek Resume.pdf",
            "source_id": "safeek-source",
            "source_type": "file",
        }]

        class EmptyCursor:
            def sort(self, *_args):
                return self

            def limit(self, *_args):
                return self

            def __iter__(self):
                return iter([])

        with (
            patch.object(chat_route, "get_model_warmup_error", return_value=None),
            patch.object(
                chat_route.conversations_collection,
                "insert_one",
                return_value=type("Inserted", (), {"inserted_id": conversation_id})(),
            ),
            patch.object(chat_route.messages_collection, "find", return_value=EmptyCursor()),
            patch.object(chat_route.messages_collection, "insert_one") as insert_message,
            patch.object(
                chat_route,
                "answer_question",
                return_value={
                    "answer": "Java is mentioned.",
                    "citations": [{
                        "filename": "Safeek Resume.pdf",
                        "source_id": "safeek-source",
                        "pages": [2],
                    }],
                    "sources": [{
                        "filename": "Safeek Resume.pdf",
                        "source_id": "safeek-source",
                        "pages": [2],
                        "relevance_percentage": 61.0,
                        "snippets": [{"text": "Java is listed."}],
                    }],
                    "searched_files": searched_files,
                },
            ),
        ):
            response = client.post("/chat/", json={"question": "Does Safeek mention Java?"})

        app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["searched_files"], searched_files)
        self.assertEqual(response.json()["source_attribution_version"], 1)
        self.assertEqual(response.json()["sources"][0]["relevance_percentage"], 61.0)
        assistant_message = insert_message.call_args_list[-1].args[0]
        self.assertEqual(assistant_message["searched_files"], searched_files)
        self.assertEqual(assistant_message["source_attribution_version"], 1)
        self.assertEqual(assistant_message["sources"][0]["snippets"][0]["text"], "Java is listed.")

    def test_sources_used_keep_filename_page_and_source_id_associated(self):
        response, _ = self._answer(self.results[:1])
        citation = response["citations"][0]
        self.assertEqual(citation["filename"], "Safeek Resume.pdf")
        self.assertEqual(citation["source_id"], "safeek-source")
        self.assertEqual(citation["page"], 2)
        self.assertEqual(citation["pages"], [2])

    def test_source_cards_include_35_percent_and_exclude_lower_or_missing_scores(self):
        candidates = [
            {"id": "at-threshold", "final_relevance_score": 0.35},
            {"id": "above-threshold", "final_relevance_score": 0.426},
            {"id": "below-threshold", "final_relevance_score": 0.3499},
            {"id": "missing-score"},
        ]
        qualifying = rag_service.qualifying_source_card_chunks(candidates)
        self.assertEqual(
            [item["id"] for item in qualifying],
            ["at-threshold", "above-threshold"],
        )

    def test_semantic_and_bm25_merge_deduplicates_chunks_and_keeps_both_signals(self):
        merged = retriever.merge_retrieval_candidates(
            [{
                "id": "chunk-a",
                "content": "Python experience in projects",
                "metadata": self.results[0]["metadata"],
                "semantic_score": 0.82,
                "lexical_score": 0.1,
            }],
            [
                {
                    "id": "chunk-a",
                    "content": "Python experience in projects",
                    "metadata": self.results[0]["metadata"],
                    "semantic_score": 0,
                    "lexical_score": 0.91,
                    "bm25_score": 1.0,
                },
                {
                    "id": "chunk-b",
                    "content": "Python skills",
                    "metadata": self.results[1]["metadata"],
                    "semantic_score": 0,
                    "lexical_score": 0.5,
                },
            ],
        )
        self.assertEqual(len(merged), 2)
        chunk_a = next(item for item in merged if item["id"] == "chunk-a")
        self.assertEqual(chunk_a["semantic_score"], 0.82)
        self.assertEqual(chunk_a["lexical_score"], 0.91)
        self.assertEqual(chunk_a["bm25_score"], 1.0)

    def test_reranker_logits_are_normalized_before_final_score_and_percentage(self):
        class FakeReranker:
            def predict(self, _pairs, **_kwargs):
                return [-2.0, 0.8]

        candidates = [
            {"id": "negative-logit", "content": "Python", "semantic_score": 0.5},
            {"id": "positive-logit", "content": "Python", "semantic_score": 0.5},
        ]
        with patch.object(retriever, "get_reranker", return_value=FakeReranker()):
            ranked = retriever.rerank_candidates("Python skills", candidates)
        by_id = {item["id"]: item for item in ranked}
        self.assertAlmostEqual(
            by_id["negative-logit"]["normalized_rerank_score"],
            1 / (1 + math.exp(2)),
        )
        self.assertAlmostEqual(
            by_id["positive-logit"]["normalized_rerank_score"],
            1 / (1 + math.exp(-0.8)),
        )
        scored = retriever.apply_final_relevance_score(ranked)
        self.assertTrue(all(0.0 <= item["final_relevance_score"] <= 1.0 for item in scored))

    def test_normal_question_passes_retrieved_text_to_generation(self):
        question = "Does Anis Fathima have Python skills?"
        evidence = {
            "id": "anis-python",
            "content": "Anis Fathima lists Python among her technical skills.",
            "metadata": {
                "source_id": "anis-resume",
                "filename": "Anis Fathima Resume.pdf",
                "source_type": "file",
                "page": 1,
            },
            "final_relevance_score": 0.81,
        }
        final_context = rag_service.build_context([evidence])
        with (
            patch.object(
                rag_service,
                "hybrid_retrieve",
                return_value=[evidence],
            ),
            patch.object(
                rag_service,
                "fit_generation_context",
                return_value=(question, final_context, ""),
            ),
            patch.object(rag_service, "generate_answer", return_value="Yes.") as generate,
            patch.object(rag_service.documents_collection, "find", return_value=[]),
        ):
            response = rag_service.answer_question(
                user_id="owner-a",
                question=question,
            )

        self.assertEqual(response["answer"], "Yes.")
        self.assertIn("Anis Fathima lists Python", generate.call_args.kwargs["context"])
        self.assertEqual(response["sources"][0]["filename"], "Anis Fathima Resume.pdf")


if __name__ == "__main__":
    unittest.main()
