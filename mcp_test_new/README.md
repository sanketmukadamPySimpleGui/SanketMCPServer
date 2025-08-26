# MCP Test New Project

This project is a web-based chatbot client built using FastAPI, designed to interact with an MCP server and utilize OpenAI's API for natural language processing.

## Project Structure

- **clients.py**: The main FastAPI application that sets up the server, manages settings, handles WebSocket connections, and defines various API endpoints.
- **static/**: Directory for serving static files such as CSS, JavaScript, and images.
- **templates/**: Contains HTML templates for rendering web pages, including `index.html`, the main chat page.
- **.env**: Environment variables for configuration, including API keys and URLs.
- **requirements.txt**: Lists the dependencies required for the project.

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd mcp_test_new
   ```

2. Create a `.env` file in the root directory with the following content:
   ```
   OPENAI_API_KEY=your_key_here
   # Optional: OPENAI_MODEL=gpt-4-turbo
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the application:
   ```
   uvicorn clients:app --reload
   ```

5. Open your browser and navigate to `http://127.0.0.1:8000` to access the chat interface.

## Usage

- The application allows users to interact with a chatbot that can query databases and provide responses based on user input.
- Users can select different database connections and utilize various tools provided by the MCP server.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.