from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from bson import ObjectId

from app.auth.jwt import (
    get_current_admin,
)

from app.database.mongodb import (
    users_collection,
    documents_collection,
)

from app.services.user_service import (
    block_user,
    unblock_user,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

def serialize_user(
    user: dict,
) -> dict:

    return {
        "id": str(
            user["_id"]
        ),
        "name": user.get(
            "name",
            "",
        ),
        "email": user.get(
            "email",
            "",
        ),
        "is_verified": user.get(
            "is_verified",
            False,
        ),
        "is_blocked": user.get(
            "is_blocked",
            False,
        ),
        "role": user.get(
            "role",
            "user",
        ),
        "created_at": (
            user.get(
                "created_at"
            ).isoformat()
            if user.get(
                "created_at"
            )
            else None
        ),
    }


def find_owner(user_id: str | None) -> dict | None:
    if not user_id or not ObjectId.is_valid(user_id):
        return None

    return users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"name": 1, "email": 1},
    )

@router.get(
    "/overview"
)
def admin_overview(
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    total_users = users_collection.count_documents(
        {}
    )

    total_documents = documents_collection.count_documents(
        {
            "source_type": "file"
        }
    )

    total_urls = documents_collection.count_documents(
        {
            "source_type": "url"
        }
    )

    blocked_users = users_collection.count_documents(
        {
            "is_blocked": True
        }
    )

    return {
        "total_users": total_users,
        "total_documents": total_documents,
        "total_urls": total_urls,
        "blocked_users": blocked_users,
    }

@router.get(
    "/users"
)
def get_users(
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    users = users_collection.find(
        {},
        {
            "password_hash": 0,
        },
    ).sort(
        "created_at",
        -1,
    )

    return {
        "users": [
            serialize_user(user)
            for user in users
        ]
    }

@router.get(
    "/users/{user_id}"
)
def get_user_details(
    user_id: str,
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    from bson import ObjectId

    if not ObjectId.is_valid(
        user_id
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid user ID",
        )

    user = users_collection.find_one(
        {
            "_id": ObjectId(
                user_id
            )
        },
        {
            "password_hash": 0,
        },
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    document_count = documents_collection.count_documents(
        {
            "user_id": user_id,
            "source_type": "file",
        }
    )

    url_count = documents_collection.count_documents(
        {
            "user_id": user_id,
            "source_type": "url",
        }
    )

    return {
        "user": serialize_user(
            user
        ),
        "document_count": document_count,
        "url_count": url_count,
    }

@router.patch(
    "/users/{user_id}/block"
)
def admin_block_user(
    user_id: str,
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    if user_id == str(
        current_admin["_id"]
    ):

        raise HTTPException(
            status_code=400,
            detail="You cannot block your own admin account.",
        )

    try:

        user = block_user(
            user_id
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found or admin account cannot be blocked.",
        )

    return {
        "message": "User blocked successfully",
        "user": serialize_user(
            user
        ),
    }

@router.patch(
    "/users/{user_id}/unblock"
)
def admin_unblock_user(
    user_id: str,
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    try:

        user = unblock_user(
            user_id
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found or admin account cannot be changed.",
        )

    return {
        "message": "User unblocked successfully",
        "user": serialize_user(
            user
        ),
    }

@router.get(
    "/documents"
)
def get_admin_documents(
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    documents = documents_collection.find(
        {
            "source_type": "file"
        },
        {
            "filename": 1,
            "file_type": 1,
            "user_id": 1,
            "created_at": 1,
            "chunk_count": 1,
        },
    ).sort(
        "created_at",
        -1,
    )

    result = []

    for document in documents:

        owner = find_owner(
            document.get("user_id")
        )

        result.append(
            {
                "id": str(
                    document["_id"]
                ),
                "filename": document.get(
                    "filename",
                    "",
                ),
                "file_type": document.get(
                    "file_type",
                    "",
                ),
                "user_id": document.get(
                    "user_id",
                    "",
                ),
                "owner_name": (
                    owner.get(
                        "name",
                        "",
                    )
                    if owner
                    else "Unknown"
                ),
                "owner_email": (
                    owner.get(
                        "email",
                        "",
                    )
                    if owner
                    else ""
                ),
                "created_at": (
                    document.get(
                        "created_at"
                    ).isoformat()
                    if document.get(
                        "created_at"
                    )
                    else None
                ),
                "chunk_count": document.get(
                    "chunk_count",
                    0,
                ),
            }
        )

    return {
        "documents": result
    }

@router.get(
    "/urls"
)
def get_admin_urls(
    current_admin: dict = Depends(
        get_current_admin
    ),
):

    urls = documents_collection.find(
        {
            "source_type": "url"
        },
        {
            "title": 1,
            "filename": 1,
            "source_url": 1,
            "url": 1,
            "user_id": 1,
            "created_at": 1,
        },
    ).sort(
        "created_at",
        -1,
    )

    result = []

    for document in urls:

        user_id = document.get(
            "user_id"
        )
        owner = find_owner(user_id)

        result.append(
            {
                "id": str(
                    document["_id"]
                ),
                "title": (
                    document.get(
                        "title"
                    )
                    or document.get(
                        "filename"
                    )
                    or "Untitled website"
                ),
                "url": (
                    document.get(
                        "source_url"
                    )
                    or document.get(
                        "url"
                    )
                    or ""
                ),
                "user_id": user_id,
                "owner_name": (
                    owner.get(
                        "name",
                        "",
                    )
                    if owner
                    else "Unknown"
                ),
                "owner_email": (
                    owner.get(
                        "email",
                        "",
                    )
                    if owner
                    else ""
                ),
                "created_at": (
                    document.get(
                        "created_at"
                    ).isoformat()
                    if document.get(
                        "created_at"
                    )
                    else None
                ),
            }
        )

    return {
        "urls": result
    }
