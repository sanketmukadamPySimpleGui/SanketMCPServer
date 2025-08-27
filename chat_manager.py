import asyncio
import json
import logging
from types import SimpleNamespace

from fastapi import WebSocket

from mcp import ClientSession, types
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# --- Helper Functions (moved from clients.py) ---

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


def _format_tool_result_for_llm(tool_result: types.CallToolResult) -> str:
    """
    Formats the result of an MCP tool call into a JSON string suitable for the LLM.
    """
    if tool_result.isError:
        error_content = "Tool call failed with an unknown error."
        if tool_result.content and isinstance(tool_result.content[0], types.TextContent):
            error_content = tool_result.content[0].text
        return json.dumps({"error": error_content})

    if tool_result.structuredContent is not None:
        return json.dumps(tool_result.structuredContent)

    if tool_result.content:
        text_parts = [
            block.text for block in tool_result.content if isinstance(block, types.TextContent)
        ]
        return json.dumps("".join(text_parts))

    return json.dumps("")


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
        tool_content = _format_tool_result_for_llm(tool_result)

        return {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "content": tool_content,
        }

    return await asyncio.gather(*(call_mcp_tool(tc) for tc in tool_calls))


# --- ChatManager Class ---

class ChatManager:
    def __init__(
        self,
        websocket: WebSocket,
        mcp_session: ClientSession,
        openai_client: AsyncOpenAI,
        ollama_client: AsyncOpenAI,
        openai_model: str,
        openai_tools: list[dict],
    ):
        self.websocket = websocket
        self.mcp_session = mcp_session
        self.openai_client = openai_client
        self.ollama_client = ollama_client
        self.openai_model = openai_model
        self.openai_tools = openai_tools
        self.messages = self._get_initial_messages()

    def _get_initial_messages(self) -> list[dict]:
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
        return [{"role": "system", "content": system_prompt}]

    async def handle_message(self, payload: dict):
        user_message = payload.get("text")
        use_mcp = payload.get("use_mcp", True)
        llm_provider = payload.get("llm_provider", "openai")
        llm_model = payload.get("llm_model")
        db_connection_name = payload.get("db_connection_name")

        if not user_message:
            return

        self.messages.append({"role": "user", "content": user_message})

        # This loop handles a single conversational turn, which may involve
        # multiple back-and-forths with the LLM if tools are used.
        while True:
            if llm_provider == "ollama":
                client_to_use = self.ollama_client
                model_to_use = llm_model or "llama3.1:latest"
            else:
                client_to_use = self.openai_client
                model_to_use = self.openai_model

            api_params = {
                "model": model_to_use,
                "messages": self.messages,
                "stream": True,
            }

            if use_mcp:
                api_params["tools"] = self.openai_tools
                api_params["tool_choice"] = "auto"

            logger.info(f"Making API call to '{client_to_use.base_url}' with model '{model_to_use}'")
            try:
                stream = await client_to_use.chat.completions.create(**api_params)
            except Exception as api_error:
                logger.error(f"LLM API call to '{client_to_use.base_url}' failed.", exc_info=True)
                await self.websocket.send_text(f"Error from LLM provider: {api_error}")
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
                self.messages.append({"role": "assistant", "content": None, "tool_calls": aggregated_tool_calls})
                tool_outputs = await _handle_tool_calls(
                    self.websocket, final_tool_calls, self.mcp_session, db_connection_name
                )
                self.messages.extend(tool_outputs)
                continue
            else:
                await self.websocket.send_text(full_response)
                self.messages.append({"role": "assistant", "content": full_response})
                break