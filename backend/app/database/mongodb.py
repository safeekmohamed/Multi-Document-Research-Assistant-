import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

client = MongoClient(
    os.getenv("MONGODB_URI"),
    server_api=ServerApi("1"),
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000,
    retryWrites=True,
)

database = client[
    os.getenv("DATABASE_NAME")
]

users_collection = database["users"]
otp_collection = database["otp"]
documents_collection = database["documents"]
conversations_collection = database["conversations"]
messages_collection = database["messages"]
google_oauth_states_collection = database["google_oauth_states"]
feedback_collection = database["feedback"]

def check_mongodb_connection() -> bool:
    try:
        client.admin.command("ping")
        return True

    except Exception as error:
        print(
            f"MongoDB connection check failed: {error}"
        )
        return False

def initialize_database():
    try:

        client.admin.command("ping")

        users_collection.create_index(
            "email",
            unique=True,
        )

        otp_collection.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
        )

        documents_collection.create_index(
            "user_id",
        )

        conversations_collection.create_index(
            "user_id",
        )

        messages_collection.create_index(
            "conversation_id",
        )

        google_oauth_states_collection.create_index(
            "state_hash",
            unique=True,
        )

        google_oauth_states_collection.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
        )

        feedback_collection.create_index(
            [("created_at", -1)],
        )
        feedback_collection.create_index(
            [("is_read", 1), ("created_at", -1)],
        )

        print(
            "MongoDB indexes initialized successfully."
        )

    except Exception as error:
        print(
            f"MongoDB initialization warning: {error}"
        )
