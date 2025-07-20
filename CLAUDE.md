# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wolf Chat is a Python-based chatbot assistant designed for integration with "Last War-Survival Game" using screen recognition, MCP (Modular Capability Provider) framework, and LLM integration. The bot monitors game chat windows and automatically responds to messages containing specific keywords.

## Development Commands

### Setup and Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Run the main application
python main.py

# Setup and configuration utility
python Setup.py
```

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
5. **config.py**: Centralized configuration management with environment variables
6. **Setup.py**: Configuration and setup utility with GUI interface
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

### Environment Variables (.env)
```bash
OPENAI_API_KEY=your_api_key_here
EXA_API_KEY=your_exa_key_here
```

### Key Configuration Files
- `config.py`: Main configuration with API settings, MCP servers, and system parameters
- `persona.json`: Bot character definition and personality traits
- `bubble_colors.json`: Color configuration for chat bubble detection
- `templates/`: UI template images for screen recognition

### MCP Server Configuration
MCP servers are configured in `config.py` under `MCP_SERVERS`. Each server includes modular system prompts:
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

Memory preloading can be configured via `ENABLE_PRELOAD_PROFILES` in config.py.

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

## System Prompt Development

### Key Documentation Files
- `SYSTEM_PROMPT_REFERENCE.md`: Complete reference guide for the 12-section system prompt
- `SYSTEM_PROMPT_USAGE.md`: Quick start guide and common modification scenarios
- `SYSTEM_PROMPT_RESTRUCTURE_PLAN.md`: Implementation plan and architectural decisions
- `system_prompt_tester.py`: Interactive testing tool for prompt validation

### Modification Guidelines
1. **High Priority Areas**: Capital management abilities and character behavior (`llm_interaction.py`)
2. **Medium Priority**: MCP tool configurations (`config.py` system_prompt fields)
3. **Character Personality**: Modify `persona.json` for behavioral changes
4. **Testing**: Always run `python system_prompt_tester.py` after modifications

### Architecture Principles
- **Modular Design**: Each MCP server has independent system_prompt
- **Data Source Separation**: Direct ChromaDB vs MCP server calls
- **Dynamic Loading**: System prompts assembled based on active MCP sessions
- **Layered Structure**: 5 logical layers for organized prompt composition