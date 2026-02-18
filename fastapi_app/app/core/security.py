import os
from fastapi import Header, HTTPException, status

def verify_internal_key(
    x_internal_key: str = Header(None)
):
    if x_internal_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Internal-Key header missing",
        )

    if x_internal_key != os.getenv("FASTAPI_INTERNAL_KEY"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal key",
        )
