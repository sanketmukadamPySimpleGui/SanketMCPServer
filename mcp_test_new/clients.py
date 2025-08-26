# FILE: /mcp_test_new/mcp_test_new/clients.py
"""
Web-based chatbot client for MCP using OpenAI API.

To run:
1. Create a `.env` file with:
   OPENAI_API_KEY=your_key_here
   # Optional: OPENAI_MODEL=gpt-4-turbo
2. Install deps: `pip install fastapi uvicorn python-dotenv mcp openai`
3. Run: `uvicorn clients:app --reload`
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic_settings import BaseSettings

from openai import AsyncOpenAI
from mcp import ClientSession, types
from mcp.client.sse import sse_client

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


async def _create_mcp_session_stack():
    """Creates and initializes an MCP session and its associated exit stack."""
    stack = AsyncExitStack()
    try:
        mcp_client_cm = sse_client(settings.MCP_SERVER_URL)
        read, write = await stack.enter_async_context(mcp_client_cm)
        mcp_session_cm = ClientSession(read, write)
        mcp_session = await stack.enter_async_context(mcp_session_cm)
        init_result = await mcp_session.initialize()
        return mcp_session, init_result.serverInfo, stack
    except Exception:
        await stack.aclose()  # Clean up if initialization fails
        raise

# --- Lifespan handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the client."""
    app.state.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    app.state.ollama_client = AsyncOpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")

    logger.info("Client application started. LLM clients configured.")

    yield

    logger.info("Application shutting down.")


# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=current_dir / "static"), name="static")


@app.get("/")
async def get_index():
    """Serve main chat page."""
    try:
        with open(current_dir / "templates" / "index.html") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/api/db-connections")
async def get_db_connections():
    """Return a list of available database connections."""
    try:
        mcp_session, _, stack = await _create_mcp_session_stack()
        async with stack:
            result = await mcp_session.call_tool(name="list_database_connections")
            connections = result.structuredContent.get("connections", []) if not result.isError else []
            return {"connections": connections}
    except Exception as e:
        logger.error(f"Failed to get DB connections: {e}", exc_info=True)
        return {"connections": [], "error": str(e)}


@app.get("/api/ollama-models")
async def get_ollama_models():
    """Fetch the list of available models from the local Ollama server."""
    if not settings.OLLAMA_BASE_URL:
        return {"models": []}

    ollama_api_url = settings.OLLAMA_BASE_URL.replace("/v1", "") + "/api/tags"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ollama_api_url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            models = [model.get("name") for model in data.get("models", []) if model.get("name")]
            return {"models": sorted(models)}
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.error(f"Could not connect to Ollama at {ollama_api_url}: {e}")
        return {"models": [], "error": f"Could not connect to Ollama. Is it running and accessible at {settings.OLLAMA_BASE_URL}?"}

@app.get("/api/server-info")
async def get_server_info():
    """Return information about the connected MCP server and its components."""
    try:
        mcp_session, server_info, stack = await _create_mcp_session_stack()
        async with stack:
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


def format_mcp_tools_for_openai(mcp_tools: list[types.Tool]) -> list[dict]:
    """Convert MCP tools into OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


async def _handle_tool_calls(
    websocket: WebSocket, tool_calls: list, session: ClientSession, db_connection_name: str | None
) -> list[dict]:
    """Executes MCP tool calls and returns results formatted for OpenAI."""

    async def call_mcp_tool(tool_call):
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": f"Error: Invalid arguments for {tool_name}",
            }

        if tool_name in ["list_tables", "get_table_schema", "run_sql_query", "find_documents"] and db_connection_name:
            tool_args["db_connection_name"] = db_connection_name

        await websocket.send_text(f"🤖 Calling `{tool_name}` with {tool_args}")
        tool_result = await session.call_tool(name=tool_name, arguments=tool_args)

        if tool_result.isError:
            error_content = "Tool call failed with an unknown error."
            if tool_result.content and isinstance(tool_result.content[0], types.TextContent):
                error_content = tool_result.content[0].text
            tool_content = json.dumps({"error": error_content})
        else:
            if tool_result.structuredContent is not None:
                tool_content = json.dumps(tool_result.structuredContent)
            elif tool_result.content:
                text_parts = [
                    block.text
                    for block in tool_result.content
                    if isinstance(block, types.TextContent)
                ]
                tool_content = json.dumps("".join(text_parts))
            else:
                tool_content = json.dumps("")

        return {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "content": tool_content,
        }

    return await asyncio.gather(*(call_mcp_tool(tc) for tc in tool_calls))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket chat endpoint."""
    await websocket.accept()
    openai_client = getattr(app.state, "openai_client", None)
    ollama_client = getattr(app.state, "ollama_client", None)

    if not openai_client or not ollama_client:
        await websocket.send_text("Error: A required client is not initialized.")
        await websocket.close()
        return

    try:
        mcp_session, _, stack = await _create_mcp_session_stack()
    except Exception as e:
        logger.error(f"Failed to establish MCP session for WebSocket: {e}", exc_info=True)
        await websocket.send_text(f"Error: Could not connect to the backend agent server. Please try refreshing.")
        await websocket.close(code=1011, reason="MCP Connection Failed")
        return

    async with stack:
        try:
            tools_result = await mcp_session.list_tools()
            openai_tools = format_mcp_tools_for_openai(tools_result.tools)

            system_prompt = """You are an expert data analyst assistant. Your primary goal is to answer questions by querying a database.

You have access to different database connections, which can be either SQL or MongoDB. You MUST adapt your strategy based on the tools available and their descriptions.

**Your procedure for EVERY database question is:**
1.  **Discover Structure**: Use `list_tables()` to see available tables/collections. Then, for each relevant one, use `get_table_schema()` to understand its fields.
2.  **Choose the Right Tool**:
    -   If you need to query a relational (SQL) database, you MUST use the `run_sql_query` tool.
    -   If you need to query a document (MongoDB) database, you MUST use the `find_documents` tool with a valid JSON filter.
3.  **Construct & Execute**: Based on the schema, construct a precise query (either SQL or a MongoDB filter) and execute it with the correct tool. DO NOT guess column or field names.
4.  **Synthesize Answer**: Use the data returned from the tool to formulate a complete, natural-language answer for the user.

For any non-database questions, you must answer directly without using any tools."""
            messages = [{"role": "system", "content": system_prompt}]

            while True:
                payload = await websocket.receive_json()
                user_message = payload.get("text")
                use_mcp = payload.get("use_mcp", True)
                llm_provider = payload.get("llm_provider", "openai")
                llm_model = payload.get("llm_model")
                db_connection_name = payload.get("db_connection_name")

                if not user_message:
                    continue

                messages.append({"role": "user", "content": user_message})

                while True:
                    if llm_provider == "ollama":
                        client_to_use = ollama_client
                        model_to_use = llm_model or "llama3.1:latest"
                    else:
                        client_to_use = openai_client
                        model_to_use = settings.OPENAI_MODEL

                    api_params = {
                        "model": model_to_use,
                        "messages": messages,
                        "stream": True,
                    }

                    if use_mcp:
                        api_params["tools"] = openai_tools
                        api_params["tool_choice"] = "auto"

                    logger.info(f"Making API call to '{client_to_use.base_url}' with model '{model_to_use}'")
                    try:
                        stream = await client_to_use.chat.completions.create(**api_params)
                    except Exception as api_error:
                        logger.error(f"LLM API call to '{client_to_use.base_url}' failed.", exc_info=True)
                        await websocket.send_text(f"Error from LLM provider: {api_error}")
                        break

                    full_response = ""
                    aggregated_tool_calls = []

                    async for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_response += delta.content
                        if delta.tool_calls:
                            for tool_call_chunk in delta.tool_calls:
                                if len(aggregated_tool_calls) <= tool_call_chunk.index:
                                    aggregated_tool_calls.append(
                                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                                    )
                                current_tool_call = aggregated_tool_calls[tool_call_chunk.index]
                                if tool_call_chunk.id:
                                    current_tool_call["id"] = tool_call_chunk.id
                                if tool_call_chunk.function:
                                    if tool_call_chunk.function.name:
                                        current_tool_call["function"]["name"] = tool_call_chunk.function.name
                                    if tool_call_chunk.function.arguments:
                                        current_tool_call["function"]["arguments"] += tool_call_chunk.function.arguments

                    if aggregated_tool_calls and use_mcp:
                        final_tool_calls = [json.loads(json.dumps(tc), object_hook=lambda d: SimpleNamespace(**d)) for tc in aggregated_tool_calls]
                        messages.append({"role": "assistant", "content": None, "tool_calls": aggregated_tool_calls})
                        tool_outputs = await _handle_tool_calls(
                            websocket, final_tool_calls, mcp_session, db_connection_name
                        )
                        messages.extend(tool_outputs)
                        continue
                    else:
                        await websocket.send_text(full_response)
                        messages.append({"role": "assistant", "content": full_response})
                        break

        except WebSocketDisconnect:
            logger.info(f"Client {websocket.client} disconnected.")
        except Exception as e:
            logger.error(f"WebSocket error for {websocket.client}: {e}", exc_info=True)
            try:
                await websocket.send_text(f"Error: {e}")
            except Exception:
                pass
            await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("clients:app", host="127.0.0.1", port=8000, reload=True)