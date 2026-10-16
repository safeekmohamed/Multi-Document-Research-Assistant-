from fastapi import APIRouter, Depends

from app.auth.jwt import get_current_user


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/me")
def get_me(
    current_user: dict = Depends(
        get_current_user
    ),
):
    return {
        "id": str(
            current_user["_id"]
        ),
        "name": current_user.get(
            "name",
            "",
        ),
        "email": current_user.get(
            "email",
            "",
        ),
        "is_verified": current_user.get(
            "is_verified",
            False,
        ),
        "role": current_user.get(
            "role",
            "user",
        ),
    }