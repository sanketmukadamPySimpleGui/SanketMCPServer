import secrets
import base64
import binascii
from fastapi import Request, WebSocket, status, Depends, HTTPException
from fastapi.security import HTTPBasicCredentials

from users import USERS

ACCESS_TOKEN_COOKIE_NAME = "mcp_access_token"

def _verify_user(credentials: HTTPBasicCredentials) -> bool:
    """Core logic to verify username and password against our user list."""
    if not credentials.username or not credentials.password:
        return False

    correct_password = USERS.get(credentials.username)
    if not correct_password:
        return False

    return secrets.compare_digest(
        correct_password.encode("utf8"), credentials.password.encode("utf8")
    )

def get_username_from_cookie(request: Request) -> str | None:
    """Dependency to get username from a session cookie."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if token and token in USERS:
        return token
    return None

def get_current_user(username: str | None = Depends(get_username_from_cookie)) -> str:
    """
    A dependency that requires a user to be authenticated via cookie.
    Raises HTTP 401 if the user is not authenticated.
    """
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
        )
    return username


async def get_username_from_ws_cookie(websocket: WebSocket) -> str | None:
    """
    Performs authentication for a WebSocket connection by reading the session cookie.
    Returns the username if successful, otherwise None.
    """
    token = websocket.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if token and token in USERS:
        return token
    return None