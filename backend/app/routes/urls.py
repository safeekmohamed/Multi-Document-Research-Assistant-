from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.auth.jwt import (
    get_current_user,
)
from app.schemas.url import (
    URLRequest,
)
from app.urls.url_service import (
    add_url_source,
    list_user_urls,
    search_web,
)


router = APIRouter(
    prefix="/urls",
    tags=["URLs"],
)


@router.post("/add")
def add_url(
    data: URLRequest,
    current_user: dict = Depends(
        get_current_user
    ),
):
    try:
        return add_url_source(
            user_id=str(
                current_user["_id"]
            ),
            url=str(data.url),
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=(
                f"URL processing failed: "
                f"{error}"
            ),
        )


@router.get("/search")
def web_search(
    query: str,
    current_user: dict = Depends(
        get_current_user
    ),
):
    try:
        return {
            "query": query,
            "results": search_web(
                query
            ),
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


@router.get("/")
def get_urls(
    current_user: dict = Depends(
        get_current_user
    ),
):
    return {
        "urls": list_user_urls(
            str(current_user["_id"])
        )
    }