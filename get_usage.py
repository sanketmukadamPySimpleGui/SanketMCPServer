import asyncio
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from contextlib import AsyncExitStack

async def main():
    stack = AsyncExitStack()
    try:
        mcp_client_cm = sse_client("http://localhost:8000/sse")
        read, write = await stack.enter_async_context(mcp_client_cm)
        mcp_session_cm = ClientSession(read, write)
        mcp_session = await stack.enter_async_context(mcp_session_cm)
        await mcp_session.initialize()
        result = await mcp_session.call_tool(name="get_system_usage")
        if not result.isError and result.structuredContent:
            print(result.structuredContent)
        else:
            print("Error calling tool")
            if result.content:
                # Check if content is a list and not empty
                if isinstance(result.content, list) and result.content:
                    # Check if the first item has a 'text' attribute
                    if hasattr(result.content[0], 'text'):
                        print(result.content[0].text)
                    else:
                        print(result.content[0])
                else:
                    print(result.content)

    finally:
        await stack.aclose()

if __name__ == "__main__":
    asyncio.run(main())
