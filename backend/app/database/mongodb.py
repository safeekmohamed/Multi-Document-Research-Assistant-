from pymongo import MongoClient
from pymongo.server_api import ServerApi

from app.core.config import settings


client = MongoClient(
    settings.MONGODB_URI,
    server_api=ServerApi("1"),
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000,
    retryWrites=True,
)

database = client[settings.DATABASE_NAME]


users_collection = database["users"]
otp_collection = database["otp"]
documents_collection = database["documents"]
conversations_collection = database["conversations"]
messages_collection = database["messages"]


def check_mongodb_connection() -> bool:
    try:
        client.admin.command("ping")
        return True

    except Exception as error:
        print(f"MongoDB connection check failed: {error}")
        return False


def initialize_database():
    try:
        # First confirm MongoDB connection
        client.admin.command("ping")

        # Users
        users_collection.create_index(
            "email",
            unique=True,
        )

        # OTP expiry
        otp_collection.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
        )

        # Documents
        documents_collection.create_index(
            "user_id",
        )

        # Conversations
        conversations_collection.create_index(
            "user_id",
        )

        # Messages
        messages_collection.create_index(
            "conversation_id",
        )

        print("MongoDB indexes initialized successfully.")

    except Exception as error:
        print(
            f"MongoDB initialization warning: {error}"
        )