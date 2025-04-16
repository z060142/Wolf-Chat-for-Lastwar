# ui_interaction.py
# Handles recognition and interaction logic with the game screen
# Includes: Bot bubble corner detection, case-sensitive keyword detection, duplicate handling mechanism, state-based ESC cleanup, complete syntax fixes

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

# --- Configuration Section ---
# Get script directory to ensure relative paths are correct
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates") # Templates image folder path
os.makedirs(TEMPLATE_DIR, exist_ok=True) # Ensure folder exists

# --- Regular Bubble Corner Templates ---
# Please save screenshots to the templates folder using the following filenames
CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "corner_tl.png") # Regular bubble - Top Left corner
CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "corner_tr.png") # Regular bubble - Top Right corner
CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "corner_bl.png") # Regular bubble - Bottom Left corner
CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "corner_br.png") # Regular bubble - Bottom Right corner

# --- Bot Bubble Corner Templates (need to be provided!) ---
# Please save screenshots to the templates folder using the following filenames
BOT_CORNER_TL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tl.png") # Bot bubble - Top Left corner
BOT_CORNER_TR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_tr.png") # Bot bubble - Top Right corner
BOT_CORNER_BL_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_bl.png") # Bot bubble - Bottom Left corner
BOT_CORNER_BR_IMG = os.path.join(TEMPLATE_DIR, "bot_corner_br.png") # Bot bubble - Bottom Right corner

# --- Keyword Templates (case-sensitive) ---
# Please save screenshots to the templates folder using the following filenames
KEYWORD_wolf_LOWER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower.png") # Lowercase "wolf"
KEYWORD_Wolf_UPPER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper.png") # Uppercase "Wolf"

# --- UI Element Templates ---
# Please save screenshots to the templates folder using the following filenames
COPY_MENU_ITEM_IMG = os.path.join(TEMPLATE_DIR, "copy_menu_item.png")     # "Copy" option in the menu
PROFILE_OPTION_IMG = os.path.join(TEMPLATE_DIR, "profile_option.png")     # Option in the profile card that opens user details
COPY_NAME_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "copy_name_button.png") # "Copy Name" button in user details
SEND_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "send_button.png")           # "Send" button for the chat input box
CHAT_INPUT_IMG = os.path.join(TEMPLATE_DIR, "chat_input.png")             # (Optional) Template image for the chat input box

# --- Status Detection Templates ---
# Please save screenshots to the templates folder using the following filenames
PROFILE_NAME_PAGE_IMG = os.path.join(TEMPLATE_DIR, "Profile_Name_page.png") # User details page identifier
PROFILE_PAGE_IMG = os.path.join(TEMPLATE_DIR, "Profile_page.png")       # Profile card page identifier
CHAT_ROOM_IMG = os.path.join(TEMPLATE_DIR, "chat_room.png")           # Chat room interface identifier

# --- Operation Parameters (need to be adjusted based on your environment) ---
# Chat input box reference coordinates or region (needed if not using image positioning)
CHAT_INPUT_REGION = None # (100, 800, 500, 50) # Example region (x, y, width, height)
CHAT_INPUT_CENTER_X = 400 # Example X coordinate
CHAT_INPUT_CENTER_Y = 1280 # Example Y coordinate

# Screenshot and recognition parameters
SCREENSHOT_REGION = None # None means full screen, or set to (x, y, width, height) to limit scanning area
CONFIDENCE_THRESHOLD = 0.8 # Main image matching confidence threshold (0.0 ~ 1.0), needs adjustment
STATE_CONFIDENCE_THRESHOLD = 0.7 # State detection confidence threshold (may need to be lower)
AVATAR_OFFSET_X = -50 # Avatar X offset relative to bubble top-left corner (based on your update)

# Duplicate handling parameters
BBOX_SIMILARITY_TOLERANCE = 10 # Pixel tolerance when determining if two bubbles are in similar positions
RECENT_TEXT_HISTORY_MAXLEN = 5 # Number of recently processed texts to keep

# --- Helper Functions ---

def find_template_on_screen(template_path, region=None, confidence=CONFIDENCE_THRESHOLD, grayscale=False):
    """
    Find a template image in a specified screen region (more robust version).

    Args:
        template_path (str): Path to the template image.
        region (tuple, optional): Screenshot region (x, y, width, height). Default is None (full screen).
        confidence (float, optional): Matching confidence threshold. Default is CONFIDENCE_THRESHOLD.
        grayscale (bool, optional): Whether to use grayscale for matching. Default is False.

    Returns:
        list: List containing center point coordinates of all found matches [(x1, y1), (x2, y2), ...],
              or empty list if none found.
    """
    locations = []
    # Check if template file exists, warn only once when not found
    if not os.path.exists(template_path):
        if not hasattr(find_template_on_screen, 'warned_paths'):
            find_template_on_screen.warned_paths = set()
        if template_path not in find_template_on_screen.warned_paths:
            print(f"Error: Template image doesn't exist: {template_path}")
            find_template_on_screen.warned_paths.add(template_path)
        return []

    try:
        # Use pyautogui to find all matches (requires opencv-python)
        matches = pyautogui.locateAllOnScreen(template_path, region=region, confidence=confidence, grayscale=grayscale)
        if matches:
            for box in matches:
                center_x = box.left + box.width // 2
                center_y = box.top + box.height // 2
                locations.append((center_x, center_y))
        # print(f"Found template '{os.path.basename(template_path)}' at {len(locations)} locations.") # Debug
        return locations
    except Exception as e:
        # Print more detailed error, including template path
        print(f"Error finding template '{os.path.basename(template_path)}' ({template_path}): {e}")
        return []

def click_at(x, y, button='left', clicks=1, interval=0.1, duration=0.1):
    """Safely click at specific coordinates, with movement time added"""
    try:
        x_int, y_int = int(x), int(y) # Ensure coordinates are integers
        print(f"Moving to and clicking at: ({x_int}, {y_int}), button: {button}, clicks: {clicks}")
        pyautogui.moveTo(x_int, y_int, duration=duration) # Smooth move to target
        pyautogui.click(button=button, clicks=clicks, interval=interval)
        time.sleep(0.1) # Brief pause after clicking
    except Exception as e:
        print(f"Error clicking at coordinates ({int(x)}, {int(y)}): {e}")

def get_clipboard_text():
    """Get text from clipboard"""
    try:
        return pyperclip.paste()
    except Exception as e:
        # pyperclip might fail in certain environments (like headless servers)
        print(f"Error reading clipboard: {e}")
        return None

def set_clipboard_text(text):
    """Set clipboard text"""
    try:
        pyperclip.copy(text)
    except Exception as e:
        print(f"Error writing to clipboard: {e}")

def are_bboxes_similar(bbox1, bbox2, tolerance=BBOX_SIMILARITY_TOLERANCE):
    """Check if two bounding boxes' positions (top-left corner) are very close"""
    if bbox1 is None or bbox2 is None:
        return False
    # Compare top-left coordinates (bbox[0], bbox[1])
    return abs(bbox1[0] - bbox2[0]) <= tolerance and abs(bbox1[1] - bbox2[1]) <= tolerance

# --- Main Logic Functions ---

def find_dialogue_bubbles():
    """
    Scan the screen for regular bubble corners and Bot bubble corners, and try to pair them.
    Returns a list containing bounding boxes and whether they are Bot bubbles.
    !!! The matching logic is very basic and needs significant improvement based on actual needs !!!
    """
    all_bubbles_with_type = [] # Store (bbox, is_bot_flag)

    # 1. Find all regular corners
    tl_corners = find_template_on_screen(CORNER_TL_IMG, region=SCREENSHOT_REGION)
    br_corners = find_template_on_screen(CORNER_BR_IMG, region=SCREENSHOT_REGION)
    # tr_corners = find_template_on_screen(CORNER_TR_IMG, region=SCREENSHOT_REGION) # Not using TR/BL for now
    # bl_corners = find_template_on_screen(CORNER_BL_IMG, region=SCREENSHOT_REGION)

    # 2. Find all Bot corners
    bot_tl_corners = find_template_on_screen(BOT_CORNER_TL_IMG, region=SCREENSHOT_REGION)
    bot_br_corners = find_template_on_screen(BOT_CORNER_BR_IMG, region=SCREENSHOT_REGION)
    # bot_tr_corners = find_template_on_screen(BOT_CORNER_TR_IMG, region=SCREENSHOT_REGION)
    # bot_bl_corners = find_template_on_screen(BOT_CORNER_BL_IMG, region=SCREENSHOT_REGION)

    # 3. Try to match regular bubbles (using TL and BR)
    processed_tls = set() # Track already matched TL indices
    if tl_corners and br_corners:
        for i, tl in enumerate(tl_corners):
            if i in processed_tls: continue
            potential_br = None
            min_dist_sq = float('inf')
            # Find the best BR corresponding to this TL (e.g., closest, or satisfying specific geometric constraints)
            for j, br in enumerate(br_corners):
                # Check if BR is in a reasonable range to the bottom-right of TL
                if br[0] > tl[0] + 20 and br[1] > tl[1] + 10: # Assume minimum width/height
                    dist_sq = (br[0] - tl[0])**2 + (br[1] - tl[1])**2
                    # Could add more conditions here, e.g., aspect ratio limits
                    if dist_sq < min_dist_sq: # Simple nearest-match
                        potential_br = br
                        min_dist_sq = dist_sq

            if potential_br:
                # Assuming we found matching TL and BR, define bounding box
                bubble_bbox = (tl[0], tl[1], potential_br[0], potential_br[1])
                all_bubbles_with_type.append((bubble_bbox, False)) # Mark as non-Bot
                processed_tls.add(i) # Mark this TL as used

    # 4. Try to match Bot bubbles (using Bot TL and Bot BR)
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
                  all_bubbles_with_type.append((bubble_bbox, True)) # Mark as Bot
                  processed_bot_tls.add(i)

    # print(f"Found {len(all_bubbles_with_type)} potential bubbles.") #reduce printing
    return all_bubbles_with_type


def find_keyword_in_bubble(bubble_bbox):
    """
    Look for the keywords "wolf" or "Wolf" images within the specified bubble area.
    """
    x_min, y_min, x_max, y_max = bubble_bbox
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0:
        # print(f"Warning: Invalid bubble area {bubble_bbox}") #reduce printing
        return None
    search_region = (x_min, y_min, width, height)
    # print(f"Searching for keywords in region {search_region}...") #reduce printing

    # 1. Try to find lowercase "wolf"
    keyword_locations_lower = find_template_on_screen(KEYWORD_wolf_LOWER_IMG, region=search_region)
    if keyword_locations_lower:
        keyword_coords = keyword_locations_lower[0]
        print(f"Found keyword (lowercase) in bubble {bubble_bbox}, position: {keyword_coords}")
        return keyword_coords

    # 2. If lowercase not found, try uppercase "Wolf"
    keyword_locations_upper = find_template_on_screen(KEYWORD_Wolf_UPPER_IMG, region=search_region)
    if keyword_locations_upper:
        keyword_coords = keyword_locations_upper[0]
        print(f"Found keyword (uppercase) in bubble {bubble_bbox}, position: {keyword_coords}")
        return keyword_coords

    # If neither found
    return None

def find_avatar_for_bubble(bubble_bbox):
    """Calculate avatar frame position based on bubble's top-left coordinates."""
    tl_x, tl_y = bubble_bbox[0], bubble_bbox[1]
    # Adjust offset and Y-coordinate calculation based on actual layout
    avatar_x = tl_x + AVATAR_OFFSET_X # Use updated offset
    avatar_y = tl_y # Assume Y coordinate is same as top-left
    print(f"Calculated avatar coordinates: ({int(avatar_x)}, {int(avatar_y)})")
    return (avatar_x, avatar_y)

def get_bubble_text(keyword_coords):
    """
    Click on keyword position, simulate menu selection "Copy" or press Ctrl+C, and get text from clipboard.
    """
    print(f"Attempting to copy @ {keyword_coords}...");
    original_clipboard = get_clipboard_text() or "" # Ensure not None
    set_clipboard_text("___MCP_CLEAR___") # Use special marker to clear
    time.sleep(0.1) # Brief wait for clipboard operation

    # Click on keyword position
    click_at(keyword_coords[0], keyword_coords[1])
    time.sleep(0.2) # Wait for possible menu or reaction

    # Try to find and click "Copy" menu item
    copy_item_locations = find_template_on_screen(COPY_MENU_ITEM_IMG, confidence=0.7)
    copied = False # Initialize copy state
    if copy_item_locations:
        copy_coords = copy_item_locations[0]
        click_at(copy_coords[0], copy_coords[1])
        print("Clicked 'Copy' menu item.")
        time.sleep(0.2) # Wait for copy operation to complete
        copied = True # Mark copy operation as attempted (via click)
    else:
        print("'Copy' menu item not found. Attempting to simulate Ctrl+C.")
        # --- Corrected try block ---
        try:
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.2) # Wait for copy operation to complete
            print("Simulated Ctrl+C.")
            copied = True # Mark copy operation as attempted (via hotkey)
        except Exception as e_ctrlc:
             print(f"Failed to simulate Ctrl+C: {e_ctrlc}")
             copied = False # Ensure copied is False on failure
        # --- End correction ---

    # Check clipboard content
    copied_text = get_clipboard_text()

    # Restore original clipboard
    pyperclip.copy(original_clipboard)

    # Determine if copy was successful
    if copied and copied_text and copied_text != "___MCP_CLEAR___":
        print(f"Successfully copied text, length: {len(copied_text)}")
        return copied_text.strip() # Return text with leading/trailing whitespace removed
    else:
        print("Error: Copy operation unsuccessful or clipboard content invalid.")
        return None

def get_sender_name(avatar_coords):
    """
    Click avatar, open profile card, click option, open user details, click copy name.
    Uses state-based ESC cleanup logic.
    """
    print(f"Attempting to get username from avatar {avatar_coords}...")
    original_clipboard = get_clipboard_text() or ""
    set_clipboard_text("___MCP_CLEAR___")
    time.sleep(0.1)
    sender_name = None # Initialize
    success = False # Mark whether name retrieval was successful

    try:
        # 1. Click avatar
        click_at(avatar_coords[0], avatar_coords[1])
        time.sleep(.3) # Wait for profile card to appear

        # 2. Find and click option on profile card (triggers user details)
        profile_option_locations = find_template_on_screen(PROFILE_OPTION_IMG, confidence=0.7)
        if not profile_option_locations:
            print("Error: User details option not found on profile card.")
            # No need to raise exception here, let finally handle cleanup
        else:
            click_at(profile_option_locations[0][0], profile_option_locations[0][1])
            print("Clicked user details option.")
            time.sleep(.3) # Wait for user details window to appear

            # 3. Find and click "Copy Name" button in user details
            copy_name_locations = find_template_on_screen(COPY_NAME_BUTTON_IMG, confidence=0.7)
            if not copy_name_locations:
                print("Error: 'Copy Name' button not found in user details.")
            else:
                click_at(copy_name_locations[0][0], copy_name_locations[0][1])
                print("Clicked 'Copy Name' button.")
                time.sleep(0.1) # Wait for copy to complete
                copied_name = get_clipboard_text()
                if copied_name and copied_name != "___MCP_CLEAR___":
                    print(f"Successfully copied username: {copied_name}")
                    sender_name = copied_name.strip() # Store successfully copied name
                    success = True # Mark success
                else:
                    print("Error: Clipboard content unchanged or empty, failed to copy username.")

        # Regardless of success above, return sender_name (might be None)
        return sender_name

    except Exception as e:
        print(f"Error during username retrieval process: {e}")
        import traceback
        traceback.print_exc()
        return None # Return None to indicate failure
    finally:
        # --- State-based cleanup logic ---
        print("Performing cleanup: Attempting to press ESC to return to chat interface based on screen state...")
        max_esc_attempts = 4 # Increase attempt count just in case
        returned_to_chat = False
        for attempt in range(max_esc_attempts):
            print(f"Cleanup attempt #{attempt + 1}/{max_esc_attempts}")
            time.sleep(0.2) # Short wait before each attempt

            # First check if already returned to chat room
            # Using lower confidence for state checks may be more stable
            if find_template_on_screen(CHAT_ROOM_IMG, confidence=STATE_CONFIDENCE_THRESHOLD):
                print("Chat room interface detected, cleanup complete.")
                returned_to_chat = True
                break # Already returned, exit loop

            # Check if in user details page
            elif find_template_on_screen(PROFILE_NAME_PAGE_IMG, confidence=STATE_CONFIDENCE_THRESHOLD):
                print("User details page detected, pressing ESC...")
                pyautogui.press('esc')
                time.sleep(0.2) # Wait for UI response
                continue # Continue to next loop iteration

            # Check if in profile card page
            elif find_template_on_screen(PROFILE_PAGE_IMG, confidence=STATE_CONFIDENCE_THRESHOLD):
                print("Profile card page detected, pressing ESC...")
                pyautogui.press('esc')
                time.sleep(0.2) # Wait for UI response
                continue # Continue to next loop iteration

            else:
                # Cannot identify current state
                print("No known page state detected.")
                if attempt < max_esc_attempts - 1:
                     print("Trying one ESC press as fallback...")
                     pyautogui.press('esc')
                     time.sleep(0.2) # Wait for response
                else:
                     print("Maximum attempts reached, stopping cleanup.")
                     break # Exit loop

        if not returned_to_chat:
             print("Warning: Could not confirm return to chat room interface via state detection.")
        # --- End of new cleanup logic ---

        # Ensure clipboard is restored
        pyperclip.copy(original_clipboard)


def paste_and_send_reply(reply_text):
    """
    Click chat input box, paste response, click send button or press Enter.
    """
    print("Preparing to send response...")
    # --- Corrected if statement ---
    if not reply_text:
        print("Error: Response content is empty, cannot send.")
        return False
    # --- End correction ---

    input_coords = None
    if os.path.exists(CHAT_INPUT_IMG):
        input_locations = find_template_on_screen(CHAT_INPUT_IMG, confidence=0.7)
        if input_locations:
            input_coords = input_locations[0]
            print(f"Found input box position via image: {input_coords}")
        else:
            print("Warning: Input box not found via image, using default coordinates.")
            input_coords = (CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y)
    else:
        print("Warning: Input box template image doesn't exist, using default coordinates.")
        input_coords = (CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y)

    click_at(input_coords[0], input_coords[1])
    time.sleep(0.3)

    print("Pasting response...")
    set_clipboard_text(reply_text)
    time.sleep(0.1)
    try:
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        print("Pasted.")
    except Exception as e:
        print(f"Error pasting response: {e}")
        return False

    send_button_locations = find_template_on_screen(SEND_BUTTON_IMG, confidence=0.7)
    if send_button_locations:
        send_coords = send_button_locations[0]
        click_at(send_coords[0], send_coords[1])
        print("Clicked send button.")
        time.sleep(0.1)
        return True
    else:
        print("Send button not found. Attempting to press Enter.")
        try:
            pyautogui.press('enter')
            print("Pressed Enter.")
            time.sleep(0.5)
            return True
        except Exception as e_enter:
            print(f"Error pressing Enter: {e_enter}")
            return False


# --- Main Monitoring and Triggering Logic ---
recent_texts = collections.deque(maxlen=RECENT_TEXT_HISTORY_MAXLEN)
last_processed_bubble_bbox = None

def monitor_chat_for_trigger(trigger_queue: queue.Queue): # Using standard queue
    """
    Continuously monitor chat area, look for bubbles containing keywords and put trigger info in Queue.
    """
    global last_processed_bubble_bbox
    print(f"\n--- Starting chat room monitoring (UI Thread) ---")
    # No longer need to get loop

    while True:
        try:
            all_bubbles_with_type = find_dialogue_bubbles()
            if not all_bubbles_with_type: time.sleep(2); continue
            other_bubbles_bboxes = [bbox for bbox, is_bot in all_bubbles_with_type if not is_bot]
            if not other_bubbles_bboxes: time.sleep(2); continue
            target_bubble = max(other_bubbles_bboxes, key=lambda b: b[3])
            if are_bboxes_similar(target_bubble, last_processed_bubble_bbox): time.sleep(2); continue

            keyword_coords = find_keyword_in_bubble(target_bubble)
            if keyword_coords:
                print(f"\n!!! Keyword detected in bubble {target_bubble} !!!")
                bubble_text = get_bubble_text(keyword_coords) # Using corrected version
                if not bubble_text: print("Error: Could not get dialogue content."); last_processed_bubble_bbox = target_bubble; continue
                if bubble_text in recent_texts: print(f"Content '{bubble_text[:30]}...' in recent history, skipping."); last_processed_bubble_bbox = target_bubble; continue

                print(">>> New trigger event <<<"); last_processed_bubble_bbox = target_bubble; recent_texts.append(bubble_text)
                avatar_coords = find_avatar_for_bubble(target_bubble)
                sender_name = get_sender_name(avatar_coords) # Using version with state cleanup
                if not sender_name: print("Error: Could not get sender name, aborting processing."); continue

                print("\n>>> Putting trigger info in Queue <<<"); print(f"   Sender: {sender_name}"); print(f"   Content: {bubble_text[:100]}...")
                try:
                    # --- Using queue.put (synchronous) ---
                    data_to_send = {'sender': sender_name, 'text': bubble_text}
                    trigger_queue.put(data_to_send) # Directly put into standard Queue
                    print("Trigger info placed in Queue.")
                except Exception as q_err: print(f"Error putting data in Queue: {q_err}")
                print("--- Single trigger processing complete ---"); time.sleep(1)
            time.sleep(1.5)
        except KeyboardInterrupt: print("\nMonitoring interrupted."); break
        except Exception as e: print(f"Unknown error in monitoring loop: {e}"); import traceback; traceback.print_exc(); print("Waiting 5 seconds before retry..."); time.sleep(5)

# if __name__ == '__main__': # Keep commented, typically called from main.py
#     pass
