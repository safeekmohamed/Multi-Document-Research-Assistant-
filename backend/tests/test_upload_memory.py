import asyncio
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.auth.jwt import get_current_user
from app.documents import document_service
from app.rag import vector_store
from app.routes import documents


class UploadMemoryTests(unittest.TestCase):
    def make_upload(self, filename="report.txt", content=b"document"):
        return UploadFile(
            file=BytesIO(content),
            size=len(content),
            filename=filename,
        )

    def test_upload_stages_in_bounded_reads_and_keeps_owner(self):
        content = b"x" * (documents.UPLOAD_COPY_CHUNK_SIZE * 2 + 17)
        upload = self.make_upload(content=content)
        original_read = upload.read
        upload.read = AsyncMock(wraps=original_read)
        captured_path = None

        def process(**kwargs):
            nonlocal captured_path
            captured_path = Path(kwargs["file_path"])
            self.assertEqual(kwargs["user_id"], "owner-17")
            self.assertNotIn("content", kwargs)
            self.assertEqual(captured_path.read_bytes(), content)
            self.assertTrue(captured_path.exists())
            return {"filename": kwargs["filename"], "chunk_count": 1}

        with patch.object(documents, "process_uploaded_document", side_effect=process):
            result = asyncio.run(documents.upload_documents(
                files=[upload],
                current_user={"_id": "owner-17"},
            ))

        self.assertEqual(result["documents"][0]["filename"], "report.txt")
        read_sizes = [args.args[0] for args in upload.read.call_args_list]
        self.assertEqual(len(read_sizes), 4)
        self.assertTrue(all(size == documents.UPLOAD_COPY_CHUNK_SIZE for size in read_sizes))
        self.assertTrue(upload.file.closed)
        self.assertFalse(captured_path.exists())

    def test_upload_rejects_oversized_file_before_processing_and_closes_it(self):
        upload = self.make_upload()
        upload.size = documents.MAX_UPLOAD_FILE_SIZE + 1
        process = Mock()

        with patch.object(documents, "process_uploaded_document", process):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(documents.upload_documents(
                    files=[upload], current_user={"_id": "owner-17"}
                ))

        self.assertEqual(raised.exception.status_code, 413)
        process.assert_not_called()
        self.assertTrue(upload.file.closed)

    def test_empty_upload_is_rejected_without_cloud_processing(self):
        upload = self.make_upload(content=b"")
        process = Mock()

        with patch.object(documents, "process_uploaded_document", process):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(documents.upload_documents(
                    files=[upload], current_user={"_id": "owner-17"}
                ))

        self.assertEqual(raised.exception.status_code, 400)
        process.assert_not_called()
        self.assertTrue(upload.file.closed)

    def test_processing_failure_returns_actionable_error_and_removes_staged_file(self):
        upload = self.make_upload()

        with patch.object(
            documents,
            "process_uploaded_document",
            side_effect=RuntimeError("private parser detail"),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(documents.upload_documents(
                    files=[upload], current_user={"_id": "owner-17"}
                ))

        self.assertEqual(raised.exception.status_code, 500)
        self.assertNotIn("private parser detail", raised.exception.detail)
        self.assertTrue(upload.file.closed)

    def test_upload_rejects_excess_file_count_and_total_size(self):
        too_many = [self.make_upload(filename=f"{index}.txt") for index in range(documents.MAX_UPLOAD_FILES + 1)]
        process = Mock()
        with patch.object(documents, "process_uploaded_document", process):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(documents.upload_documents(
                    files=too_many, current_user={"_id": "owner-17"}
                ))
        self.assertEqual(raised.exception.status_code, 413)
        self.assertTrue(all(upload.file.closed for upload in too_many))
        process.assert_not_called()

        too_large = [
            self.make_upload(filename=f"{index}.txt")
            for index in range(3)
        ]
        for upload in too_large:
            upload.size = documents.MAX_UPLOAD_FILE_SIZE
        with patch.object(documents, "process_uploaded_document", process):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(documents.upload_documents(
                    files=too_large, current_user={"_id": "owner-17"}
                ))
        self.assertEqual(raised.exception.status_code, 413)
        self.assertTrue(all(upload.file.closed for upload in too_large))
        process.assert_not_called()

    def test_multipart_parser_rejects_excess_file_count_before_upload_handler(self):
        app = FastAPI()
        app.include_router(documents.router)
        app.dependency_overrides[get_current_user] = lambda: {"_id": "owner-17"}
        files = [
            ("files", (f"{index}.txt", b"x", "text/plain"))
            for index in range(documents.MAX_UPLOAD_FILES + 1)
        ]
        with (
            patch.object(documents, "process_uploaded_document") as process,
            TestClient(app) as client,
        ):
            response = client.post("/documents/upload", files=files)

        self.assertEqual(response.status_code, 413)
        process.assert_not_called()

    def test_vector_chunks_are_embedded_and_added_in_bounded_batches(self):
        chunks = [f"chunk-{index}" for index in range(vector_store.EMBEDDING_BATCH_SIZE * 2 + 3)]
        metadatas = [{"source_id": "source-a", "page": index + 1} for index in range(len(chunks))]
        collection = Mock()

        with (
            patch.object(vector_store, "get_chroma_collection", return_value=collection),
            patch.object(
                vector_store,
                "create_embeddings",
                side_effect=lambda batch, batch_size: [[float(len(batch))] for _ in batch],
            ) as embed,
        ):
            ids = vector_store.add_chunks("owner-17", chunks, metadatas)

        self.assertEqual(len(ids), len(chunks))
        self.assertEqual(embed.call_count, 3)
        self.assertTrue(all(len(item.args[0]) <= vector_store.EMBEDDING_BATCH_SIZE for item in embed.call_args_list))
        written = [item.kwargs for item in collection.add.call_args_list]
        self.assertEqual(
            [len(item["documents"]) for item in written],
            [vector_store.EMBEDDING_BATCH_SIZE] * 2 + [3],
        )
        self.assertEqual([value for item in written for value in item["documents"]], chunks)
        stored_metadata = [value for item in written for value in item["metadatas"]]
        self.assertTrue(all(item["user_id"] == "owner-17" for item in stored_metadata))
        self.assertEqual([item["page"] for item in stored_metadata], list(range(1, len(chunks) + 1)))
        self.assertTrue(all(item["source_id"] == "source-a" for item in stored_metadata))

    def test_failed_batch_rolls_back_all_generated_vector_ids(self):
        collection = Mock()
        collection.add.side_effect = [None, RuntimeError("simulated add failure")]
        chunks = ["first"] * (vector_store.EMBEDDING_BATCH_SIZE + 1)
        metadatas = [{"source_id": "source-a"} for _ in chunks]

        with (
            patch.object(vector_store, "get_chroma_collection", return_value=collection),
            patch.object(vector_store, "create_embeddings", side_effect=lambda batch, batch_size: [[0.1] for _ in batch]),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated add failure"):
                vector_store.add_chunks("owner-17", chunks, metadatas)

        deleted_ids = collection.delete.call_args.kwargs["ids"]
        self.assertEqual(len(deleted_ids), len(chunks))
        self.assertEqual(len(set(deleted_ids)), len(chunks))

    def test_path_based_processing_streams_path_to_cloudinary_and_preserves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            staged_path = Path(directory) / "report.txt"
            staged_path.write_text("Text from the uploaded file", encoding="utf-8")
            cloudinary_result = {"secure_url": "https://cloudinary.example/report", "public_id": "report"}
            insert_result = Mock(inserted_id="document-id")
            with (
                patch.object(document_service.cloudinary.uploader, "upload", return_value=cloudinary_result) as upload,
                patch.object(document_service, "load_document", return_value=[{"text": "Text from the uploaded file", "page": 1}]) as load,
                patch.object(document_service, "classify_document", return_value=("report", 0.9)),
                patch.object(document_service, "split_document_pages", return_value=[{"text": "Text from the uploaded file", "page": 1}]),
                patch.object(document_service, "add_chunks", return_value=["vector-id"]) as add,
                patch.object(document_service.documents_collection, "insert_one", return_value=insert_result),
            ):
                result = document_service.process_uploaded_document(
                    user_id="owner-17",
                    filename="report.txt",
                    file_path=staged_path,
                )

            self.assertEqual(upload.call_args.args[0], str(staged_path))
            load.assert_called_once_with(str(staged_path))
            self.assertEqual(add.call_args.kwargs["user_id"], "owner-17")
            metadata = add.call_args.kwargs["metadatas"][0]
            self.assertTrue(metadata["source_id"])
            self.assertEqual(metadata["filename"], "report.txt")
            self.assertEqual(metadata["page"], 1)
            self.assertEqual(result["chunk_count"], 1)
            self.assertTrue(staged_path.exists())

    def test_extracted_text_limit_stops_before_classification_or_embedding(self):
        with tempfile.TemporaryDirectory() as directory:
            staged_path = Path(directory) / "large.txt"
            staged_path.write_text("large", encoding="utf-8")
            with (
                patch.object(document_service.cloudinary.uploader, "upload", return_value={
                    "secure_url": "https://cloudinary.example/large",
                    "public_id": "large",
                }),
                patch.object(document_service, "load_document", return_value=[{"text": "too much", "page": 1}]),
                patch.object(document_service, "classify_document") as classify,
                patch.object(document_service, "add_chunks") as add,
                patch.object(document_service.cloudinary.uploader, "destroy") as destroy,
                patch.object(document_service, "MAX_DOCUMENT_TEXT_CHARACTERS", 1),
            ):
                with self.assertRaisesRegex(ValueError, "5 million character processing limit"):
                    document_service.process_uploaded_document(
                        user_id="owner-17",
                        filename="large.txt",
                        file_path=staged_path,
                    )

            classify.assert_not_called()
            add.assert_not_called()
            destroy.assert_called_once()
            self.assertTrue(staged_path.exists())

    def test_office_archive_expansion_limit_is_checked_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            staged_path = Path(directory) / "large.xlsx"
            with zipfile.ZipFile(staged_path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", "x" * 2048)

            with patch.object(document_service, "MAX_OFFICE_ARCHIVE_EXPANDED_BYTES", 1024):
                with self.assertRaisesRegex(ValueError, "expanded Office document"):
                    document_service.validate_office_archive_size(staged_path, ".xlsx")


if __name__ == "__main__":
    unittest.main()
