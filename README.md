# Wolf Chat - Last War Game Automated Chat Assistant

## Project Overview

Wolf Chat is a chatbot assistant designed specifically for integration with "Last War-Survival Game," using screen recognition technology to monitor the game's chat window and automatically respond to messages containing keywords.

This bot will:
- Automatically monitor the game chat window
- Detect chat messages containing the keywords "wolf" or "Wolf"
- Generate responses using a language model
- Automatically input responses into the game chat interface
- Serve as Vice President role to remove server members' Congress positions/buffs upon request

## Main Features

- **Language Model Integration**: Supports OpenAI API or compatible AI services for intelligent response generation
- **MCP Framework**: Modular Capability Provider architecture supporting extended functionality and tool calls
- **Persona System**: Provides detailed character definition for personality-driven responses
- **Chat Logging**: Automatically saves conversation history for contextual understanding

## System Requirements

- Python 3.8-3.12 (Python 3.11 recommended)
- OpenAI API key or compatible service
- Game client ("Last War-Survival Game")
- Windows OS (with administrator privileges recommended)
- OpenCV, PyAutoGUI, and other dependencies (see requirements.txt)

## Installation Guide

### Quick Start (Recommended - Using UV)

1. **Download the Project**:
   - Download the ZIP file directly from GitHub (click the green "Code" button, select "Download ZIP")
   - Extract to a folder of your choice

2. **Install UV Package Manager**:
   Open PowerShell and run:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. **Run the Launcher**:
   ```batch
   start.bat
   ```

   This will automatically:
   - Create a virtual environment using UV
   - Install all dependencies
   - Download the embedding model
   - Launch the Setup.py configuration tool

4. **Configure via Setup.py**:
   - The Setup.py GUI will open automatically
   - Configure your API keys, MCP servers, and system settings
   - Setup.py will automatically generate `config.py` and `.env` files
   - **Never edit config.py directly** - always use Setup.py

5. **Capture necessary UI template images** (see "UI Setup" section below)

### Alternative Installation (Traditional pip)

If you prefer using pip instead of UV:

1. **Install Dependencies**:
   ```batch
   pip install -r requirements.txt
   ```

2. **Run Setup.py**:
   ```batch
   python Setup.py
   ```

3. **Configure via the GUI**:
   - Setup.py will guide you through the configuration
   - It will create `.env` and `config.py` files automatically

### Manual Environment Setup

If you need to manually manage the environment:

```batch
# Activate the UV environment
scripts\activate_uv_env.bat

# Install new packages
uv pip install package-name

# Update dependencies
uv pip install -r requirements.txt
```

## Configuration Settings

⚠️ **IMPORTANT: Always use Setup.py for configuration!**

`config.py` is **automatically generated** by Setup.py and should **NEVER be edited directly**. All configuration changes must be made through the Setup.py GUI to ensure consistency.

### Using Setup.py

1. **Launch Setup.py**:
   ```batch
   start.bat
   ```
   Or if environment is already set up:
   ```batch
   python Setup.py
   ```

2. **Configure Settings via GUI**:
   - **API Settings**: Set your preferred language model provider (OpenAI, OpenRouter, DeepSeek, etc.)
   - **MCP Servers**: Enable/disable and configure MCP servers (Exa, Chroma, custom servers)
   - **Game Settings**: Set game window title and monitoring parameters
   - **System Parameters**: Configure detection thresholds, deduplication, and other system settings

3. **Automatic File Generation**:
   - Setup.py creates/updates `.env` file with API keys
   - Setup.py generates `config.py` with all configurations
   - Changes are validated and saved transactionally

### Direct Configuration (Advanced Users)

If you need to modify settings that are not in Setup.py:

1. **Chat Persona**: Edit `persona.json` to define the bot's personality traits
2. **Bubble Colors**: Edit `bubble_colors.json` for chat bubble detection colors
3. **UI Templates**: Add/update template images in the `templates/` folder

### Configuration Architecture

- `Setup.py` → Source of truth for all settings
- `config.py` → Auto-generated configuration file (DO NOT EDIT)
- `.env` → Environment variables (API keys)
- `persona.json` → Character personality definition

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

### First-Time Setup

1. **Run the launcher**:
   ```batch
   start.bat
   ```
   This will set up the environment and open Setup.py for configuration

2. **Configure via Setup.py GUI**:
   - Set your API keys
   - Configure MCP servers
   - Adjust system parameters

3. **Capture UI templates** (see "UI Setup" section)

### Running the Bot

**Recommended Method (Using Setup.py GUI)**:

1. **Launch Setup.py**:
   ```batch
   python Setup.py
   ```

2. **Start Bot & Game**:
   - In the Setup.py window, click **"Start Managed bot & Game"** button
   - This will automatically:
     - Launch the game client
     - Start the chatbot with proper monitoring
     - Manage both processes together

3. **Test Chat Functionality**:
   - Click **"Run Test"** button in Setup.py to test the chat response without game interaction
   - This allows you to verify LLM responses and configurations safely

**Alternative Method (Manual Launch)**:

1. **Start the game client manually**

2. **Launch the bot**:
   ```batch
   scripts\run_main.bat
   ```
   Or manually:
   ```batch
   .venv\Scripts\activate.bat
   python main.py
   ```

3. **Bot Operation**:
   - The bot will start monitoring the chat for messages containing "wolf" or "Wolf"
   - When a keyword is detected, it will:
     - Copy the message content
     - Get the sender's name
     - Process the request using the language model
     - Automatically send a response in the chat

### Available Scripts

**Main Scripts**:
- `start.bat` - Main launcher (setup environment + run Setup.py)
- `scripts\run_main.bat` - Launch main application
- `scripts\activate_uv_env.bat` - Activate virtual environment for manual commands
- `scripts\setup_uv_env.bat` - Manually reinstall environment

**Developer Tools**:
- `scripts\run_chroma_view.bat` - ChromaDB viewer for inspecting memory data
- `scripts\run_color_picker.bat` - Color picker tool for UI template matching
- `scripts\run_llm_debug.bat` - LLM debug script for testing without UI
- `scripts\run_system_prompt_tester.bat` - System prompt configuration tester

## Hotkeys

- **F7**: Clear recently processed conversation history
- **F8**: Pause/resume the script's main functions (UI monitoring, LLM interaction)
- **F9**: Trigger the script's normal shutdown process

## Developer Tools

Wolf Chat provides several developer tools for debugging and configuration:

### LLM Debug Script
**Script**: `test/llm_debug_script.py`
**Launcher**: `scripts\run_llm_debug.bat`

Bypasses the UI interaction layer to directly interact with the language model for debugging. Useful for testing prompts and MCP tool calls without running the full application.

### ChromaDB Viewer
**Script**: `tools/chroma_view.py`
**Launcher**: `scripts\run_chroma_view.bat`

GUI tool for inspecting ChromaDB collections. View conversations, profiles, and bot memory. Export and analyze stored data.

### Color Picker Tool
**Script**: `tools/color_picker.py`
**Launcher**: `scripts\run_color_picker.bat`

Interactive tool for configuring chat bubble colors. Captures game area screenshots and allows you to sample colors by clicking on chat bubbles. Automatically updates `bubble_colors.json`.

### System Prompt Tester
**Script**: `system_prompt_tester.py`
**Launcher**: `scripts\run_system_prompt_tester.bat`

Test and preview system prompt configurations. Test different MCP server combinations and validate prompt scenarios before deployment.

## Troubleshooting

- **Template Recognition Issues**: Adjust the `CONFIDENCE_THRESHOLD` in `ui_interaction.py`
- **MCP Connection Errors**: Check server configurations in `config.py`
- **API Errors**: Verify your API keys in the `.env` file
- **UI Automation Failures**: Update template images to match your client's appearance
- **Window Position Issues**: Ensure the game window stays in the correct position, use `window-monitor-script.py`
