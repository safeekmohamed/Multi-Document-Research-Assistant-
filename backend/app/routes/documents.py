from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.jwt import get_current_user
from app.documents.document_service import (
    list_user_documents,
    process_uploaded_document,
    delete_user_document,
)
router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(
        description="Upload one or more PDF, DOCX, or TXT files"
    ),
    current_user: dict = Depends(get_current_user),
):
    results = []

    for file in files:
        try:
            content = await file.read()

            result = process_uploaded_document(
                user_id=str(current_user["_id"]),
                filename=file.filename or "document",
                content=content,
            )

            results.append(result)

        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            )

        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Document processing failed: {error}",
            )

    return {
        "message": "Documents processed successfully",
        "documents": results,
    }


@router.get("/")
def get_documents(
    current_user: dict = Depends(get_current_user),
):
    return {
        "documents": list_user_documents(
            str(current_user["_id"])
        )
    }
@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        document = delete_user_document(
            user_id=str(current_user["_id"]),
            document_id=document_id,
        )

        return {
            "message": "Document deleted successfully",
            "document": {
                "id": str(document["_id"]),
                "filename": document.get(
                    "filename",
                    "",
                ),
            },
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Document deletion failed: {error}",
        )