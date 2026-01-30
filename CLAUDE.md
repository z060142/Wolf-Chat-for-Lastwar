# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wolf Chat is a Python-based chatbot assistant designed for integration with "Last War-Survival Game" using screen recognition, MCP (Modular Capability Provider) framework, and LLM integration. The bot monitors game chat windows and automatically responds to messages containing specific keywords.

## Development Commands

### Setup and Installation

**⚠️ IMPORTANT: Always run Setup.py first before running the application!**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run Setup.py to generate config.py (REQUIRED for first-time setup)
# This interactive GUI utility will create and manage all configuration
python Setup.py

# 3. Run the main application
python main.py
```

**Critical Notes:**
- `config.py` is **automatically generated** by `Setup.py` - **DO NOT edit config.py directly**
- All configuration changes must be made through `Setup.py` to ensure consistency
- If you need to modify any settings (API keys, MCP servers, system parameters), always use `Setup.py`

### Development Tools
```bash
# LLM debug script (bypasses UI for testing)
python test/llm_debug_script.py

# Color picker tool for UI template matching
python tools/color_picker.py

# ChromaDB viewer for memory inspection
python tools/chroma_view.py

# Memory backup utilities
python tools/Chroma_DB_backup.py
python memory_backup.py
```

### Testing and Debugging
```bash
# Test MCP connections and tool discovery
python mcp_client.py

# Test UI interaction components
python ui_interaction.py

# Test memory management
python memory_manager.py

# Test system prompt structure and generation
python system_prompt_tester.py
```

## Architecture Overview

### Core Components

1. **main.py**: Main orchestrator that coordinates all modules, manages MCP connections, and handles the main event loop
2. **ui_interaction.py**: Handles screen recognition, chat monitoring, and game UI automation using OpenCV and PyAutoGUI
3. **llm_interaction.py**: Manages LLM API communication, system prompts, and tool calling functionality
4. **mcp_client.py**: Handles MCP server communication, tool discovery, and execution
5. **Setup.py**: ⚠️ **Configuration manager** - Interactive GUI utility that generates and manages `config.py`. **All configuration changes must go through this script**
6. **config.py**: ⚠️ **AUTO-GENERATED FILE** - Centralized configuration storage created by Setup.py. **DO NOT EDIT DIRECTLY** - use Setup.py instead
7. **game_manager.py**: Game window monitoring and process management
8. **chroma_client.py**: ChromaDB vector database client for memory management
9. **memory_manager.py**: Advanced memory system with entity profiles and conversation history

### Key Features

- **Screen Recognition**: Uses OpenCV for template matching and game UI detection
- **MCP Framework**: Modular tool system for extensible functionality
- **Memory System**: ChromaDB-based persistent memory with entity profiles
- **Persona System**: JSON-based character definition for consistent role-playing
- **Multi-threading**: Separate threads for UI monitoring and main processing
- **Fault Tolerance**: Graceful handling of MCP server failures and connection issues

## Configuration

### ⚠️ Configuration Management Philosophy

**CRITICAL: config.py is AUTO-GENERATED - Never Edit Directly!**

All configuration in this project is managed through `Setup.py`:
- `config.py` is **automatically generated** by running `python Setup.py`
- **DO NOT modify config.py manually** - changes will be overwritten
- To change any settings, always run `Setup.py` and use its GUI interface
- When modifying code that references config parameters, update `Setup.py` instead

### Environment Variables (.env)
```bash
OPENAI_API_KEY=your_api_key_here
EXA_API_KEY=your_exa_key_here
```

### Key Configuration Files
- **`Setup.py`**: ⚠️ **Configuration source of truth** - Modify this to change any settings
- **`config.py`**: ⚠️ **AUTO-GENERATED** - Created by Setup.py, contains API settings, MCP servers, and system parameters
- `persona.json`: Bot character definition and personality traits
- `bubble_colors.json`: Color configuration for chat bubble detection
- `templates/`: UI template images for screen recognition

### MCP Server Configuration
MCP servers are configured through `Setup.py`, which generates the configuration in `config.py` under `MCP_SERVERS`. Each server includes modular system prompts:
```python
MCP_SERVERS = {
    "exa": {
        "command": "npx",
        "args": ["exa-mcp-server", "--tools=web_search,research_paper_search"],
        "env": {"EXA_API_KEY": EXA_API_KEY},
        "system_prompt": """
        **WEB SEARCH CAPABILITIES:**
        You have access to advanced web search tools...
        """
    },
    "chroma": {
        "command": "uvx",
        "args": ["chroma-mcp", "--client-type", "persistent", "--data-dir", "chroma_data"],
        "system_prompt": """
        **CHROMADB SEMANTIC QUERY CAPABILITIES:**
        You have access to semantic queries for complex conversations...
        """
    }
}
```

### System Prompt Architecture
The system uses a modular 5-layer system prompt architecture:

1. **Layer 1: Core Identity** - Basic persona and environment
2. **Layer 2: Context Data** - User profiles and conversation history (direct ChromaDB calls)
3. **Layer 3: Core Abilities** - Capital management and character behavior
4. **Layer 4: Additional Tools** - MCP tool framework and server-specific guides
5. **Layer 5: Operations** - Output format and usage examples

System prompts are dynamically composed in `llm_interaction.py` based on active MCP servers.

## Memory System

The project uses a dual-layer memory architecture:

### Direct ChromaDB Access (chroma_client.py)
- **User Profiles**: Direct retrieval of user profile data
- **Conversation History**: Multi-turn conversation context (5 current user + 5 other users)
- **Immediate Context**: Data directly provided to LLM system prompt

### MCP ChromaDB Server (via tool_calls)
- **Semantic Queries**: Complex knowledge retrieval for enhanced conversations
- **Game Mechanics**: Query-based access to game knowledge and concepts
- **Contextual Enhancement**: Additional context when basic data isn't sufficient

Main collections:
- **Profiles**: Entity profiles and user information
- **Conversations**: Chat history and context
- **Bot Memory**: Game knowledge and reference information

Memory preloading can be configured via `ENABLE_PRELOAD_PROFILES` setting in `Setup.py` (which generates the parameter in config.py).

## UI System

The UI interaction system uses:
- **Template Matching**: OpenCV-based image recognition for game UI elements
- **Screen Capture**: PyAutoGUI for screenshots and coordinate detection
- **Color Detection**: JSON-based color configuration for chat bubbles
- **Automated Input**: Keyboard/mouse automation for game interaction

Critical UI templates must be captured and stored in `templates/` folder for proper functionality.

## Hotkeys

- **F7**: Clear conversation history
- **F8**: Pause/Resume script operation
- **F9**: Graceful shutdown

## Error Handling

The system includes comprehensive error handling for:
- MCP server connection failures (continues operation with warnings)
- UI recognition failures (automatic retry with fallbacks)
- LLM API errors (with exponential backoff)
- Memory system failures (graceful degradation)

## Dependencies

Key dependencies include:
- OpenAI API or compatible LLM service
- MCP framework (`mcp` package)
- OpenCV for computer vision (`opencv-python`)
- PyAutoGUI for UI automation
- ChromaDB for vector storage
- Various Windows-specific packages (`pywin32`, `pygetwindow`)

## Development Notes

- Code is primarily in English with Chinese comments and logs
- Uses asyncio for concurrent operations
- Implements robust message deduplication system
- Supports both manual and automated game window management
- Designed for Windows environment with cross-platform considerations

## ⚠️ Configuration Management Rules

**CRITICAL: Read this before modifying any configuration!**

### The Golden Rule
- **config.py is AUTO-GENERATED** - It is created and managed entirely by Setup.py
- **NEVER edit config.py directly** - All manual edits will be lost when Setup.py runs again

### What to do instead
1. **To change settings**: Run `python Setup.py` and use the GUI interface
2. **To add new parameters**: Modify `Setup.py` to include the new parameter in its generation logic
3. **To modify MCP servers**: Edit the MCP server configuration section in `Setup.py`
4. **To change system prompts**: Update the system_prompt fields in `Setup.py`

### Why this matters
- Setup.py ensures configuration consistency and validation
- Direct edits to config.py will be overwritten without warning
- Setup.py handles environment variable loading, path resolution, and error checking
- This architecture prevents configuration drift and ensures reproducibility

### When developing new features
If your feature requires new configuration parameters:
1. Add the parameter to `Setup.py` (in the appropriate section)
2. Update the config generation logic in `Setup.py`
3. Run `Setup.py` to regenerate `config.py`
4. Import the parameter from `config` in your code

**Remember**: config.py is not source code - it's a build artifact. Treat it like a compiled binary.

## System Prompt Development

### Key Documentation Files
- `SYSTEM_PROMPT_REFERENCE.md`: Complete reference guide for the 12-section system prompt
- `SYSTEM_PROMPT_USAGE.md`: Quick start guide and common modification scenarios
- `SYSTEM_PROMPT_RESTRUCTURE_PLAN.md`: Implementation plan and architectural decisions
- `system_prompt_tester.py`: Interactive testing tool for prompt validation

### Modification Guidelines
1. **High Priority Areas**: Capital management abilities and character behavior (`llm_interaction.py`)
2. **Medium Priority**: MCP tool configurations (modify `Setup.py` to change system_prompt fields - **DO NOT edit config.py directly**)
3. **Character Personality**: Modify `persona.json` for behavioral changes
4. **Configuration Changes**: ⚠️ **Always use Setup.py** - never edit config.py manually
5. **Testing**: Always run `python system_prompt_tester.py` after modifications

### Architecture Principles
- **Modular Design**: Each MCP server has independent system_prompt
- **Data Source Separation**: Direct ChromaDB vs MCP server calls
- **Dynamic Loading**: System prompts assembled based on active MCP sessions
- **Layered Structure**: 5 logical layers for organized prompt composition