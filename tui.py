"""
Textual-based TUI client for MCP.
"""

import anyio
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, TabbedContent, TabPane
from textual.reactive import reactive

from mcp import ClientSession, types
from mcp.shared.metadata_utils import get_display_name


class TuiApp(App[None]):
    """A Textual app to display MCP tools/resources/prompts."""

    TITLE = "MCP Client"
    sub_title = reactive("")

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, session: ClientSession, server_info: types.Implementation):
        super().__init__()
        self.session = session
        self.server_info = server_info

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Tools", id="tools_tab"):
                yield DataTable(id="tools_table", cursor_type="row")
            with TabPane("Resources", id="resources_tab"):
                yield DataTable(id="resources_table", cursor_type="row")
            with TabPane("Prompts", id="prompts_tab"):
                yield DataTable(id="prompts_table", cursor_type="row")
        yield Footer()

    async def on_mount(self) -> None:
        self.sub_title = f"Connected to: {self.server_info.name} v{self.server_info.version}"
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._populate_tools)
            tg.start_soon(self._populate_resources)
            tg.start_soon(self._populate_prompts)

    async def _populate_tools(self) -> None:
        table = self.query_one("#tools_table", DataTable)
        table.add_columns("Tool", "Description")
        table.loading = True
        try:
            tools_result = await self.session.list_tools()
            table.clear()
            if not tools_result.tools:
                table.add_row("No tools found on the server.")
            else:
                for tool in tools_result.tools:
                    table.add_row(get_display_name(tool), tool.description or "", key=tool.name)
        except Exception as e:
            table.clear()
            table.add_row("Error fetching tools", str(e))
        finally:
            table.loading = False

    async def _populate_resources(self) -> None:
        table = self.query_one("#resources_table", DataTable)
        table.add_columns("URI / Template", "Description", "Type")
        table.loading = True
        try:
            static_resources = await self.session.list_resources()
            templates = await self.session.list_resource_templates()
            table.clear()
            if not static_resources.resources and not templates.resourceTemplates:
                table.add_row("No resources/templates found")
            else:
                for r in static_resources.resources:
                    table.add_row(str(r.uri), r.description or "", r.mimeType or "N/A", key=str(r.uri))
                for t in templates.resourceTemplates:
                    table.add_row(t.uriTemplate, t.description or "", "Template", key=t.uriTemplate)
        except Exception as e:
            table.clear()
            table.add_row("Error fetching resources", str(e))
        finally:
            table.loading = False

    async def _populate_prompts(self) -> None:
        table = self.query_one("#prompts_table", DataTable)
        table.add_columns("Prompt", "Description")
        table.loading = True
        try:
            prompts_result = await self.session.list_prompts()
            table.clear()
            if not prompts_result.prompts:
                table.add_row("No prompts found")
            else:
                for prompt in prompts_result.prompts:
                    table.add_row(get_display_name(prompt), prompt.description or "", key=prompt.name)
        except Exception as e:
            table.clear()
            table.add_row("Error fetching prompts", str(e))
        finally:
            table.loading = False

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    from contextlib import AsyncExitStack

    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def main():
        """Sets up the MCP client and runs the TUI app."""
        server_params = StdioServerParameters(
            command="python",
            args=["fastmcp_quickstart.py", "--transport", "stdio"],
            env=None,
        )
        async with AsyncExitStack() as stack:
            mcp_client_cm = stdio_client(server_params)
            read, write = await stack.enter_async_context(mcp_client_cm)

            mcp_session_cm = ClientSession(read, write)
            session = await stack.enter_async_context(mcp_session_cm)
            await session.initialize()

            if session.server_info:
                app = TuiApp(session, session.server_info)
                await app.run_async()

    anyio.run(main)
