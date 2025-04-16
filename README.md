# Dandan MCP Chat Bot

A specialized chat assistant that integrates with the "Last War-Survival Game" by monitoring the game's chat window using screen recognition technology.

## Overview

This project implements an AI assistant that:
- Monitors the game chat window using computer vision
- Detects messages containing keywords ("wolf" or "Wolf")
- Processes requests through a language model
- Automatically responds in the game chat

The code is developed in English, but supports Traditional Chinese interface and logs for broader accessibility.

## Features

- **Image-based Chat Monitoring**: Uses OpenCV and PyAutoGUI to detect chat bubbles and keywords
- **Language Model Integration**: Uses GPT models or compatible AI services
- **MCP Framework**: Integrates with Modular Capability Provider for extensible features
- **Persona System**: Supports detailed character persona definition
- **Automated UI Interaction**: Handles copy/paste operations and menu navigation

## Requirements

- Python 3.8+
- OpenAI API key or compatible service
- MCP Framework
- Game client ("Last War-Survival Game")
- OpenCV, PyAutoGUI, and other dependencies (see requirements.txt)

## Installation

1. Clone this repository:
   ```
   git clone [repository-url]
   cd dandan
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your API keys:
   ```
   OPENAI_API_KEY=your_api_key_here
   EXA_API_KEY=your_exa_key_here
   ```

4. Capture required UI template images (see "UI Setup" section)

## Configuration

1. **API Settings**: Edit `config.py` to set up your preferred language model provider:
   ```python
   OPENAI_API_BASE_URL = "https://openrouter.ai/api/v1" # Or other compatible provider
   LLM_MODEL = "deepseek/deepseek-chat-v3-0324" # Or other model
   ```

2. **MCP Servers**: Configure MCP servers in `config.py`:
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

4. **Chat Persona**: Customize `persona.json` to define the bot's personality

## UI Setup

The system requires template images of UI elements to function properly:

1. Run the window setup script to position your game window:
   ```
   python window-setup-script.py --launch
   ```

2. Capture the following UI elements and save them to the `templates` folder:
   - Chat bubble corners (regular and bot)
   - Keywords "wolf" and "Wolf"
   - Menu elements like "Copy" button
   - Profile and user detail page elements

   Screenshot names should match the constants defined in `ui_interaction.py`.

## Usage

1. Start the game client

2. Run the bot:
   ```
   python main.py
   ```

3. The bot will start monitoring the chat for messages containing "wolf" or "Wolf"

4. When detected, it will:
   - Copy the message content
   - Get the sender's name
   - Process the request using the language model
   - Automatically send a response in chat

## How It Works

1. **Monitoring**: The UI thread continuously scans the screen for chat bubbles
2. **Detection**: When a bubble with "wolf" keyword is found, the message is extracted
3. **Processing**: The message is sent to the language model with the persona context
4. **Response**: The AI generates a response based on the persona
5. **Interaction**: The system automatically inputs the response in the game chat

## Developer Tools

- **Window Setup Script**: Helps position the game window for UI template capture
- **UI Interaction Debugging**: Can be tested independently by running `ui_interaction.py`
- **Persona Customization**: Edit `persona.json` to change the bot's character

## Troubleshooting

- **Template Recognition Issues**: Adjust the `CONFIDENCE_THRESHOLD` in `ui_interaction.py`
- **MCP Connection Errors**: Check server configurations in `config.py`
- **API Errors**: Verify your API keys in the `.env` file
- **UI Automation Failures**: Update template images to match your client's appearance

