import asyncio
import os
import unittest
from io import BytesIO
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.auth import jwt as jwt_auth
from app.routes import auth, documents


class DocumentViewTests(unittest.TestCase):
    def _view_app(self):
        app = FastAPI()
        app.include_router(documents.router)
        return app

    def _token(self, user_id, *, expired=False):
        if expired:
            return jwt_auth.jwt.encode(
                {
                    "user_id": user_id,
                    "email": "owner@example.test",
                    "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
                },
                os.environ["JWT_SECRET_KEY"],
                algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            )
        return jwt_auth.create_access_token(user_id, "owner@example.test")

    def test_bearer_session_can_open_owned_document_over_http(self):
        user_id = "507f1f77bcf86cd799439021"
        cloud_file = Mock()
        cloud_file.status_code = 200
        cloud_file.headers = {"Content-Type": "application/pdf"}
        cloud_file.iter_content.return_value = [b"pdf-bytes"]
        app = FastAPI()
        app.include_router(documents.router)

        with (
            patch.dict(
                os.environ,
                {"JWT_SECRET_KEY": "view-test-signing-key-for-isolated-tests"},
            ),
            patch.object(
                jwt_auth.users_collection,
                "find_one",
                return_value={"_id": jwt_auth.ObjectId(user_id)},
            ),
            patch.object(
                documents.documents_collection,
                "find_one",
                return_value={
                    "user_id": user_id,
                    "source_type": "file",
                    "filename": "report.pdf",
                    "cloudinary_public_id": "reports/report.pdf",
                    "cloudinary_url": (
                        "https://res.cloudinary.com/example/raw/upload/report.pdf"
                    ),
                },
            ),
            patch.object(documents.requests, "get", return_value=cloud_file),
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed"),
        ):
            token = jwt_auth.create_access_token(user_id, "owner@example.test")
            response = TestClient(app).get(
                "/documents/view/507f1f77bcf86cd799439022",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"pdf-bytes")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertNotIn("location", response.headers)

    def test_login_issued_token_opens_owned_document(self):
        user_id = "507f1f77bcf86cd799439031"
        user = {
            "_id": jwt_auth.ObjectId(user_id),
            "email": "owner@example.com",
            "is_blocked": False,
        }
        cloud_file = Mock()
        cloud_file.status_code = 200
        cloud_file.headers = {"Content-Type": "application/pdf"}
        cloud_file.iter_content.return_value = [b"pdf-bytes"]
        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(documents.router)

        with (
            patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": (
                        "login-to-view-test-signing-key-for-isolated-tests"
                    )
                },
            ),
            patch.object(auth, "authenticate_user", return_value=user),
            patch.object(jwt_auth.users_collection, "find_one", return_value=user),
            patch.object(
                documents.documents_collection,
                "find_one",
                return_value={
                    "user_id": user_id,
                    "source_type": "file",
                    "filename": "report.pdf",
                    "cloudinary_public_id": "reports/report.pdf",
                    "cloudinary_url": (
                        "https://res.cloudinary.com/example/raw/upload/report.pdf"
                    ),
                },
            ),
            patch.object(documents.requests, "get", return_value=cloud_file),
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed"),
        ):
            client = TestClient(app)
            login_response = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "test-password"},
            )
            self.assertEqual(login_response.status_code, 200)
            token = login_response.json()["access_token"]
            view_response = client.get(
                "/documents/view/507f1f77bcf86cd799439032",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(view_response.status_code, 200)
        self.assertEqual(view_response.content, b"pdf-bytes")
        self.assertEqual(view_response.headers["content-type"], "application/pdf")
        self.assertNotIn("location", view_response.headers)

    def test_document_view_rejects_requests_without_bearer_session(self):
        response = TestClient(self._view_app()).get(
            "/documents/view/507f1f77bcf86cd799439022")

        self.assertIn(response.status_code, {401, 403})

    def test_document_view_rejects_invalid_token(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "view-test-signing-key-for-isolated-tests"}):
            response = TestClient(self._view_app()).get(
                "/documents/view/507f1f77bcf86cd799439022",
                headers={"Authorization": "Bearer invalid-token"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid or expired token")

    def test_document_view_rejects_expired_token(self):
        user_id = "507f1f77bcf86cd799439021"
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "view-test-signing-key-for-isolated-tests"}):
            token = self._token(user_id, expired=True)
            response = TestClient(self._view_app()).get(
                "/documents/view/507f1f77bcf86cd799439022",
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid or expired token")

    def test_document_view_does_not_return_another_users_document(self):
        user_id = "507f1f77bcf86cd799439021"
        app = self._view_app()
        with (
            patch.dict(os.environ, {"JWT_SECRET_KEY": "view-test-signing-key-for-isolated-tests"}),
            patch.object(jwt_auth.users_collection, "find_one", return_value={"_id": jwt_auth.ObjectId(user_id)}),
            patch.object(documents.documents_collection, "find_one", return_value=None) as find_document,
            patch.object(documents.requests, "get") as get_file,
        ):
            token = self._token(user_id)
            response = TestClient(app).get(
                "/documents/view/507f1f77bcf86cd799439022",
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Document not found")
        self.assertEqual(
            find_document.call_args.args[0]["user_id"], user_id,
        )
        get_file.assert_not_called()

    def test_owner_receives_streamed_file_without_redirect(self):
        cloud_file = Mock()
        cloud_file.status_code = 200
        cloud_file.ok = True
        cloud_file.headers = {
            "Content-Type": "application/pdf",
            "Content-Length": "7",
        }
        cloud_file.iter_content.return_value = [b"%PDF-1.7"]

        with (
            patch.object(
                documents.documents_collection,
                "find_one",
                return_value={
                    "user_id": "owner-id",
                    "source_type": "file",
                    "filename": "report.pdf",
                    "cloudinary_public_id": "reports/report.pdf",
                    "cloudinary_url": (
                        "https://res.cloudinary.com/example/raw/upload/report.pdf"
                    ),
                },
            ),
            patch.object(documents.requests, "get", return_value=cloud_file) as get_file,
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed") as sign_download,
        ):
            response = documents.view_document(
                "document-id",
                {"_id": "owner-id"},
            )

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "application/pdf")
        sign_download.assert_called_once()
        self.assertEqual(sign_download.call_args.args[:2], ("reports/report.pdf", "pdf"))
        self.assertEqual(sign_download.call_args.kwargs["resource_type"], "raw")
        self.assertEqual(sign_download.call_args.kwargs["type"], "upload")
        self.assertEqual(get_file.call_args.args[0], "https://api.cloudinary.com/download/signed")
        self.assertEqual(
            response.headers["content-disposition"],
            "inline; filename*=UTF-8''report.pdf",
        )
        get_file.assert_called_once()
        self.assertFalse(get_file.call_args.kwargs["allow_redirects"])
        async def read_body():
            return [chunk async for chunk in response.body_iterator]

        self.assertEqual(
            asyncio.run(read_body()),
            [b"%PDF-1.7"],
        )
        asyncio.run(response.background())

    def test_missing_cloudinary_reference_returns_not_found(self):
        with (
            patch.object(documents.documents_collection, "find_one", return_value={
                "user_id": "owner-id", "source_type": "file", "filename": "report.pdf",
            }),
            patch.object(documents.requests, "get") as get_file,
            patch.object(documents.cloudinary.utils, "private_download_url") as sign_download,
        ):
            with self.assertRaises(HTTPException) as raised:
                documents.view_document("document-id", {"_id": "owner-id"})
        self.assertEqual(raised.exception.status_code, 404)
        get_file.assert_not_called()
        sign_download.assert_not_called()

    def test_cloudinary_missing_resource_returns_not_found(self):
        cloud_file = Mock()
        cloud_file.status_code = 404
        cloud_file.close = Mock()
        with (
            patch.object(documents.documents_collection, "find_one", return_value={
                "user_id": "owner-id", "source_type": "file", "filename": "report.pdf",
                "cloudinary_public_id": "reports/report.pdf",
            }),
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed"),
            patch.object(documents.requests, "get", return_value=cloud_file),
        ):
            with self.assertRaises(HTTPException) as raised:
                documents.view_document("document-id", {"_id": "owner-id"})
        self.assertEqual(raised.exception.status_code, 404)
        cloud_file.close.assert_called_once()

    def test_cloudinary_network_failure_is_reported_as_upstream_failure(self):
        with (
            patch.object(documents.documents_collection, "find_one", return_value={
                "user_id": "owner-id", "source_type": "file", "filename": "report.pdf",
                "cloudinary_public_id": "reports/report.pdf",
            }),
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed"),
            patch.object(documents.requests, "get", side_effect=documents.requests.Timeout("timeout")),
        ):
            with self.assertRaises(HTTPException) as raised:
                documents.view_document("document-id", {"_id": "owner-id"})
        self.assertEqual(raised.exception.status_code, 502)

    def test_xlsx_preview_returns_actual_rows_from_multiple_sheets(self):
        workbook = Workbook()
        workbook.active.title = "Summary"
        workbook.active.append(["Name", "Count"])
        workbook.active.append(["Articles", 3])
        detail = workbook.create_sheet("Details")
        detail.append(["Topic"])
        detail.append(["Research"])
        buffer = BytesIO()
        workbook.save(buffer)
        cloud_file = Mock()
        cloud_file.status_code = 200
        cloud_file.headers = {}
        cloud_file.iter_content.return_value = [buffer.getvalue()]
        with (
            patch.object(documents.documents_collection, "find_one", return_value={
                "user_id": "owner-id", "source_type": "file", "filename": "data.xlsx",
                "file_type": "xlsx", "cloudinary_public_id": "reports/data.xlsx",
            }),
            patch.object(documents.cloudinary.utils, "private_download_url", return_value="https://api.cloudinary.com/download/signed"),
            patch.object(documents.requests, "get", return_value=cloud_file),
        ):
            result = documents.preview_document_data("document-id", {"_id": "owner-id"})
        self.assertEqual(result["filename"], "data.xlsx")
        self.assertEqual(len(result["sheets"]), 2)
        self.assertEqual(len(result["sheets"][0]["rows"]), 2)
        self.assertEqual(result["sheets"][0]["rows"][1], ["Articles", "3"])
        self.assertEqual(result["sheets"][1]["rows"][1], ["Research"])
        self.assertFalse(result["truncated"])
        cloud_file.close.assert_called_once()

    def test_xlsx_preview_preserves_document_ownership(self):
        with (
            patch.object(documents.documents_collection, "find_one", return_value=None) as lookup,
            patch.object(documents.requests, "get") as cloudinary_get,
        ):
            with self.assertRaises(HTTPException) as raised:
                documents.preview_document_data("document-id", {"_id": "requesting-user"})
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(lookup.call_args.args[0]["user_id"], "requesting-user")
        cloudinary_get.assert_not_called()

    def test_missing_or_other_users_document_is_not_retrieved(self):
        with (
            patch.object(
                documents.documents_collection,
                "find_one",
                return_value=None,
            ),
            patch.object(documents.requests, "get") as get_file,
        ):
            with self.assertRaises(HTTPException) as raised:
                documents.view_document(
                    "document-id",
                    {"_id": "requesting-user"},
                )

        self.assertEqual(raised.exception.status_code, 404)
        get_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
