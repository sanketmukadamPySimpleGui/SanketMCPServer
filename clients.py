"""
Web-based chatbot client for MCP using OpenAI API.

To run:
1. Create a `.env` file with:
   OPENAI_API_KEY=your_key_here
   # Optional: OPENAI_MODEL=gpt-4-turbo
2. Install deps: `uv pip install fastapi uvicorn python-dotenv mcp openai`
3. Run: `uv run uvicorn clients:app --reload`
"""

import asyncio
import json
import logging
import os
from types import SimpleNamespace
from urllib.parse import urlparse, urlunparse
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings
from fastapi.security import HTTPBasicCredentials

from openai import AsyncOpenAI
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from auth import _verify_user, get_username_from_cookie, get_username_from_ws_cookie, get_current_user, ACCESS_TOKEN_COOKIE_NAME
from chat_manager import ChatManager, format_mcp_tools_for_openai

# --- Setup ---
load_dotenv()

class Settings(BaseSettings):
    """Manages application settings, loaded from .env file."""
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4-turbo"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    MCP_SERVER_URL: str = "http://127.0.0.1:8001/sse"

settings = Settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

current_dir = Path(__file__).parent


@asynccontextmanager
async def managed_mcp_session():
    """
    Provides an MCP session within a context, handling setup and teardown.
    Yields a tuple of (session, server_info).
    Raises an exception on connection failure, to be caught by the caller.
    """
    stack = AsyncExitStack()
    try:
        mcp_client_cm = sse_client(settings.MCP_SERVER_URL)
        read, write = await stack.enter_async_context(mcp_client_cm)
        mcp_session_cm = ClientSession(read, write)
        mcp_session = await stack.enter_async_context(mcp_session_cm)
        init_result = await mcp_session.initialize() # noqa
        yield mcp_session, init_result.serverInfo
    finally:
        await stack.aclose()


# --- Lifespan handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the client."""
    # Setup LLM clients
    app.state.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    app.state.ollama_client = AsyncOpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")

    # The previous check for MCP server connectivity at startup has been removed.
    # It was found to potentially interfere with the Uvicorn event loop.
    # Connectivity is now checked on-demand by each API endpoint.
    logger.info("Client application started. LLM clients configured.")

    yield

    logger.info("Application shutting down.")


# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=current_dir / "static"), name="static")
templates = Jinja2Templates(directory=current_dir / "templates")


@app.get("/health", status_code=status.HTTP_200_OK, include_in_schema=False)
async def health_check():
    """Simple health check endpoint that doesn't require authentication."""
    return {"status": "ok"}


@app.get("/")
async def get_index(request: Request, username: str | None = Depends(get_username_from_cookie)):
    """Serve main chat page."""
    if not username:
        return RedirectResponse("/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request, error: str | None = None):
    """Serves the custom HTML login page."""
    context = {
        "request": request,
        "server_name": "SanketMukadam's MCP Server",
        "error_message": "Invalid username or password." if error else "",
    }
    return templates.TemplateResponse("login.html", context)

@app.post("/login")
async def handle_login(username: str = Form(), password: str = Form()):
    """Handles the login form submission, sets a cookie, and redirects."""
    if not _verify_user(HTTPBasicCredentials(username=username, password=password)):
        return RedirectResponse("/login?error=true", status_code=status.HTTP_303_SEE_OTHER)

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key=ACCESS_TOKEN_COOKIE_NAME, value=username, httponly=True, samesite="lax", secure=True)
    return response

@app.get("/logout")
async def logout(request: Request):
    """Logs the user out by clearing the session cookie."""
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, secure=True, httponly=True, samesite="lax")
    return response

@app.get("/api/db-connections")
async def get_db_connections(username: str = Depends(get_current_user)):
    """Return a list of available database connections."""
    try:
        async with managed_mcp_session() as (mcp_session, _):
            result = await mcp_session.call_tool(name="list_database_connections")
            if not result.isError and result.structuredContent and "connections" in result.structuredContent:
                connections = result.structuredContent.get("connections", [])
            else:
                connections = []
            return {"connections": connections}
    except Exception as e:
        logger.error(f"Failed to get DB connections: {e}", exc_info=True)
        return {"connections": [], "error": str(e)}


@app.get("/api/ollama-models")
async def get_ollama_models(username: str = Depends(get_current_user)):
    """Fetch the list of available models from the local Ollama server."""
    if not settings.OLLAMA_BASE_URL:
        return {"models": []}

    # The base URL is like http://host.docker.internal:11434/v1, we need http://.../api/tags
    # Use urlparse for a more robust way to construct the API URL.
    parsed_url = urlparse(settings.OLLAMA_BASE_URL)
    tags_path = "/api/tags"
    ollama_api_url = urlunparse((parsed_url.scheme, parsed_url.netloc, tags_path, '', '', ''))

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ollama_api_url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            # The API returns a list of models, each with a 'name' field.
            models = [model.get("name") for model in data.get("models", []) if model.get("name")]
            return {"models": sorted(models)}
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.error(f"Could not connect to Ollama at {ollama_api_url}: {e}")
        return {"models": [], "error": f"Could not connect to Ollama. Is it running and accessible at {settings.OLLAMA_BASE_URL}?"}

@app.get("/api/server-info")
async def get_server_info(username: str = Depends(get_current_user)):
    """Return information about the connected MCP server and its components."""
    try:
        async with managed_mcp_session() as (mcp_session, server_info):
            tools_result, resources_result, prompts_result, templates_result = await asyncio.gather(
                mcp_session.list_tools(),
                mcp_session.list_resources(),
                mcp_session.list_prompts(),
                mcp_session.list_resource_templates(),
            )

            all_resources = [res.model_dump() for res in resources_result.resources]
            all_resources.extend(
                {"uri": t.uriTemplate, "name": t.name, "description": t.description, "mimeType": "Template"}
                for t in templates_result.resourceTemplates
            )

            return {
                "server_info": server_info.model_dump(),
                "tools": [tool.model_dump() for tool in tools_result.tools],
                "resources": all_resources,
                "prompts": [prompt.model_dump() for prompt in prompts_result.prompts],
            }
    except Exception as e:
        logger.error(f"Failed to get server info: {e}", exc_info=True)
        return {"server_info": {}, "tools": [], "resources": [], "prompts": [], "error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket chat endpoint."""
    await websocket.accept()

    username = await get_username_from_ws_cookie(websocket)
    if not username:
        logger.warning("WebSocket authentication failed.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    logger.info(f"WebSocket connection authenticated for user: {username}")

    openai_client = getattr(app.state, "openai_client", None)
    ollama_client = getattr(app.state, "ollama_client", None)

    if not openai_client or not ollama_client:
        await websocket.send_text("Error: A required client is not initialized.")
        await websocket.close()
        return

    # Create a new MCP session for each WebSocket connection.
    # This is more robust than sharing a single session.
    try:
        async with managed_mcp_session() as (mcp_session, _):
            if not mcp_session:
                # This case handles if the context manager were to yield None on error.
                # With the current design, it will raise an exception instead, which is caught below.
                raise ConnectionError("Failed to establish MCP session.")

            tools_result = await mcp_session.list_tools()
            openai_tools = format_mcp_tools_for_openai(tools_result.tools)

            chat_manager = ChatManager(
                websocket=websocket,
                mcp_session=mcp_session,
                openai_client=openai_client,
                ollama_client=ollama_client,
                openai_model=settings.OPENAI_MODEL,
                openai_tools=openai_tools,
            )

            while True:
                payload = await websocket.receive_json()
                await chat_manager.handle_message(payload)

    except WebSocketDisconnect:
        logger.info(f"Client {websocket.client} disconnected.")
    except Exception as e:
        # This block now catches both WebSocket errors and MCP connection errors
        logger.error(f"WebSocket error for {websocket.client}: {e}", exc_info=True)
        try:
            await websocket.send_text(f"Error: Could not connect to the backend agent server. Please try refreshing.")
            await websocket.close(code=1011, reason="MCP Connection Failed")
        except Exception:
            # The connection might already be closed, so we pass silently.
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("clients:app", host="127.0.0.1", port=8000, reload=True)
