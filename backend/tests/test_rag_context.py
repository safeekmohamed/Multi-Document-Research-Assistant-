import unittest
import re
from unittest.mock import Mock, patch

from app.main import configured_frontend_origins
from app.rag import rag_service, retriever, vector_store
from app.rag import chain
from app.rag.retriever import (
    bm25_candidates,
    diversify_sources,
    filter_relevant_sources,
    merge_retrieval_candidates,
    rerank_candidates,
    select_rerank_candidates,
)


class FollowUpContextTests(unittest.TestCase):
    def setUp(self):
        self.history = [
            {
                "role": "user",
                "content": "What is LangChain?",
            },
            {
                "role": "assistant",
                "content": (
                    "1. Chains connect components.\n"
                    "2. Prompt templates prepare inputs.\n"
                    "3. Callbacks observe and manage execution."
                ),
                "citations": [
                    {
                        "source_type": "file",
                        "source_id": "langchain-source",
                        "filename": "LangChain.pdf",
                    }
                ],
            },
            {
                "role": "user",
                "content": "What is RAG?",
            },
            {
                "role": "assistant",
                "content": (
                    "1. Retrieval finds relevant material.\n"
                    "2. Augmentation adds that material to the prompt.\n"
                    "3. Generation uses the supplied evidence to answer."
                ),
                "citations": [
                    {
                        "source_type": "file",
                        "source_id": "rag-source",
                        "filename": "RAG.pdf",
                    }
                ],
            },
        ]

    def test_point_phrasings_resolve_to_latest_answer(self):
        cases = (
            ("Explain point 2", "2"),
            ("Explain 3 point", "3"),
            ("Explain the third point", "3"),
            ("What about point 5?", "5"),
        )

        for question, expected_number in cases:
            with self.subTest(question=question):
                request = rag_service.get_numbered_point_request(
                    question,
                    self.history,
                )
                self.assertEqual(
                    request["number"],
                    expected_number,
                )

        request = rag_service.get_numbered_point_request(
            "Explain point 3",
            self.history,
        )
        self.assertEqual(
            request["number"],
            "3",
        )
        resolved_query = rag_service.build_retrieval_query(
            "Explain point 3",
            self.history,
            follow_up=True,
        )
        self.assertIn("What is RAG?", resolved_query)
        self.assertIn(
            "Generation uses the supplied evidence",
            resolved_query,
        )
        self.assertNotIn("point 3", resolved_query.casefold())
        self.assertIn("RAG.pdf", resolved_query)
        self.assertNotIn("LangChain.pdf", resolved_query)


    def test_all_points_uses_latest_answer(self):
        request = rag_service.get_numbered_point_request(
            "Explain all points",
            self.history,
        )
        self.assertEqual(request["type"], "all")
        self.assertEqual(
            [point["number"] for point in request["points"]],
            ["1", "2", "3"],
        )
        resolved_query = rag_service.build_retrieval_query(
            "Explain all points",
            self.history,
            follow_up=True,
        )
        self.assertNotIn("point 1", resolved_query.casefold())

    def test_open_ended_follow_ups_retrieve_from_latest_turn(self):
        cases = (
            "Summarize it",
            "Tell me more",
            "Compare them",
            "What are its advantages?",
        )
        for question in cases:
            with self.subTest(question=question):
                self.assertTrue(
                    rag_service.is_follow_up_question(
                        question,
                        self.history,
                    )
                )
                resolved_query = rag_service.build_retrieval_query(
                    question,
                    self.history,
                    follow_up=True,
                )
                self.assertIn("What is RAG?", resolved_query)
                self.assertIn(
                    "Generation uses the supplied evidence",
                    resolved_query,
                )
                self.assertNotIn(
                    "Chaining components",
                    resolved_query,
                )
                self.assertIn("RAG.pdf", resolved_query)

    def test_answer_pipeline_retrieves_latest_numbered_point(self):
        supporting_chunks = [
            {
                "content": (
                    "Generation uses supplied evidence to create a response "
                    "that addresses the user's question."
                ),
                "metadata": {
                    "source_id": "rag-source",
                    "filename": "RAG.pdf",
                    "source_type": "file",
                },
                "final_relevance_score": 0.9,
            }
        ]
        with (
            patch.object(
                rag_service,
                "hybrid_retrieve",
                return_value=supporting_chunks,
            ) as retrieve,
            patch.object(
                rag_service,
                "generate_answer",
                return_value="Generation turns the evidence into an answer.",
            ),
            patch.object(
                rag_service.documents_collection,
                "find",
                return_value=[],
            ),
        ):
            response = rag_service.answer_question(
                user_id="test-user",
                question="Give an example for point 3",
                conversation_history=self.history,
            )

        retrieval_query = retrieve.call_args.kwargs["query"]
        self.assertIn(
            "Generation uses the supplied evidence",
            retrieval_query,
        )
        self.assertNotIn("point 3", retrieval_query.casefold())
        self.assertEqual(
            retrieve.call_args.kwargs["preferred_sources"][0]["source_id"],
            "rag-source",
        )
        self.assertEqual(len(response["citations"]), 1)

    def test_unavailable_point_requests_clarification(self):
        response = rag_service.answer_question(
            user_id="test-user",
            question="Explain point 3",
            conversation_history=[
                {"role": "assistant", "content": "A short unnumbered answer."}
            ],
        )
        self.assertIn("Could you paste or describe", response["answer"])
        self.assertEqual(response["citations"], [])

    def test_natural_general_questions_can_use_general_knowledge(self):
        self.assertTrue(
            rag_service._can_answer_from_general_knowledge(
                "Please explain how a compiler works.",
                follow_up=False,
            )
        )
        self.assertFalse(
            rag_service._can_answer_from_general_knowledge(
                "What does my PDF say about compilers?",
                follow_up=False,
            )
        )


class RetrievalCoverageTests(unittest.TestCase):
    def test_semantic_search_requests_every_user_chunk(self):
        collection = Mock()
        collection.get.return_value = {"ids": [str(index) for index in range(1234)]}
        collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        with (
            patch.object(vector_store, "get_chroma_collection", return_value=collection),
            patch.object(vector_store, "create_embeddings", return_value=[[0.1, 0.2]]),
        ):
            vector_store.search_semantic(
                user_id="test-user",
                query="What is LLM?",
                limit=None,
            )

        self.assertEqual(
            collection.query.call_args.kwargs["n_results"],
            1234,
        )
        self.assertEqual(
            collection.get.call_args.kwargs["where"],
            {"user_id": "test-user"},
        )

    def test_source_search_requests_every_chunk_per_source(self):
        collection = Mock()
        collection.get.side_effect = [
            {"ids": [str(index) for index in range(90)]},
            {"ids": [str(index) for index in range(90)]},
        ]
        collection.query.side_effect = [
            {
                "ids": [["a"]],
                "documents": [["chunk a"]],
                "metadatas": [[{"source_id": "a"}]],
                "distances": [[0.1]],
            },
            {
                "ids": [["b"]],
                "documents": [["chunk b"]],
                "metadatas": [[{"source_id": "b"}]],
                "distances": [[0.2]],
            },
        ]

        with (
            patch.object(vector_store, "get_chroma_collection", return_value=collection),
            patch.object(vector_store, "create_embeddings", return_value=[[0.1, 0.2]]),
        ):
            vector_store.search_semantic_by_sources(
                user_id="test-user",
                query="compare the supplied documents",
                source_filters=[
                    {"source_id": "a"},
                    {"source_id": "b"},
                ],
                limit=None,
            )

        self.assertEqual(
            [
                call.kwargs["n_results"]
                for call in collection.query.call_args_list
            ],
            [90, 90],
        )
        self.assertEqual(
            [
                call.kwargs["where"]
                for call in collection.get.call_args_list
            ],
            [
                {"$and": [{"user_id": "test-user"}, {"source_id": "a"}]},
                {"$and": [{"user_id": "test-user"}, {"source_id": "b"}]},
            ],
        )

    def test_reranking_has_no_fixed_candidate_slice(self):
        candidates = [
            {
                "id": str(index),
                "content": f"candidate passage {index}",
                "metadata": {"source_id": str(index % 8)},
            }
            for index in range(240)
        ]
        reranker = Mock()
        reranker.predict.return_value = [
            float(index) / 100
            for index in range(len(candidates))
        ]

        with patch(
            "app.rag.retriever.get_reranker",
            return_value=reranker,
        ):
            reranked = rerank_candidates("research query", candidates)

        self.assertEqual(len(reranked), len(candidates))
        self.assertEqual(
            len(reranker.predict.call_args.args[0]),
            len(candidates),
        )
        self.assertEqual(reranker.predict.call_args.kwargs["batch_size"], 8)

    def test_rerank_selection_keeps_semantic_leaders_from_every_source(self):
        candidates = [
            {
                "id": f"{source}-{index}",
                "content": f"passage {source}-{index}",
                "metadata": {"source_id": source},
                "semantic_score": 1.0 - (index / 100),
                "lexical_score": 0.5,
            }
            for source in ("source-a", "source-b", "source-c")
            for index in range(30)
        ]

        selected = select_rerank_candidates(candidates)

        self.assertEqual(
            {
                candidate["metadata"]["source_id"]
                for candidate in selected
            },
            {"source-a", "source-b", "source-c"},
        )
        self.assertTrue(
            all(
                sum(
                    candidate["metadata"]["source_id"]
                    == source
                    for candidate in selected
                )
                == 12
                for source in ("source-a", "source-b", "source-c")
            )
        )

    def test_cleanup_preserves_all_sources_when_limit_is_unbounded(self):
        candidates = [
            {
                "id": f"chunk-{index}",
                "content": f"Unique content from source {index}.",
                "metadata": {"source_id": f"source-{index}"},
                "final_relevance_score": 0.9 - index / 100,
            }
            for index in range(18)
        ]

        cleaned = retriever.cleanup_candidates(candidates, limit=None)

        self.assertEqual(len(cleaned), 18)


class RetrievalBehaviorTests(unittest.TestCase):
    def test_cors_allows_production_frontend_and_configured_loopback_alias(self):
        self.assertEqual(
            configured_frontend_origins("http://localhost:3000"),
            [
                "https://multi-document-research-assistant.vercel.app",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
        )
        self.assertEqual(
            configured_frontend_origins("https://research.example"),
            [
                "https://multi-document-research-assistant.vercel.app",
                "https://research.example",
            ],
        )
        self.assertEqual(
            configured_frontend_origins(""),
            ["https://multi-document-research-assistant.vercel.app"],
        )

    def test_resume_comparison_phrasings_enter_resume_retrieval(self):
        for question in (
            "Compare two resumes",
            "Compare these resumes",
            "Compare these two resumes",
            "Which resume contains Python?",
            "What are the common skills in these resumes?",
        ):
            with self.subTest(question=question):
                self.assertTrue(
                    retriever.is_resume_content_query(question)
                )

    def test_resume_discovery_uses_legacy_chunk_content_and_skips_urls(self):
        documents = [
            {
                "source_id": "tagged-resume",
                "filename": "CandidateA.pdf",
                "document_type": "resume",
                "source_type": "file",
            },
            {
                "source_id": "legacy-resume",
                "filename": "CandidateB.pdf",
                "document_type": "other",
                "source_type": "file",
            },
            {
                "source_id": "website",
                "filename": "CandidateC",
                "document_type": "other",
                "source_type": "url",
                "url": "https://example.invalid",
            },
        ]
        indexed_chunks = {
            "documents": ["legacy content"],
            "metadatas": [
                {
                    "source_id": "legacy-resume",
                    "filename": "CandidateB.pdf",
                }
            ],
        }

        with (
            patch.object(
                retriever,
                "get_user_file_metadata",
                return_value=documents,
            ),
            patch.object(
                retriever,
                "get_all_user_chunks",
                return_value=indexed_chunks,
            ),
            patch.object(
                retriever,
                "classify_document",
                return_value=("resume", 0.9),
            ) as classify,
        ):
            resumes = retriever.discover_resumes("test-user")

        self.assertEqual(
            {document["source_id"] for document in resumes},
            {"tagged-resume", "legacy-resume"},
        )
        classify.assert_called_once()

    def test_legacy_spreadsheet_is_not_misclassified_as_resume(self):
        documents = [{
            "source_id": "employee-table",
            "filename": "sample-employees.xlsx",
            "file_type": "xlsx",
            "document_type": "other",
            "source_type": "file",
        }]
        indexed_chunks = {
            "documents": ["Employee data with skills, education, and experience columns."],
            "metadatas": [{
                "source_id": "employee-table",
                "filename": "sample-employees.xlsx",
                "file_type": "xlsx",
            }],
        }

        with (
            patch.object(retriever, "get_user_file_metadata", return_value=documents),
            patch.object(retriever, "get_all_user_chunks", return_value=indexed_chunks),
            patch.object(retriever, "classify_document", return_value=("resume", 0.99)) as classify,
        ):
            resumes = retriever.discover_resumes("test-user")

        self.assertEqual(resumes, [])
        classify.assert_not_called()

    def test_resume_comparison_searches_only_resume_sources_without_chunk_type_tags(self):
        documents = [
            {
                "source_id": "tagged-resume",
                "filename": "CandidateA.pdf",
                "document_type": "resume",
                "source_type": "file",
            },
            {
                "source_id": "legacy-resume",
                "filename": "CandidateB.pdf",
                "document_type": "other",
                "source_type": "file",
            },
            {
                "source_id": "website",
                "filename": "Unrelated",
                "document_type": "other",
                "source_type": "url",
                "url": "https://example.invalid",
            },
        ]
        candidate = {
            "id": "legacy-chunk",
            "content": "Unlabeled indexed resume content.",
            "metadata": {
                "source_id": "legacy-resume",
                "filename": "CandidateB.pdf",
            },
        }
        unrelated_candidate = {
            "id": "website-chunk",
            "content": "Unrelated website content.",
            "metadata": {
                "source_id": "website",
                "filename": "Unrelated",
                "source_type": "url",
            },
        }
        empty_result = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        indexed_chunks = {
            "documents": ["legacy content"],
            "metadatas": [
                {
                    "source_id": "legacy-resume",
                    "filename": "CandidateB.pdf",
                }
            ],
        }

        with (
            patch.object(
                retriever,
                "get_user_file_metadata",
                return_value=documents,
            ),
            patch.object(
                retriever,
                "get_all_user_chunks",
                return_value=indexed_chunks,
            ),
            patch.object(
                retriever,
                "classify_document",
                return_value=("resume", 0.9),
            ),
            patch.object(
                retriever,
                "search_semantic_by_sources",
                return_value=empty_result,
            ) as source_search,
            patch.object(
                retriever,
                "search_semantic",
            ) as general_search,
            patch.object(
                retriever,
                "detect_source_filter",
                return_value=None,
            ),
            patch.object(
                retriever,
                "build_candidates",
                return_value=[candidate, unrelated_candidate],
            ),
            patch.object(
                retriever,
                "rerank_candidates",
                return_value=[candidate],
            ),
            patch.object(
                retriever,
                "apply_final_relevance_score",
                return_value=[candidate],
            ),
            patch.object(
                retriever,
                "filter_relevant_sources",
            ) as relevance_filter,
            patch.object(
                retriever,
                "filter_resume_query_candidates",
            ) as resume_filter,
            patch.object(
                retriever,
                "apply_preferred_source_boost",
                return_value=[candidate],
            ),
            patch.object(
                retriever,
                "diversify_sources",
                return_value=[candidate],
            ),
            patch.object(
                retriever,
                "sort_final_candidates",
                return_value=[candidate],
            ),
            patch.object(
                retriever,
                "cleanup_candidates",
                return_value=[candidate],
            ),
        ):
            results = retriever.hybrid_retrieve(
                user_id="test-user",
                query="Compare these two resumes",
                limit=None,
            )

        source_filters = source_search.call_args_list[0].kwargs["source_filters"]
        self.assertEqual(
            {item["source_id"] for item in source_filters},
            {"tagged-resume", "legacy-resume"},
        )
        general_search.assert_not_called()
        relevance_filter.assert_not_called()
        resume_filter.assert_not_called()
        self.assertEqual(results, [candidate])

    def test_source_relevance_keeps_high_scoring_documents(self):
        candidates = [
            {
                "id": "a-1",
                "content": "Relevant explanation from source A.",
                "metadata": {"source_id": "source-a"},
                "final_relevance_score": 0.92,
            },
            {
                "id": "a-2",
                "content": "Another useful passage from source A.",
                "metadata": {"source_id": "source-a"},
                "final_relevance_score": 0.90,
            },
            {
                "id": "b-1",
                "content": "Relevant explanation from source B.",
                "metadata": {"source_id": "source-b"},
                "final_relevance_score": 0.88,
            },
            {
                "id": "b-2",
                "content": "Another useful passage from source B.",
                "metadata": {"source_id": "source-b"},
                "final_relevance_score": 0.87,
            },
            {
                "id": "c-1",
                "content": "Unrelated content from source C.",
                "metadata": {"source_id": "source-c"},
                "final_relevance_score": 0.20,
            },
        ]

        selected = filter_relevant_sources(candidates)
        self.assertEqual(
            {item["metadata"]["source_id"] for item in selected},
            {"source-a", "source-b"},
        )
        diversified = diversify_sources(
            selected,
            limit=None,
            max_chunks_per_source=None,
        )
        self.assertEqual(len(diversified), 4)

    def test_citations_group_pages_by_unique_document(self):
        results = [
            {
                "content": "Source A page one explains the subject in detail.",
                "metadata": {
                    "source_id": "source-a",
                    "filename": "A.pdf",
                    "source_type": "file",
                    "page": 1,
                    "section": "Introduction",
                },
                "final_relevance_score": 0.82,
            },
            {
                "content": "Source A page two gives a second useful detail.",
                "metadata": {
                    "source_id": "source-a",
                    "filename": "A.pdf",
                    "source_type": "file",
                    "page": 2,
                    "section": "Methods",
                },
                "final_relevance_score": 0.79,
            },
            {
                "content": "Source B explains another relevant concept.",
                "metadata": {
                    "source_id": "source-b",
                    "filename": "B.pdf",
                    "source_type": "file",
                    "page": 3,
                },
                "final_relevance_score": 0.76,
            },
        ]

        context = rag_service.build_context(results)
        citations = rag_service.create_citations(results, context)

        self.assertEqual(len(citations), 2)
        source_a = next(
            citation
            for citation in citations
            if citation["source_id"] == "source-a"
        )
        self.assertEqual(source_a["pages"], [1, 2])
        self.assertEqual(
            set(source_a["sections"]),
            {"Introduction", "Methods"},
        )

        with patch.object(
            rag_service.documents_collection,
            "find",
            return_value=[
                {"source_id": "source-a", "_id": "mongo-document-a"},
                {"source_id": "source-b", "_id": "mongo-document-b"},
            ],
        ):
            citations_with_ids = rag_service.create_citations(
                results,
                context,
                user_id="test-user",
            )
        self.assertEqual(
            {
                citation["document_id"]
                for citation in citations_with_ids
            },
            {"mongo-document-a", "mongo-document-b"},
        )

    def test_legacy_chunk_without_source_id_uses_unique_filename_mapping(self):
        result = {
            "content": "A relevant explanatory passage from an older index.",
            "metadata": {
                "filename": "OlderIndex.pdf",
                "source_type": "file",
                "page": 1,
            },
            "final_relevance_score": 0.7,
        }
        with patch.object(
            rag_service.documents_collection,
            "find",
            return_value=[
                {
                    "_id": "mongo-document",
                    "filename": "OlderIndex.pdf",
                }
            ],
        ) as find_documents:
            citations = rag_service.create_citations(
                [result],
                user_id="test-user",
            )

        self.assertIn(
            {"filename": {"$in": ["OlderIndex.pdf"]}},
            find_documents.call_args.args[0]["$or"],
        )
        self.assertEqual(
            citations[0]["document_id"],
            "mongo-document",
        )

    def test_generation_context_retains_each_retrieved_source(self):
        original_budget = chain.MAX_REQUEST_TOKEN_ESTIMATE
        chain.MAX_REQUEST_TOKEN_ESTIMATE = 12000
        context = "\n\n".join(
            f"[Source {index}: source-{index}.pdf, page 1]\n"
            + (
                f"Source {index} explains the subject with useful "
                "supporting detail and evidence. "
            ) * 25
            for index in range(1, 5)
        )

        try:
            _, fitted_context, _ = chain.fit_generation_context(
                "What is the subject?",
                context,
                [],
            )
        finally:
            chain.MAX_REQUEST_TOKEN_ESTIMATE = original_budget

        source_ids = set(
            re.findall(r"\[Source\s+(\d+):", fitted_context)
        )
        self.assertEqual(source_ids, {"1", "2", "3", "4"})

    def test_two_relevant_sources_are_not_ranked_out_by_a_score_gap(self):
        candidates = [
            {
                "id": "a",
                "metadata": {"source_id": "source-a"},
                "final_relevance_score": 0.9,
            },
            {
                "id": "b",
                "metadata": {"source_id": "source-b"},
                "final_relevance_score": 0.4,
            },
        ]
        self.assertEqual(
            filter_relevant_sources(candidates),
            candidates,
        )

    def test_two_source_score_distribution_excludes_a_separate_low_group(self):
        candidates = [
            {
                "id": "a-1",
                "metadata": {"source_id": "source-a"},
                "final_relevance_score": 0.91,
            },
            {
                "id": "a-2",
                "metadata": {"source_id": "source-a"},
                "final_relevance_score": 0.89,
            },
            {
                "id": "b-1",
                "metadata": {"source_id": "source-b"},
                "final_relevance_score": 0.42,
            },
            {
                "id": "b-2",
                "metadata": {"source_id": "source-b"},
                "final_relevance_score": 0.40,
            },
        ]
        selected = filter_relevant_sources(candidates)
        self.assertEqual(
            {item["metadata"]["source_id"] for item in selected},
            {"source-a"},
        )

    def test_show_all_documents_uses_document_listing(self):
        with (
            patch.object(
                rag_service,
                "list_user_documents",
                return_value=[
                    {"filename": "First.pdf", "source_type": "file"},
                    {"filename": "Second.pdf", "source_type": "file"},
                ],
            ) as list_documents,
            patch.object(rag_service, "hybrid_retrieve") as retrieve,
        ):
            response = rag_service.answer_question(
                user_id="test-user",
                question="Show all my documents",
            )

        list_documents.assert_called_once_with("test-user")
        retrieve.assert_not_called()
        self.assertIn("First.pdf", response["answer"])
        self.assertIn("Second.pdf", response["answer"])

    def test_normal_question_keeps_all_selected_source_cards(self):
        chunks = [
            {
                "content": "An LLM learns patterns from text to generate language.",
                "metadata": {
                    "source_id": "llm-a",
                    "filename": "A.pdf",
                    "source_type": "file",
                    "page": 2,
                },
                "final_relevance_score": 0.84,
            },
            {
                "content": "Large language models are trained on text data.",
                "metadata": {
                    "source_id": "llm-b",
                    "filename": "B.pdf",
                    "source_type": "file",
                    "page": 4,
                },
                "final_relevance_score": 0.81,
            },
        ]
        for question in (
            "What is LLM?",
            "Summarize the relevant documents.",
        ):
            with self.subTest(question=question):
                with (
                    patch.object(
                        rag_service,
                        "hybrid_retrieve",
                        return_value=chunks,
                    ) as retrieve,
                    patch.object(
                        rag_service,
                        "generate_answer",
                        return_value="A moderately detailed explanation.",
                    ),
                    patch.object(
                        rag_service.documents_collection,
                        "find",
                        return_value=[],
                    ),
                ):
                    response = rag_service.answer_question(
                        user_id="test-user",
                        question=question,
                    )

                self.assertIsNone(retrieve.call_args.kwargs["limit"])
                self.assertEqual(
                    {
                        citation["source_id"]
                        for citation in response["citations"]
                    },
                    {"llm-a", "llm-b"},
                )

    def test_displayed_sources_keep_all_context_used_valid_sources(self):
        citations = [
            {
                "filename": "exact.pdf",
                "source_type": "file",
                "source_id": "exact",
                "relevance": 0.35,
            },
            {
                "filename": "below.docx",
                "source_type": "file",
                "source_id": "below",
                "relevance": 0.349,
            },
            {
                "filename": "above.xlsx",
                "source_type": "file",
                "source_id": "above",
                "relevance": 0.351,
                "relevance_percentage": 35.1,
            },
            {
                "filename": "site",
                "source_type": "url",
                "source_id": "site",
                "url": "https://example.test",
                "relevance": 0.8,
            },
            {
                "filename": "raw-score.pdf",
                "source_type": "file",
                "source_id": "raw",
                "relevance": 42,
            },
            {
                "filename": "invalid.pdf",
                "source_type": "other",
                "source_id": "invalid",
                "relevance": 0.9,
            },
            {
                "filename": "No matching source",
                "source_type": "none",
                "source_id": "fake",
                "relevance": 0.9,
            },
        ]

        displayed = rag_service.filter_displayed_sources(citations)
        self.assertEqual(
            {citation["source_id"] for citation in displayed},
            {"exact", "below", "above", "site"},
        )
        self.assertEqual(
            next(
                citation["relevance_percentage"]
                for citation in displayed
                if citation["source_id"] == "above"
            ),
            35.1,
        )

    def test_display_filter_does_not_remove_generation_context(self):
        chunks = [
            {
                "content": "A relevant passage just below the card threshold.",
                "metadata": {
                    "source_id": "lower-source",
                    "filename": "Lower.pdf",
                    "source_type": "file",
                    "page": 1,
                },
                "final_relevance_score": 0.35,
            },
            {
                "content": "A useful passage above the card threshold.",
                "metadata": {
                    "source_id": "higher-source",
                    "filename": "Higher.pdf",
                    "source_type": "file",
                    "page": 2,
                },
                "final_relevance_score": 0.36,
            },
        ]
        with (
            patch.object(
                rag_service,
                "hybrid_retrieve",
                return_value=chunks,
            ),
            patch.object(
                rag_service,
                "generate_answer",
                return_value="Grounded answer.",
            ) as generate,
            patch.object(
                rag_service.documents_collection,
                "find",
                return_value=[],
            ),
        ):
            response = rag_service.answer_question(
                user_id="test-user",
                question="Explain the documents.",
            )

        self.assertIn("Lower.pdf", generate.call_args.kwargs["context"])
        self.assertIn("Higher.pdf", generate.call_args.kwargs["context"])
        self.assertEqual(
            [citation["source_id"] for citation in response["citations"]],
            ["higher-source", "lower-source"],
        )


class HybridLexicalRetrievalTests(unittest.TestCase):
    def test_bm25_independently_finds_exact_terms_semantic_search_missed(self):
        chunks = {
            "ids": ["exact", "unrelated"],
            "documents": [
                "A distinctive quartz oscillator controls timing.",
                "A study about birds and river habitats.",
            ],
            "metadatas": [
                {"user_id": "user-a", "filename": "Quartz.pdf", "source_id": "a"},
                {"user_id": "user-a", "filename": "Birds.pdf", "source_id": "b"},
            ],
        }
        lexical = bm25_candidates("quartz oscillator", chunks)
        self.assertEqual([item["id"] for item in lexical], ["exact"])
        self.assertGreater(lexical[0]["bm25_score"], 0)
        self.assertEqual(lexical[0]["semantic_score"], 0)

    def test_bm25_respects_explicit_source_filter_and_merges_with_semantic(self):
        chunks = {
            "ids": ["a", "b"],
            "documents": ["quartz oscillator details", "quartz oscillator summary"],
            "metadatas": [
                {"filename": "A.pdf", "source_id": "a"},
                {"filename": "B.pdf", "source_id": "b"},
            ],
        }
        lexical = bm25_candidates(
            "quartz oscillator",
            chunks,
            {"type": "filename", "filename": "A.pdf"},
        )
        semantic = [{
            "id": "a",
            "content": "quartz oscillator details",
            "metadata": chunks["metadatas"][0],
            "semantic_score": 0.8,
            "lexical_score": 0.1,
        }]
        combined = merge_retrieval_candidates(semantic, lexical)
        self.assertEqual([item["id"] for item in combined], ["a"])
        self.assertEqual(combined[0]["semantic_score"], 0.8)
        self.assertGreater(combined[0]["bm25_score"], 0)

    def test_hybrid_retrieval_returns_bm25_hit_when_semantic_search_is_empty(self):
        chunks = {
            "ids": ["lexical-only"],
            "documents": ["quartz oscillator frequency control"],
            "metadatas": [{
                "user_id": "user-a",
                "filename": "Quartz.pdf",
                "source_id": "quartz-source",
                "source_type": "file",
                "page": 3,
            }],
        }
        empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        with (
            patch.object(retriever, "search_semantic", return_value=empty),
            patch.object(retriever, "get_all_user_chunks", return_value=chunks) as lexical_index,
            patch.object(retriever, "rerank_candidates", side_effect=lambda query, candidates: candidates),
            patch.object(retriever, "filter_relevant_sources", side_effect=lambda candidates: candidates),
        ):
            results = retriever.hybrid_retrieve(
                user_id="user-a",
                query="quartz oscillator frequency",
                limit=4,
            )

        lexical_index.assert_called_once_with(user_id="user-a", file_type=None)
        self.assertEqual([item["id"] for item in results], ["lexical-only"])
        self.assertEqual(results[0]["metadata"]["page"], 3)
        self.assertGreater(results[0]["bm25_score"], 0)


if __name__ == "__main__":
    unittest.main()
