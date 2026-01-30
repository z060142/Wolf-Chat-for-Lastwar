# Scripts Directory

This directory contains utility scripts for managing the Wolf Chat environment.

## Script Overview

### Main Launcher Scripts

#### `start.bat` (Root Directory)
**Purpose**: Main entry point for Wolf Chat
**Location**: `z:\coding4\wolf-chat\start.bat`
**Features**:
- Checks for administrator privileges (optional)
- Automatically sets up UV environment if needed
- Detects changes in requirements.txt and prompts for updates
- Launches Setup.py for configuration

**Usage**:
```batch
start.bat
```

### Environment Setup

#### `setup_uv_env.bat`
**Purpose**: Install UV and set up Python virtual environment
**Features**:
- Automatically installs UV package manager if not present
- Creates `.venv` virtual environment using UV
- Installs all dependencies from requirements.txt (10-100x faster than pip)
- Downloads sentence-transformers embedding model
- Handles environment variable refresh

**Usage**:
```batch
scripts\setup_uv_env.bat
```

**Note**: This script is automatically called by `start.bat` if `.venv` doesn't exist

### Application Launchers

#### `run_main.bat`
**Purpose**: Launch the main Wolf Chat application (main.py)
**Features**:
- Checks for virtual environment
- Activates environment
- Runs main.py

**Usage**:
```batch
scripts\run_main.bat
```

### Developer Tools

#### `run_chroma_view.bat`
**Purpose**: Launch ChromaDB viewer for inspecting memory data
**Features**:
- Opens GUI tool for viewing ChromaDB collections
- Browse conversations, profiles, and bot memory
- Export and analyze stored data

**Usage**:
```batch
scripts\run_chroma_view.bat
```

#### `run_color_picker.bat`
**Purpose**: Launch color picker tool for UI template matching
**Features**:
- Captures game area screenshot
- Sample colors from chat bubbles
- Configure bubble_colors.json automatically

**Usage**:
```batch
scripts\run_color_picker.bat
```

**Instructions**:
1. Click on chat bubble areas to sample colors
2. Press 'q' to quit and save configuration

#### `run_llm_debug.bat`
**Purpose**: Launch LLM debug script for testing without UI
**Features**:
- Test LLM interactions bypassing UI layer
- Debug prompts and tool calls
- Test MCP server responses

**Usage**:
```batch
scripts\run_llm_debug.bat
```

#### `run_system_prompt_tester.bat`
**Purpose**: Launch system prompt tester
**Features**:
- Test and preview system prompt configurations
- Test different MCP server combinations
- Validate prompt scenarios

**Usage**:
```batch
scripts\run_system_prompt_tester.bat
```

### Environment Management

#### `activate_uv_env.bat`
**Purpose**: Activate virtual environment for manual commands
**Features**:
- Activates `.venv` environment
- Opens command prompt with environment active
- Displays helpful commands and usage instructions

**Usage**:
```batch
scripts\activate_uv_env.bat
```

**Example Commands After Activation**:
```batch
python Setup.py              # Run configuration
python main.py               # Run application
uv pip install package-name  # Install new package
uv pip list                  # List installed packages
deactivate                   # Exit environment
```

### System Utilities

#### `check_admin.bat`
**Purpose**: Check if script is running with administrator privileges
**Returns**:
- errorlevel 0 if running as admin
- errorlevel 1 if not admin

**Usage** (typically called by other scripts):
```batch
call scripts\check_admin.bat
if errorlevel 1 (
    echo Not running as administrator
)
```

#### `request_admin.vbs`
**Purpose**: VBScript to request administrator privileges
**Usage** (typically called by other scripts):
```batch
cscript //NoLogo scripts\request_admin.vbs "path\to\script.bat"
```

## Directory Structure

```
wolf-chat/
├── start.bat                          # Main launcher
├── scripts/
│   ├── README.md                     # This file
│   ├── setup_uv_env.bat              # UV environment setup
│   ├── run_main.bat                  # Launch main.py
│   ├── activate_uv_env.bat           # Activate environment
│   ├── run_chroma_view.bat           # ChromaDB viewer tool
│   ├── run_color_picker.bat          # Color picker tool
│   ├── run_llm_debug.bat             # LLM debug script
│   ├── run_system_prompt_tester.bat  # System prompt tester
│   ├── check_admin.bat               # Check admin privileges
│   └── request_admin.vbs             # Request admin elevation
└── .venv/                            # Virtual environment (created by UV)
```

## Workflow

### First-Time Setup
1. User runs `start.bat`
2. `start.bat` checks for `.venv`
3. If not found, calls `scripts\setup_uv_env.bat`
4. `setup_uv_env.bat` installs UV and creates environment
5. `start.bat` launches Setup.py for configuration

### Regular Usage
1. User runs `start.bat` OR `scripts\run_main.bat`
2. Environment is activated
3. Application runs

### Manual Development
1. User runs `scripts\activate_uv_env.bat`
2. Command prompt opens with environment active
3. User can run Python commands manually
4. Type `deactivate` to exit

### Using Developer Tools
1. User runs specific tool launcher:
   - `scripts\run_chroma_view.bat` - Database inspection
   - `scripts\run_color_picker.bat` - UI color configuration
   - `scripts\run_llm_debug.bat` - LLM testing
   - `scripts\run_system_prompt_tester.bat` - Prompt testing
2. Tool opens with environment pre-activated
3. Use the tool as needed
4. Close tool when done

## Benefits of UV

UV is an extremely fast Python package installer and resolver:

- **Speed**: 10-100x faster than pip
- **Caching**: Automatic package caching for offline installation
- **Dependency Resolution**: Advanced conflict resolution
- **Compatibility**: Drop-in replacement for pip commands

**Example Speed Comparison**:
```
pip install -r requirements.txt     # ~5-10 minutes
uv pip install -r requirements.txt  # ~30-60 seconds
```

## Troubleshooting

### UV Installation Issues
If UV fails to install:
1. Manually download from: https://github.com/astral-sh/uv
2. Add to PATH: `%USERPROFILE%\.cargo\bin`
3. Restart terminal

### Environment Activation Issues
If `.venv\Scripts\activate.bat` fails:
1. Delete `.venv` folder
2. Run `scripts\setup_uv_env.bat` again

### Administrator Privileges
Some features may require admin privileges:
- Installing system-wide packages
- Accessing certain Windows APIs
- If prompted, allow the script to run as administrator

### Requirements Changes
If requirements.txt changes:
1. Run `start.bat` - it will auto-detect changes
2. Or manually: `uv pip install -r requirements.txt`

## Additional Resources

- UV Documentation: https://github.com/astral-sh/uv
- Python Virtual Environments: https://docs.python.org/3/library/venv.html
- Wolf Chat Documentation: See main README.md
