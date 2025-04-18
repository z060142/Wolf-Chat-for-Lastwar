# ui_interaction.py
# Refactored to separate Detection and Interaction logic.

import pyautogui
import cv2 # opencv-python
import numpy as np
import pyperclip
import time
import os
import collections
import asyncio
import pygetwindow as gw # Used to check/activate windows
import config          # Used to read window title
import queue
from typing import List, Tuple, Optional, Dict, Any

# --- Configuration Section ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# --- Template Paths (Consider moving to config.py or loading dynamically) ---
# Bubble Corners
CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "corner_tl.png")
CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "corner_tr.png")
CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "corner_bl.png")
CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "corner_br.png")
BOT_CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tl.png")
BOT_CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tr.png")
BOT_CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_bl.png")
BOT_CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_br.png")
# Keywords
KEYWORD_wolf_LOWER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower.png")
KEYWORD_Wolf_UPPER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper.png")
# UI Elements
COPY_MENU_ITEM_IMG = os.path.join(TEMPLATE_DIR, "copy_menu_item.png")
PROFILE_OPTION_IMG = os.path.join(TEMPLATE_DIR, "profile_option.png")
COPY_NAME_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "copy_name_button.png")
SEND_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "send_button.png")
CHAT_INPUT_IMG = os.path.join(TEMPLATE_DIR, "chat_input.png")
# State Detection
PROFILE_NAME_PAGE_IMG = os.path.join(TEMPLATE_DIR, "Profile_Name_page.png")
PROFILE_PAGE_IMG = os.path.join(TEMPLATE_DIR, "Profile_page.png")
CHAT_ROOM_IMG = os.path.join(TEMPLATE_DIR, "chat_room.png")
# Add World/Private chat identifiers later
WORLD_CHAT_IMG = os.path.join(TEMPLATE_DIR, "World_Label_normal.png") # Example
PRIVATE_CHAT_IMG = os.path.join(TEMPLATE_DIR, "Private_Label_normal.png") # Example

# --- Operation Parameters (Consider moving to config.py) ---
CHAT_INPUT_REGION = None # Example: (100, 800, 500, 50)
CHAT_INPUT_CENTER_X = 400
CHAT_INPUT_CENTER_Y = 1280
SCREENSHOT_REGION = None
CONFIDENCE_THRESHOLD = 0.8
STATE_CONFIDENCE_THRESHOLD = 0.7
AVATAR_OFFSET_X = -50
BBOX_SIMILARITY_TOLERANCE = 10
RECENT_TEXT_HISTORY_MAXLEN = 5 # This state likely belongs in the coordinator

# --- Helper Function (Module Level) ---
def are_bboxes_similar(bbox1: Optional[Tuple[int, int, int, int]],
                       bbox2: Optional[Tuple[int, int, int, int]],
                       tolerance: int = BBOX_SIMILARITY_TOLERANCE) -> bool:
    """Check if two bounding boxes' top-left corners are close."""
    if bbox1 is None or bbox2 is None:
        return False
    return abs(bbox1[0] - bbox2[0]) <= tolerance and abs(bbox1[1] - bbox2[1]) <= tolerance

# ==============================================================================
# Detection Module
# ==============================================================================
class DetectionModule:
    """Handles finding elements and states on the screen using image recognition."""

    def __init__(self, templates: Dict[str, str], confidence: float = CONFIDENCE_THRESHOLD, state_confidence: float = STATE_CONFIDENCE_THRESHOLD, region: Optional[Tuple[int, int, int, int]] = SCREENSHOT_REGION):
        self.templates = templates
        self.confidence = confidence
        self.state_confidence = state_confidence
        self.region = region
        self._warned_paths = set()
        print("DetectionModule initialized.")

    def _find_template(self, template_key: str, confidence: Optional[float] = None, region: Optional[Tuple[int, int, int, int]] = None, grayscale: bool = False) -> List[Tuple[int, int]]:
        """Internal helper to find a template by its key."""
        template_path = self.templates.get(template_key)
        if not template_path:
            print(f"Error: Template key '{template_key}' not found in provided templates.")
            return []

        # Check if template file exists, warn only once
        if not os.path.exists(template_path):
            if template_path not in self._warned_paths:
                print(f"Error: Template image doesn't exist: {template_path}")
                self._warned_paths.add(template_path)
            return []

        locations = []
        current_region = region if region is not None else self.region
        current_confidence = confidence if confidence is not None else self.confidence

        try:
            matches = pyautogui.locateAllOnScreen(template_path, region=current_region, confidence=current_confidence, grayscale=grayscale)
            if matches:
                for box in matches:
                    center_x = box.left + box.width // 2
                    center_y = box.top + box.height // 2
                    locations.append((center_x, center_y))
            # print(f"Found template '{template_key}' at {len(locations)} locations.") # Debug
            return locations
        except Exception as e:
            print(f"Error finding template '{template_key}' ({template_path}): {e}")
            return []

    def find_elements(self, template_keys: List[str], confidence: Optional[float] = None, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, List[Tuple[int, int]]]:
        """Find multiple templates by their keys."""
        results = {}
        for key in template_keys:
            results[key] = self._find_template(key, confidence=confidence, region=region)
        return results

    def find_dialogue_bubbles(self) -> List[Tuple[Tuple[int, int, int, int], bool]]:
        """
        Scan screen for regular and bot bubble corners and pair them.
        Returns list of (bbox, is_bot_flag). Basic matching logic.
        """
        all_bubbles_with_type = []

        # Find corners using the internal helper
        tl_corners = self._find_template('corner_tl')
        br_corners = self._find_template('corner_br')
        bot_tl_corners = self._find_template('bot_corner_tl')
        bot_br_corners = self._find_template('bot_corner_br')

        # Match regular bubbles
        processed_tls = set()
        if tl_corners and br_corners:
            for i, tl in enumerate(tl_corners):
                if i in processed_tls: continue
                potential_br = None
                min_dist_sq = float('inf')
                for j, br in enumerate(br_corners):
                    if br[0] > tl[0] + 20 and br[1] > tl[1] + 10:
                        dist_sq = (br[0] - tl[0])**2 + (br[1] - tl[1])**2
                        if dist_sq < min_dist_sq:
                            potential_br = br
                            min_dist_sq = dist_sq
                if potential_br:
                    bubble_bbox = (tl[0], tl[1], potential_br[0], potential_br[1])
                    all_bubbles_with_type.append((bubble_bbox, False))
                    processed_tls.add(i)

        # Match Bot bubbles
        processed_bot_tls = set()
        if bot_tl_corners and bot_br_corners:
            for i, tl in enumerate(bot_tl_corners):
                 if i in processed_bot_tls: continue
                 potential_br = None
                 min_dist_sq = float('inf')
                 for j, br in enumerate(bot_br_corners):
                      if br[0] > tl[0] + 20 and br[1] > tl[1] + 10:
                           dist_sq = (br[0] - tl[0])**2 + (br[1] - tl[1])**2
                           if dist_sq < min_dist_sq:
                                potential_br = br
                                min_dist_sq = dist_sq
                 if potential_br:
                      bubble_bbox = (tl[0], tl[1], potential_br[0], potential_br[1])
                      all_bubbles_with_type.append((bubble_bbox, True))
                      processed_bot_tls.add(i)

        return all_bubbles_with_type

    def find_keyword_in_region(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """Look for keywords within a specified region."""
        if region[2] <= 0 or region[3] <= 0: return None # Invalid region width/height

        # Try lowercase
        locations_lower = self._find_template('keyword_wolf_lower', region=region)
        if locations_lower:
            print(f"Found keyword (lowercase) in region {region}, position: {locations_lower[0]}")
            return locations_lower[0]

        # Try uppercase
        locations_upper = self._find_template('keyword_wolf_upper', region=region)
        if locations_upper:
            print(f"Found keyword (uppercase) in region {region}, position: {locations_upper[0]}")
            return locations_upper[0]

        return None

    def calculate_avatar_coords(self, bubble_bbox: Tuple[int, int, int, int], offset_x: int = AVATAR_OFFSET_X) -> Tuple[int, int]:
        """Calculate avatar coordinates based on bubble top-left."""
        tl_x, tl_y = bubble_bbox[0], bubble_bbox[1]
        avatar_x = tl_x + offset_x
        avatar_y = tl_y # Assuming Y is same as top-left
        # print(f"Calculated avatar coordinates: ({int(avatar_x)}, {int(avatar_y)})") # Reduce noise
        return (int(avatar_x), int(avatar_y))

    def get_current_ui_state(self) -> str:
        """Determine the current UI state based on visible elements."""
        # Check in order of specificity or likelihood
        if self._find_template('profile_name_page', confidence=self.state_confidence):
            return 'user_details'
        if self._find_template('profile_page', confidence=self.state_confidence):
            return 'profile_card'
        # Add checks for world/private chat later
        if self._find_template('world_chat', confidence=self.state_confidence): # Example
             return 'world_chat'
        if self._find_template('private_chat', confidence=self.state_confidence): # Example
             return 'private_chat'
        if self._find_template('chat_room', confidence=self.state_confidence):
            return 'chat_room' # General chat room if others aren't found

        return 'unknown'

# ==============================================================================
# Interaction Module
# ==============================================================================
class InteractionModule:
    """Handles performing actions on the UI like clicking, typing, clipboard."""

    def __init__(self, detector: DetectionModule, input_coords: Tuple[int, int] = (CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y), input_template_key: Optional[str] = 'chat_input', send_button_key: str = 'send_button'):
        self.detector = detector
        self.default_input_coords = input_coords
        self.input_template_key = input_template_key
        self.send_button_key = send_button_key
        print("InteractionModule initialized.")

    def click_at(self, x: int, y: int, button: str = 'left', clicks: int = 1, interval: float = 0.1, duration: float = 0.1):
        """Safely click at specific coordinates."""
        try:
            print(f"Moving to and clicking at: ({x}, {y}), button: {button}, clicks: {clicks}")
            pyautogui.moveTo(x, y, duration=duration)
            pyautogui.click(button=button, clicks=clicks, interval=interval)
            time.sleep(0.1)
        except Exception as e:
            print(f"Error clicking at coordinates ({x}, {y}): {e}")

    def press_key(self, key: str, presses: int = 1, interval: float = 0.1):
        """Press a specific key."""
        try:
            print(f"Pressing key: {key} ({presses} times)")
            for _ in range(presses):
                pyautogui.press(key)
                time.sleep(interval)
        except Exception as e:
            print(f"Error pressing key '{key}': {e}")

    def hotkey(self, *args):
        """Press a key combination (e.g., 'ctrl', 'c')."""
        try:
            print(f"Pressing hotkey: {args}")
            pyautogui.hotkey(*args)
            time.sleep(0.1) # Short pause after hotkey
        except Exception as e:
            print(f"Error pressing hotkey {args}: {e}")

    def get_clipboard(self) -> Optional[str]:
        """Get text from clipboard."""
        try:
            return pyperclip.paste()
        except Exception as e:
            print(f"Error reading clipboard: {e}")
            return None

    def set_clipboard(self, text: str):
        """Set clipboard text."""
        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"Error writing to clipboard: {e}")

    def copy_text_at(self, coords: Tuple[int, int]) -> Optional[str]:
        """Attempt to copy text after clicking at given coordinates."""
        print(f"Attempting to copy text at {coords}...")
        original_clipboard = self.get_clipboard() or ""
        self.set_clipboard("___MCP_CLEAR___")
        time.sleep(0.1)

        self.click_at(coords[0], coords[1])
        time.sleep(0.2) # Wait for menu/reaction

        copied = False
        # Try finding "Copy" menu item first
        copy_item_locations = self.detector._find_template('copy_menu_item', confidence=0.7) # Use detector
        if copy_item_locations:
            copy_coords = copy_item_locations[0]
            self.click_at(copy_coords[0], copy_coords[1])
            print("Clicked 'Copy' menu item.")
            time.sleep(0.2)
            copied = True
        else:
            print("'Copy' menu item not found. Attempting Ctrl+C.")
            try:
                self.hotkey('ctrl', 'c')
                time.sleep(0.2)
                print("Simulated Ctrl+C.")
                copied = True
            except Exception as e_ctrlc:
                 print(f"Failed to simulate Ctrl+C: {e_ctrlc}")
                 copied = False

        copied_text = self.get_clipboard()
        self.set_clipboard(original_clipboard) # Restore clipboard

        if copied and copied_text and copied_text != "___MCP_CLEAR___":
            print(f"Successfully copied text, length: {len(copied_text)}")
            return copied_text.strip()
        else:
            print("Error: Copy operation unsuccessful or clipboard content invalid.")
            return None

    def retrieve_sender_name_interaction(self, avatar_coords: Tuple[int, int]) -> Optional[str]:
        """
        Perform the sequence of actions to copy sender name, *without* cleanup.
        Returns the name or None if failed.
        """
        print(f"Attempting interaction to get username from avatar {avatar_coords}...")
        original_clipboard = self.get_clipboard() or ""
        self.set_clipboard("___MCP_CLEAR___")
        time.sleep(0.1)
        sender_name = None

        try:
            # 1. Click avatar
            self.click_at(avatar_coords[0], avatar_coords[1])
            time.sleep(0.3) # Wait for profile card

            # 2. Find and click profile option
            profile_option_locations = self.detector._find_template('profile_option', confidence=0.7)
            if not profile_option_locations:
                print("Error: User details option not found on profile card.")
                return None # Fail early if critical step missing
            self.click_at(profile_option_locations[0][0], profile_option_locations[0][1])
            print("Clicked user details option.")
            time.sleep(0.3) # Wait for user details window

            # 3. Find and click "Copy Name" button
            copy_name_locations = self.detector._find_template('copy_name_button', confidence=0.7)
            if not copy_name_locations:
                print("Error: 'Copy Name' button not found in user details.")
                return None # Fail early
            self.click_at(copy_name_locations[0][0], copy_name_locations[0][1])
            print("Clicked 'Copy Name' button.")
            time.sleep(0.1)

            # 4. Get name from clipboard
            copied_name = self.get_clipboard()
            if copied_name and copied_name != "___MCP_CLEAR___":
                print(f"Successfully copied username: {copied_name}")
                sender_name = copied_name.strip()
            else:
                print("Error: Clipboard content invalid after clicking copy name.")
                sender_name = None

            return sender_name

        except Exception as e:
            print(f"Error during username retrieval interaction: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Restore clipboard regardless of success/failure
            self.set_clipboard(original_clipboard)
            # NO cleanup logic here - should be handled by coordinator

    def send_chat_message(self, reply_text: str) -> bool:
        """Paste text into chat input and send it."""
        print("Preparing to send response...")
        if not reply_text:
            print("Error: Response content is empty, cannot send.")
            return False

        # Find input box coordinates
        input_coords = self.default_input_coords # Fallback
        if self.input_template_key and self.detector.templates.get(self.input_template_key):
            input_locations = self.detector._find_template(self.input_template_key, confidence=0.7)
            if input_locations:
                input_coords = input_locations[0]
                print(f"Found input box position via image: {input_coords}")
            else:
                print(f"Warning: Input box template '{self.input_template_key}' not found, using default coordinates.")
        else:
             print("Warning: Input box template key not set or image missing, using default coordinates.")

        # Click input, paste, send
        self.click_at(input_coords[0], input_coords[1])
        time.sleep(0.3)

        print("Pasting response...")
        self.set_clipboard(reply_text)
        time.sleep(0.1)
        try:
            self.hotkey('ctrl', 'v')
            time.sleep(0.5)
            print("Pasted.")
        except Exception as e:
            print(f"Error pasting response: {e}")
            return False

        # Try clicking send button first
        send_button_locations = self.detector._find_template(self.send_button_key, confidence=0.7)
        if send_button_locations:
            send_coords = send_button_locations[0]
            self.click_at(send_coords[0], send_coords[1])
            print("Clicked send button.")
            time.sleep(0.1)
            return True
        else:
            # Fallback to pressing Enter
            print("Send button not found. Attempting to press Enter.")
            try:
                self.press_key('enter')
                print("Pressed Enter.")
                time.sleep(0.5)
                return True
            except Exception as e_enter:
                print(f"Error pressing Enter: {e_enter}")
                return False

# ==============================================================================
# Coordinator Logic (Placeholder - To be implemented in main.py)
# ==============================================================================

# --- State-based Cleanup Function (To be called by Coordinator) ---
def perform_state_cleanup(detector: DetectionModule, interactor: InteractionModule, max_attempts: int = 4) -> bool:
    """
    Attempt to return to the main chat room interface by pressing ESC based on detected state.
    Returns True if confirmed back in chat room, False otherwise.
    """
    print("Performing cleanup: Attempting to press ESC to return to chat interface...")
    returned_to_chat = False
    for attempt in range(max_attempts):
        print(f"Cleanup attempt #{attempt + 1}/{max_attempts}")
        time.sleep(0.2)

        current_state = detector.get_current_ui_state()
        print(f"Detected state: {current_state}")

        if current_state == 'chat_room' or current_state == 'world_chat' or current_state == 'private_chat': # Adjust as needed
            print("Chat room interface detected, cleanup complete.")
            returned_to_chat = True
            break
        elif current_state == 'user_details' or current_state == 'profile_card':
            print(f"{current_state.replace('_', ' ').title()} detected, pressing ESC...")
            interactor.press_key('esc')
            time.sleep(0.3) # Wait longer for UI response after ESC
            continue
        else: # Unknown state
            print("Unknown page state detected.")
            if attempt < max_attempts - 1:
                 print("Trying one ESC press as fallback...")
                 interactor.press_key('esc')
                 time.sleep(0.3)
            else:
                 print("Maximum attempts reached, stopping cleanup.")
                 break

    if not returned_to_chat:
         print("Warning: Could not confirm return to chat room interface via state detection.")
    return returned_to_chat


# --- UI Monitoring Loop Function (To be run in a separate thread) ---
def run_ui_monitoring_loop(trigger_queue: queue.Queue, command_queue: queue.Queue):
    """
    Continuously monitors the UI, detects triggers, performs interactions,
    puts trigger data into trigger_queue, and processes commands from command_queue.
    """
    print("\n--- Starting UI Monitoring Loop (Thread) ---")

    # --- Initialization (Instantiate modules within the thread) ---
    # Load templates directly using constants defined in this file for now
    # Consider passing config or a template loader object in the future
    templates = {
        'corner_tl': CORNER_TL_IMG, 'corner_br': CORNER_BR_IMG,
        'bot_corner_tl': BOT_CORNER_TL_IMG, 'bot_corner_br': BOT_CORNER_BR_IMG,
        'keyword_wolf_lower': KEYWORD_wolf_LOWER_IMG, 'keyword_wolf_upper': KEYWORD_Wolf_UPPER_IMG,
        'copy_menu_item': COPY_MENU_ITEM_IMG, 'profile_option': PROFILE_OPTION_IMG,
        'copy_name_button': COPY_NAME_BUTTON_IMG, 'send_button': SEND_BUTTON_IMG,
        'chat_input': CHAT_INPUT_IMG, 'profile_name_page': PROFILE_NAME_PAGE_IMG,
        'profile_page': PROFILE_PAGE_IMG, 'chat_room': CHAT_ROOM_IMG,
        'world_chat': WORLD_CHAT_IMG, 'private_chat': PRIVATE_CHAT_IMG # Add other templates as needed
    }
    # Use default confidence/region settings from constants
    detector = DetectionModule(templates, confidence=CONFIDENCE_THRESHOLD, state_confidence=STATE_CONFIDENCE_THRESHOLD, region=SCREENSHOT_REGION)
    # Use default input coords/keys from constants
    interactor = InteractionModule(detector, input_coords=(CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y), input_template_key='chat_input', send_button_key='send_button')

    # --- State Management (Local to this monitoring thread) ---
    last_processed_bubble_bbox = None
    recent_texts = collections.deque(maxlen=RECENT_TEXT_HISTORY_MAXLEN) # Context-specific history needed

    while True:
        # --- Process Commands First (Non-blocking) ---
        try:
            command_data = command_queue.get_nowait() # Check for commands without blocking
            action = command_data.get('action')
            if action == 'send_reply':
                text_to_send = command_data.get('text')
                if text_to_send:
                    print(f"UI Thread: Received command to send reply: '{text_to_send[:50]}...'")
                    interactor.send_chat_message(text_to_send)
                else:
                    print("UI Thread: Received send_reply command with no text.")
            else:
                print(f"UI Thread: Received unknown command: {action}")
        except queue.Empty:
            pass # No command waiting, continue with monitoring
        except Exception as cmd_err:
            print(f"UI Thread: Error processing command queue: {cmd_err}")

        # --- Then Perform UI Monitoring ---
        try:
            # 1. Detect Bubbles
            all_bubbles = detector.find_dialogue_bubbles()
            if not all_bubbles: time.sleep(2); continue

            # Filter out bot bubbles, find newest non-bot bubble (example logic)
            other_bubbles = [bbox for bbox, is_bot in all_bubbles if not is_bot]
            if not other_bubbles: time.sleep(2); continue
            # Simple logic: assume lowest bubble is newest (might need improvement)
            target_bubble = max(other_bubbles, key=lambda b: b[3]) # b[3] is y_max

            # 2. Check for Duplicates (Position & Content)
            if are_bboxes_similar(target_bubble, last_processed_bubble_bbox):
                time.sleep(2); continue

            # 3. Detect Keyword in Bubble
            bubble_region = (target_bubble[0], target_bubble[1], target_bubble[2]-target_bubble[0], target_bubble[3]-target_bubble[1])
            keyword_coords = detector.find_keyword_in_region(bubble_region)

            if keyword_coords:
                print(f"\n!!! Keyword detected in bubble {target_bubble} !!!")

                # 4. Interact: Get Bubble Text
                bubble_text = interactor.copy_text_at(keyword_coords)
                if not bubble_text:
                    print("Error: Could not get dialogue content.")
                    last_processed_bubble_bbox = target_bubble # Mark as processed even if failed
                    perform_state_cleanup(detector, interactor) # Attempt cleanup after failed copy
                    continue

                # Check recent text history (needs context awareness)
                if bubble_text in recent_texts:
                    print(f"Content '{bubble_text[:30]}...' in recent history, skipping.")
                    last_processed_bubble_bbox = target_bubble
                    continue

                print(">>> New trigger event <<<")
                last_processed_bubble_bbox = target_bubble
                recent_texts.append(bubble_text)

                # 5. Interact: Get Sender Name
                avatar_coords = detector.calculate_avatar_coords(target_bubble)
                sender_name = interactor.retrieve_sender_name_interaction(avatar_coords)

                # 6. Perform Cleanup (Crucial after potentially leaving chat screen)
                cleanup_successful = perform_state_cleanup(detector, interactor)
                if not cleanup_successful:
                    print("Error: Failed to return to chat screen after getting name. Aborting trigger.")
                    continue # Skip putting in queue if cleanup failed

                if not sender_name:
                    print("Error: Could not get sender name, aborting processing.")
                    continue # Already cleaned up, just skip

                # 7. Send Trigger Info to Main Thread/Async Loop
                print("\n>>> Putting trigger info in Queue <<<")
                print(f"   Sender: {sender_name}")
                print(f"   Content: {bubble_text[:100]}...")
                try:
                    data_to_send = {'sender': sender_name, 'text': bubble_text}
                    trigger_queue.put(data_to_send) # Put in the queue for main loop
                    print("Trigger info placed in Queue.")
                except Exception as q_err:
                    print(f"Error putting data in Queue: {q_err}")

                print("--- Single trigger processing complete ---")
                time.sleep(1) # Pause after successful trigger

            time.sleep(1.5) # Polling interval

        except KeyboardInterrupt:
            print("\nMonitoring interrupted.")
            break
        except Exception as e:
            print(f"Unknown error in monitoring loop: {e}")
            import traceback
            traceback.print_exc()
            # Attempt cleanup in case of unexpected error during interaction
            print("Attempting cleanup after unexpected error...")
            perform_state_cleanup(detector, interactor)
            print("Waiting 5 seconds before retry...")
            time.sleep(5)

# Note: The old monitor_chat_for_trigger function is replaced by the example_coordinator_loop.
# The actual UI monitoring thread started in main.py should call a function like this example loop.
# The main async loop in main.py will handle getting items from the queue and interacting with the LLM.

# if __name__ == '__main__':
#     # This module is not meant to be run directly after refactoring.
#     # Initialization and coordination happen in main.py.
#     pass
