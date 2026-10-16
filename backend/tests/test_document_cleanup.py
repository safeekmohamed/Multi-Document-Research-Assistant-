import unittest
from unittest.mock import patch

from app.documents import document_service


class DocumentCleanupTests(unittest.TestCase):
    def test_file_cleanup_is_scoped_to_the_uploaded_source_id(self):
        document_id = "507f1f77bcf86cd799439011"
        source_id = "unique-file-source"
        document = {
            "_id": document_service.ObjectId(document_id),
            "user_id": "owner-id",
            "source_id": source_id,
            "source_type": "file",
            "filename": "duplicate-name.pdf",
        }

        with (
            patch.object(
                document_service.documents_collection,
                "find_one",
                return_value=document,
            ),
            patch.object(document_service, "delete_source") as remove_vectors,
            patch.object(
                document_service.documents_collection,
                "delete_one",
            ),
        ):
            document_service.delete_user_document(
                "owner-id",
                document_id,
            )

        remove_vectors.assert_called_once_with(
            user_id="owner-id",
            source_type="file",
            source_value="duplicate-name.pdf",
            source_id=source_id,
        )

    def test_url_cleanup_is_scoped_to_the_ingested_source_id(self):
        document_id = "507f1f77bcf86cd799439012"
        source_id = "unique-url-source"
        document = {
            "_id": document_service.ObjectId(document_id),
            "user_id": "owner-id",
            "source_id": source_id,
            "source_type": "url",
            "source_url": "https://example.com/research",
        }

        with (
            patch.object(
                document_service.documents_collection,
                "find_one",
                return_value=document,
            ),
            patch.object(document_service, "delete_source") as remove_vectors,
            patch.object(
                document_service.documents_collection,
                "delete_one",
            ),
        ):
            document_service.delete_user_document(
                "owner-id",
                document_id,
            )

        remove_vectors.assert_called_once_with(
            user_id="owner-id",
            source_type="url",
            source_value="https://example.com/research",
            source_id=source_id,
        )


if __name__ == "__main__":
    unittest.main()
