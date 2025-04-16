# mcp_client.py (Complete code including ValidationError workaround)

import asyncio
import json # Import json for parsing error details
import ast  # Import ast for safely evaluating string literals
from mcp import ClientSession, types, McpError # Import McpError
# Import Pydantic validation error if needed for specific catch
try:
    # pydantic_core is where ValidationError lives in Pydantic v2+
    from pydantic_core import ValidationError
except ImportError:
    try:
        # Fallback for Pydantic v1 or other structures
        from pydantic import ValidationError
    except ImportError:
        ValidationError = None # Define as None if pydantic is not available or structure differs
        print("Warning: Unable to import pydantic_core.ValidationError or pydantic.ValidationError. Error handling may be limited.")

# --- Import Tool type ---
# Attempt to import the Tool type definition from common SDK locations
try:
    from mcp.types import Tool
except ImportError:
    try:
        from mcp import Tool
    except ImportError:
        # Define a placeholder if import fails, to avoid NameError,
        # but actual functionality might depend on the real type.
        print("Warning: Unable to import 'Tool' type from MCP SDK. Tool processing may fail.")
        Tool = type('Tool', (object,), {}) # Placeholder type

import config # Import configuration

# --- list_mcp_tools Function ---
async def list_mcp_tools(session: ClientSession) -> list[dict]:
    """
    Lists the available MCP tools for a given session.
    Parses the response structure and converts Tool objects to dictionaries.

    Args:
        session: The active MCP ClientSession.

    Returns:
        A list of tool definition dictionaries, ready for formatting for LLM.
        Returns an empty list on error or if no tools are found.
    """
    tool_definition_list = [] # Initialize list for the dictionaries we will return
    try:
        # Check if the session object has the necessary method
        if not hasattr(session, 'list_tools') or not callable(session.list_tools):
             print(f"Error: MCP ClientSession object is missing the callable 'list_tools' method. Please check the SDK.")
             return tool_definition_list

        # Call the SDK method to get the response containing tools
        response = await session.list_tools()
        # print(f"DEBUG: Raw list_tools response from session {session}: {response}") # Debug

        # Extract the raw list of tools (likely Tool objects)
        tools_list_raw = []
        if isinstance(response, dict):
            # If response is a dictionary, get the 'tools' key
            tools_list_raw = response.get('tools', [])
        elif hasattr(response, 'tools'):
            # If response is an object, get the 'tools' attribute
            tools_list_raw = getattr(response, 'tools', [])
        else:
            # Handle unexpected response type
            print(f"Warning: Unexpected response type from session.list_tools(): {type(response)}. Unable to extract tools.")
            print(f"Complete response: {response}")
            return tool_definition_list

        # Validate that we actually got a list
        if not isinstance(tools_list_raw, list):
             print(f"Warning: Expected a list under 'tools' key/attribute, but got {type(tools_list_raw)}. Response: {response}")
             return tool_definition_list

        # --- Convert Tool objects (or items) to dictionaries ---
        print(f"Extracted {len(tools_list_raw)} raw tool items from Server, converting...")
        for item in tools_list_raw:
            try:
                # Check if the item is likely a Tool object using hasattr for safety
                if hasattr(item, 'name') and hasattr(item, 'description') and hasattr(item, 'inputSchema'):
                    tool_name = getattr(item, 'name', 'UnknownToolName')
                    tool_description = getattr(item, 'description', '')
                    tool_input_schema = getattr(item, 'inputSchema', None)

                    # Create the dictionary for our internal use / LLM formatting
                    tool_dict = {
                        'name': tool_name,
                        'description': tool_description,
                        # Map 'inputSchema' from MCP Tool to 'parameters' key
                        'parameters': tool_input_schema if isinstance(tool_input_schema, dict) else {"type": "object", "properties": {}}
                    }

                    # Basic validation of parameters structure
                    if not isinstance(tool_dict['parameters'], dict):
                         print(f"Warning: The inputSchema for tool '{tool_dict['name']}' is not a dictionary, using empty parameters. Schema: {tool_dict['parameters']}")
                         tool_dict['parameters'] = {"type": "object", "properties": {}}

                    tool_definition_list.append(tool_dict)
                else:
                    # Handle cases where items in the list are not Tool objects
                    print(f"Warning: Item in tool list is not in expected Tool object format: {item} (type: {type(item)})")
            except Exception as conversion_err:
                 print(f"Warning: Error converting tool item '{getattr(item, 'name', item)}': {conversion_err}.")

        print(f"Successfully converted {len(tool_definition_list)} tool definitions to dictionaries.")
        return tool_definition_list # Return the list of dictionaries

    except AttributeError as ae:
         print(f"Error: MCP ClientSession object is missing 'list_tools' attribute/method: {ae}. Please check the SDK.")
         return []
    except Exception as e:
        print(f"Error: Failed to execute list_tools or parse tools: {e}")
        import traceback
        traceback.print_exc()
        return []

# --- _confirm_execution Function ---
def _confirm_execution(tool_name: str, arguments: dict) -> bool:
    """
    If configured, prompts the user for confirmation before executing a tool.
    Includes corrected indentation.
    """
    if config.MCP_CONFIRM_TOOL_EXECUTION:
        # Correctly indented try-except block
        try:
            confirm = input(f"\033[93m[CONFIRM]\033[0m Allow execution of MCP tool: '{tool_name}'\n    Parameters: {arguments}\n    (y/n)? ").lower().strip()
            if confirm == 'y':
                print("--> Execution confirmed.")
                return True
            else:
                print("--> Execution denied.")
                return False
        except Exception as e:
             print(f"Error reading confirmation: {e}, denying.")
             return False
    else:
        # Confirmation not required
        return True

# --- call_mcp_tool Function ---
async def call_mcp_tool(session: ClientSession, tool_name: str, arguments: dict):
    """
    Calls a specified MCP tool via the given session.
    Includes confirmation step and workaround for ValidationError on missing 'content'.
    """
    # Call confirmation helper function
    if not _confirm_execution(tool_name, arguments):
        return {"error": "User declined execution", "tool_name": tool_name}

    try:
        # Check if the session object has the necessary method
        if not hasattr(session, 'call_tool') or not callable(session.call_tool):
             error_msg = f"Error: MCP ClientSession object does not have a callable 'call_tool' method."
             print(error_msg)
             return {"error": error_msg, "tool_name": tool_name}

        print(f"Calling MCP tool '{tool_name}'...")
        # The actual SDK call that might raise McpError wrapping ValidationError
        result = await session.call_tool(tool_name, arguments=arguments)
        print(f"Tool '{tool_name}' execution completed (SDK validation passed).")
        return result # Return the validated result if successful

    except McpError as mcp_err:
        # --- Workaround for ValidationError on missing 'content' ---
        error_details = getattr(mcp_err, 'details', None) or {} # Get error details if available
        error_message = str(mcp_err) # Get the full error message string
        print(f"Tool '{tool_name}' call encountered McpError: {error_message}") # Log the original error

        # Check if it's the specific validation error we want to handle
        # This checks the error message string for keywords
        is_validation_error = (
            ValidationError is not None and # Check if ValidationError was imported
            isinstance(mcp_err.__cause__, ValidationError) and # Check the underlying cause
            "CallToolResult" in error_message and # Check specific model name
            "content" in error_message and # Check specific field name
            "Field required" in error_message # Check specific error type
        )
        # Alternative check if __cause__ isn't reliable
        is_validation_error_str_check = (
             "validation error for CallToolResult" in error_message and
             "content" in error_message and
             "Field required" in error_message
        )

        raw_input_value = None # Initialize variable for raw server response

        # Attempt to extract raw input value if it looks like our specific error
        if is_validation_error or is_validation_error_str_check:
             print("Detected potential ValidationError for missing 'content', attempting to extract raw server response...")
             try:
                 # Try getting 'input' from error details first (safer)
                 if isinstance(error_details, dict):
                     raw_input_value = error_details.get('input')

                 # If not found in details, try parsing from the error message string (more fragile)
                 if not raw_input_value:
                      start_index = error_message.find("input_value=")
                      if start_index != -1:
                           dict_str_start = error_message.find("{", start_index)
                           # Find the matching closing brace carefully
                           brace_level = 0
                           dict_str_end = -1
                           if dict_str_start != -1:
                               for i, char in enumerate(error_message[dict_str_start:]):
                                    if char == '{': brace_level += 1
                                    elif char == '}': brace_level -= 1
                                    if brace_level == 0: dict_str_end = dict_str_start + i; break

                           if dict_str_start != -1 and dict_str_end != -1:
                                dict_str = error_message[dict_str_start : dict_str_end + 1]
                                try:
                                     # Use ast.literal_eval for safer evaluation than eval()
                                     raw_input_value = ast.literal_eval(dict_str)
                                     print(f"Extracted raw input from error message string: {raw_input_value}")
                                except (ValueError, SyntaxError, TypeError) as eval_err:
                                     print(f"Failed to parse raw input from error message: {eval_err}")
                                     raw_input_value = None # Reset if parsing failed
                           else:
                                print("Unable to locate complete input_value dictionary in error message.")
                      else:
                           print("'input_value=' not found in error message.")

             except Exception as parse_err:
                  print(f"Error extracting raw input from McpError details or message: {parse_err}")
                  raw_input_value = None

        # Check if we successfully got the raw input and if it contains 'toolResult'
        if raw_input_value and isinstance(raw_input_value, dict) and 'toolResult' in raw_input_value:
             # If yes, return the raw toolResult, bypassing SDK validation
             print(f"Warning: Bypassing SDK validation, returning raw toolResult to LLM.")
             return raw_input_value['toolResult'] # Return the nested toolResult dictionary
        else:
             # If it wasn't the specific error or we couldn't extract data, return a standard error message
             print(f"Unable to extract valid data from ValidationError, returning generic error message.")
             return {"error": f"MCP Error during '{tool_name}': {error_message}", "tool_name": tool_name}
        # --- End Workaround ---

    except AttributeError as ae:
         # Handle cases where the session object is missing expected methods
         error_msg = f"Error: MCP ClientSession object missing attribute/method: {ae}."
         print(error_msg)
         return {"error": error_msg, "tool_name": tool_name}
    except Exception as e:
        # Catch any other unexpected errors during the tool call
        error_msg = f"Unknown error calling MCP tool '{tool_name}': {e}"
        print(error_msg)
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return {"error": error_msg, "tool_name": tool_name}

