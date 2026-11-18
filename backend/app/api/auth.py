from fastapi import APIRouter, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/check", status_code=status.HTTP_204_NO_CONTENT)
def check_access() -> None:
    """Succeed (204) when the request may use the API: the access key is valid, or none
    is configured. Mounted with the access key dependency, which returns 401 otherwise."""
