import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import get_current_user
from app.routes.history import router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs.sort(
            key=lambda item: item.get(field) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    def __iter__(self):
        return iter(self.docs)


class TestHistoryRoutes(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

        self.user_id = str(ObjectId())
        self.other_user_id = str(ObjectId())

        self.mock_user = {
            "_id": ObjectId(self.user_id),
            "email": "user@example.com",
            "name": "Test User",
        }

        self.app.dependency_overrides[get_current_user] = lambda: self.mock_user

    def tearDown(self):
        self.app.dependency_overrides.clear()

    @patch("app.routes.history.conversations_collection")
    def test_get_conversations_user_scoped(self, mock_conversations):
        conv_id = ObjectId()
        mock_conversations.find.return_value = MockCursor([
            {
                "_id": conv_id,
                "user_id": self.user_id,
                "title": "Research Session",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ])

        response = self.client.get("/history/conversations")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["conversations"]), 1)
        self.assertEqual(data["conversations"][0]["id"], str(conv_id))
        mock_conversations.find.assert_called_once_with({"user_id": self.user_id})

    @patch("app.routes.history.messages_collection")
    @patch("app.routes.history.conversations_collection")
    def test_history_preserves_source_attribution_fields(
        self,
        mock_conversations,
        mock_messages,
    ):
        conversation_id = str(ObjectId())
        searched_files = [{
            "filename": "Safeek Resume.pdf",
            "source_id": "safeek-source",
            "source_type": "file",
        }]
        mock_conversations.find_one.return_value = {
            "_id": ObjectId(conversation_id),
            "user_id": self.user_id,
            "title": "Resume question",
        }
        mock_messages.find.return_value = MockCursor([{
            "_id": ObjectId(),
            "role": "assistant",
            "content": "Java is listed.",
            "citations": [{
                "filename": "Safeek Resume.pdf",
                "source_id": "safeek-source",
                "pages": [2],
            }],
            # Older messages without a dedicated sources field remain
            # renderable from their persisted citations.
            "searched_files": searched_files,
            "source_attribution_version": 1,
            "attachments": [],
            "created_at": datetime.now(timezone.utc),
        }])

        response = self.client.get(
            f"/history/conversations/{conversation_id}"
        )
        self.assertEqual(response.status_code, 200)
        message = response.json()["messages"][0]
        self.assertEqual(message["searched_files"], searched_files)
        self.assertEqual(message["source_attribution_version"], 1)
        self.assertEqual(message["citations"][0]["pages"], [2])
        self.assertEqual(message["sources"][0]["source_id"], "safeek-source")

    @patch("app.routes.history.messages_collection")
    @patch("app.routes.history.conversations_collection")
    def test_delete_conversation_success(self, mock_conversations, mock_messages):
        conv_id = str(ObjectId())
        mock_conversations.delete_one.return_value = Mock(deleted_count=1)
        mock_messages.delete_many.return_value = Mock(deleted_count=3)

        response = self.client.delete(f"/history/conversations/{conv_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["message"], "Conversation deleted successfully")
        self.assertEqual(data["conversation_id"], conv_id)

        mock_conversations.delete_one.assert_called_once_with({
            "_id": ObjectId(conv_id),
            "user_id": self.user_id,
        })
        mock_messages.delete_many.assert_called_once_with({
            "conversation_id": conv_id,
            "user_id": self.user_id,
        })

    @patch("app.routes.history.conversations_collection")
    def test_delete_conversation_not_found(self, mock_conversations):
        conv_id = str(ObjectId())
        mock_conversations.delete_one.return_value = Mock(deleted_count=0)

        response = self.client.delete(f"/history/conversations/{conv_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Conversation not found")

    def test_delete_conversation_invalid_id(self):
        response = self.client.delete("/history/conversations/invalid-id-format")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid conversation ID")


if __name__ == "__main__":
    unittest.main()
