# Wolf Chat - Last War Game Automated Chat Assistant

## Project Overview

Wolf Chat is a chatbot assistant designed specifically for integration with "Last War-Survival Game," using screen recognition technology to monitor the game's chat window and automatically respond to messages containing keywords.

This bot will:
- Automatically monitor the game chat window
- Detect chat messages containing the keywords "wolf" or "Wolf"
- Generate responses using a language model
- Automatically input responses into the game chat interface

## Main Features

- **Language Model Integration**: Supports OpenAI API or compatible AI services for intelligent response generation
- **MCP Framework**: Modular Capability Provider architecture supporting extended functionality and tool calls
- **Persona System**: Provides detailed character definition for personality-driven responses
- **Chat Logging**: Automatically saves conversation history for contextual understanding

## System Requirements

- Python 3.8+
- OpenAI API key or compatible service
- Game client ("Last War-Survival Game")
- OpenCV, PyAutoGUI, and other dependencies (see requirements.txt)

## Installation Guide

1. **Download Method**:
   - Download the ZIP file directly from GitHub (click the green "Code" button, select "Download ZIP")
   - Extract to a folder of your choice

2. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```

3. **Create a `.env` file** with your API keys:
   ```
   OPENAI_API_KEY=your_api_key_here
   EXA_API_KEY=your_exa_key_here
   ```

4. **Capture necessary UI template images** (see "UI Setup" section below)

## Configuration Settings

1. **API Settings**: Edit `config.py` to set your preferred language model provider:
   ```python
   OPENAI_API_BASE_URL = "https://openrouter.ai/api/v1" # Or other compatible provider
   LLM_MODEL = "deepseek/deepseek-chat-v3-0324" # Or other model
   ```

2. **MCP Servers**: Configure MCP servers in `config.py` (if using this feature):
   ```python
   MCP_SERVERS = {
       "exa": { "command": "cmd", "args": [...] },
       "memorymesh": { "command": "node", "args": [...] }
   }
   ```

3. **Game Window**: Set your game window title in `config.py`:
   ```python
   WINDOW_TITLE = "Last War-Survival Game"
   ```

4. **Chat Persona**: Customize `persona.json` to define the bot's personality traits

## UI Setup

The system requires template images of UI elements to function properly:

1. **Run the window setup script** to position your game window:
   ```
   python window-setup-script.py --launch
   ```

2. **Capture the following UI elements** and save them to the `templates` folder:
   - Chat bubble corners (regular and bot)
   - Keywords "wolf" and "Wolf"
   - Menu elements like "Copy" button
   - Profile and user detail page elements
   - **Capitol icon in the Profile page** (critical!)

   Screenshot names should match the constants defined in `ui_interaction.py`.

3. **Window Monitor Tool**: Use the following command to start window monitoring, ensuring the game window stays on top:
   ```
   python window-monitor-script.py
   ```

## Usage Instructions

1. Start the game client

2. Run the bot:
   ```
   python main.py
   ```

3. The bot will start monitoring the chat for messages containing "wolf" or "Wolf"

4. When a keyword is detected, it will:
   - Copy the message content
   - Get the sender's name
   - Process the request using the language model
   - Automatically send a response in the chat

## Hotkeys

- **F7**: Clear recently processed conversation history
- **F8**: Pause/resume the script's main functions (UI monitoring, LLM interaction)
- **F9**: Trigger the script's normal shutdown process

## Developer Tools

- **LLM Debug Script** (`test/llm_debug_script.py`): Bypasses the UI interaction layer to directly interact with the language model for debugging, useful for testing prompts and MCP tool calls

## Troubleshooting

- **Template Recognition Issues**: Adjust the `CONFIDENCE_THRESHOLD` in `ui_interaction.py`
- **MCP Connection Errors**: Check server configurations in `config.py`
- **API Errors**: Verify your API keys in the `.env` file
- **UI Automation Failures**: Update template images to match your client's appearance
- **Window Position Issues**: Ensure the game window stays in the correct position, use `window-monitor-script.py`
