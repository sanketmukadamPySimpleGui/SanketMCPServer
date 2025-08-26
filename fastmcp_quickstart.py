"""
FastMCP quickstart example.

Run MCP server:
    uv run python fastmcp_quickstart.py
"""

import os
import platform
import subprocess
import sqlite3
import psutil
import sys
from typing import Any
from datetime import datetime

import httpx
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from database import DatabaseManager
from starlette.requests import Request
from starlette.responses import HTMLResponse

import logging
logging.basicConfig(level=logging.INFO)
load_dotenv()

# --- API Key Setup ---
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
if not OPENWEATHERMAP_API_KEY:
    logging.warning(
        "OPENWEATHERMAP_API_KEY not found in .env file. The weather tool will be disabled."
    )

# Create an MCP server
mcp = FastMCP("Demo")

# --- Database Setup ---
db_manager = DatabaseManager()
db_manager.connect_all()


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool()
def get_current_datetime() -> str:
    """Gets the current date and time in ISO format."""
    return datetime.now().isoformat()


@mcp.tool()
def list_files(path: str = ".") -> list[str]:
    """Lists files and directories at a given path."""
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return [f"Error: Directory not found at '{path}'"]
    except NotADirectoryError:
        return [f"Error: Path '{path}' is not a directory"]
    except PermissionError:
        return [f"Error: Permission denied for '{path}'"]


@mcp.tool()
def read_file(path: str) -> str:
    """Reads the entire content of a file and returns it as a string."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found at '{path}'"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Writes the given content to a file, overwriting it if it exists."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{path}'"
    except Exception as e:
        return f"Error writing to file: {e}"


@mcp.tool()
def run_shell_command(command: str) -> str:
    """
    Executes a shell command and returns its output.
    WARNING: This tool can execute any command and has the potential to be dangerous.
    Use with caution, especially in a non-local environment.
    """
    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True, timeout=30
        )
        output = f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}"
        return output
    except subprocess.CalledProcessError as e:
        return f"Command failed with exit code {e.returncode}:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {e}"


@mcp.tool()
def get_system_usage() -> dict[str, str]:
    """Returns the current system CPU and memory usage."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    return {
        "cpu_usage": f"{cpu_percent}%",
        "memory_usage": f"{memory_info.percent}%",
        "available_memory": f"{memory_info.available / (1024**3):.2f} GB",
    }


@mcp.tool()
async def get_current_weather(city: str, state_code: str | None = None, country_code: str | None = None) -> dict[str, Any]:
    """
    Gets the current weather for a given city.
    For US locations, providing the state_code is recommended for accuracy.
    For non-US locations, providing the country_code is recommended.
    Example: get_current_weather(city="London", country_code="GB")
    """
    if not OPENWEATHERMAP_API_KEY:
        return {"error": "Weather API key is not configured on the server."}

    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    weather_url = "https://api.openweathermap.org/data/2.5/weather"

    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Geocoding to get lat/lon
            location_parts = [city]
            if state_code:
                location_parts.append(state_code)
            if country_code:
                location_parts.append(country_code)
            location_query = ",".join(location_parts)

            geo_params = {"q": location_query, "limit": 1, "appid": OPENWEATHERMAP_API_KEY}
            geo_response = await client.get(geo_url, params=geo_params)
            logging.info(f"Geocoding API call to: {geo_response.url}")
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            logging.info(f"Geocoding API response: {geo_data}")

            if not geo_data:
                logging.warning(f"Geocoding failed for city: '{city}'. No location found.")
                return {"error": f"City '{city}' not found."}

            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]

            # Step 2: Get weather using lat/lon
            weather_params = {"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"}
            weather_response = await client.get(weather_url, params=weather_params)
            logging.info(f"Weather API call to: {weather_response.url}")
            weather_response.raise_for_status()
            data = weather_response.json()
            logging.info(f"Weather API response: {data}")

            temp_c = data["main"]["temp"]
            temp_f = (temp_c * 9/5) + 32

            result_dict = {
                "location": data["name"],
                "description": data["weather"][0]["description"],
                "temperature": f"{temp_c:.1f}°C ({temp_f:.1f}°F)",
                "humidity": f"{data['main']['humidity']}%",
                "wind_speed": f"{data['wind']['speed']} m/s",
            }
            logging.info(f"Weather tool returning: {result_dict}")
            return result_dict
    except httpx.HTTPStatusError as e:
        logging.error(f"Weather API HTTP error: {e.response.status_code} - {e.response.text}", exc_info=True)
        if e.response.status_code == 401:
            return {"error": "Invalid Weather API key."}
        return {"error": f"API error: {e.response.status_code}"}
    except Exception as e:
        logging.error(f"Weather tool error: {e}", exc_info=True)
        return {"error": f"An unexpected error occurred: {str(e)}"}


# --- Database Tools ---

@mcp.tool()
def list_database_connections() -> dict[str, Any]:
    """Lists the names of all available database connections."""
    return {"connections": db_manager.list_connections()}

@mcp.tool()
def list_tables(db_connection_name: str) -> dict[str, Any]:
    """Lists all tables (for SQL) or collections (for NoSQL) in the specified database."""
    connector = db_manager.get_connector(db_connection_name)
    if not connector:
        return {"error": f"Database connection '{db_connection_name}' not found."}
    return {"tables_or_collections": connector.list_tables()}

@mcp.tool()
def get_table_schema(db_connection_name: str, collection_name: str) -> str:
    """Returns the schema of a specific table (for SQL) or a sample document (for NoSQL)."""
    connector = db_manager.get_connector(db_connection_name)
    if not connector:
        return f"Error: Database connection '{db_connection_name}' not found."
    return connector.get_table_schema(collection_name)

@mcp.tool()
def run_sql_query(db_connection_name: str, sql_query: str) -> dict[str, Any]:
    """
    Executes a read-only SQL query against a SQL database.
    Use this for connections that support SQL.
    """
    connector = db_manager.get_connector(db_connection_name)
    if not connector:
        return {"error": f"Database connection '{db_connection_name}' not found."}
    return connector.run_sql_query(sql_query)

@mcp.tool()
def find_documents(db_connection_name: str, collection_name: str, filter: dict, projection: dict | None = None, limit: int = 50) -> dict[str, Any]:
    """
    Finds documents in a MongoDB collection that match a given filter.
    Use this for MongoDB database connections.
    'filter' is a standard MongoDB query filter document.
    'projection' is an optional document to specify which fields to include or exclude.
    """
    connector = db_manager.get_connector(db_connection_name)
    if not connector:
        return {"error": f"Database connection '{db_connection_name}' not found."}
    return connector.find_documents(collection_name, filter, projection, limit)

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"


@mcp.resource("resource://system/info")
def system_info() -> dict[str, str]:
    """Provides basic system information."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": sys.version,
    }


# Add a prompt
@mcp.prompt()
def greet_user(name: str, style: str = "friendly") -> str:
    """Generate a greeting prompt"""
    styles = {
        "friendly": "Please write a warm, friendly greeting",
        "formal": "Please write a formal, professional greeting",
        "casual": "Please write a casual, relaxed greeting",
    }

    return f"{styles.get(style, styles['friendly'])} for someone named {name}."


@mcp.prompt()
def summarize_text(text: str) -> str:
    """Generate a prompt to summarize the given text."""
    return f"Please provide a concise summary of the following text:\n\n---\n{text}\n---"


@mcp.prompt()
def translate_text(text: str, target_language: str) -> str:
    """Generate a prompt to translate text to a target language."""
    return f"Translate the following text to {target_language}:\n\n---\n{text}\n---"


# Add a root path to serve a simple HTML page.
# By default, the SSE transport does not serve anything at the root path ("/"),
# which is why you see a "404 Not Found" error in the browser.
@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def root(request: Request) -> HTMLResponse:
    """A simple landing page to confirm the server is running."""
    return HTMLResponse(
        """
        <html>
            <head><title>MCP Server</title></head>
            <body>
                <h1>✅ MCP Server is running!</h1>
                <p>This is a backend server designed to be used with an MCP client. The SSE endpoint is at <code>/sse</code>.</p>
            </body>
        </html>
        """
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the FastMCP Demo Server.")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"], help="The transport protocol to use.")
    parser.add_argument("--host", default=None, help="Host to bind the server to (overrides FASTMCP_HOST).")
    parser.add_argument("--port", default=None, type=int, help="Port to bind the server to (overrides FASTMCP_PORT).")
    cli_args = parser.parse_args()

    # Override settings from CLI arguments if they are provided
    if cli_args.host:
        mcp.settings.host = cli_args.host
    if cli_args.port:
        mcp.settings.port = cli_args.port

    # The `mcp.run()` method is a synchronous function that starts the server.
    # By default, it uses the "stdio" transport, which communicates over the
    # terminal's standard input and output. This is why it appears to hang.
    # To run it as an HTTP server, you can specify the "sse" transport.
    mcp.run(transport=cli_args.transport)
