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
import threading # Import threading for Lock if needed, or just use a simple flag

# --- Global Pause Flag ---
# Using a simple mutable object (list) for thread-safe-like access without explicit lock
# Or could use threading.Event()
monitoring_paused_flag = [False] # List containing a boolean

# --- Configuration Section ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# --- Debugging ---
DEBUG_SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "debug_screenshots")
MAX_DEBUG_SCREENSHOTS = 8
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)
# --- End Debugging ---

# --- Template Paths (Consider moving to config.py or loading dynamically) ---
# Bubble Corners
CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "corner_tl.png")
# CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "corner_tr.png") # Unused
# CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "corner_bl.png") # Unused
CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "corner_br.png")
# --- Additional Regular Bubble Types (Skins) ---
CORNER_TL_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "corner_tl_type2.png") # Added
CORNER_BR_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "corner_br_type2.png") # Added
CORNER_TL_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "corner_tl_type3.png") # Added
CORNER_BR_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "corner_br_type3.png") # Added
# --- End Additional Regular Types ---
BOT_CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tl.png")
# BOT_CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tr.png") # Unused
# BOT_CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_bl.png") # Unused
BOT_CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_br.png")
# --- Additional Bot Bubble Types (Skins) ---
# Type 2
BOT_CORNER_TL_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tl_type2.png")
BOT_CORNER_BR_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_br_type2.png")
# Type 3
BOT_CORNER_TL_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tl_type3.png")
BOT_CORNER_BR_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_br_type3.png")
# --- End Additional Types ---
# Keywords
KEYWORD_wolf_LOWER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower.png")
KEYWORD_Wolf_UPPER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper.png")
KEYWORD_wolf_LOWER_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower_type3.png") # Added for type3 bubbles
KEYWORD_Wolf_UPPER_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper_type3.png") # Added for type3 bubbles
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
BASE_SCREEN_IMG = os.path.join(TEMPLATE_DIR, "base.png") # Added for navigation
WORLD_MAP_IMG = os.path.join(TEMPLATE_DIR, "World_map.png") # Added for navigation
# Add World/Private chat identifiers later
WORLD_CHAT_IMG = os.path.join(TEMPLATE_DIR, "World_Label_normal.png") # Example
PRIVATE_CHAT_IMG = os.path.join(TEMPLATE_DIR, "Private_Label_normal.png") # Example

# Position Icons (Near Bubble)
POS_DEV_IMG = os.path.join(TEMPLATE_DIR, "positions", "development.png")
POS_INT_IMG = os.path.join(TEMPLATE_DIR, "positions", "interior.png")
POS_SCI_IMG = os.path.join(TEMPLATE_DIR, "positions", "science.png")
POS_SEC_IMG = os.path.join(TEMPLATE_DIR, "positions", "security.png")
POS_STR_IMG = os.path.join(TEMPLATE_DIR, "positions", "strategy.png")

# Capitol Page Elements
CAPITOL_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "capitol", "capitol_#11.png")
PRESIDENT_TITLE_IMG = os.path.join(TEMPLATE_DIR, "capitol", "president_title.png")
POS_BTN_DEV_IMG = os.path.join(TEMPLATE_DIR, "capitol", "position_development.png")
POS_BTN_INT_IMG = os.path.join(TEMPLATE_DIR, "capitol", "position_interior.png")
POS_BTN_SCI_IMG = os.path.join(TEMPLATE_DIR, "capitol", "position_science.png")
POS_BTN_SEC_IMG = os.path.join(TEMPLATE_DIR, "capitol", "position_security.png")
POS_BTN_STR_IMG = os.path.join(TEMPLATE_DIR, "capitol", "position_strategy.png")
PAGE_DEV_IMG = os.path.join(TEMPLATE_DIR, "capitol", "page_DEVELOPMENT.png")
PAGE_INT_IMG = os.path.join(TEMPLATE_DIR, "capitol", "page_INTERIOR.png")
PAGE_SCI_IMG = os.path.join(TEMPLATE_DIR, "capitol", "page_SCIENCE.png")
PAGE_SEC_IMG = os.path.join(TEMPLATE_DIR, "capitol", "page_SECURITY.png")
PAGE_STR_IMG = os.path.join(TEMPLATE_DIR, "capitol", "page_STRATEGY.png")
DISMISS_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "capitol", "dismiss.png")
CONFIRM_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "capitol", "confirm.png")
CLOSE_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "capitol", "close_button.png")
BACK_ARROW_IMG = os.path.join(TEMPLATE_DIR, "capitol", "black_arrow_down.png")
REPLY_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "reply_button.png") # Added for reply functionality


# --- Operation Parameters (Consider moving to config.py) ---
CHAT_INPUT_REGION = None # Example: (100, 800, 500, 50)
CHAT_INPUT_CENTER_X = 400
CHAT_INPUT_CENTER_Y = 1280
SCREENSHOT_REGION = None
CONFIDENCE_THRESHOLD = 0.9 # Increased threshold for corner matching
STATE_CONFIDENCE_THRESHOLD = 0.7
AVATAR_OFFSET_X = -55 # Original offset, used for non-reply interactions like position removal
# AVATAR_OFFSET_X_RELOCATED = -50 # Replaced by specific reply offsets
AVATAR_OFFSET_X_REPLY = -45 # Horizontal offset for avatar click after re-location (for reply context)
AVATAR_OFFSET_Y_REPLY = 10  # Vertical offset for avatar click after re-location (for reply context)
BUBBLE_RELOCATE_CONFIDENCE = 0.8 # Reduced confidence for finding the bubble snapshot (was 0.9)
BUBBLE_RELOCATE_FALLBACK_CONFIDENCE = 0.6 # Lower confidence for fallback attempts
BBOX_SIMILARITY_TOLERANCE = 10
RECENT_TEXT_HISTORY_MAXLEN = 5 # This state likely belongs in the coordinator

# --- Helper Function (Module Level) ---
def are_bboxes_similar(bbox1: Optional[Tuple[int, int, int, int]],
                       bbox2: Optional[Tuple[int, int, int, int]],
                       tolerance: int = BBOX_SIMILARITY_TOLERANCE) -> bool:
    """Check if two bounding boxes' top-left corners are close."""
    if bbox1 is None or bbox2 is None:
        return False
    # Compare based on bbox top-left (index 0 and 1)
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
        """Internal helper to find a template by its key. Returns list of CENTER coordinates."""
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
            # locateAllOnScreen returns Box objects (left, top, width, height)
            matches = pyautogui.locateAllOnScreen(template_path, region=current_region, confidence=current_confidence, grayscale=grayscale)
            if matches:
                for box in matches:
                    # Calculate center coordinates from the Box object
                    center_x = box.left + box.width // 2
                    center_y = box.top + box.height // 2
                    locations.append((center_x, center_y))
            # print(f"Found template '{template_key}' at {len(locations)} locations.") # Debug
            return locations
        except Exception as e:
            print(f"Error finding template '{template_key}' ({template_path}): {e}")
            return []

    def _find_template_raw(self, template_key: str, confidence: Optional[float] = None, region: Optional[Tuple[int, int, int, int]] = None, grayscale: bool = False) -> List[Tuple[int, int, int, int]]:
        """Internal helper to find a template by its key. Returns list of raw Box tuples (left, top, width, height)."""
        template_path = self.templates.get(template_key)
        if not template_path:
            print(f"Error: Template key '{template_key}' not found in provided templates.")
            return []
        if not os.path.exists(template_path):
            if template_path not in self._warned_paths:
                print(f"Error: Template image doesn't exist: {template_path}")
                self._warned_paths.add(template_path)
            return []

        locations = []
        current_region = region if region is not None else self.region
        current_confidence = confidence if confidence is not None else self.confidence
        try:
            # --- Temporary Debug Print ---
            print(f"DEBUG: Searching for template '{template_key}' with confidence {current_confidence}...")
            # --- End Temporary Debug Print ---
            matches = pyautogui.locateAllOnScreen(template_path, region=current_region, confidence=current_confidence, grayscale=grayscale)
            match_count = 0 # Initialize count
            if matches:
                for box in matches:
                    locations.append((box.left, box.top, box.width, box.height))
                    match_count += 1 # Increment count
            # --- Temporary Debug Print ---
            print(f"DEBUG: Found {match_count} instance(s) of template '{template_key}'.")
            # --- End Temporary Debug Print ---
            return locations
        except Exception as e:
            print(f"Error finding template raw '{template_key}' ({template_path}): {e}")
            return []

    def find_elements(self, template_keys: List[str], confidence: Optional[float] = None, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, List[Tuple[int, int]]]:
        """Find multiple templates by their keys. Returns center coordinates."""
        results = {}
        for key in template_keys:
            results[key] = self._find_template(key, confidence=confidence, region=region)
        return results

    def find_dialogue_bubbles(self) -> List[Dict[str, Any]]:
        """
        Scan screen for regular and multiple types of bot bubble corners and pair them.
        Returns a list of dictionaries, each containing:
        {'bbox': (tl_x, tl_y, br_x, br_y), 'is_bot': bool, 'tl_coords': (original_tl_x, original_tl_y)}
        """
        all_bubbles_info = []
        processed_tls = set() # Keep track of TL corners already used in a bubble

        # --- Find ALL Regular Bubble Corners (Raw Coordinates) ---
        regular_tl_keys = ['corner_tl', 'corner_tl_type2', 'corner_tl_type3'] # Modified
        regular_br_keys = ['corner_br', 'corner_br_type2', 'corner_br_type3'] # Modified

        all_regular_tl_boxes = []
        for key in regular_tl_keys:
            all_regular_tl_boxes.extend(self._find_template_raw(key))

        all_regular_br_boxes = []
        for key in regular_br_keys:
            all_regular_br_boxes.extend(self._find_template_raw(key))

        # --- Find Bot Bubble Corners (Raw Coordinates - Single Type) ---
        bot_tl_boxes = self._find_template_raw('bot_corner_tl') # Modified
        bot_br_boxes = self._find_template_raw('bot_corner_br') # Modified

        # --- Match Regular Bubbles (Any Type TL with Any Type BR) ---
        if all_regular_tl_boxes and all_regular_br_boxes:
            for tl_box in all_regular_tl_boxes:
                tl_coords = (tl_box[0], tl_box[1]) # Extract original TL (left, top)
                # Skip if this TL is already part of a matched bubble
                if tl_coords in processed_tls: continue

                potential_br_box = None
                min_y_diff = float('inf') # Prioritize minimum Y difference
                # Find the valid BR corner (from any regular type) with the closest Y-coordinate
                for br_box in all_regular_br_boxes:
                    br_coords = (br_box[0], br_box[1]) # BR top-left
                    # Basic geometric check: BR must be below and to the right of TL
                    if br_coords[0] > tl_coords[0] + 20 and br_coords[1] > tl_coords[1] + 10:
                        y_diff = abs(br_coords[1] - tl_coords[1]) # Calculate Y difference
                        if y_diff < min_y_diff:
                            potential_br_box = br_box
                            min_y_diff = y_diff
                        # Optional: Add a secondary check for X distance if Y diff is the same?
                        # elif y_diff == min_y_diff:
                        #    if potential_br_box is None or abs(br_coords[0] - tl_coords[0]) < abs(potential_br_box[0] - tl_coords[0]):
                        #         potential_br_box = br_box

                if potential_br_box:
                    # Calculate bbox using TL's top-left and BR's bottom-right
                    bubble_bbox = (tl_coords[0], tl_coords[1],
                                   potential_br_box[0] + potential_br_box[2], potential_br_box[1] + potential_br_box[3])
                    all_bubbles_info.append({
                        'bbox': bubble_bbox,
                        'is_bot': False,
                        'tl_coords': tl_coords # Store the original TL coords
                    })
                    processed_tls.add(tl_coords) # Mark this TL as used

        # --- Match Bot Bubbles (Single Type) ---
        if bot_tl_boxes and bot_br_boxes:
            for tl_box in bot_tl_boxes:
                tl_coords = (tl_box[0], tl_box[1]) # Extract original TL (left, top)
                # Skip if this TL is already part of a matched bubble
                if tl_coords in processed_tls: continue

                potential_br_box = None
                min_y_diff = float('inf') # Prioritize minimum Y difference
                # Find the valid BR corner with the closest Y-coordinate
                for br_box in bot_br_boxes:
                    br_coords = (br_box[0], br_box[1]) # BR top-left
                    # Basic geometric check: BR must be below and to the right of TL
                    if br_coords[0] > tl_coords[0] + 20 and br_coords[1] > tl_coords[1] + 10:
                        y_diff = abs(br_coords[1] - tl_coords[1]) # Calculate Y difference
                        if y_diff < min_y_diff:
                            potential_br_box = br_box
                            min_y_diff = y_diff
                        # Optional: Add a secondary check for X distance if Y diff is the same?
                        # elif y_diff == min_y_diff:
                        #    if potential_br_box is None or abs(br_coords[0] - tl_coords[0]) < abs(potential_br_box[0] - tl_coords[0]):
                        #         potential_br_box = br_box

                if potential_br_box:
                    # Calculate bbox using TL's top-left and BR's bottom-right
                    bubble_bbox = (tl_coords[0], tl_coords[1],
                                   potential_br_box[0] + potential_br_box[2], potential_br_box[1] + potential_br_box[3])
                    all_bubbles_info.append({
                        'bbox': bubble_bbox,
                        'is_bot': True,
                        'tl_coords': tl_coords # Store the original TL coords
                    })
                    processed_tls.add(tl_coords) # Mark this TL as used

        # Note: This logic prioritizes matching regular bubbles first, then bot bubbles.
        # Confidence thresholds might need tuning.
        return all_bubbles_info

    def find_keyword_in_region(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """Look for keywords within a specified region. Returns center coordinates."""
        if region[2] <= 0 or region[3] <= 0: return None # Invalid region width/height

        # Try original lowercase with color matching
        locations_lower = self._find_template('keyword_wolf_lower', region=region, grayscale=False) # Changed grayscale to False
        if locations_lower:
            print(f"Found keyword (lowercase, color) in region {region}, position: {locations_lower[0]}") # Updated log message
            return locations_lower[0]

        # Try original uppercase with color matching
        locations_upper = self._find_template('keyword_wolf_upper', region=region, grayscale=False) # Changed grayscale to False
        if locations_upper:
            print(f"Found keyword (uppercase, color) in region {region}, position: {locations_upper[0]}") # Updated log message
            return locations_upper[0]

        # Try type3 lowercase (white text, no grayscale)
        locations_lower_type3 = self._find_template('keyword_wolf_lower_type3', region=region, grayscale=False) # Added type3 check
        if locations_lower_type3:
            print(f"Found keyword (lowercase, type3) in region {region}, position: {locations_lower_type3[0]}")
            return locations_lower_type3[0]

        # Try type3 uppercase (white text, no grayscale)
        locations_upper_type3 = self._find_template('keyword_wolf_upper_type3', region=region, grayscale=False) # Added type3 check
        if locations_upper_type3:
            print(f"Found keyword (uppercase, type3) in region {region}, position: {locations_upper_type3[0]}")
            return locations_upper_type3[0]

        return None

    def calculate_avatar_coords(self, bubble_tl_coords: Tuple[int, int], offset_x: int = AVATAR_OFFSET_X) -> Tuple[int, int]:
        """
        Calculate avatar coordinates based on the EXACT top-left corner coordinates of the bubble.
        Uses the Y-coordinate of the TL corner directly.
        """
        tl_x, tl_y = bubble_tl_coords[0], bubble_tl_coords[1]
        avatar_x = tl_x + offset_x
        avatar_y = tl_y # Use the exact Y from the detected TL corner
        # print(f"Calculated avatar coordinates using TL {bubble_tl_coords}: ({int(avatar_x)}, {int(avatar_y)})") # Reduce noise
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
        time.sleep(0.1) # Wait for menu/reaction

        copied = False
        # Try finding "Copy" menu item first
        copy_item_locations = self.detector._find_template('copy_menu_item', confidence=0.7) # Use detector
        if copy_item_locations:
            copy_coords = copy_item_locations[0]
            self.click_at(copy_coords[0], copy_coords[1])
            print("Clicked 'Copy' menu item.")
            time.sleep(0.15)
            copied = True
        else:
            print("'Copy' menu item not found. Attempting Ctrl+C.")
            try:
                self.hotkey('ctrl', 'c')
                time.sleep(0.1)
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

    def retrieve_sender_name_interaction(self,
                                         initial_avatar_coords: Tuple[int, int],
                                         bubble_snapshot: Any, # PIL Image object
                                         search_area: Optional[Tuple[int, int, int, int]]) -> Optional[str]:
        """
        Perform the sequence of actions to copy sender name, *without* cleanup.
        Includes retries with bubble re-location if the initial avatar click fails.
        Returns the name or None if failed.
        """
        print(f"Attempting interaction to get username, initial avatar guess: {initial_avatar_coords}...")
        original_clipboard = self.get_clipboard() or ""
        self.set_clipboard("___MCP_CLEAR___")
        time.sleep(0.1)
        sender_name = None
        profile_page_found = False
        current_avatar_coords = initial_avatar_coords

        for attempt in range(3): # Retry up to 3 times
            print(f"Attempt #{attempt + 1} to click avatar and find profile page...")

            # --- Re-locate bubble on retries ---
            if attempt > 0:
                print("Re-locating bubble before retry...")
                if bubble_snapshot is None:
                    print("Error: Cannot retry re-location, bubble snapshot is missing.")
                    break # Cannot retry without snapshot

                new_bubble_box_retry = pyautogui.locateOnScreen(bubble_snapshot, region=search_area, confidence=BUBBLE_RELOCATE_CONFIDENCE)
                if new_bubble_box_retry:
                    new_tl_x_retry, new_tl_y_retry = new_bubble_box_retry.left, new_bubble_box_retry.top
                    print(f"Successfully re-located bubble snapshot for retry at: ({new_tl_x_retry}, {new_tl_y_retry})")
                    # Recalculate avatar coords for the retry
                    current_avatar_coords = (new_tl_x_retry + AVATAR_OFFSET_X_REPLY, new_tl_y_retry + AVATAR_OFFSET_Y_REPLY)
                    print(f"Recalculated avatar coordinates for retry: {current_avatar_coords}")
                else:
                    print("Warning: Failed to re-locate bubble snapshot on retry. Aborting name retrieval.")
                    break # Stop retrying if bubble can't be found

            # --- Click Avatar ---
            try:
                self.click_at(current_avatar_coords[0], current_avatar_coords[1])
                time.sleep(0.15) # Slightly longer wait after click to allow UI to update
            except Exception as click_err:
                print(f"Error clicking avatar at {current_avatar_coords} on attempt {attempt + 1}: {click_err}")
                time.sleep(0.3) # Wait a bit longer after a click error before retrying
                continue # Go to next attempt

            # --- Check for Profile Page ---
            if self.detector._find_template('profile_page', confidence=self.detector.state_confidence):
                print("Profile page verified.")
                profile_page_found = True
                break # Success, exit retry loop
            else:
                print(f"Profile page not found after click attempt {attempt + 1}.")
                # Optional: Press ESC once to close potential wrong menus before retrying?
                # self.press_key('esc')
                # time.sleep(0.1)
                time.sleep(0.3) # Wait before next attempt

        # --- If Profile Page was found, proceed ---
        if profile_page_found:
            try:
                # 2. Find and click profile option
                profile_option_locations = self.detector._find_template('profile_option', confidence=0.7)
                if not profile_option_locations:
                    print("Error: User details option not found on profile card.")
                    return None # Fail early if critical step missing
                self.click_at(profile_option_locations[0][0], profile_option_locations[0][1])
                print("Clicked user details option.")
                time.sleep(0.1) # Wait for user details window

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

            except Exception as e:
                print(f"Error during username retrieval interaction (after profile page found): {e}")
                import traceback
                traceback.print_exc()
                sender_name = None # Ensure None is returned on error
        else:
             print("Failed to verify profile page after multiple attempts.")
             sender_name = None

        # --- Final Cleanup & Return ---
        self.set_clipboard(original_clipboard) # Restore clipboard
        # NO cleanup logic (like ESC) here - should be handled by coordinator after this function returns
        return sender_name

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
        time.sleep(0.1)

        print("Pasting response...")
        self.set_clipboard(reply_text)
        time.sleep(0.1)
        try:
            self.hotkey('ctrl', 'v')
            time.sleep(0.1)
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
                time.sleep(0.1)
                return True
            except Exception as e_enter:
                print(f"Error pressing Enter: {e_enter}")
                return False

# ==============================================================================
# Position Removal Logic
# ==============================================================================
def remove_user_position(detector: DetectionModule,
                         interactor: InteractionModule,
                         trigger_bubble_region: Tuple[int, int, int, int], # Original region, might be outdated
                         bubble_snapshot: Any, # PIL Image object for re-location
                         search_area: Optional[Tuple[int, int, int, int]]) -> bool: # Area to search snapshot in
    """
    Performs the sequence of UI actions to remove a user's position based on the triggering chat bubble.
    Includes re-location using the provided snapshot before proceeding.
    Returns True if successful, False otherwise.
    """
    print(f"\n--- Starting Position Removal Process (Initial Trigger Region: {trigger_bubble_region}) ---")

    # --- Re-locate Bubble First ---
    print("Attempting to re-locate bubble using snapshot before removing position...")
    # If bubble_snapshot is None, try to create one from the trigger_bubble_region
    if bubble_snapshot is None:
        print("Bubble snapshot is missing. Attempting to create a new snapshot from the trigger region...")
        try:
            if trigger_bubble_region and len(trigger_bubble_region) == 4:
                bubble_region_tuple = (int(trigger_bubble_region[0]), int(trigger_bubble_region[1]), 
                                      int(trigger_bubble_region[2]), int(trigger_bubble_region[3]))
                
                if bubble_region_tuple[2] <= 0 or bubble_region_tuple[3] <= 0:
                    print(f"Warning: Invalid bubble region {bubble_region_tuple} for taking new snapshot.")
                    return False
                
                print(f"Taking new screenshot of region: {bubble_region_tuple}")
                bubble_snapshot = pyautogui.screenshot(region=bubble_region_tuple)
                if bubble_snapshot:
                    print("Successfully created new bubble snapshot.")
                else:
                    print("Failed to create new bubble snapshot.")
                    return False
            else:
                print("Invalid trigger_bubble_region format, cannot create snapshot.")
                return False
        except Exception as e:
            print(f"Error creating new bubble snapshot: {e}")
            return False
    if search_area is None:
        print("Warning: Search area for snapshot is missing. Creating a default search area.")
        # Create a default search area centered around the original trigger region
        # This creates a search area that's twice the size of the original bubble
        if trigger_bubble_region and len(trigger_bubble_region) == 4:
            x, y, width, height = trigger_bubble_region
            # Expand by 100% in each direction
            search_x = max(0, x - width//2)
            search_y = max(0, y - height//2)
            search_width = width * 2
            search_height = height * 2
            search_area = (search_x, search_y, search_width, search_height)
            print(f"Created default search area based on bubble region: {search_area}")
        else:
            # If no valid trigger_bubble_region, default to full screen search
            search_area = None # Set search_area to None for full screen search
            print(f"Using full screen search as fallback.")

    # Try to locate the bubble with decreasing confidence levels if needed
    new_bubble_box = None

    # Determine the region to search: use provided search_area or None for full screen
    region_to_search = search_area
    print(f"Attempting bubble location. Search Region: {'Full Screen' if region_to_search is None else region_to_search}")

    # First attempt with standard confidence
    print(f"First attempt with confidence {BUBBLE_RELOCATE_CONFIDENCE}...")
    try:
        new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                region=region_to_search,
                                                confidence=BUBBLE_RELOCATE_CONFIDENCE)
    except Exception as e:
        print(f"Exception during initial bubble location attempt: {e}")

    # Second attempt with fallback confidence if first failed
    if not new_bubble_box:
        print(f"First attempt failed. Trying with lower confidence {BUBBLE_RELOCATE_FALLBACK_CONFIDENCE}...")
        try:
            # Try with a lower confidence threshold
            new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                    region=region_to_search,
                                                    confidence=BUBBLE_RELOCATE_FALLBACK_CONFIDENCE)
        except Exception as e:
            print(f"Exception during fallback bubble location attempt: {e}")

    # Third attempt with even lower confidence as last resort
    if not new_bubble_box:
        print("Second attempt failed. Trying with even lower confidence 0.4...")
        try:
            # Last resort with very low confidence
            new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                   region=region_to_search,
                                                   confidence=0.4)
        except Exception as e:
            print(f"Exception during last resort bubble location attempt: {e}")

    # If we still can't find the bubble using snapshot, try re-detecting bubbles
    if not new_bubble_box:
        print("Snapshot location failed. Attempting secondary fallback: Re-detecting bubbles...")
        try:
            # Helper function to calculate distance - define it here or move globally if used elsewhere
            def calculate_distance(p1, p2):
                return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5

            current_bubbles_info = detector.find_dialogue_bubbles()
            non_bot_bubbles = [b for b in current_bubbles_info if not b.get('is_bot')]

            if non_bot_bubbles and trigger_bubble_region and len(trigger_bubble_region) == 4:
                original_tl = (trigger_bubble_region[0], trigger_bubble_region[1])
                closest_bubble = None
                min_distance = float('inf')
                MAX_ALLOWED_DISTANCE = 150 # Example threshold: Don't match bubbles too far away

                for bubble_info in non_bot_bubbles:
                    bubble_bbox = bubble_info.get('bbox')
                    if bubble_bbox:
                        current_tl = (bubble_bbox[0], bubble_bbox[1])
                        distance = calculate_distance(original_tl, current_tl)
                        if distance < min_distance:
                            min_distance = distance
                            closest_bubble = bubble_info

                if closest_bubble and min_distance <= MAX_ALLOWED_DISTANCE:
                    print(f"Found a close bubble via re-detection (Distance: {min_distance:.2f}). Using its bbox.")
                    bbox = closest_bubble['bbox']
                    # Create a dummy box using PyAutoGUI's Box class or a similar structure
                    from collections import namedtuple
                    Box = namedtuple('Box', ['left', 'top', 'width', 'height'])
                    new_bubble_box = Box(left=bbox[0], top=bbox[1], width=bbox[2]-bbox[0], height=bbox[3]-bbox[1])
                    print(f"Created fallback bubble box from re-detected bubble: {new_bubble_box}")
                else:
                    print(f"Re-detection fallback failed: No close bubble found (Min distance: {min_distance:.2f} > Threshold: {MAX_ALLOWED_DISTANCE}).")
            else:
                print("Re-detection fallback failed: No non-bot bubbles found or invalid trigger region.")

        except Exception as redetect_err:
            print(f"Error during bubble re-detection fallback: {redetect_err}")


    # Final fallback: If STILL no bubble box, use original trigger region
    if not new_bubble_box:
        print("All location attempts failed (snapshot & re-detection). Using original trigger region as last resort.")
        if trigger_bubble_region and len(trigger_bubble_region) == 4:
            # Create a mock bubble_box from the original region
            x, y, width, height = trigger_bubble_region
            print(f"Using original trigger region as fallback: {trigger_bubble_region}")
            
            # Create a dummy box using PyAutoGUI's Box class or a similar structure
            from collections import namedtuple
            Box = namedtuple('Box', ['left', 'top', 'width', 'height'])
            new_bubble_box = Box(left=x, top=y, width=width, height=height)
            print("Created fallback bubble box from original coordinates.")
        else:
            print("Error: No original trigger region available for fallback. Aborting position removal.")
            return False

    # Use the NEW coordinates for all subsequent calculations
    bubble_x, bubble_y = new_bubble_box.left, new_bubble_box.top
    bubble_w, bubble_h = new_bubble_box.width, new_bubble_box.height
    print(f"Successfully re-located bubble at: ({bubble_x}, {bubble_y}, {bubble_w}, {bubble_h})")
    # --- End Re-location ---


    # 1. Find the closest position icon above the *re-located* bubble
    search_height_pixels = 50 # Search exactly 50 pixels above as requested
    search_region_y_end = bubble_y # Use re-located Y
    search_region_y_start = max(0, bubble_y - search_height_pixels) # Search 50 pixels above
    search_region_x_start = max(0, bubble_x - 100) # Keep horizontal search wide
    search_region_x_end = bubble_x + bubble_w + 100
    search_region_width = search_region_x_end - search_region_x_start
    search_region_height = search_region_y_end - search_region_y_start
    
    # Ensure region has positive width and height
    if search_region_width <= 0 or search_region_height <= 0:
        print(f"Error: Invalid search region calculated for position icons: width={search_region_width}, height={search_region_height}")
        return False
        
    search_region = (search_region_x_start, search_region_y_start, search_region_width, search_region_height)
    print(f"Searching for position icons in region: {search_region}")

    position_templates = {
        'DEVELOPMENT': POS_DEV_IMG, 'INTERIOR': POS_INT_IMG, 'SCIENCE': POS_SCI_IMG,
        'SECURITY': POS_SEC_IMG, 'STRATEGY': POS_STR_IMG
    }
    found_positions = []
    position_icon_confidence = 0.8 # Slightly increased confidence (was 0.75)
    for name, path in position_templates.items():
        # Use unique keys for detector templates
        locations = detector._find_template(name.lower() + '_pos', confidence=position_icon_confidence, region=search_region)
        for loc in locations:
            found_positions.append({'name': name, 'coords': loc, 'path': path})

    if not found_positions:
        print("Error: No position icons found near the trigger bubble.")
        return False

    # Find the closest one to the bubble's top-center
    bubble_top_center_x = bubble_x + bubble_w // 2
    bubble_top_center_y = bubble_y
    closest_position = min(found_positions, key=lambda p:
                           (p['coords'][0] - bubble_top_center_x)**2 + (p['coords'][1] - bubble_top_center_y)**2)

    target_position_name = closest_position['name']
    print(f"Found pending position: |{target_position_name}| at {closest_position['coords']}")

    # 2. Click user avatar (offset from *re-located* bubble top-left)
    # --- MODIFIED: Use specific offsets for remove_position command as requested ---
    avatar_click_x = bubble_x + AVATAR_OFFSET_X_REPLY # Use -45 offset
    avatar_click_y = bubble_y + AVATAR_OFFSET_Y_REPLY # Use +10 offset
    print(f"Clicking avatar for position removal at calculated position: ({avatar_click_x}, {avatar_click_y}) using offsets ({AVATAR_OFFSET_X_REPLY}, {AVATAR_OFFSET_Y_REPLY}) from re-located bubble top-left ({bubble_x}, {bubble_y})")
    # --- END MODIFICATION ---
    interactor.click_at(avatar_click_x, avatar_click_y)
    time.sleep(0.15) # Wait for profile page

    # 3. Verify Profile Page and Click Capitol Button
    if not detector._find_template('profile_page', confidence=detector.state_confidence):
        print("Error: Failed to verify Profile Page after clicking avatar.")
        perform_state_cleanup(detector, interactor) # Attempt cleanup
        return False
    print("Profile page verified.")

    capitol_button_locs = detector._find_template('capitol_button', confidence=0.8)
    if not capitol_button_locs:
        print("Error: Capitol button (#11) not found on profile page.")
        perform_state_cleanup(detector, interactor)
        return False
    interactor.click_at(capitol_button_locs[0][0], capitol_button_locs[0][1])
    print("Clicked Capitol button.")
    time.sleep(0.15) # Wait for capitol page

    # 4. Verify Capitol Page
    if not detector._find_template('president_title', confidence=detector.state_confidence):
        print("Error: Failed to verify Capitol Page (President Title not found).")
        perform_state_cleanup(detector, interactor)
        return False
    print("Capitol page verified.")

    # 5. Find and Click Corresponding Position Button
    position_button_templates = {
        'DEVELOPMENT': 'pos_btn_dev', 'INTERIOR': 'pos_btn_int', 'SCIENCE': 'pos_btn_sci',
        'SECURITY': 'pos_btn_sec', 'STRATEGY': 'pos_btn_str'
    }
    target_button_key = position_button_templates.get(target_position_name)
    if not target_button_key:
        print(f"Error: Internal error - unknown position name '{target_position_name}'")
        perform_state_cleanup(detector, interactor)
        return False

    pos_button_locs = detector._find_template(target_button_key, confidence=0.8)
    if not pos_button_locs:
        print(f"Error: Position button for '{target_position_name}' not found on Capitol page.")
        perform_state_cleanup(detector, interactor)
        return False
    interactor.click_at(pos_button_locs[0][0], pos_button_locs[0][1])
    print(f"Clicked '{target_position_name}' position button.")
    time.sleep(0.15) # Wait for position page

    # 6. Verify Position Page
    position_page_templates = {
        'DEVELOPMENT': 'page_dev', 'INTERIOR': 'page_int', 'SCIENCE': 'page_sci',
        'SECURITY': 'page_sec', 'STRATEGY': 'page_str'
    }
    target_page_key = position_page_templates.get(target_position_name)
    if not target_page_key:
         print(f"Error: Internal error - unknown position name '{target_position_name}' for page verification")
         perform_state_cleanup(detector, interactor)
         return False

    if not detector._find_template(target_page_key, confidence=detector.state_confidence):
        print(f"Error: Failed to verify correct position page for '{target_position_name}'.")
        perform_state_cleanup(detector, interactor)
        return False
    print(f"Verified '{target_position_name}' position page.")

    # 7. Find and Click Dismiss Button
    dismiss_locs = detector._find_template('dismiss_button', confidence=0.8)
    if not dismiss_locs:
        print("Error: Dismiss button not found on position page.")
        perform_state_cleanup(detector, interactor)
        return False
    interactor.click_at(dismiss_locs[0][0], dismiss_locs[0][1])
    print("Clicked Dismiss button.")
    time.sleep(0.1) # Wait for confirmation

    # 8. Find and Click Confirm Button
    confirm_locs = detector._find_template('confirm_button', confidence=0.8)
    if not confirm_locs:
        print("Error: Confirm button not found after clicking dismiss.")
        # Don't cleanup here, might be stuck in confirmation state
        return False # Indicate failure, but let main loop decide next step
    interactor.click_at(confirm_locs[0][0], confirm_locs[0][1])
    print("Clicked Confirm button. Position should be dismissed.")
    time.sleep(0.1) # Wait for action to complete

    # 9. Cleanup: Return to Chat Room
    # Click Close on position page (should now be back on capitol page implicitly)
    close_locs = detector._find_template('close_button', confidence=0.8)
    if close_locs:
        interactor.click_at(close_locs[0][0], close_locs[0][1])
        print("Clicked Close button (returning to Capitol).")
        time.sleep(0.1)
    else:
        print("Warning: Close button not found after confirm, attempting back arrow anyway.")

    # Click Back Arrow on Capitol page (should return to profile)
    back_arrow_locs = detector._find_template('back_arrow', confidence=0.8)
    if back_arrow_locs:
        interactor.click_at(back_arrow_locs[0][0], back_arrow_locs[0][1])
        print("Clicked Back Arrow (returning to Profile).")
        time.sleep(0.1)
    else:
        print("Warning: Back arrow not found on Capitol page, attempting ESC cleanup.")

    # Use standard ESC cleanup
    print("Initiating final ESC cleanup to return to chat...")
    cleanup_success = perform_state_cleanup(detector, interactor)

    if cleanup_success:
        print("--- Position Removal Process Completed Successfully ---")
        return True
    else:
        print("--- Position Removal Process Completed, but failed to confirm return to chat room ---")
        return False # Technically removed, but UI state uncertain


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
        time.sleep(0.1)

        current_state = detector.get_current_ui_state()
        print(f"Detected state: {current_state}")

        if current_state == 'chat_room' or current_state == 'world_chat' or current_state == 'private_chat': # Adjust as needed
            print("Chat room interface detected, cleanup complete.")
            returned_to_chat = True
            break
        elif current_state == 'user_details' or current_state == 'profile_card':
            print(f"{current_state.replace('_', ' ').title()} detected, pressing ESC...")
            interactor.press_key('esc')
            time.sleep(0.1) # Wait longer for UI response after ESC
            continue
        else: # Unknown state
            print("Unknown page state detected.")
            if attempt < max_attempts - 1:
                 print("Trying one ESC press as fallback...")
                 interactor.press_key('esc')
                 time.sleep(0.1)
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
        # Regular Bubble (Original + Skins) - Keys match those used in find_dialogue_bubbles
        'corner_tl': CORNER_TL_IMG, 'corner_br': CORNER_BR_IMG,
        'corner_tl_type2': CORNER_TL_TYPE2_IMG, 'corner_br_type2': CORNER_BR_TYPE2_IMG,
        'corner_tl_type3': CORNER_TL_TYPE3_IMG, 'corner_br_type3': CORNER_BR_TYPE3_IMG, # Corrected: Added missing keys here
        # Bot Bubble (Single Type)
        'bot_corner_tl': BOT_CORNER_TL_IMG, 'bot_corner_br': BOT_CORNER_BR_IMG,
        # Keywords & UI Elements
        'keyword_wolf_lower': KEYWORD_wolf_LOWER_IMG,
        'keyword_wolf_upper': KEYWORD_Wolf_UPPER_IMG,
        'keyword_wolf_lower_type3': KEYWORD_wolf_LOWER_TYPE3_IMG, # Added
        'keyword_wolf_upper_type3': KEYWORD_Wolf_UPPER_TYPE3_IMG, # Added
        'copy_menu_item': COPY_MENU_ITEM_IMG, 'profile_option': PROFILE_OPTION_IMG,
        'copy_name_button': COPY_NAME_BUTTON_IMG, 'send_button': SEND_BUTTON_IMG,
        'chat_input': CHAT_INPUT_IMG, 'profile_name_page': PROFILE_NAME_PAGE_IMG,
        'profile_page': PROFILE_PAGE_IMG, 'chat_room': CHAT_ROOM_IMG,
        'base_screen': BASE_SCREEN_IMG, 'world_map_screen': WORLD_MAP_IMG, # Added for navigation
        'world_chat': WORLD_CHAT_IMG, 'private_chat': PRIVATE_CHAT_IMG,
        # Add position templates
        'development_pos': POS_DEV_IMG, 'interior_pos': POS_INT_IMG, 'science_pos': POS_SCI_IMG,
        'security_pos': POS_SEC_IMG, 'strategy_pos': POS_STR_IMG,
        # Add capitol templates
        'capitol_button': CAPITOL_BUTTON_IMG, 'president_title': PRESIDENT_TITLE_IMG,
        'pos_btn_dev': POS_BTN_DEV_IMG, 'pos_btn_int': POS_BTN_INT_IMG, 'pos_btn_sci': POS_BTN_SCI_IMG,
        'pos_btn_sec': POS_BTN_SEC_IMG, 'pos_btn_str': POS_BTN_STR_IMG,
        'page_dev': PAGE_DEV_IMG, 'page_int': PAGE_INT_IMG, 'page_sci': PAGE_SCI_IMG,
        'page_sec': PAGE_SEC_IMG, 'page_str': PAGE_STR_IMG,
        'dismiss_button': DISMISS_BUTTON_IMG, 'confirm_button': CONFIRM_BUTTON_IMG,
        'close_button': CLOSE_BUTTON_IMG, 'back_arrow': BACK_ARROW_IMG,
        'reply_button': REPLY_BUTTON_IMG # Added reply button template key
    }
    # Use default confidence/region settings from constants
    detector = DetectionModule(templates, confidence=CONFIDENCE_THRESHOLD, state_confidence=STATE_CONFIDENCE_THRESHOLD, region=SCREENSHOT_REGION)
    # Use default input coords/keys from constants
    interactor = InteractionModule(detector, input_coords=(CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y), input_template_key='chat_input', send_button_key='send_button')

# --- State Management (Local to this monitoring thread) ---
    last_processed_bubble_info = None # Store the whole dict now
    recent_texts = collections.deque(maxlen=RECENT_TEXT_HISTORY_MAXLEN) # Context-specific history needed
    screenshot_counter = 0 # Initialize counter for debug screenshots

    while True:
        # --- Process ALL Pending Commands First ---
        commands_processed_this_cycle = False
        try:
            while True: # Loop to drain the queue
                command_data = command_queue.get_nowait() # Check for commands without blocking
                commands_processed_this_cycle = True
                action = command_data.get('action')

                if action == 'send_reply':
                    text_to_send = command_data.get('text')
                    if not text_to_send:
                        print("UI Thread: Received send_reply command with no text.")
                        continue # Process next command in queue
                    print(f"UI Thread: Processing command to send reply: '{text_to_send[:50]}...'")
                    interactor.send_chat_message(text_to_send)

                elif action == 'remove_position':
                    # region = command_data.get('trigger_bubble_region') # This is the old region, keep for reference?
                    snapshot = command_data.get('bubble_snapshot')
                    area = command_data.get('search_area')
                    # Pass all necessary data to the function, including the original region if needed for context
                    # but the function should primarily use the snapshot for re-location.
                    original_region = command_data.get('trigger_bubble_region')
                    if snapshot: # Check for snapshot presence
                        print(f"UI Thread: Processing command to remove position (Snapshot provided: {'Yes' if snapshot else 'No'})")
                        success = remove_user_position(detector, interactor, original_region, snapshot, area)
                        print(f"UI Thread: Position removal attempt finished. Success: {success}")
                    else:
                        print("UI Thread: Received remove_position command without necessary snapshot data.")


                elif action == 'pause':
                    if not monitoring_paused_flag[0]: # Avoid redundant prints if already paused
                        print("UI Thread: Processing pause command. Pausing monitoring.")
                        monitoring_paused_flag[0] = True
                    # No continue needed here, let it finish draining queue

                elif action == 'resume':
                    if monitoring_paused_flag[0]: # Avoid redundant prints if already running
                         print("UI Thread: Processing resume command. Resuming monitoring.")
                         monitoring_paused_flag[0] = False
                    # No continue needed here

                else:
                    print(f"UI Thread: Received unknown command: {action}")

        except queue.Empty:
            # No more commands in the queue for this cycle
            if commands_processed_this_cycle:
                 print("UI Thread: Finished processing commands for this cycle.")
            pass
        except Exception as cmd_err:
            print(f"UI Thread: Error processing command queue: {cmd_err}")
            # Consider if pausing is needed on error, maybe not

        # --- Now, Check Pause State ---
        if monitoring_paused_flag[0]:
            # If paused, sleep and skip UI monitoring part
            time.sleep(0.1) # Sleep briefly while paused
            continue # Go back to check commands again

        # --- If not paused, proceed with UI Monitoring ---

        # --- Check for Main Screen Navigation ---
        try:
            base_locs = detector._find_template('base_screen', confidence=0.8)
            map_locs = detector._find_template('world_map_screen', confidence=0.8)
            if base_locs or map_locs:
                print("UI Thread: Detected main screen (Base or World Map). Clicking to return to chat...")
                # Coordinates provided by user (adjust if needed based on actual screen resolution/layout)
                # IMPORTANT: Ensure these coordinates are correct for the target window/resolution
                target_x, target_y = 600, 1300
                interactor.click_at(target_x, target_y)
                time.sleep(0.1) # Short delay after click
                print("UI Thread: Clicked to return to chat. Re-checking screen state...")
                continue # Skip the rest of the loop and re-evaluate
        except Exception as nav_err:
            print(f"UI Thread: Error during main screen navigation check: {nav_err}")
            # Decide if you want to continue or pause after error

        # --- Process Commands Second (Non-blocking) ---
        # This block seems redundant now as commands are processed at the start of the loop.
        # Keeping it commented out for now, can be removed later if confirmed unnecessary.
        # try:
        #     command_data = command_queue.get_nowait() # Check for commands without blocking
        #     action = command_data.get('action')
        #     if action == 'send_reply':
        #         text_to_send = command_data.get('text')
        #         # reply_context_activated = command_data.get('reply_context_activated', False) # Check if reply context was set
        #
        #         if not text_to_send:
        #             print("UI Thread: Received send_reply command with no text.")
        #             continue # Skip if no text
        #
        #         print(f"UI Thread: Received command to send reply: '{text_to_send[:50]}...'")
        #         # The reply context (clicking bubble + reply button) is now handled *before* putting into queue.
        #         # So, we just need to send the message directly here.
        #         # The input field should already be focused and potentially have @Username prefix if reply context was activated.
        #         interactor.send_chat_message(text_to_send)
        #
        #     elif action == 'remove_position': # <--- Handle new command
        #         region = command_data.get('trigger_bubble_region')
        #         if region:
        #             print(f"UI Thread: Received command to remove position triggered by bubble region: {region}")
        #             # Call the new UI function
        #             success = remove_user_position(detector, interactor, region) # Call synchronous function
        #             print(f"UI Thread: Position removal attempt finished. Success: {success}")
        #             # Note: No need to send result back unless main thread needs confirmation
        #         else:
        #             print("UI Thread: Received remove_position command without trigger_bubble_region.")
        #     elif action == 'pause': # <--- Handle pause command
        #         print("UI Thread: Received pause command. Pausing monitoring.")
        #         monitoring_paused_flag[0] = True
        #         continue # Immediately pause after receiving command
        #     elif action == 'resume': # <--- Handle resume command (might be redundant if checked above, but safe)
        #         print("UI Thread: Received resume command. Resuming monitoring.")
        #         monitoring_paused_flag[0] = False
        #     else:
        #         print(f"UI Thread: Received unknown command: {action}")
        # except queue.Empty:
        #     pass # No command waiting, continue with monitoring
        # except Exception as cmd_err:
        #      print(f"UI Thread: Error processing command queue: {cmd_err}")
        #      # This block is now part of the command processing loop above
        #      pass

        # --- Verify Chat Room State Before Bubble Detection (Only if NOT paused) ---
        try:
            # Use a slightly lower confidence maybe, or state_confidence
            chat_room_locs = detector._find_template('chat_room', confidence=detector.state_confidence)
            if not chat_room_locs:
                print("UI Thread: Not in chat room state before bubble detection. Attempting cleanup...")
                # Call the existing cleanup function to try and return
                perform_state_cleanup(detector, interactor)
                # Regardless of cleanup success, restart the loop to re-evaluate state from the top
                print("UI Thread: Continuing loop after attempting chat room cleanup.")
                time.sleep(0.5) # Small pause after cleanup attempt
                continue
            # else: # Optional: Log if chat room is confirmed
            #    print("UI Thread: Chat room state confirmed.")

        except Exception as state_check_err:
             print(f"UI Thread: Error checking for chat room state: {state_check_err}")
             # Decide how to handle error - maybe pause and retry? For now, continue cautiously.
             time.sleep(1)


        # --- Then Perform UI Monitoring (Bubble Detection) ---
        try:
            # 1. Detect Bubbles
            all_bubbles_data = detector.find_dialogue_bubbles() # Returns list of dicts
            if not all_bubbles_data: time.sleep(2); continue

            # Filter out bot bubbles, find newest non-bot bubble (example logic)
            other_bubbles_data = [b_info for b_info in all_bubbles_data if not b_info['is_bot']]
            if not other_bubbles_data: time.sleep(0.2); continue
            # Simple logic: assume lowest bubble is newest (might need improvement)
            # Sort by bbox bottom y-coordinate (index 3)
            target_bubble_info = max(other_bubbles_data, key=lambda b_info: b_info['bbox'][3])

            # 2. Check for Duplicates (Position & Content)
            # Compare using the 'bbox' from the info dicts
            if are_bboxes_similar(target_bubble_info.get('bbox'), last_processed_bubble_info.get('bbox') if last_processed_bubble_info else None):
                time.sleep(0.2); continue

            # 3. Detect Keyword in Bubble
            target_bbox = target_bubble_info['bbox']
            bubble_region = (target_bbox[0], target_bbox[1], target_bbox[2]-target_bbox[0], target_bbox[3]-target_bbox[1])
            keyword_coords = detector.find_keyword_in_region(bubble_region)

            if keyword_coords:
                print(f"\n!!! Keyword detected in bubble {target_bbox} !!!")

                # --- Variables needed later ---
                bubble_snapshot = None # Initialize snapshot variable
                search_area = SCREENSHOT_REGION # Define search area early
                if search_area is None:
                    print("Warning: SCREENSHOT_REGION not defined, searching full screen for bubble snapshot.")
                    # Consider adding a default chat region if SCREENSHOT_REGION is often None

                # --- Take Snapshot for Re-location (and potentially save it) ---
                try:
                    bubble_region_tuple = (int(bubble_region[0]), int(bubble_region[1]), int(bubble_region[2]), int(bubble_region[3]))
                    if bubble_region_tuple[2] <= 0 or bubble_region_tuple[3] <= 0:
                        print(f"Warning: Invalid bubble region {bubble_region_tuple} for snapshot. Skipping trigger.")
                        continue
                    bubble_snapshot = pyautogui.screenshot(region=bubble_region_tuple)
                    if bubble_snapshot is None:
                         print("Warning: Failed to capture bubble snapshot. Skipping trigger.")
                         continue

                    # --- Save Snapshot for Debugging (Replaces old debug screenshot logic) ---
                    try:
                        screenshot_index = (screenshot_counter % MAX_DEBUG_SCREENSHOTS) + 1
                        # Use a more descriptive filename
                        screenshot_filename = f"debug_relocation_snapshot_{screenshot_index}.png"
                        screenshot_path = os.path.join(DEBUG_SCREENSHOT_DIR, screenshot_filename)
                        print(f"Attempting to save bubble snapshot used for re-location to: {screenshot_path}")
                        bubble_snapshot.save(screenshot_path) # Save the PIL image object
                        print(f"Successfully saved bubble snapshot: {screenshot_path}")
                        screenshot_counter += 1
                    except Exception as save_err:
                        print(f"Error saving bubble snapshot to {screenshot_path}: {repr(save_err)}")
                        # Continue even if saving fails

                except Exception as snapshot_err:
                     print(f"Error taking initial bubble snapshot: {repr(snapshot_err)}")
                     continue # Skip trigger if snapshot fails

                # 4. Interact: Get Bubble Text
                bubble_text = interactor.copy_text_at(keyword_coords)
                if not bubble_text:
                    print("Error: Could not get dialogue content.")
                    last_processed_bubble_info = target_bubble_info # Mark as processed even if failed
                    perform_state_cleanup(detector, interactor) # Attempt cleanup after failed copy
                    continue

                # Check recent text history (needs context awareness)
                if bubble_text in recent_texts:
                    print(f"Content '{bubble_text[:30]}...' in recent history, skipping.")
                    last_processed_bubble_info = target_bubble_info
                    continue

                print(">>> New trigger event <<<")
                last_processed_bubble_info = target_bubble_info
                recent_texts.append(bubble_text)

                # 5. Interact: Get Sender Name (with Bubble Re-location)
                sender_name = None
                try:
                    # --- Bubble Re-location Logic with Fallback Mechanism ---
                    print("Attempting to re-locate bubble before getting sender name...")
                    if bubble_snapshot is None: # Should not happen if we reached here, but check anyway
                         print("Error: Bubble snapshot missing for re-location. Skipping.")
                         continue

                    # First attempt with standard confidence
                    print(f"First attempt with confidence {BUBBLE_RELOCATE_CONFIDENCE}...")
                    new_bubble_box = None
                    try:
                        new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot, 
                                                                region=search_area, 
                                                                confidence=BUBBLE_RELOCATE_CONFIDENCE)
                    except Exception as e:
                        print(f"Exception during initial bubble location attempt: {e}")
                    
                    # Second attempt with fallback confidence if first failed
                    if not new_bubble_box:
                        print(f"First attempt failed. Trying with lower confidence {BUBBLE_RELOCATE_FALLBACK_CONFIDENCE}...")
                        try:
                            # Try with a lower confidence threshold
                            new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot, 
                                                                    region=search_area, 
                                                                    confidence=BUBBLE_RELOCATE_FALLBACK_CONFIDENCE)
                        except Exception as e:
                            print(f"Exception during fallback bubble location attempt: {e}")
                    
                    # Third attempt with even lower confidence as last resort
                    if not new_bubble_box:
                        print("Second attempt failed. Trying with even lower confidence 0.4...")
                        try:
                            # Last resort with very low confidence
                            new_bubble_box = pyautogui.locateOnScreen(bubble_snapshot, 
                                                                    region=search_area, 
                                                                    confidence=0.4)
                        except Exception as e:
                            print(f"Exception during last resort bubble location attempt: {e}")

                    if new_bubble_box:
                        new_tl_x, new_tl_y = new_bubble_box.left, new_bubble_box.top
                        print(f"Successfully re-located bubble snapshot at: ({new_tl_x}, {new_tl_y})")
                        # Calculate avatar coords based on the *new* top-left and the *reply* offsets
                        new_avatar_coords = (new_tl_x + AVATAR_OFFSET_X_REPLY, new_tl_y + AVATAR_OFFSET_Y_REPLY)
                        print(f"Calculated new avatar coordinates for reply context: {new_avatar_coords}")
                        # Proceed to get sender name using the new coordinates, passing snapshot info for retries
                        sender_name = interactor.retrieve_sender_name_interaction(
                            initial_avatar_coords=new_avatar_coords,
                            bubble_snapshot=bubble_snapshot,
                            search_area=search_area
                        )
                    else:
                        print("Warning: Failed to re-locate bubble snapshot on screen after multiple attempts with decreasing confidence thresholds.")
                        print("Trying direct approach with original bubble coordinates...")
                        
                        # Fallback to original coordinates based on the target_bubble_info
                        original_tl_coords = target_bubble_info.get('tl_coords')
                        if original_tl_coords:
                            fallback_avatar_coords = (original_tl_coords[0] + AVATAR_OFFSET_X_REPLY, 
                                                    original_tl_coords[1] + AVATAR_OFFSET_Y_REPLY)
                            print(f"Using fallback avatar coordinates from original detection: {fallback_avatar_coords}")
                            
                            # Try with direct coordinates
                            sender_name = interactor.retrieve_sender_name_interaction(
                                initial_avatar_coords=fallback_avatar_coords,
                                bubble_snapshot=bubble_snapshot, 
                                search_area=search_area
                            )
                            
                            if not sender_name:
                                print("Direct approach failed. Skipping this trigger.")
                                last_processed_bubble_info = target_bubble_info # Mark as processed
                                perform_state_cleanup(detector, interactor) # Cleanup
                                continue
                        else:
                            print("No original coordinates available. Skipping sender name retrieval.")
                            # No need to continue if we can't find the bubble again
                            last_processed_bubble_info = target_bubble_info # Mark as processed to avoid re-triggering immediately
                            perform_state_cleanup(detector, interactor) # Attempt cleanup as state might be inconsistent
                            continue
                    # --- End Bubble Re-location Logic ---

                except Exception as reloc_err:
                    print(f"Error during bubble re-location or subsequent interaction: {reloc_err}")
                    import traceback
                    traceback.print_exc()
                    # Attempt cleanup after error during this critical phase
                    perform_state_cleanup(detector, interactor)
                    continue # Skip further processing for this trigger

                # 6. Perform Cleanup (Crucial after potentially leaving chat screen)
                # Moved the check for sender_name *after* potential re-location attempt
                cleanup_successful = perform_state_cleanup(detector, interactor)
                if not cleanup_successful:
                    print("Error: Failed to return to chat screen after getting name. Aborting trigger.")
                    continue # Skip putting in queue if cleanup failed

                if not sender_name:
                    print("Error: Could not get sender name, aborting processing.")
                    continue # Already cleaned up, just skip

                # --- Attempt to activate reply context BEFORE putting in queue ---
                reply_context_activated = False
                try:
                    print("Attempting to activate reply context...")
                    # Re-locate the bubble *again* to click its center for reply
                    if bubble_snapshot is None:
                         print("Warning: Bubble snapshot missing for reply context activation. Skipping.")
                         final_bubble_box_for_reply = None # Ensure it's None
                    else:
                         print(f"Attempting final re-location for reply context using search_area: {search_area}")
                         final_bubble_box_for_reply = pyautogui.locateOnScreen(bubble_snapshot, region=search_area, confidence=BUBBLE_RELOCATE_CONFIDENCE)

                    if final_bubble_box_for_reply:
                        print(f"Final re-location successful at: {final_bubble_box_for_reply}")
                        bubble_x_reply, bubble_y_reply = final_bubble_box_for_reply.left, final_bubble_box_for_reply.top
                        bubble_w_reply, bubble_h_reply = final_bubble_box_for_reply.width, final_bubble_box_for_reply.height
                        center_x_reply = bubble_x_reply + bubble_w_reply // 2
                        center_y_reply = bubble_y_reply + bubble_h_reply // 2

                        print(f"Clicking bubble center for reply at ({center_x_reply}, {center_y_reply})")
                        interactor.click_at(center_x_reply, center_y_reply)
                        time.sleep(0.15) # Increased wait time for menu/reply button to appear

                        print("Searching for reply button...")
                        reply_button_locs = detector._find_template('reply_button', confidence=0.8)
                        if reply_button_locs:
                            reply_coords = reply_button_locs[0]
                            print(f"Found reply button at {reply_coords}. Clicking...")
                            interactor.click_at(reply_coords[0], reply_coords[1])
                            time.sleep(0.07) # Wait after click
                            reply_context_activated = True
                            print("Reply context activated.")
                        else:
                            print(">>> Reply button template ('reply_button') not found after clicking bubble center. <<<")
                            # Optional: Press ESC to close menu if reply button wasn't found?
                            # print("Attempting to press ESC to close potential menu.")
                            # interactor.press_key('esc')
                            # time.sleep(0.1)
                    else:
                        # This log message was already present but is important
                        print("Warning: Failed to re-locate bubble for activating reply context.")

                except Exception as reply_context_err:
                    print(f"!!! Error during reply context activation: {reply_context_err} !!!")
                    # Ensure reply_context_activated remains False

                # 7. Send Trigger Info to Main Thread/Async Loop
                print("\n>>> Putting trigger info in Queue <<<")
                print(f"   Sender: {sender_name}")
                print(f"   Content: {bubble_text[:100]}...")
                print(f"   Bubble Region: {bubble_region}") # Include region derived from bbox
                print(f"   Reply Context Activated: {reply_context_activated}") # Include the flag
                try:
                    # Include bubble_region and reply_context_activated flag
                    data_to_send = {
                        'sender': sender_name,
                        'text': bubble_text,
                        'bubble_region': bubble_region, # Use bbox-derived region for general use
                        'reply_context_activated': reply_context_activated, # Send the flag
                        'bubble_snapshot': bubble_snapshot, # <-- Add snapshot
                        'search_area': search_area        # <-- Add search area used for snapshot
                        # 'tl_coords': target_bubble_info['tl_coords'] # Optionally send if needed elsewhere
                    }
                    trigger_queue.put(data_to_send) # Put in the queue for main loop
                    print("Trigger info (with region, reply flag, snapshot, search_area) placed in Queue.")
                except Exception as q_err:
                    print(f"Error putting data in Queue: {q_err}")

                print("--- Single trigger processing complete ---")
                time.sleep(0.1) # Pause after successful trigger

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
            print("Waiting 3 seconds before retry...")
            time.sleep(3)

# Note: The old monitor_chat_for_trigger function is replaced by the example_coordinator_loop.
# The actual UI monitoring thread started in main.py should call a function like this example loop.
# The main async loop in main.py will handle getting items from the queue and interacting with the LLM.

# if __name__ == '__main__':
#     # This module is not meant to be run directly after refactoring.
#     # Initialization and coordination happen in main.py.
#     pass
