import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.jwt import get_current_admin, get_current_user
from app.routes import feedback
from app.schemas.feedback import FeedbackCreateRequest


class FeedbackCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        self.documents.sort(
            key=lambda item: item.get(field) or datetime.min.replace(
                tzinfo=timezone.utc
            ),
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class InMemoryFeedbackCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        stored = {**document, "_id": ObjectId()}
        self.documents.append(stored)
        return Mock(inserted_id=stored["_id"])

    def find(self, query):
        return FeedbackCursor([
            item for item in self.documents
            if all(item.get(key) == value for key, value in query.items())
        ])

    def count_documents(self, query):
        return sum(
            all(item.get(key) == value for key, value in query.items())
            for item in self.documents
        )

    def find_one(self, query):
        return next(
            (item for item in self.documents
             if all(item.get(key) == value for key, value in query.items())),
            None,
        )

    def update_one(self, query, update):
        document = self.find_one(query)
        if document:
            document.update(update.get("$set", {}))


class FeedbackSchemaTests(unittest.TestCase):
    def test_message_is_trimmed_and_category_is_limited(self):
        request = FeedbackCreateRequest(
            category="bug_report",
            message="  The upload button is not responding.  ",
        )

        self.assertEqual(request.message, "The upload button is not responding.")

        with self.assertRaises(ValidationError):
            FeedbackCreateRequest(category="other", message="Message")

    def test_empty_and_control_character_messages_are_rejected(self):
        with self.assertRaises(ValidationError):
            FeedbackCreateRequest(category="general", message=" \t ")

        with self.assertRaises(ValidationError):
            FeedbackCreateRequest(category="general", message="Hello\x00world")


class FeedbackRouteTests(unittest.TestCase):
    def test_submission_uses_authenticated_user_and_stores_unread_feedback(self):
        inserted_id = ObjectId()
        collection = Mock()
        collection.insert_one.return_value = Mock(inserted_id=inserted_id)
        current_user = {
            "_id": ObjectId(),
            "name": "Research User",
            "email": "research@example.com",
        }

        with patch.object(feedback, "feedback_collection", collection):
            response = feedback.submit_feedback(
                FeedbackCreateRequest(
                    category="suggestion",
                    message="Add source filters",
                ),
                current_user,
            )

        stored = collection.insert_one.call_args.args[0]
        self.assertEqual(stored["user_id"], str(current_user["_id"]))
        self.assertEqual(stored["user_email"], current_user["email"])
        self.assertEqual(stored["message"], "Add source filters")
        self.assertFalse(stored["is_read"])
        self.assertIsNone(stored["read_at"])
        self.assertEqual(response["feedback_id"], str(inserted_id))

    def test_notification_response_uses_database_unread_count(self):
        feedback_record = {
            "_id": ObjectId(),
            "user_name": "Research User",
            "user_email": "research@example.com",
            "category": "general",
            "message": "Useful workspace",
            "created_at": datetime.now(timezone.utc),
            "is_read": False,
        }
        collection = Mock()
        collection.count_documents.return_value = 3
        collection.find.return_value.sort.return_value.limit.return_value = [
            feedback_record
        ]

        with patch.object(feedback, "feedback_collection", collection):
            response = feedback.get_admin_feedback_notifications()

        self.assertEqual(response["unread_count"], 3)
        self.assertEqual(len(response["notifications"]), 1)
        self.assertEqual(
            response["notifications"][0]["id"],
            str(feedback_record["_id"]),
        )

    def test_mark_read_updates_feedback_and_read_timestamp(self):
        feedback_id = ObjectId()
        stored_feedback = {
            "_id": feedback_id,
            "user_name": "Research User",
            "category": "bug_report",
            "message": "Unexpected error",
            "created_at": datetime.now(timezone.utc),
            "is_read": False,
            "read_at": None,
        }
        collection = Mock()
        collection.find_one.return_value = stored_feedback

        with patch.object(feedback, "feedback_collection", collection):
            response = feedback.mark_admin_feedback_read(str(feedback_id))

        collection.update_one.assert_called_once()
        self.assertTrue(response["feedback"]["is_read"])
        self.assertIsNotNone(response["feedback"]["read_at"])

    def test_mark_read_rejects_invalid_and_missing_ids(self):
        with self.assertRaises(HTTPException) as invalid_id:
            feedback.mark_admin_feedback_read("not-an-object-id")
        self.assertEqual(invalid_id.exception.status_code, 400)

        collection = Mock()
        collection.find_one.return_value = None
        with patch.object(feedback, "feedback_collection", collection):
            with self.assertRaises(HTTPException) as missing_record:
                feedback.mark_admin_feedback_read(str(ObjectId()))
        self.assertEqual(missing_record.exception.status_code, 404)

    def test_admin_routes_use_the_existing_admin_dependency(self):
        protected_routes = [
            route
            for route in feedback.admin_router.routes
            if isinstance(route, APIRoute)
        ]
        self.assertEqual(len(protected_routes), 3)
        for route in protected_routes:
            dependencies = [dependency.call for dependency in route.dependant.dependencies]
            self.assertIn(get_current_admin, dependencies)

        submission_route = next(
            route
            for route in feedback.router.routes
            if isinstance(route, APIRoute)
        )
        dependencies = [
            dependency.call
            for dependency in submission_route.dependant.dependencies
        ]
        self.assertIn(get_current_user, dependencies)

    def test_admin_feedback_endpoints_reject_missing_and_non_admin_sessions(self):
        application = FastAPI()
        application.include_router(feedback.admin_router)
        client = TestClient(application)

        self.assertEqual(
            client.get("/admin/feedback").status_code,
            401,
        )

        application.dependency_overrides[get_current_user] = lambda: {
            "role": "user"
        }
        self.assertEqual(
            client.get("/admin/feedback/notifications").status_code,
            403,
        )

    def test_feedback_submission_to_admin_read_flow_over_http(self):
        application = FastAPI()
        application.include_router(feedback.router)
        application.include_router(feedback.admin_router)

        def authenticate_request(request: Request):
            authorization = request.headers.get("authorization", "")
            if authorization == "Bearer user-session":
                return {
                    "_id": ObjectId(),
                    "name": "Research User",
                    "email": "research@example.com",
                    "role": "user",
                }
            if authorization == "Bearer admin-session":
                return {
                    "_id": ObjectId(),
                    "name": "Workspace Admin",
                    "email": "admin@example.com",
                    "role": "admin",
                }
            raise HTTPException(status_code=401, detail="Authentication required")

        application.dependency_overrides[get_current_user] = authenticate_request
        collection = InMemoryFeedbackCollection()
        client = TestClient(application)

        with patch.object(feedback, "feedback_collection", collection):
            submitted = client.post(
                "/feedback/",
                headers={"Authorization": "Bearer user-session"},
                json={
                    "category": "bug_report",
                    "message": "The source list did not load.",
                },
            )
            self.assertEqual(submitted.status_code, 200)

            notification = client.get(
                "/admin/feedback/notifications",
                headers={"Authorization": "Bearer admin-session"},
            )
            self.assertEqual(notification.status_code, 200)
            self.assertEqual(notification.json()["unread_count"], 1)

            feedback_id = submitted.json()["feedback_id"]
            read_result = client.patch(
                f"/admin/feedback/{feedback_id}/read",
                headers={"Authorization": "Bearer admin-session"},
            )
            self.assertEqual(read_result.status_code, 200)
            self.assertTrue(read_result.json()["feedback"]["is_read"])

            updated_notification = client.get(
                "/admin/feedback/notifications",
                headers={"Authorization": "Bearer admin-session"},
            )
            self.assertEqual(updated_notification.json()["unread_count"], 0)

            denied = client.get(
                "/admin/feedback",
                headers={"Authorization": "Bearer user-session"},
            )
            self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
