# Agentic AI Chatbot with a Local MCP Server

## Overview

This project is a Proof-of-Concept (PoC) demonstrating a powerful, agentic AI chatbot. The application features a web-based chat interface that connects to large language models (LLMs) and leverages a local **Model Context Protocol (MCP)** server to execute a wide range of real-world tasks. This architecture allows the AI to go beyond simple text generation and interact with its local environment, databases, and external APIs.

## Features

- **Interactive Web UI**: A clean, modern chat interface built with FastAPI and vanilla JavaScript, protected by a custom login page.
- **Switchable LLM Providers**: Seamlessly switch between OpenAI's cloud models and a locally-run Ollama instance. The list of available Ollama models is detected automatically and populated in the UI.
- **Secure & Containerized**: The entire application stack is containerized with Docker and served securely over HTTPS via an Nginx reverse proxy.
- **Rich Toolset**: The MCP server exposes a comprehensive set of tools for:
  - **Authentication**: A simple, secure login mechanism protects access to the application.
  - **File System Operations**: Listing, reading, and writing files.
  - **System Interaction**: Executing shell commands and checking system resource usage.
  - **Data Analysis**: Querying an in-memory SQLite database with natural language.
-   **Multi-Database Connectivity**: Querying multiple databases (SQLite and MongoDB) with natural language, with the ability to select the target data source from the UI.
  - **External API Calls**: Fetching real-time weather data from the OpenWeatherMap API.
- **Dynamic Tool-Use**: A toggle switch allows the user to enable or disable the agent's ability to use tools, demonstrating the modularity of the MCP integration.

## Architecture

The application consists of three main components that work together to create the agentic experience:

1.  **Web Client (`clients.py`)**: This is the user-facing application and the central orchestrator. It's a FastAPI web server that serves the chat UI. When a user sends a message, the client is responsible for communicating with the selected LLM, managing the conversation history, and invoking the MCP server when the LLM decides to use a tool.

2.  **LLM Provider (OpenAI or Ollama)**: This is the "brain" of the agent. The client sends the conversation history and a description of the available MCP tools to the LLM. The LLM then decides whether to respond with text or to request a tool call to gather more information or perform an action.

3.  **MCP Server (`fastmcp_quickstart.py`)**: This is the "hands" of the agent. It's a local server that exposes a set of capabilities (tools) to the client via the Model Context Protocol. It handles the actual execution of tasks like reading a file, running a SQL query, or calling the weather API.

### The Role of the Model Context Protocol (MCP)

MCP is the standardized communication layer that connects the **Web Client** and the **MCP Server**. It defines how the client can discover the server's capabilities and how it can execute them.

-   **Tool Discovery**: When the client starts, it sends a `tools/list` request to the MCP server. The server responds with a list of all its available tools and their schemas (i.e., their names, descriptions, and required arguments). The client then formats this information to be included in the prompt for the LLM.
-   **Tool Invocation**: When the LLM decides to use a tool, the client sends a `tools/call` request to the MCP server, specifying the tool's name and arguments. The server executes the corresponding function and sends the result back to the client.
-   **Message Format**: All communication between the client and server follows the JSON-RPC standard, ensuring reliable and interoperable message passing.

## Components in Detail

### MCP Server (`fastmcp_quickstart.py`)

This server defines all the capabilities the agent can perform. It currently includes:

#### General Tools
-   `add(a, b)`: Adds two numbers.
-   `get_current_datetime()`: Returns the current date and time.
-   `get_system_usage()`: Returns current CPU and memory usage.

#### File System Tools
-   `list_files(path)`: Lists files and directories at a given path.
-   `read_file(path)`: Reads the content of a specified file.
-   `write_file(path, content)`: Writes content to a specified file.

#### Advanced Tools
-   `run_shell_command(command)`: Executes a shell command. **(Use with caution)**.
-   `get_current_weather(city, ...)`: Fetches real-time weather data from the OpenWeatherMap API.

#### Database Tools
The server initializes and connects to multiple databases to demonstrate the agent's versatility.

**1. Supply Chain & HR Database (In-Memory SQLite)**
-   **Connection Name**: `supply_chain`
-   **Type**: SQL
-   **Description**: An in-memory SQLite database containing two schemas:
    -   A **Supply Chain** schema with tables like `products`, `suppliers`, `warehouses`, and `purchase_orders`.
    -   A **Human Resources** schema with `employees` and `departments` tables.
-   **Tools**: `list_tables`, `get_table_schema`, `run_sql_query`.

**2. Retail Order-to-Cash Database (MongoDB)**
-   **Connection Name**: `retail_otc`
-   **Type**: NoSQL (MongoDB)
-   **Description**: A MongoDB database containing a sample Order-to-Cash schema with collections like `customers`, `products`, and `orders`.
-   **Tools**: `list_tables`, `get_table_schema`, `find_documents`.

### Web Client (`clients.py`)

This script is the heart of the application. Its responsibilities include:

-   Serving the `index.html` and static assets.
-   Managing the WebSocket connection for real-time chat.
-   Maintaining a persistent `ClientSession` with the MCP server.
-   Orchestrating the conversation flow:
    1.  Receives a message and configuration (LLM provider, tool usage) from the UI.
    2.  Sends the conversation history and available tools to the selected LLM.
    3.  Receives a response, which is either text or a tool call request.
    4.  If it's a tool call, it executes the tool on the MCP server.
    5.  It sends the tool's result back to the LLM for a final answer.
    6.  Streams the final text response back to the UI.

## Getting Started

This project is designed to be run with Docker, which is the recommended method for both local development and deployment. The following instructions will guide you through the setup.

### Prerequisites

-   Docker and Docker Compose (or Docker Desktop / Colima).
-   (Optional) Ollama installed with a model pulled (e.g., `ollama run llama3.1`).

### 1. Setup Environment

Create a `.env` file in the project root directory by copying the example. This file stores your secret keys and configuration.

```properties
# .env

# --- LLM and API Keys ---
OPENAI_API_KEY="your_openai_api_key_here"
OPENAI_MODEL="gpt-4-turbo" # Or another model like gpt-3.5-turbo
OPENWEATHERMAP_API_KEY="your_openweathermap_api_key_here"

# --- Application Users ---
# A comma-separated list of users in the format "username:password".
# These users will be able to log into the web client.
APP_USERS="admin:supersecret123,sanket:password"

# --- Database Connections ---
# The application can connect to multiple databases defined by environment variables.
# Each connection needs a unique name (e.g., SUPPLY_CHAIN, RETAIL_OTC).
# Use the format DB_CONN_<NAME>_<PROPERTY>=<VALUE>. Do not enclose values in extra quotes.

# Example 1: An in-memory SQLite database for supply chain and HR data.
DB_CONN_SUPPLY_CHAIN_TYPE=sqlite_in_memory

# Example 2: A MongoDB connection for retail order-to-cash data.
# IMPORTANT: Replace <username>, <password>, and <your-cluster-hostname> with your actual MongoDB Atlas credentials and cluster address.
DB_CONN_RETAIL_OTC_TYPE=mongodb
DB_CONN_RETAIL_OTC_URI="mongodb+srv://<username>:<password>@<your-cluster-hostname>/?retryWrites=true&w=majority&appName=Cluster0"
DB_CONN_RETAIL_OTC_DBNAME=retail_otc_poc

# --- Local Service URLs ---
# This is needed if you run Ollama locally and want the Dockerized client to access it.
# For Docker Desktop (Mac/Windows) and Colima, 'host.docker.internal' is the correct hostname.
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

### 2. Install Dependencies

Install the required Python packages using `uv`. This is mainly for local development and editor support, as Docker will handle dependencies inside the containers.
```bash
uv pip install -r requirements.txt
```

### 3. Run the Application

Start the web server from your terminal:

```bash
uv run uvicorn clients:app --reload
```

Now, open your web browser and navigate to **http://127.0.0.1:8000**.

## How to Use the Chatbot

-   **MCP Tools Toggle**: Use the "Enable MCP Tools" checkbox to control whether the agent can use its tools. When disabled, it will act as a standard LLM.
-   **LLM Provider Selection**: Use the dropdown to switch between OpenAI and your local Ollama instance. If you select Ollama, a second dropdown will appear to let you choose a specific model.
-   **Sidebar**: The sidebar on the left displays information about the connected MCP server, including a full list of its available tools, resources, and prompts.

### Example Prompts

Try asking the chatbot questions that require it to use its tools:
-   **Weather**: "What is the weather like in New York?"
-   **File System**: "List the files in the current directory." then "Read the contents of README.md"
-   **System**: "What is the current system usage?"
-   **Database (HR)**: "Who is the highest-paid employee?" or "How many people work in the Engineering department?" (Use the `supply_chain` connection)
-   **Database (Supply Chain)**: "List all pending purchase orders." (Use the `supply_chain` connection)
-   **Database (Retail)**: "Find all orders for customer C1001." (Use the `retail_otc` connection)

---

This documentation provides a comprehensive guide to understanding, running, and interacting with your agentic AI chatbot.