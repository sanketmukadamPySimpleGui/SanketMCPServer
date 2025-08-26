console.log("script.js: File loaded by browser.");

document.addEventListener("DOMContentLoaded", () => {
    console.log("script.js: DOMContentLoaded event fired. Initializing chat UI.");
    const messagesDiv = document.getElementById("messages");
    const messageInput = document.getElementById("message-input");
    const sendButton = document.getElementById("send-button");
    const thinkingDiv = document.getElementById("thinking");
    const llmProviderSelect = document.getElementById("llm-provider-select");
    const ollamaModelSelect = document.getElementById("ollama-model-select");
    const dbConnectionSelect = document.getElementById("db-connection-select");

    const ws = new WebSocket(`ws://${window.location.host}/ws`);

    function showThinking(isThinking) {
        thinkingDiv.style.display = isThinking ? "block" : "none";
    }

    llmProviderSelect.addEventListener("change", () => {
        if (llmProviderSelect.value === "ollama") {
            ollamaModelSelect.classList.remove("hidden");
        } else {
            ollamaModelSelect.classList.add("hidden");
        }
    });

    loadServerInfo(); // Load server info as soon as the page is ready
    loadDbConnections();

    ws.onmessage = function(event) {
        showThinking(false);
        const message = document.createElement("div");
        // Simple check to see if it's a "Calling tool" message
        if (event.data.startsWith("🤖 Calling")) {
            message.className = "message tool-call-message";
        } else {
            message.className = "message bot-message";
        }
        message.textContent = event.data;
        messagesDiv.insertBefore(message, thinkingDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    };

    ws.onerror = function(event) {
        console.error("WebSocket error:", event);
        const errorDiv = document.createElement("div");
        errorDiv.className = "message error-message";
        errorDiv.textContent = "Connection error. Please refresh the page.";
        messagesDiv.insertBefore(errorDiv, thinkingDiv);
        showThinking(false);
    };

    ws.onclose = function(event) {
        console.log("WebSocket connection closed");
        showThinking(false);
    };

    function sendMessage() {
        const messageText = messageInput.value.trim();
        const useMcp = document.getElementById("mcp-toggle").checked;
        const llmProvider = llmProviderSelect.value;
        const llmModel = ollamaModelSelect.value;
        const dbConnectionName = dbConnectionSelect.value;

        if (messageText && ws.readyState === WebSocket.OPEN) {
            const message = document.createElement("div");
            message.className = "message user-message";
            message.textContent = messageText;
            messagesDiv.insertBefore(message, thinkingDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            const payload = JSON.stringify({
                text: messageText,
                use_mcp: useMcp,
                llm_provider: llmProvider,
                llm_model: llmProvider === 'ollama' ? llmModel : null,
                db_connection_name: dbConnectionName,
            });
            ws.send(payload);
            messageInput.value = "";
            messageInput.style.height = 'auto'; // Reset height
            showThinking(true);
        }
    }

    sendButton.addEventListener("click", sendMessage);
    messageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = (messageInput.scrollHeight) + 'px';
    });

    // Fetch and display server info
    async function loadServerInfo() {
        console.log("script.js: loadServerInfo() function called.");
        const serverInfoContent = document.getElementById('server-info-content');
        const toolsList = document.getElementById('tools-list');
        const resourcesList = document.getElementById('resources-list');
        const promptsList = document.getElementById('prompts-list');

        function showError(element, message) {
            if (element) {
                // For <ul>, wrap in <li>. For <div>, wrap in <p>
                if (element.tagName === 'UL') {
                    element.innerHTML = `<li class="error-message">${message}</li>`;
                } else {
                    element.innerHTML = `<p class="error-message">${message}</p>`;
                }
            }
        }

        try {
            console.log("script.js: Attempting to fetch /api/server-info...");
            const response = await fetch('/api/server-info');
            console.log(`script.js: Fetch response received with status: ${response.status}`);
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Failed to fetch server info:', response.status, errorText);
                showError(serverInfoContent, 'Failed to load server info.');
                showError(toolsList, 'Failed to load tools.');
                showError(resourcesList, 'Failed to load resources.');
                showError(promptsList, 'Failed to load prompts.');
                return;
            }
            const data = await response.json();

            // Populate Server Info
            if (serverInfoContent && data && data.server_info) {
                serverInfoContent.innerHTML = `
                    <strong>Name:</strong> ${data.server_info.name}<br>
                    <strong>Version:</strong> ${data.server_info.version}
                `;
            } else {
                showError(serverInfoContent, 'Server info not available in response.');
            }

            // Populate Tools
            if (toolsList && data && data.tools) {
                toolsList.innerHTML = data.tools.length > 0
                    ? data.tools.map(tool => `<li><strong>${tool.name}</strong>: ${tool.description || 'No description'}</li>`).join('')
                    : '<li>No tools available.</li>';
            } else {
                showError(toolsList, 'Tools list not available in response.');
            }

            // Populate Resources
            if (resourcesList && data && data.resources) {
                resourcesList.innerHTML = data.resources.length > 0
                    ? data.resources.map(res => `<li><code>${res.uri}</code>: ${res.description || 'No description'}</li>`).join('')
                    : '<li>No resources available.</li>';
            } else {
                showError(resourcesList, 'Resources list not available in response.');
            }

            // Populate Prompts
            if (promptsList && data && data.prompts) {
                promptsList.innerHTML = data.prompts.length > 0
                    ? data.prompts.map(p => `<li><strong>${p.name}</strong>: ${p.description || 'No description'}</li>`).join('')
                    : '<li>No prompts available.</li>';
            } else {
                showError(promptsList, 'Prompts list not available in response.');
            }

        } catch (error) {
            console.error('script.js: A critical error occurred in loadServerInfo:', error);
            showError(serverInfoContent, 'Error loading server info.');
            showError(toolsList, 'Error loading tools.');
            showError(resourcesList, 'Error loading resources.');
            showError(promptsList, 'Error loading prompts.');
        }
    }

    async function loadDbConnections() {
        console.log("script.js: loadDbConnections() function called.");
        try {
            const response = await fetch('/api/db-connections');
            if (!response.ok) {
                dbConnectionSelect.innerHTML = '<option>Error loading</option>';
                return;
            }
            const data = await response.json();
            if (data.connections && data.connections.length > 0) {
                dbConnectionSelect.innerHTML = data.connections
                    .map(conn => `<option value="${conn}">${conn.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>`)
                    .join('');
            } else {
                dbConnectionSelect.innerHTML = '<option>No DBs found</option>';
            }
        } catch (error) {
            console.error('Error loading DB connections:', error);
            dbConnectionSelect.innerHTML = '<option>Error loading</option>';
        }
    }
});