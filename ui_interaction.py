# ui_interaction.py
# Refactored to separate Detection and Interaction logic.

import pyautogui
import cv2 # opencv-python
import numpy as np
import sys # Added for special character handling
import io  # Added for special character handling
import pyperclip
import time
import os
import collections
import asyncio
import pygetwindow as gw # Used to check/activate windows
import config          # Used to read window title
import json # Added for color config loading
import queue
from typing import List, Tuple, Optional, Dict, Any
import threading # Import threading for Lock if needed, or just use a simple flag
import math # Added for distance calculation in dual method
import datetime # Added for MCP result timestamps
import hashlib # Added for UI stability checking
import time # Ensure time is imported for MessageDeduplication
from simple_bubble_dedup import SimpleBubbleDeduplication
import difflib # Added for text similarity
import os # Already imported, but good to note for RobustMessageDeduplication
import json # Already imported, but good to note for RobustMessageDeduplication

# 替換現有的 MessageDeduplication 類
class RobustMessageDeduplication:
    def __init__(self, storage_file="persistent_dedup.json", expiry_seconds=3600):
        self.storage_file = storage_file
        self.expiry_seconds = expiry_seconds
        self.processed_messages = {}
        self.last_save_time = 0
        self.save_interval = 10  # 每10秒保存一次
        
        # 啟動時加載持久化數據
        self._load_from_storage()
        
        # 清理過期記錄
        self._cleanup_expired()
        
        print(f"RobustDeduplication initialized with {len(self.processed_messages)} existing records")
    
    def _load_from_storage(self):
        """從持久化文件加載去重記錄"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.processed_messages = data.get('messages', {})
                    print(f"Loaded {len(self.processed_messages)} dedup records from storage")
        except Exception as e:
            print(f"Warning: Could not load dedup storage: {e}")
            self.processed_messages = {}
    
    def _save_to_storage(self, force=False):
        """保存去重記錄到持久化文件"""
        current_time = time.time()
        if not force and (current_time - self.last_save_time) < self.save_interval:
            return
        
        try:
            # 只保存未過期的記錄
            valid_records = {}
            for key, timestamp in self.processed_messages.items():
                if current_time - timestamp < self.expiry_seconds:
                    valid_records[key] = timestamp
            
            data = {
                'messages': valid_records,
                'last_updated': current_time
            }
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.processed_messages = valid_records
            self.last_save_time = current_time
            
        except Exception as e:
            print(f"Error saving dedup storage: {e}")
    
    def _cleanup_expired(self):
        """清理過期記錄"""
        current_time = time.time()
        before_count = len(self.processed_messages)
        
        self.processed_messages = {
            key: timestamp for key, timestamp in self.processed_messages.items()
            if current_time - timestamp < self.expiry_seconds
        }
        
        after_count = len(self.processed_messages)
        if before_count > after_count:
            print(f"Cleaned up {before_count - after_count} expired dedup records")
    
    def _create_message_key(self, sender, content):
        """創建標準化的消息鍵"""
        # 標準化處理
        clean_sender = sender.lower().strip() if sender else ""
        clean_content = ' '.join(content.strip().split()) if content else ""
        return f"{clean_sender}:{clean_content}"
    
    def is_duplicate(self, sender, content):
        """強化的重複檢查"""
        if not sender or not content:
            print("Deduplication: Missing sender or content, treating as new")
            return False
        
        current_time = time.time()
        
        # 定期清理（每5分鐘）
        if hasattr(self, '_last_cleanup'):
            if current_time - self._last_cleanup > 300:
                self._cleanup_expired()
                self._last_cleanup = current_time
        else:
            self._last_cleanup = current_time
        
        # 創建消息鍵
        message_key = self._create_message_key(sender, content)
        
        # 精確匹配檢查
        if message_key in self.processed_messages:
            age = current_time - self.processed_messages[message_key]
            if age < self.expiry_seconds:
                print(f"DUPLICATE EXACT: {sender} - {content[:40]}... (age: {age:.1f}s)")
                return True
            else:
                # 過期了，移除
                del self.processed_messages[message_key]
        
        # 相似性檢查（更嚴格）
        clean_content = ' '.join(content.strip().split())
        for existing_key, timestamp in list(self.processed_messages.items()):
            age = current_time - timestamp
            if age >= self.expiry_seconds:
                continue
                
            try:
                stored_sender, stored_content = existing_key.split(":", 1)
                if sender.lower().strip() == stored_sender:
                    # 計算相似度
                    similarity = difflib.SequenceMatcher(None, clean_content, stored_content).ratio()
                    if similarity >= 0.95:  # 95%相似度
                        print(f"DUPLICATE SIMILAR: {sender} - {content[:40]}... (similarity: {similarity:.3f}, age: {age:.1f}s)")
                        return True
            except ValueError:
                continue
        
        # 記錄新消息
        self.processed_messages[message_key] = current_time
        print(f"NEW MESSAGE RECORDED: {sender} - {content[:40]}...")
        
        # 異步保存（不阻塞主流程）
        self._save_to_storage()
        
        return False
    
    def clear_all(self):
        """清空所有記錄"""
        self.processed_messages.clear()
        self._save_to_storage(force=True)
        print("All dedup records cleared and persisted")
    
    def get_stats(self):
        """獲取統計信息"""
        current_time = time.time()
        active_count = sum(1 for timestamp in self.processed_messages.values() 
                          if current_time - timestamp < self.expiry_seconds)
        
        return {
            'total_records': len(self.processed_messages),
            'active_records': active_count,
            'oldest_record_age': min([current_time - t for t in self.processed_messages.values()]) if self.processed_messages else 0
        }

# 診斷工具：狀態重置檢測器
class StateResetDetector:
    def __init__(self, log_file="state_resets.log"):
        self.log_file = log_file
        self.start_time = time.time()
        self.reset_count = 0
        
    def log_reset(self, reset_type, context=""):
        """記錄狀態重置事件"""
        self.reset_count += 1
        timestamp = time.time()
        
        log_entry = f"{timestamp:.3f}: RESET #{self.reset_count} - {reset_type} - {context}\n"
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except:
            pass
        
        print(f"STATE RESET DETECTED: {reset_type} - {context}")
    
    def check_object_identity(self, obj, obj_name):
        """檢查對象是否被重新創建"""
        obj_id = id(obj)
        attr_name = f"_{obj_name}_last_id"
        
        if hasattr(self, attr_name):
            last_id = getattr(self, attr_name)
            if last_id != obj_id:
                self.log_reset("OBJECT_RECREATED", f"{obj_name} object was recreated")
        
        setattr(self, attr_name, obj_id)

# --- Global Pause Flag ---
# Using a simple mutable object (list) for thread-safe-like access without explicit lock
# Or could use threading.Event()
monitoring_paused_flag = [False] # List containing a boolean

# --- Global Error Handling Setup for Text Encoding ---
def handle_text_encoding(text, default_text="[無法處理的文字]"):
    """安全處理任何文字，確保不會因編碼問題而崩潰程序"""
    if text is None:
        return default_text
    
    try:
        # 嘗試使用 utf-8 編碼
        return text
    except UnicodeEncodeError:
        try:
            # 嘗試將特殊字符替換為可顯示字符
            return text.encode('utf-8', errors='replace').decode('utf-8')
        except:
            # 最後手段：忽略任何無法處理的字符
            try:
                return text.encode('utf-8', errors='ignore').decode('utf-8')
            except:
                return default_text

# --- Color Config Loading ---
def load_bubble_colors(config_path='bubble_colors.json'):
    """Loads bubble color configuration from a JSON file."""
    try:
        # Ensure the path is absolute or relative to the script directory
        if not os.path.isabs(config_path):
            config_path = os.path.join(SCRIPT_DIR, config_path)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            print(f"Successfully loaded color config from {config_path}")
            return config.get('bubble_types', [])
    except FileNotFoundError:
        print(f"Warning: Color config file not found at {config_path}. Using default colors.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {config_path}. Using default colors.")
    except Exception as e:
        print(f"Error loading color config: {e}. Using default colors.")

    # Default configuration if loading fails
    return [
        {
            "name": "normal_user",
            "is_bot": False, # Corrected boolean value
            "hsv_lower": [6, 0, 240],
            "hsv_upper": [18, 23, 255],
            "min_area": 2500,
            "max_area": 300000
            },
            {
            "name": "bot",
            "is_bot": True, # Corrected boolean value
            "hsv_lower": [105, 9, 208],
            "hsv_upper": [116, 43, 243],
            "min_area": 2500,
            "max_area": 300000
        }
    ]

# --- Configuration Section ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# --- Debugging ---
DEBUG_SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "debug_screenshots")
MAX_DEBUG_SCREENSHOTS = 8
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)
DEBUG_LEVEL = 1 # 0=Off, 1=Basic Info, 2=Detailed, 3=Visual Debug
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
CORNER_TL_TYPE4_IMG = os.path.join(TEMPLATE_DIR, "corner_tl_type4.png") # Added type4
CORNER_BR_TYPE4_IMG = os.path.join(TEMPLATE_DIR, "corner_br_type4.png") # Added type4
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
# Keywords (Refactored based on guide)
KEYWORD_wolf_LOWER_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower.png")  # Active Core
KEYWORD_Wolf_UPPER_IMG = os.path.join(TEMPLATE_DIR, "keyword_Wolf_upper.png")  # Active Core
KEYWORD_WOLF_REPLY_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_reply.png")  # Active Core

# Deprecated but kept for potential legacy fallback or reference
KEYWORD_wolf_LOWER_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower_type2.png") # Deprecated
KEYWORD_Wolf_UPPER_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper_type2.png") # Deprecated
KEYWORD_wolf_LOWER_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower_type3.png") # Deprecated
KEYWORD_Wolf_UPPER_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper_type3.png") # Deprecated
KEYWORD_wolf_LOWER_TYPE4_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_lower_type4.png") # Deprecated
KEYWORD_Wolf_UPPER_TYPE4_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_upper_type4.png") # Deprecated
KEYWORD_WOLF_REPLY_TYPE2_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_reply_type2.png") # Deprecated
KEYWORD_WOLF_REPLY_TYPE3_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_reply_type3.png") # Deprecated
KEYWORD_WOLF_REPLY_TYPE4_IMG = os.path.join(TEMPLATE_DIR, "keyword_wolf_reply_type4.png") # Deprecated
# UI Elements
COPY_MENU_ITEM_IMG = os.path.join(TEMPLATE_DIR, "copy_menu_item.png")
PROFILE_OPTION_IMG = os.path.join(TEMPLATE_DIR, "profile_option.png")
COPY_NAME_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "copy_name_button.png")
SEND_BUTTON_IMG = os.path.join(TEMPLATE_DIR, "send_button.png")
CHAT_INPUT_IMG = os.path.join(TEMPLATE_DIR, "chat_input.png")
# 新增的模板路徑
CHAT_OPTION_IMG = os.path.join(TEMPLATE_DIR, "chat_option.png")
UPDATE_CONFIRM_IMG = os.path.join(TEMPLATE_DIR, "update_confirm.png")
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
SCREENSHOT_REGION = (70, 50, 800, 1365) # Updated region
CONFIDENCE_THRESHOLD = 0.9 # Increased threshold for corner matching
STATE_CONFIDENCE_THRESHOLD = 0.9
AVATAR_OFFSET_X = -50 # Original offset, used for non-reply interactions like position removal
AVATAR_OFFSET_Y = 15  # Vertical offset for non-reply interactions, as requested
# AVATAR_OFFSET_X_RELOCATED = -50 # Replaced by specific reply offsets
AVATAR_OFFSET_X_REPLY = -45 # Horizontal offset for avatar click after re-location (for reply context)
AVATAR_OFFSET_Y_REPLY = 10  # Vertical offset for avatar click after re-location (for reply context)
AVATAR_EXTENSION_PX = 120  # Extended pixels to the left for avatar inclusion in screenshots
BUBBLE_RELOCATE_CONFIDENCE = 0.8 # Reduced confidence for finding the bubble snapshot (was 0.9)
BUBBLE_RELOCATE_FALLBACK_CONFIDENCE = 0.6 # Lower confidence for fallback attempts
BBOX_SIMILARITY_TOLERANCE = 10
RECENT_TEXT_HISTORY_MAXLEN = 5 # This state likely belongs in the coordinator

# --- New Constants for Dual Method ---
CLAHE_CLIP_LIMIT = 2.0  # CLAHE enhancement parameter
CLAHE_TILE_SIZE = (8, 8)  # CLAHE grid size
MATCH_DISTANCE_THRESHOLD = 10  # Threshold for considering detections as overlapping (pixels)
DUAL_METHOD_CONFIDENCE_THRESHOLD = 0.85 # Confidence threshold for individual methods in dual mode
DUAL_METHOD_HIGH_CONFIDENCE_THRESHOLD = 0.85 # Threshold for accepting single method result directly
DUAL_METHOD_FALLBACK_CONFIDENCE_THRESHOLD = 0.8 # Threshold for accepting single method result in fallback

# --- Helper Functions for Extended Screenshot ---
def capture_extended_bubble_screenshot(bubble_region_tuple, extension_left=AVATAR_EXTENSION_PX):
    """擴展泡泡截圖範圍，向左擴展指定像素以包含頭像"""
    x, y, w, h = bubble_region_tuple
    extended_region = (max(0, x - extension_left), y, w + extension_left, h)
    return pyautogui.screenshot(region=extended_region), extension_left

def compensate_coordinates_for_extended_screenshot(bubble_box, extension_px=AVATAR_EXTENSION_PX):
    """將擴展截圖中的座標轉換為螢幕絕對座標"""
    return (bubble_box.left + extension_px, bubble_box.top, bubble_box.width, bubble_box.height)

# Global DPI scale cache to avoid repeated detection
_cached_dpi_scale = None

def get_windows_dpi_scale():
    """獲取Windows DPI縮放因子，處理125%等UI显示縮放（帶緩存）"""
    global _cached_dpi_scale
    
    if _cached_dpi_scale is not None:
        return _cached_dpi_scale
        
    try:
        import ctypes
        from ctypes import wintypes
        
        # 讓程序感知DPI（只設定一次）
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        
        # 獲取螢幕DPI
        dc = user32.GetDC(0)
        gdi32 = ctypes.windll.gdi32
        dpi = gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        user32.ReleaseDC(0, dc)
        
        # 標準DPI是96，計算縮放因子
        scale_factor = dpi / 96.0
        _cached_dpi_scale = scale_factor
        print(f"Windows DPI detected: {dpi}, Scale factor: {scale_factor:.2f} ({scale_factor*100:.0f}%)")
        return scale_factor
    except Exception as e:
        print(f"Warning: Could not detect DPI scaling, assuming 100%: {e}")
        _cached_dpi_scale = 1.0
        return 1.0

def calculate_safe_click_region():
    """計算安全點擊區域，考慮DPI縮放並基於config中的遊戲視窗設定，內縮5px作為安全區域"""
    # 獲取DPI縮放因子
    scale_factor = get_windows_dpi_scale()
    
    # 從 config 讀取遊戲視窗設定（100%基準）
    window_x = config.GAME_WINDOW_X
    window_y = config.GAME_WINDOW_Y 
    window_width = config.GAME_WINDOW_WIDTH
    window_height = config.GAME_WINDOW_HEIGHT
    
    # 檢查是否需要DPI調整（預設啟用）
    apply_dpi_scaling = getattr(config, 'APPLY_DPI_SCALING', True)
    
    if apply_dpi_scaling and scale_factor != 1.0:
        # 應用DPI縮放調整（config是按100%記錄）
        actual_x = int(window_x * scale_factor)
        actual_y = int(window_y * scale_factor) 
        actual_width = int(window_width * scale_factor)
        actual_height = int(window_height * scale_factor)
        safe_margin = int(5 * scale_factor)
    else:
        # 不應用DPI調整或縮放為100%
        actual_x = window_x
        actual_y = window_y
        actual_width = window_width
        actual_height = window_height
        safe_margin = 5
    
    # 計算安全區域
    safe_x_min = actual_x + safe_margin
    safe_y_min = actual_y + safe_margin
    safe_x_max = actual_x + actual_width - safe_margin
    safe_y_max = actual_y + actual_height - safe_margin
    
    return (safe_x_min, safe_y_min, safe_x_max, safe_y_max)

def is_click_position_safe(x: int, y: int) -> bool:
    """檢查點擊位置是否在安全區域內"""
    safe_x_min, safe_y_min, safe_x_max, safe_y_max = calculate_safe_click_region()
    return safe_x_min <= x <= safe_x_max and safe_y_min <= y <= safe_y_max

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
    """Handles finding elements and states on the screen using image recognition or color analysis."""

    def __init__(self, templates: Dict[str, str], confidence: float = CONFIDENCE_THRESHOLD,
                 state_confidence: float = STATE_CONFIDENCE_THRESHOLD,
                 region: Optional[Tuple[int, int, int, int]] = SCREENSHOT_REGION,
                 use_dual_method: bool = True): # Added use_dual_method flag
        # --- Hardcoded Settings (as per user instruction) ---
        self.use_color_detection: bool = True # Set to True to enable color detection by default
        self.color_config_path: str = "bubble_colors.json"
        # --- End Hardcoded Settings ---

        self.templates = templates
        self.confidence = confidence # Default confidence for legacy methods
        self.state_confidence = state_confidence
        self.region = region
        self._warned_paths = set()

        # --- Dual Method Specific Initialization ---
        self.use_dual_method = use_dual_method
        self.clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_SIZE)
        self.core_keyword_templates = {k: v for k, v in templates.items()
                                       if k in ['keyword_wolf_lower', 'keyword_Wolf_upper', 'keyword_wolf_reply']}
        self.last_detection_method = None
        self.last_detection_confidence = 0.0
        self.DEBUG_LEVEL = DEBUG_LEVEL # Use global debug level

        # Performance Stats
        self.performance_stats = {
            'total_detections': 0,
            'successful_detections': 0,
            'gray_only_detections': 0,
            'clahe_only_detections': 0,
            'dual_method_detections': 0,
            'fallback_detections': 0, # Added for fallback tracking
            'total_detection_time': 0.0,
            'inverted_matches': 0,
            'adaptive_threshold_successes': 0,
            'stability_waits': 0,
            'verification_failures': 0
        }
        # --- End Dual Method Specific Initialization ---
        
        # Enhanced reliability settings (optimized for game UI responsiveness)
        self.ui_stability_timeout = 0.5  # Maximum wait time for UI stability (reduced for gaming)
        self.ui_stability_duration = 0.1  # Required stable duration (games are fast)
        self.verification_attempts = 3   # Number of verification attempts
        self.coordinate_tolerance = 10   # Pixel tolerance for coordinate similarity

        # Load color configuration if color detection is enabled
        self.bubble_colors = []
        if self.use_color_detection:
            self.bubble_colors = load_bubble_colors(self.color_config_path) # Use internal path
            if not self.bubble_colors:
                 print("Warning: Color detection enabled, but failed to load any color configurations. Color detection might not work.")

        # 經濟模式相關變數
        self.eco_mode_enabled = False
        self.no_new_bubbles_count = 0  # 連續無新泡泡的循環次數
        self.eco_mode_threshold = 2    # 觸發經濟模式的閾值
        self.eco_mode_interval = 1.5   # 經濟模式的檢測間隔（秒）
        self.eco_mode_region = (90, 550, 610, 200)  # 固定監控區域 (x, y, width, height)
        self.last_eco_screenshot = None  # 上次經濟模式截圖的numpy array
        
        print(f"DetectionModule initialized. Color Detection: {'Enabled' if self.use_color_detection else 'Disabled'}. Dual Keyword Method: {'Enabled' if self.use_dual_method else 'Disabled'}")

    def _apply_clahe(self, image):
        """Apply CLAHE to enhance image contrast."""
        if image is None:
            print("Warning: _apply_clahe received None image.")
            return None
        try:
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy() # Assume already grayscale
            enhanced = self.clahe.apply(gray)
            return enhanced
        except Exception as e:
            print(f"Error applying CLAHE: {e}")
            # Return original grayscale image on error
            return gray if 'gray' in locals() else image

    def _find_template(self, template_key: str, confidence: Optional[float] = None, region: Optional[Tuple[int, int, int, int]] = None, grayscale: bool = False) -> List[Tuple[int, int]]:
        """Internal helper to find a template by its key using PyAutoGUI. Returns list of CENTER coordinates (absolute)."""
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
        Detects dialogue bubbles using either color analysis or template matching,
        based on the 'use_color_detection' flag. Includes fallback to template matching.
        Returns a list of dictionaries, each containing:
        {'bbox': (tl_x, tl_y, br_x, br_y), 'is_bot': bool, 'tl_coords': (tl_x, tl_y)}
        """
        # --- Try Color Detection First if Enabled ---
        if self.use_color_detection:
            print("Attempting bubble detection using color analysis...")
            try:
                # Use a scale factor of 0.5 for performance
                bubbles = self.find_dialogue_bubbles_by_color(scale_factor=0.5)
                # If color detection returns results, use them
                if bubbles:
                    print("Color detection successful.")
                    return bubbles
                else:
                    print("Color detection returned no bubbles. Falling back to template matching.")
            except Exception as e:
                print(f"Color detection failed with error: {e}. Falling back to template matching.")
                import traceback
                traceback.print_exc()
        else:
             print("Color detection disabled. Using template matching.")

        # --- Fallback to Template Matching ---
        print("Executing template matching for bubble detection...")
        all_bubbles_info = []
        processed_tls = set() # Keep track of TL corners already used in a bubble

        # --- Find ALL Regular Bubble Corners (Raw Coordinates) ---
        regular_tl_keys = ['corner_tl', 'corner_tl_type2', 'corner_tl_type3', 'corner_tl_type4'] # Added type4
        regular_br_keys = ['corner_br', 'corner_br_type2', 'corner_br_type3', 'corner_br_type4'] # Added type4

        bubble_detection_region = (200, 330, 680, 1200) # Define the specific region for bubbles
        print(f"DEBUG: Using specific region for bubble corner detection: {bubble_detection_region}")

        all_regular_tl_boxes = []
        for key in regular_tl_keys:
            all_regular_tl_boxes.extend(self._find_template_raw(key, region=bubble_detection_region)) # Pass region

        all_regular_br_boxes = []
        for key in regular_br_keys:
            all_regular_br_boxes.extend(self._find_template_raw(key, region=bubble_detection_region)) # Pass region

        # --- Find Bot Bubble Corners (Raw Coordinates - Single Type) ---
        bot_tl_boxes = self._find_template_raw('bot_corner_tl', region=bubble_detection_region) # Pass region
        bot_br_boxes = self._find_template_raw('bot_corner_br', region=bubble_detection_region) # Pass region

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
        print(f"Template matching found {len(all_bubbles_info)} bubbles.") # Added log
        return all_bubbles_info

    def find_dialogue_bubbles_by_color(self, scale_factor=0.5) -> List[Dict[str, Any]]:
        """
        Find dialogue bubbles using color analysis within a specific region.
        Applies scaling to improve performance.
        Returns a list of dictionaries, each containing:
        {'bbox': (tl_x, tl_y, br_x, br_y), 'is_bot': bool, 'tl_coords': (tl_x, tl_y)}
        """
        all_bubbles_info = []

        # Define the specific region for bubble detection (same as template matching)
        bubble_detection_region = (200, 270, 680, 1200)
        print(f"Using bubble color detection region: {bubble_detection_region}")

        try:
            # 1. Capture the specified region
            screenshot = pyautogui.screenshot(region=bubble_detection_region)
            if screenshot is None:
                print("Error: Failed to capture screenshot for color detection.")
                return []
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR) # Convert RGB (from pyautogui) to BGR (for OpenCV)

            # 2. Resize for performance
            if scale_factor < 1.0:
                h, w = img.shape[:2]
                new_h, new_w = int(h * scale_factor), int(w * scale_factor)
                if new_h <= 0 or new_w <= 0:
                    print(f"Error: Invalid dimensions after scaling: {new_w}x{new_h}. Using original image.")
                    img_small = img
                    current_scale_factor = 1.0
                else:
                    img_small = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    print(f"Original resolution: {w}x{h}, Scaled down to: {new_w}x{new_h}")
                    current_scale_factor = scale_factor
            else:
                img_small = img
                current_scale_factor = 1.0

            # 3. Convert to HSV color space
            hsv = cv2.cvtColor(img_small, cv2.COLOR_BGR2HSV)

            # 4. Process each configured bubble type
            if not self.bubble_colors:
                print("Error: No bubble color configurations loaded for detection.")
                return []

            for color_config in self.bubble_colors:
                name = color_config.get('name', 'unknown')
                is_bot = color_config.get('is_bot', False)
                hsv_lower = np.array(color_config.get('hsv_lower', [0,0,0]))
                hsv_upper = np.array(color_config.get('hsv_upper', [179,255,255]))
                min_area_config = color_config.get('min_area', 3000)
                max_area_config = color_config.get('max_area', 100000)

                # Adjust area thresholds based on scaling factor
                min_area = min_area_config * (current_scale_factor ** 2)
                max_area = max_area_config * (current_scale_factor ** 2)

                print(f"Processing color type: {name} (Bot: {is_bot}), HSV Lower: {hsv_lower}, HSV Upper: {hsv_upper}, Area: {min_area:.0f}-{max_area:.0f}")

                # 5. Create mask based on HSV range
                mask = cv2.inRange(hsv, hsv_lower, hsv_upper)

                # 6. Morphological operations (Closing) to remove noise and fill holes
                kernel = np.ones((3, 3), np.uint8)
                mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2) # Increased iterations

                # Optional: Dilation to merge nearby parts?
                # mask_closed = cv2.dilate(mask_closed, kernel, iterations=1)

                # 7. Find connected components
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_closed)

                # 8. Filter components by area and add to results
                for i in range(1, num_labels): # Skip background label 0
                    area = stats[i, cv2.CC_STAT_AREA]

                    if min_area <= area <= max_area:
                        x_s = stats[i, cv2.CC_STAT_LEFT]
                        y_s = stats[i, cv2.CC_STAT_TOP]
                        w_s = stats[i, cv2.CC_STAT_WIDTH]
                        h_s = stats[i, cv2.CC_STAT_HEIGHT]

                        # Convert coordinates back to original resolution
                        if current_scale_factor < 1.0:
                            x = int(x_s / current_scale_factor)
                            y = int(y_s / current_scale_factor)
                            width = int(w_s / current_scale_factor)
                            height = int(h_s / current_scale_factor)
                        else:
                            x, y, width, height = x_s, y_s, w_s, h_s

                        # Adjust coordinates relative to the full screen (add region offset)
                        x_adjusted = x + bubble_detection_region[0]
                        y_adjusted = y + bubble_detection_region[1]

                        bubble_bbox = (x_adjusted, y_adjusted, x_adjusted + width, y_adjusted + height)
                        tl_coords = (x_adjusted, y_adjusted) # Top-left coords in full screen space

                        all_bubbles_info.append({
                            'bbox': bubble_bbox,
                            'is_bot': is_bot,
                            'tl_coords': tl_coords
                        })
                        print(f"  -> Found '{name}' bubble component. Area: {area:.0f} (Scaled). Original Coords: {bubble_bbox}")

        except pyautogui.FailSafeException:
             print("FailSafe triggered during color detection.")
             return []
        except Exception as e:
            print(f"Error during color-based bubble detection: {e}")
            import traceback
            traceback.print_exc()
            return [] # Return empty list on error

        print(f"Color detection found {len(all_bubbles_info)} bubbles.")
        return all_bubbles_info

    def _find_keyword_legacy(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """
        Original find_keyword_in_region implementation using multiple templates and PyAutoGUI.
        Kept for backward compatibility or fallback. Returns absolute center coordinates or None.
        """
        if region[2] <= 0 or region[3] <= 0: return None # Invalid region width/height

        # Define the order of templates to check (legacy approach)
        legacy_keyword_templates = [
            # Original keywords first
            'keyword_wolf_lower', 'keyword_wolf_upper',
            # Deprecated keywords next (order might matter based on visual similarity)
            'keyword_wolf_lower_type2', 'keyword_wolf_upper_type2',
            'keyword_wolf_lower_type3', 'keyword_wolf_upper_type3',
            'keyword_wolf_lower_type4', 'keyword_wolf_upper_type4',
            # Reply keywords last
            'keyword_wolf_reply', 'keyword_wolf_reply_type2',
            'keyword_wolf_reply_type3', 'keyword_wolf_reply_type4'
        ]

        for key in legacy_keyword_templates:
            # Determine grayscale based on key (example logic, adjust as needed)
            # Original logic seemed to use grayscale=True for lower/upper, False otherwise. Let's replicate that.
            use_grayscale = ('lower' in key or 'upper' in key) and 'type' not in key and 'reply' not in key
            # Use the default confidence defined in __init__ for legacy checks
            locations = self._find_template(key, region=region, grayscale=use_grayscale, confidence=self.confidence)
            if locations:
                print(f"Legacy method found keyword ('{key}') in region {region}, position: {locations[0]}")
                return locations[0] # Return the first match found

        return None # No keyword found using legacy method

    def find_keyword_dual_method(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """
        Find keywords using grayscale and CLAHE preprocessed images with OpenCV template matching.
        Applies coordinate correction to return absolute screen coordinates.
        Returns absolute center coordinates tuple (x, y) or None.
        """
        if region is None or len(region) != 4 or region[2] <= 0 or region[3] <= 0:
            print(f"Error: Invalid region provided to find_keyword_dual_method: {region}")
            return None

        start_time = time.time()
        region_x, region_y, region_w, region_h = region

        try:
            screenshot = pyautogui.screenshot(region=region)
            if screenshot is None:
                print("Error: Failed to capture screenshot for dual method detection.")
                return None
            img = np.array(screenshot)
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"Error capturing or converting screenshot in region {region}: {e}")
            return None

        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_clahe = self._apply_clahe(img_gray) # Use helper method

        if img_clahe is None:
            print("Error: CLAHE preprocessing failed. Cannot proceed with CLAHE matching.")
            # Optionally, could proceed with only grayscale matching here, but for simplicity, we return None.
            return None

        gray_results = []
        clahe_results = []
        template_types = { # Map core template keys to types
            'keyword_wolf_lower': 'standard',
            'keyword_Wolf_upper': 'standard',
            'keyword_wolf_reply': 'reply'
        }

        for key, template_path in self.core_keyword_templates.items():
            if not os.path.exists(template_path):
                if template_path not in self._warned_paths:
                    print(f"Warning: Core keyword template not found: {template_path}")
                    self._warned_paths.add(template_path)
                continue

            template_bgr = cv2.imread(template_path)
            if template_bgr is None:
                if template_path not in self._warned_paths:
                    print(f"Warning: Failed to load core keyword template: {template_path}")
                    self._warned_paths.add(template_path)
                continue

            template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
            template_clahe = self._apply_clahe(template_gray) # Use helper method

            if template_clahe is None:
                 print(f"Warning: CLAHE preprocessing failed for template {key}. Skipping CLAHE match for this template.")
                 continue # Skip CLAHE part for this template

            h_gray, w_gray = template_gray.shape[:2]
            h_clahe, w_clahe = template_clahe.shape[:2]

            # --- Grayscale Matching ---
            try:
                gray_res = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                gray_inv_res = cv2.matchTemplate(img_gray, cv2.bitwise_not(template_gray), cv2.TM_CCOEFF_NORMED)
                gray_combined = np.maximum(gray_res, gray_inv_res)
                _, gray_max_val, _, gray_max_loc = cv2.minMaxLoc(gray_combined)

                if gray_max_val >= DUAL_METHOD_CONFIDENCE_THRESHOLD:
                    # Calculate relative center
                    relative_center_x = gray_max_loc[0] + w_gray // 2
                    relative_center_y = gray_max_loc[1] + h_gray // 2
                    # *** COORDINATE CORRECTION ***
                    absolute_center_x = region_x + relative_center_x
                    absolute_center_y = region_y + relative_center_y

                    # Check inversion
                    gray_orig_val = gray_res[gray_max_loc[1], gray_max_loc[0]] # Get value at max_loc from original match
                    is_inverted = (gray_orig_val < gray_max_val - 0.05)

                    gray_results.append({
                        'template': key,
                        'center': (absolute_center_x, absolute_center_y), # Store absolute coords
                        'confidence': gray_max_val,
                        'is_inverted': is_inverted,
                        'type': template_types.get(key, 'standard')
                    })
            except cv2.error as e:
                print(f"OpenCV Error during Grayscale matching for {key}: {e}")
            except Exception as e:
                print(f"Unexpected Error during Grayscale matching for {key}: {e}")


            # --- CLAHE Matching ---
            try:
                clahe_res = cv2.matchTemplate(img_clahe, template_clahe, cv2.TM_CCOEFF_NORMED)
                clahe_inv_res = cv2.matchTemplate(img_clahe, cv2.bitwise_not(template_clahe), cv2.TM_CCOEFF_NORMED)
                clahe_combined = np.maximum(clahe_res, clahe_inv_res)
                _, clahe_max_val, _, clahe_max_loc = cv2.minMaxLoc(clahe_combined)

                if clahe_max_val >= DUAL_METHOD_CONFIDENCE_THRESHOLD:
                    # Calculate relative center
                    relative_center_x = clahe_max_loc[0] + w_clahe // 2
                    relative_center_y = clahe_max_loc[1] + h_clahe // 2
                    # *** COORDINATE CORRECTION ***
                    absolute_center_x = region_x + relative_center_x
                    absolute_center_y = region_y + relative_center_y

                    # Check inversion
                    clahe_orig_val = clahe_res[clahe_max_loc[1], clahe_max_loc[0]] # Get value at max_loc from original match
                    is_inverted = (clahe_orig_val < clahe_max_val - 0.05)

                    clahe_results.append({
                        'template': key,
                        'center': (absolute_center_x, absolute_center_y), # Store absolute coords
                        'confidence': clahe_max_val,
                        'is_inverted': is_inverted,
                        'type': template_types.get(key, 'standard')
                    })
            except cv2.error as e:
                print(f"OpenCV Error during CLAHE matching for {key}: {e}")
            except Exception as e:
                print(f"Unexpected Error during CLAHE matching for {key}: {e}")

        # --- Result Merging and Selection ---
        elapsed_time = time.time() - start_time
        self.performance_stats['total_detections'] += 1
        self.performance_stats['total_detection_time'] += elapsed_time

        best_match = None
        final_result_coords = None
        final_template_key = None # 新增：用於儲存最終匹配的範本 key
        detection_type = "None" # For stats

        if not gray_results and not clahe_results:
            if self.DEBUG_LEVEL > 1:
                print(f"[Dual Method] No keywords found by either method. Time: {elapsed_time:.3f}s")
            self.last_detection_method = None
            self.last_detection_confidence = 0.0
            return None

        # Strategy 1: High-confidence single method result
        best_gray = max(gray_results, key=lambda x: x['confidence']) if gray_results else None
        best_clahe = max(clahe_results, key=lambda x: x['confidence']) if clahe_results else None

        if best_gray and not best_clahe and best_gray['confidence'] >= DUAL_METHOD_HIGH_CONFIDENCE_THRESHOLD:
            final_result_coords = best_gray['center']
            final_template_key = best_gray['template'] # 新增
            self.last_detection_method = "Gray" + (" (Inv)" if best_gray['is_inverted'] else "")
            self.last_detection_confidence = best_gray['confidence']
            detection_type = "Gray Only (High Conf)"
            self.performance_stats['gray_only_detections'] += 1
            if best_gray['is_inverted']: self.performance_stats['inverted_matches'] += 1
            print(f"[Dual Method] Using high-confidence Gray result: {best_gray['template']} at {final_result_coords} (Conf: {best_gray['confidence']:.2f})")

        elif best_clahe and not best_gray and best_clahe['confidence'] >= DUAL_METHOD_HIGH_CONFIDENCE_THRESHOLD:
            final_result_coords = best_clahe['center']
            final_template_key = best_clahe['template'] # 新增
            self.last_detection_method = "CLAHE" + (" (Inv)" if best_clahe['is_inverted'] else "")
            self.last_detection_confidence = best_clahe['confidence']
            detection_type = "CLAHE Only (High Conf)"
            self.performance_stats['clahe_only_detections'] += 1
            if best_clahe['is_inverted']: self.performance_stats['inverted_matches'] += 1
            print(f"[Dual Method] Using high-confidence CLAHE result: {best_clahe['template']} at {final_result_coords} (Conf: {best_clahe['confidence']:.2f})")

        # Strategy 2: Find overlapping results if no high-confidence single result yet
        if final_result_coords is None:
            best_overlap_match = None
            highest_overlap_confidence = 0

            for gray_match in gray_results:
                for clahe_match in clahe_results:
                    # Check if templates match (or maybe just type?) - let's stick to same template for now
                    if gray_match['template'] == clahe_match['template']:
                        dist = math.sqrt((gray_match['center'][0] - clahe_match['center'][0])**2 +
                                       (gray_match['center'][1] - clahe_match['center'][1])**2)

                        if dist < MATCH_DISTANCE_THRESHOLD:
                            # Use average confidence or max? Let's use average.
                            combined_confidence = (gray_match['confidence'] + clahe_match['confidence']) / 2
                            if combined_confidence > highest_overlap_confidence:
                                highest_overlap_confidence = combined_confidence
                                avg_center = (
                                    (gray_match['center'][0] + clahe_match['center'][0]) // 2,
                                    (gray_match['center'][1] + clahe_match['center'][1]) // 2
                                )
                                best_overlap_match = {
                                    'template': gray_match['template'],
                                    'center': avg_center,
                                    'confidence': combined_confidence,
                                    'dist': dist,
                                    'is_inverted': gray_match['is_inverted'] or clahe_match['is_inverted'],
                                    'type': gray_match['type'] # Type should be same
                                }

            if best_overlap_match:
                final_result_coords = best_overlap_match['center']
                final_template_key = best_overlap_match['template'] # 新增
                self.last_detection_method = "Dual Overlap" + (" (Inv)" if best_overlap_match['is_inverted'] else "")
                self.last_detection_confidence = best_overlap_match['confidence']
                detection_type = "Dual Overlap"
                self.performance_stats['dual_method_detections'] += 1
                if best_overlap_match['is_inverted']: self.performance_stats['inverted_matches'] += 1
                print(f"[Dual Method] Using overlapping result: {best_overlap_match['template']} at {final_result_coords} (Conf: {best_overlap_match['confidence']:.2f}, Dist: {best_overlap_match['dist']:.1f}px)")

        # Strategy 3: Fallback to best single result if no overlap found
        if final_result_coords is None:
            all_results = gray_results + clahe_results
            if all_results:
                best_overall = max(all_results, key=lambda x: x['confidence'])
                # Use a slightly lower threshold for fallback
                if best_overall['confidence'] >= DUAL_METHOD_FALLBACK_CONFIDENCE_THRESHOLD:
                    final_result_coords = best_overall['center']
                    final_template_key = best_overall['template'] # 新增
                    method_name = "Gray Fallback" if best_overall in gray_results else "CLAHE Fallback"
                    method_name += " (Inv)" if best_overall['is_inverted'] else ""
                    self.last_detection_method = method_name
                    self.last_detection_confidence = best_overall['confidence']
                    detection_type = "Fallback"
                    self.performance_stats['fallback_detections'] += 1 # Track fallbacks
                    if best_overall in gray_results: self.performance_stats['gray_only_detections'] += 1
                    else: self.performance_stats['clahe_only_detections'] += 1
                    if best_overall['is_inverted']: self.performance_stats['inverted_matches'] += 1
                    print(f"[Dual Method] Using fallback result ({method_name}): {best_overall['template']} at {final_result_coords} (Conf: {best_overall['confidence']:.2f})")

        # --- Final Result Handling & Debug ---
        if final_result_coords:
            self.performance_stats['successful_detections'] += 1
            if self.DEBUG_LEVEL >= 3:
                # --- Visual Debugging ---
                try:
                    # Create side-by-side comparison of gray and clahe
                    debug_processed_path = os.path.join(DEBUG_SCREENSHOT_DIR, f"dual_processed_{int(time.time())}.png")
                    # Ensure images have same height for hstack
                    h_gray_img, w_gray_img = img_gray.shape[:2]
                    h_clahe_img, w_clahe_img = img_clahe.shape[:2]
                    max_h = max(h_gray_img, h_clahe_img)
                    # Resize if needed (convert to BGR for stacking color images if necessary)
                    img_gray_bgr = cv2.cvtColor(cv2.resize(img_gray, (int(w_gray_img * max_h / h_gray_img), max_h)), cv2.COLOR_GRAY2BGR)
                    img_clahe_bgr = cv2.cvtColor(cv2.resize(img_clahe, (int(w_clahe_img * max_h / h_clahe_img), max_h)), cv2.COLOR_GRAY2BGR)
                    debug_img_processed = np.hstack([img_gray_bgr, img_clahe_bgr])
                    cv2.imwrite(debug_processed_path, debug_img_processed)

                    # Draw results on original BGR image
                    result_img = img_bgr.copy()
                    # Draw relative centers for visualization within the region
                    for result in gray_results:
                        rel_x = result['center'][0] - region_x
                        rel_y = result['center'][1] - region_y
                        cv2.circle(result_img, (rel_x, rel_y), 5, (0, 0, 255), -1) # Red = Gray
                    for result in clahe_results:
                        rel_x = result['center'][0] - region_x
                        rel_y = result['center'][1] - region_y
                        cv2.circle(result_img, (rel_x, rel_y), 5, (0, 255, 0), -1) # Green = CLAHE

                    # Mark final chosen point (relative)
                    final_rel_x = final_result_coords[0] - region_x
                    final_rel_y = final_result_coords[1] - region_y
                    cv2.circle(result_img, (final_rel_x, final_rel_y), 8, (255, 0, 0), 2) # Blue circle = Final

                    debug_result_path = os.path.join(DEBUG_SCREENSHOT_DIR, f"dual_result_{int(time.time())}.png")
                    cv2.imwrite(debug_result_path, result_img)
                    print(f"[Dual Method Debug] Saved processed image to {debug_processed_path}")
                    print(f"[Dual Method Debug] Saved result image to {debug_result_path}")
                except Exception as debug_e:
                    print(f"Error during visual debugging image generation: {debug_e}")
                # --- End Visual Debugging ---

            # Return absolute coordinates and the matched key
            return (final_result_coords, final_template_key)
        else:
            if self.DEBUG_LEVEL > 0: # Log failure only if debug level > 0
                 print(f"[Dual Method] No sufficiently confident match found. Time: {elapsed_time:.3f}s")
            self.last_detection_method = None
            self.last_detection_confidence = 0.0
            return None # Return None for both coords and key on failure

    def find_keyword_in_region(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[Tuple[int, int], str]]:
        """
        Wrapper method to find keywords in a region.
        Uses either the new dual method or the legacy method based on the 'use_dual_method' flag.
        Returns a tuple (absolute_center_coordinates, matched_template_key) or None.
        """
        if region is None or len(region) != 4 or region[2] <= 0 or region[3] <= 0:
            print(f"Error: Invalid region provided to find_keyword_in_region: {region}")
            return None

        if self.use_dual_method:
            # Directly return the result from the dual method (now returns tuple or None)
            return self.find_keyword_dual_method(region)
        else:
            # Legacy method needs adaptation if we want it to return a key.
            # For now, it returns only coords or None. We'll return None for the key part.
            legacy_coords = self._find_keyword_legacy(region)
            if legacy_coords:
                # We don't know the key from the legacy method easily. Return a placeholder or None.
                return (legacy_coords, None) # Or maybe a specific string like 'legacy_match'
            else:
                return None

    def print_detection_stats(self):
        """Prints the collected keyword detection performance statistics."""
        stats = self.performance_stats
        total = stats['total_detections']
        successful = stats['successful_detections']

        if total == 0:
            print("\n=== Keyword Detection Performance Stats ===")
            print("No detections recorded yet.")
            return

        print("\n=== Keyword Detection Performance Stats ===")
        print(f"Total Detection Attempts: {total}")
        success_rate = (successful / total * 100) if total > 0 else 0
        print(f"Successful Detections: {successful} ({success_rate:.1f}%)")
        avg_time = (stats['total_detection_time'] / total * 1000) if total > 0 else 0
        print(f"Average Detection Time: {avg_time:.2f} ms")

        if successful > 0:
            dual_pct = stats['dual_method_detections'] / successful * 100
            gray_pct = stats['gray_only_detections'] / successful * 100
            clahe_pct = stats['clahe_only_detections'] / successful * 100
            fallback_pct = stats['fallback_detections'] / successful * 100 # Percentage of successful that were fallbacks

            print("\nDetection Method Distribution (Successful Detections):")
            print(f"  - Dual Overlap: {stats['dual_method_detections']} ({dual_pct:.1f}%)")
            print(f"  - Gray Only:    {stats['gray_only_detections']} ({gray_pct:.1f}%)")
            print(f"  - CLAHE Only:   {stats['clahe_only_detections']} ({clahe_pct:.1f}%)")
            # Note: Gray Only + CLAHE Only might include high-confidence singles and fallbacks.
            # Fallback count is a subset of Gray/CLAHE Only.
            print(f"  - Fallback Used:{stats['fallback_detections']} ({fallback_pct:.1f}%)")


            if stats['inverted_matches'] > 0:
                inv_pct = stats['inverted_matches'] / successful * 100
                print(f"\nInverted Matches Detected: {stats['inverted_matches']} ({inv_pct:.1f}%)")
                
        # Enhanced Reliability Stats
        print("\nEnhanced Reliability Performance:")
        print(f"  - Adaptive Threshold Successes: {stats['adaptive_threshold_successes']}")
        print(f"  - UI Stability Waits: {stats['stability_waits']}")
        print(f"  - Verification Failures: {stats['verification_failures']}")
        
        if total > 0:
            adaptive_rate = (stats['adaptive_threshold_successes'] / total * 100)
            verification_failure_rate = (stats['verification_failures'] / total * 100)
            print(f"  - Adaptive Success Rate: {adaptive_rate:.1f}%")
            print(f"  - Verification Failure Rate: {verification_failure_rate:.1f}%")
            
        print("==========================================")

    # Enhanced Reliability Methods
    # ==============================================================================
    
    def calculate_image_difference(self, img1, img2) -> float:
        """
        Calculate the difference between two PIL Images.
        Returns a value between 0 (identical) and 1 (completely different).
        """
        try:
            arr1 = np.array(img1)
            arr2 = np.array(img2)
            
            # Ensure same dimensions
            if arr1.shape != arr2.shape:
                return 1.0  # Consider different sizes as completely different
            
            # Calculate mean absolute difference
            diff = np.mean(np.abs(arr1.astype(float) - arr2.astype(float))) / 255.0
            return diff
        except Exception as e:
            print(f"Error calculating image difference: {e}")
            return 1.0  # Assume different on error

    def wait_for_ui_stability(self, region: Tuple[int, int, int, int]) -> bool:
        """
        Wait for UI to become stable before detection.
        Returns True if UI is stable, False if timeout occurred.
        """
        last_screenshot = None
        stable_start_time = None
        start_time = time.time()
        
        while time.time() - start_time < self.ui_stability_timeout:
            try:
                current_screenshot = pyautogui.screenshot(region=region)
                
                if last_screenshot is not None:
                    diff = self.calculate_image_difference(last_screenshot, current_screenshot)
                    
                    if diff < 0.02:  # Less than 1% difference indicates stability (tighter for games)
                        if stable_start_time is None:
                            stable_start_time = time.time()
                        elif time.time() - stable_start_time >= self.ui_stability_duration:
                            self.performance_stats['stability_waits'] += 1
                            return True  # UI has been stable for required duration
                    else:
                        stable_start_time = None  # Reset stability timer
                
                last_screenshot = current_screenshot
                time.sleep(0.05)  # Short interval between checks
                
            except Exception as e:
                print(f"Error during UI stability check: {e}")
                return False
        
        return False  # Timeout reached without achieving stability

    def coordinates_are_similar(self, coords_list: List[Tuple[int, int]], tolerance: int = None) -> bool:
        """
        Check if a list of coordinates are similar within tolerance.
        Returns True if all coordinates are within tolerance of each other.
        """
        if tolerance is None:
            tolerance = self.coordinate_tolerance
            
        if len(coords_list) < 2:
            return True
        
        first_coord = coords_list[0]
        for coord in coords_list[1:]:
            if (abs(coord[0] - first_coord[0]) > tolerance or 
                abs(coord[1] - first_coord[1]) > tolerance):
                return False
        return True

    def verify_detection_result(self, detection_method, *args, **kwargs):
        """
        Verify detection result consistency through multiple attempts.
        Returns the verified result or None if verification fails.
        """
        results = []
        
        for i in range(self.verification_attempts):
            try:
                result = detection_method(*args, **kwargs)
                results.append(result)
                
                if i < self.verification_attempts - 1:  # Don't wait after last attempt
                    time.sleep(0.05)  # Short interval between verification attempts
                    
            except Exception as e:
                print(f"Error during verification attempt {i+1}: {e}")
                results.append(None)
        
        # Analyze results for consistency
        valid_results = [r for r in results if r is not None]
        
        if len(valid_results) >= 2:  # Need at least 2 successful detections
            # Check if results are coordinate-based or bubble-based
            if all(isinstance(r, tuple) and len(r) == 2 for r in valid_results):
                # Check if these are coordinate tuples or (coord, key) tuples
                if all(isinstance(r[0], (int, float)) for r in valid_results):
                    # Simple coordinate tuples (x, y)
                    if self.coordinates_are_similar(valid_results):
                        return valid_results[0]  # Return first valid result
                else:
                    # These are (coordinates, key) tuples from keyword detection
                    coords_only = [r[0] for r in valid_results if r[0] is not None]
                    if len(coords_only) >= 2 and self.coordinates_are_similar(coords_only):
                        return valid_results[0]  # Return first valid result
            elif all(isinstance(r, list) for r in valid_results):
                # Bubble list results - check if similar bubbles detected
                if len(valid_results[0]) == len(valid_results[1]):  # Same number of bubbles
                    return valid_results[0]  # Return first valid result
            else:
                # Other result types - just check for consistency
                if all(r == valid_results[0] for r in valid_results[1:]):
                    return valid_results[0]
        
        # Verification failed
        self.performance_stats['verification_failures'] += 1
        return None

    def adaptive_threshold_detection(self, template_key: str, region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int]]:
        """
        Perform adaptive threshold detection to eliminate boundary oscillation.
        Tests multiple confidence levels and returns result only if stable across levels.
        """
        confidence_levels = [0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
        stable_results = []
        
        for confidence in confidence_levels:
            try:
                # Use existing dual method with custom confidence
                result = self._find_template_with_confidence(template_key, region, confidence)
                if result:
                    stable_results.append((result, confidence))
            except Exception as e:
                print(f"Error in adaptive threshold detection at confidence {confidence}: {e}")
                continue
        
        # Require at least 2 successful detections at different confidence levels
        if len(stable_results) >= 2:
            # Check if coordinates are similar across confidence levels
            coords = [r[0] for r in stable_results]
            if self.coordinates_are_similar(coords):
                self.performance_stats['adaptive_threshold_successes'] += 1
                return stable_results[0][0]  # Return most conservative result
        
        return None

    def _find_template_with_confidence(self, template_key: str, region: Tuple[int, int, int, int], confidence: float) -> Optional[Tuple[int, int]]:
        """
        Helper method to find template with specific confidence level.
        Returns center coordinates or None.
        """
        template_path = self.templates.get(template_key)
        if not template_path or not os.path.exists(template_path):
            return None
        
        try:
            matches = pyautogui.locateAllOnScreen(template_path, region=region, confidence=confidence, grayscale=True)
            if matches:
                for box in matches:
                    center_x = box.left + box.width // 2
                    center_y = box.top + box.height // 2
                    return (center_x, center_y)
        except Exception as e:
            print(f"Error in template matching with confidence {confidence}: {e}")
        
        return None

    def enhanced_bubble_detection(self) -> List[Dict[str, Any]]:
        """
        Enhanced bubble detection with stability verification and result validation.
        """
        # Wait for UI stability first
        if not self.wait_for_ui_stability(self.region):
            return []
        
        # Use verification for reliable results
        result = self.verify_detection_result(self.find_dialogue_bubbles)
        return result if result is not None else []

    def enhanced_keyword_detection(self, region: Tuple[int, int, int, int]) -> Optional[Tuple[Tuple[int, int], str]]:
        """
        Enhanced keyword detection with adaptive thresholds and verification.
        """
        # Wait for UI stability first
        if not self.wait_for_ui_stability(region):
            return None
        
        # Use verification on the regular dual method
        return self.verify_detection_result(
            lambda r: self.find_keyword_dual_method(r), region
        )
    
    def eco_mode_check_region_change(self) -> bool:
        """
        經濟模式：檢測固定區域是否有變化
        使用腳本原有的cv2和numpy方法
        返回True表示檢測到變化，應該退出經濟模式
        """
        try:
            # 只在聊天室狀態下執行
            if not self._find_template('chat_room', confidence=self.state_confidence):
                print("經濟模式：不在聊天室狀態，跳過檢測")
                return False
            
            # 截取固定區域並轉換為numpy array
            current_screenshot = pyautogui.screenshot(region=self.eco_mode_region)
            current_img = np.array(current_screenshot)
            current_img = cv2.cvtColor(current_img, cv2.COLOR_RGB2BGR)
            
            # 轉換為灰度圖像以提高比較效率
            current_gray = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)
            
            if self.last_eco_screenshot is None:
                self.last_eco_screenshot = current_gray
                print("經濟模式：初始化基準截圖")
                return False
            
            # 計算結構相似性指數(SSIM)或直接使用像素差異
            # 使用簡單的像素差異比較（與腳本風格一致）
            diff = cv2.absdiff(self.last_eco_screenshot, current_gray)
            non_zero_count = cv2.countNonZero(diff)
            total_pixels = diff.shape[0] * diff.shape[1]
            change_percentage = (non_zero_count / total_pixels) * 100
            
            # 設定變化閾值（可調整）
            change_threshold = 2.0  # 2%的像素變化
            
            if change_percentage > change_threshold:
                print(f"經濟模式：檢測到顯著變化 {change_percentage:.2f}%，退出經濟模式")
                self.last_eco_screenshot = current_gray  # 更新基準
                return True
            
            print(f"經濟模式：無顯著變化 {change_percentage:.2f}%，繼續監控")
            return False
            
        except Exception as e:
            print(f"經濟模式檢測錯誤: {e}")
            return False

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
        """Safely click at specific coordinates with safety boundary check."""
        # 安全區域檢查
        if not is_click_position_safe(x, y):
            safe_x_min, safe_y_min, safe_x_max, safe_y_max = calculate_safe_click_region()
            scale_factor = get_windows_dpi_scale()
            scale_factor = get_windows_dpi_scale()
            print(f"\n⚠️  SAFETY VIOLATION: Click position ({x}, {y}) is outside safe game window boundary!")
            print(f"Safe area: ({safe_x_min}, {safe_y_min}) to ({safe_x_max}, {safe_y_max})")
            print(f"Config window (100%): ({config.GAME_WINDOW_X}, {config.GAME_WINDOW_Y}) size ({config.GAME_WINDOW_WIDTH}x{config.GAME_WINDOW_HEIGHT})")
            print(f"DPI scale factor: {scale_factor:.2f} ({scale_factor*100:.0f}%)")
            print(f"DPI scaling: {'ENABLED' if getattr(config, 'APPLY_DPI_SCALING', True) else 'DISABLED'}")
            print(f"Click operation BLOCKED for safety.")
            return False  # 禁止點擊並返回false
        
        try:
            scale_factor = get_windows_dpi_scale()
            scaling_info = f" [DPI {scale_factor:.2f}]" if scale_factor != 1.0 else ""
            print(f"Moving to and clicking at: ({x}, {y}) [SAFE]{scaling_info}, button: {button}, clicks: {clicks}")
            pyautogui.moveTo(x, y, duration=duration)
            pyautogui.click(button=button, clicks=clicks, interval=interval)
            time.sleep(0.1)
            return True  # 成功點擊
        except Exception as e:
            print(f"Error clicking at coordinates ({x}, {y}): {e}")
            return False  # 點擊失敗

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
            # 添加編碼安全處理
            try:
                safe_text = handle_text_encoding(copied_text.strip())
                return safe_text
            except Exception as e:
                print(f"Error handling copied text encoding: {str(e)}")
                return copied_text.strip()  # 即使有問題也嘗試返回原始文字
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
            time.sleep(0.4)  # Extended delay for UI to process paste operation
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
            time.sleep(0.2)
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
                         search_area: Optional[Tuple[int, int, int, int]]) -> dict: # Area to search snapshot in
    """
    Performs the sequence of UI actions to remove a user's position based on the triggering chat bubble.
    Includes re-location using the provided snapshot before proceeding.
    Returns dict with status, error_type, and message.
    """
    
    def _return_result(status: str, error_type: str = None, message: str = "") -> dict:
        """Helper function to return consistent result format"""
        return {
            "status": status,
            "error_type": error_type,
            "message": message
        }
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
                    return _return_result("failed", "ui_operation_failed", "Invalid bubble region for snapshot creation")
                
                print(f"Taking new screenshot of region: {bubble_region_tuple}")
                bubble_snapshot, extension_used = capture_extended_bubble_screenshot(bubble_region_tuple)
                if bubble_snapshot:
                    print(f"Successfully created extended bubble snapshot with {extension_used}px left extension.")
                else:
                    print("Failed to create new bubble snapshot.")
                    return _return_result("failed", "ui_operation_failed", "Failed to create bubble snapshot")
            else:
                print("Invalid trigger_bubble_region format, cannot create snapshot.")
                return _return_result("failed", "ui_operation_failed", "Invalid trigger bubble region format")
        except Exception as e:
            print(f"Error creating new bubble snapshot: {e}")
            return _return_result("failed", "ui_operation_failed", f"Exception creating bubble snapshot: {str(e)}")
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
        temp_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                region=region_to_search,
                                                confidence=BUBBLE_RELOCATE_CONFIDENCE)
        if temp_bubble_box:
            compensated_coords = compensate_coordinates_for_extended_screenshot(temp_bubble_box)
            new_bubble_box = type(temp_bubble_box)(compensated_coords[0], compensated_coords[1], compensated_coords[2], compensated_coords[3])
        else:
            new_bubble_box = None
    except Exception as e:
        print(f"Exception during initial bubble location attempt: {e}")

    # Second attempt with fallback confidence if first failed
    if not new_bubble_box:
        print(f"First attempt failed. Trying with lower confidence {BUBBLE_RELOCATE_FALLBACK_CONFIDENCE}...")
        try:
            # Try with a lower confidence threshold
            temp_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                    region=region_to_search,
                                                    confidence=BUBBLE_RELOCATE_FALLBACK_CONFIDENCE)
            if temp_bubble_box:
                compensated_coords = compensate_coordinates_for_extended_screenshot(temp_bubble_box)
                new_bubble_box = type(temp_bubble_box)(compensated_coords[0], compensated_coords[1], compensated_coords[2], compensated_coords[3])
            else:
                new_bubble_box = None
        except Exception as e:
            print(f"Exception during fallback bubble location attempt: {e}")

    # Third attempt with even lower confidence as last resort
    if not new_bubble_box:
        print("Second attempt failed. Trying with even lower confidence 0.4...")
        try:
            # Last resort with very low confidence
            temp_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                   region=region_to_search,
                                                   confidence=0.4)
            if temp_bubble_box:
                compensated_coords = compensate_coordinates_for_extended_screenshot(temp_bubble_box)
                new_bubble_box = type(temp_bubble_box)(compensated_coords[0], compensated_coords[1], compensated_coords[2], compensated_coords[3])
            else:
                new_bubble_box = None
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
            return _return_result("failed", "ui_operation_failed", "No original trigger region available for fallback")

    # Use compensated coordinates for screen clicks, but original coordinates for template search
    # Store both compensated (for clicks) and original (for template search) coordinates
    compensated_x, compensated_y = new_bubble_box.left, new_bubble_box.top
    bubble_w, bubble_h = new_bubble_box.width, new_bubble_box.height
    
    # For position detection, we need the original bubble coordinates (subtract extension offset)
    bubble_x = compensated_x - AVATAR_EXTENSION_PX  # Remove the 120px extension for search region
    bubble_y = compensated_y  # Y coordinate is not affected by left extension
    
    print(f"Successfully re-located bubble - Compensated: ({compensated_x}, {compensated_y}), Search base: ({bubble_x}, {bubble_y})")
    print(f"Using search base coordinates for position detection, compensated coordinates for avatar clicks")
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
        return _return_result("failed", "ui_operation_failed", "Invalid search region calculated for position icons")
        
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
        return _return_result("failed", "no_position_found", "User does not have any position assigned")

    # Find the closest one to the bubble's top-center
    bubble_top_center_x = bubble_x + bubble_w // 2
    bubble_top_center_y = bubble_y
    closest_position = min(found_positions, key=lambda p:
                           (p['coords'][0] - bubble_top_center_x)**2 + (p['coords'][1] - bubble_top_center_y)**2)

    target_position_name = closest_position['name']
    print(f"Found pending position: |{target_position_name}| at {closest_position['coords']}")

    # 2. Click user avatar (offset from *compensated* bubble coordinates for accurate clicking)
    # --- MODIFIED: Use compensated coordinates for avatar clicks ---
    avatar_click_x = compensated_x + AVATAR_OFFSET_X # Use non-reply offset for position removal
    avatar_click_y = compensated_y + AVATAR_OFFSET_Y # Use non-reply offset for position removal
    print(f"Clicking avatar for position removal at calculated position: ({avatar_click_x}, {avatar_click_y}) using offsets ({AVATAR_OFFSET_X}, {AVATAR_OFFSET_Y}) from compensated bubble coordinates ({compensated_x}, {compensated_y})")
    # --- END MODIFICATION ---
    interactor.click_at(avatar_click_x, avatar_click_y)
    time.sleep(0.15) # Wait for profile page

    # 3. Verify Profile Page and Click Capitol Button
    if not detector._find_template('profile_page', confidence=detector.state_confidence):
        print("Error: Failed to verify Profile Page after clicking avatar.")
        perform_state_cleanup(detector, interactor) # Attempt cleanup
        return _return_result("failed", "ui_operation_failed", "Failed to verify Profile Page after clicking avatar")
    print("Profile page verified.")

    capitol_button_locs = detector._find_template('capitol_button', confidence=0.8)
    if not capitol_button_locs:
        print("Error: Capitol button (#11) not found on profile page.")
        perform_state_cleanup(detector, interactor)
        return _return_result("failed", "ui_operation_failed", "Capitol button not found on profile page")
    interactor.click_at(capitol_button_locs[0][0], capitol_button_locs[0][1])
    print("Clicked Capitol button.")
    time.sleep(0.15) # Wait for capitol page

    # 4. Verify Capitol Page
    if not detector._find_template('president_title', confidence=detector.state_confidence):
        print("Error: Failed to verify Capitol Page (President Title not found).")
        perform_state_cleanup(detector, interactor)
        return _return_result("failed", "ui_operation_failed", "Failed to verify Capitol Page - President Title not found")
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
        return _return_result("failed", "ui_operation_failed", f"Internal error - unknown position name: {target_position_name}")

    pos_button_locs = detector._find_template(target_button_key, confidence=0.8)
    if not pos_button_locs:
        print(f"Error: Position button for '{target_position_name}' not found on Capitol page.")
        perform_state_cleanup(detector, interactor)
        return _return_result("failed", "ui_operation_failed", f"Position button for '{target_position_name}' not found on Capitol page")
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
         return _return_result("failed", "ui_operation_failed", f"Internal error - unknown position name for page verification: {target_position_name}")

    if not detector._find_template(target_page_key, confidence=detector.state_confidence):
        print(f"Error: Failed to verify correct position page for '{target_position_name}'.")
        perform_state_cleanup(detector, interactor)
        return _return_result("failed", "ui_operation_failed", f"Failed to verify correct position page for '{target_position_name}'")
    print(f"Verified '{target_position_name}' position page.")

    # 7. Find and Click Dismiss Button
    dismiss_locs = detector._find_template('dismiss_button', confidence=0.8)
    if not dismiss_locs:
        print("Error: Dismiss button not found on position page.")
        perform_state_cleanup(detector, interactor)
        return _return_result("failed", "ui_operation_failed", "Dismiss button not found on position page")
    interactor.click_at(dismiss_locs[0][0], dismiss_locs[0][1])
    print("Clicked Dismiss button.")
    time.sleep(0.1) # Wait for confirmation

    # 8. Find and Click Confirm Button
    confirm_locs = detector._find_template('confirm_button', confidence=0.8)
    if not confirm_locs:
        print("Error: Confirm button not found after clicking dismiss.")
        # Don't cleanup here, might be stuck in confirmation state
        return _return_result("failed", "ui_operation_failed", "Confirm button not found after clicking dismiss")
    interactor.click_at(confirm_locs[0][0], confirm_locs[0][1])
    print("Clicked Confirm button. Position should be dismissed.")
    time.sleep(0.05) # Wait for action to complete (Reduced from 0.1)

    # 9. Cleanup: Return to Chat Room
    # Click Close on position page (should now be back on capitol page implicitly)
    close_locs = detector._find_template('close_button', confidence=0.8)
    if close_locs:
        interactor.click_at(close_locs[0][0], close_locs[0][1])
        print("Clicked Close button (returning to Capitol).")
        time.sleep(0.05) # Reduced from 0.1
    else:
        print("Warning: Close button not found after confirm, attempting back arrow anyway.")

    # Click Back Arrow on Capitol page (should return to profile)
    back_arrow_locs = detector._find_template('back_arrow', confidence=0.8)
    if back_arrow_locs:
        interactor.click_at(back_arrow_locs[0][0], back_arrow_locs[0][1])
        print("Clicked Back Arrow (returning to Profile).")
        time.sleep(0.05) # Reduced from 0.1
    else:
        print("Warning: Back arrow not found on Capitol page, attempting ESC cleanup.")

    # Use standard ESC cleanup
    print("Initiating final ESC cleanup to return to chat...")
    cleanup_success = perform_state_cleanup(detector, interactor)

    if cleanup_success:
        print("--- Position Removal Process Completed Successfully ---")
        return _return_result("success", None, "Position removal completed successfully")
    else:
        print("--- Position Removal Process Completed Successfully (automatic navigation recovery will handle chat return) ---")
        return _return_result("success", None, "Position removal completed successfully")


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
def run_ui_monitoring_loop_enhanced(trigger_queue: queue.Queue, command_queue: queue.Queue, deduplicator: 'RobustMessageDeduplication', state_monitor: 'StateResetDetector'):
    """
    Continuously monitors the UI, detects triggers, performs interactions,
    puts trigger data into trigger_queue, and processes commands from command_queue.
    Includes state monitoring and robust deduplication.
    """
    print("\n--- Starting Enhanced UI Monitoring Loop (Thread) ---")

    # --- 初始化氣泡圖像去重系統（新增） ---
    bubble_deduplicator = SimpleBubbleDeduplication(
        storage_file="simple_bubble_dedup.json",
        max_bubbles=4,  # 增加記憶數量以覆蓋整個螢幕的泡泡
        threshold=8,      # 哈希差異閾值（值越小越嚴格）
        hash_size=16      # 哈希大小
    )
    # --- 初始化氣泡圖像去重系統結束 ---

    # --- Initialization (Instantiate modules within the thread) ---
    # --- Template Dictionary Setup (Refactored) ---
    essential_templates = {
        # Bubble Corners (All types needed for legacy/color fallback)
        'corner_tl': CORNER_TL_IMG, 'corner_br': CORNER_BR_IMG,
        'corner_tl_type2': CORNER_TL_TYPE2_IMG, 'corner_br_type2': CORNER_BR_TYPE2_IMG,
        'corner_tl_type3': CORNER_TL_TYPE3_IMG, 'corner_br_type3': CORNER_BR_TYPE3_IMG,
        'corner_tl_type4': CORNER_TL_TYPE4_IMG, 'corner_br_type4': CORNER_BR_TYPE4_IMG, # Added type4
        'bot_corner_tl': BOT_CORNER_TL_IMG, 'bot_corner_br': BOT_CORNER_BR_IMG,
        # Core Keywords (for dual method)
        'keyword_wolf_lower': KEYWORD_wolf_LOWER_IMG,
        'keyword_Wolf_upper': KEYWORD_Wolf_UPPER_IMG,
        'keyword_wolf_reply': KEYWORD_WOLF_REPLY_IMG,
        # Essential UI Elements
        'copy_menu_item': COPY_MENU_ITEM_IMG, 'profile_option': PROFILE_OPTION_IMG,
        'copy_name_button': COPY_NAME_BUTTON_IMG, 'send_button': SEND_BUTTON_IMG,
        'chat_input': CHAT_INPUT_IMG, 'profile_name_page': PROFILE_NAME_PAGE_IMG,
        'profile_page': PROFILE_PAGE_IMG, 'chat_room': CHAT_ROOM_IMG,
        'base_screen': BASE_SCREEN_IMG, 'world_map_screen': WORLD_MAP_IMG,
        'world_chat': WORLD_CHAT_IMG, 'private_chat': PRIVATE_CHAT_IMG,
        # Position templates
        'development_pos': POS_DEV_IMG, 'interior_pos': POS_INT_IMG, 'science_pos': POS_SCI_IMG,
        'security_pos': POS_SEC_IMG, 'strategy_pos': POS_STR_IMG,
        # Capitol templates
        'capitol_button': CAPITOL_BUTTON_IMG, 'president_title': PRESIDENT_TITLE_IMG,
        'pos_btn_dev': POS_BTN_DEV_IMG, 'pos_btn_int': POS_BTN_INT_IMG, 'pos_btn_sci': POS_BTN_SCI_IMG,
        'pos_btn_sec': POS_BTN_SEC_IMG, 'pos_btn_str': POS_BTN_STR_IMG,
        'page_dev': PAGE_DEV_IMG, 'page_int': PAGE_INT_IMG, 'page_sci': PAGE_SCI_IMG,
        'page_sec': PAGE_SEC_IMG, 'page_str': PAGE_STR_IMG,
        'dismiss_button': DISMISS_BUTTON_IMG, 'confirm_button': CONFIRM_BUTTON_IMG,
        'close_button': CLOSE_BUTTON_IMG, 'back_arrow': BACK_ARROW_IMG,
        'reply_button': REPLY_BUTTON_IMG,
        # 添加新模板
        'chat_option': CHAT_OPTION_IMG, 'update_confirm': UPDATE_CONFIRM_IMG,
    }
    legacy_templates = {
        # Deprecated Keywords (for legacy method fallback)
        'keyword_wolf_lower_type2': KEYWORD_wolf_LOWER_TYPE2_IMG,
        'keyword_wolf_upper_type2': KEYWORD_Wolf_UPPER_TYPE2_IMG,
        'keyword_wolf_lower_type3': KEYWORD_wolf_LOWER_TYPE3_IMG,
        'keyword_wolf_upper_type3': KEYWORD_Wolf_UPPER_TYPE3_IMG,
        'keyword_wolf_lower_type4': KEYWORD_wolf_LOWER_TYPE4_IMG,
        'keyword_wolf_upper_type4': KEYWORD_Wolf_UPPER_TYPE4_IMG,
        'keyword_wolf_reply_type2': KEYWORD_WOLF_REPLY_TYPE2_IMG,
        'keyword_wolf_reply_type3': KEYWORD_WOLF_REPLY_TYPE3_IMG,
        'keyword_wolf_reply_type4': KEYWORD_WOLF_REPLY_TYPE4_IMG,
    }
    # Combine dictionaries
    all_templates = {**essential_templates, **legacy_templates}
    # --- End Template Dictionary Setup ---

    # --- Instantiate Modules ---
    detector = DetectionModule(all_templates,
                               confidence=CONFIDENCE_THRESHOLD, # Default for legacy pyautogui calls
                               state_confidence=STATE_CONFIDENCE_THRESHOLD,
                               region=SCREENSHOT_REGION,
                               use_dual_method=True) # Enable new method by default
    interactor = InteractionModule(detector,
                                   input_coords=(CHAT_INPUT_CENTER_X, CHAT_INPUT_CENTER_Y),
                                   input_template_key='chat_input',
                                   send_button_key='send_button')

# --- State Management (Local to this monitoring thread) ---
    last_processed_bubble_info = None # Store the whole dict now
    recent_texts = collections.deque(maxlen=RECENT_TEXT_HISTORY_MAXLEN) # Context-specific history needed
    screenshot_counter = 0 # Initialize counter for debug screenshots
    main_screen_click_counter = 0 # Counter for consecutive main screen clicks

    loop_counter = 0 # Add loop counter for debugging
    
    while True:
        loop_counter += 1
        found_new_bubble_this_cycle = False  # 追蹤本循環是否有新泡泡被處理
        
        # 每100次循環檢查一次對象狀態
        if loop_counter % 100 == 0:
            state_monitor.check_object_identity(deduplicator, "deduplicator")
            
            # 輸出統計信息
            stats = deduplicator.get_stats()
            print(f"Dedup Stats: {stats['active_records']} active records (total: {stats['total_records']})")
        
        # print(f"\n--- UI Loop Iteration #{loop_counter} ---") # DEBUG REMOVED

        # --- Process ALL Pending Commands First ---
        # print("[DEBUG] UI Loop: Processing command queue...") # DEBUG REMOVED
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

                elif action == 'remove_position_with_feedback':
                    # Check position removal lock first (DISABLED)
                    # if main.position_removal_used:
                    #     print(f"UI Thread: Position removal already used in this conversation, blocking request")
                    #     result = {
                    #         "status": "blocked",
                    #         "message": "Position removal function has already been used in this conversation. Only one usage per conversation is allowed.",
                    #         "user_name": command_data.get('user_context', 'Unknown User'),
                    #         "execution_time": datetime.datetime.now().isoformat(),
                    #         "request_id": command_data.get('request_id')
                    #     }
                    #     if command_data.get('mcp_request', False):
                    #         main.position_result_queue.put(result)
                    #     continue
                    
                    # Set the lock before processing (DISABLED)
                    # main.position_removal_used = True
                    # print(f"UI Thread: Position removal lock activated for this conversation")
                    
                    # 新增：帶結果回傳的職位移除（用於MCP tool）
                    snapshot = command_data.get('bubble_snapshot')
                    area = command_data.get('search_area')
                    original_region = command_data.get('trigger_bubble_region')
                    user_context = command_data.get('user_context', '')
                    is_mcp_request = command_data.get('mcp_request', False)
                    request_id = command_data.get('request_id')  # 新增：獲取request_id
                    
                    print(f"UI Thread: Processing remove_position_with_feedback (MCP: {is_mcp_request}, Request ID: {request_id})")
                    print(f"UI Thread: User context: {user_context}")
                    
                    if snapshot:
                        print(f"UI Thread: Snapshot available, attempting position removal...")
                        removal_result = remove_user_position(detector, interactor, original_region, snapshot, area)
                        
                        # Process detailed result information
                        if removal_result["status"] == "success":
                            result = {
                                "status": "success",
                                "message": "Position removal completed successfully",
                                "position_name": "Unknown Position",  # Can be improved with UI recognition in future
                                "user_name": user_context if user_context else "Unknown User",
                                "execution_time": datetime.datetime.now().isoformat(),
                                "request_id": request_id
                            }
                            print(f"UI Thread: Position removal successful: {result}")
                        else:
                            # Handle different failure types
                            error_type = removal_result.get("error_type", "unknown")
                            base_message = removal_result.get("message", "Unknown error occurred")
                            
                            # Reset lock for certain failure types that allow retry (DISABLED)
                            # if error_type in ["ui_operation_failed", "unknown"]:
                            #     main.position_removal_used = False
                            #     print(f"UI Thread: Position removal lock reset due to technical failure ({error_type})")
                            
                            if error_type == "no_position_found":
                                user_message = "Target user does not have any position assigned"
                            elif error_type == "ui_operation_failed":
                                user_message = f"UI operation failed: {base_message}"
                            else:
                                user_message = f"Operation failed: {base_message}"
                            
                            result = {
                                "status": "failed",
                                "error_type": error_type,
                                "message": user_message,
                                "user_name": user_context if user_context else "Unknown User", 
                                "execution_time": datetime.datetime.now().isoformat(),
                                "request_id": request_id
                            }
                            print(f"UI Thread: Position removal failed ({error_type}): {result}")
                    else:
                        # Reset lock for missing snapshot (technical issue) (DISABLED)
                        # main.position_removal_used = False
                        # print(f"UI Thread: Position removal lock reset due to missing snapshot data")
                        
                        result = {
                            "status": "error",
                            "message": "Missing essential UI positioning data (bubble snapshot)",
                            "user_name": user_context if user_context else "Unknown User",
                            "execution_time": datetime.datetime.now().isoformat(),
                            "request_id": request_id
                        }
                        print(f"UI Thread: Missing snapshot data: {result}")
                    
                    # 改進：優先使用文件系統回傳結果（MCP通訊）
                    if is_mcp_request and request_id:
                        try:
                            # 直接寫入結果文件
                            with open("position_result.json", 'w', encoding='utf-8') as f:
                                json.dump(result, f, ensure_ascii=False, indent=2)
                            print(f"UI Thread: Result written to file for MCP request {request_id}")
                        except Exception as file_error:
                            print(f"UI Thread: Error writing result file: {file_error}")
                            # 備用：嘗試使用舊的queue方式
                            try:
                                import main
                                main.position_result_queue.put(result)
                                print("UI Thread: Fallback - Result sent via queue")
                            except Exception as queue_error:
                                print(f"UI Thread: Both file and queue methods failed: {queue_error}")
                    else:
                        # 非MCP請求或無request_id，使用舊方式
                        try:
                            import main
                            main.position_result_queue.put(result)
                            print("UI Thread: Result sent back via legacy queue method")
                        except Exception as e:
                            print(f"UI Thread: Error with legacy queue method: {e}")

                elif action == 'remove_position':
                    # Check position removal lock first (DISABLED)
                    # if main.position_removal_used:
                    #     print(f"UI Thread: Position removal already used in this conversation, blocking legacy request")
                    #     continue
                    
                    # Set the lock before processing (DISABLED)
                    # main.position_removal_used = True
                    # print(f"UI Thread: Position removal lock activated for this conversation (legacy)")
                    
                    # Legacy branch maintained (backward compatibility)
                    snapshot = command_data.get('bubble_snapshot')
                    area = command_data.get('search_area')
                    original_region = command_data.get('trigger_bubble_region')
                    if snapshot: # Check for snapshot presence
                        print(f"UI Thread: Processing legacy remove_position command (Snapshot provided: {'Yes' if snapshot else 'No'})")
                        removal_result = remove_user_position(detector, interactor, original_region, snapshot, area)
                        success = removal_result["status"] == "success"
                        
                        # Reset lock for technical failures in legacy mode (DISABLED)
                        # if not success:
                        #     error_type = removal_result.get("error_type", "unknown")
                        #     if error_type in ["ui_operation_failed", "unknown"]:
                        #         main.position_removal_used = False
                        #         print(f"UI Thread: Position removal lock reset due to technical failure in legacy mode ({error_type})")
                        
                        print(f"UI Thread: Legacy position removal attempt finished. Success: {success}, Type: {removal_result.get('error_type', 'N/A')}")
                    else:
                        # Reset lock for missing snapshot (technical issue) (DISABLED)
                        # main.position_removal_used = False
                        # print(f"UI Thread: Position removal lock reset due to missing snapshot data (legacy)")
                        print("UI Thread: Received legacy remove_position command without necessary snapshot data.")


                elif action == 'pause':
                    if not monitoring_paused_flag[0]: # Avoid redundant prints if already paused
                        print("UI Thread: Processing pause command. Pausing monitoring.")
                        monitoring_paused_flag[0] = True
                    # No continue needed here, let it finish draining queue

                elif action == 'resume':
                    if monitoring_paused_flag[0]: # Avoid redundant prints if already running
                         print("UI Thread: Processing resume command. Resuming monitoring.")
                         monitoring_paused_flag[0] = False
                         # No state reset here, reset_state command handles that

                elif action == 'handle_restart_complete': # Added for game monitor restart signal
                    print("UI Thread: Received 'handle_restart_complete' command. Initiating internal pause/wait/resume sequence.")
                    # --- Internal Pause/Wait/Resume Sequence ---
                    if not monitoring_paused_flag[0]: # Only pause if not already paused
                        print("UI Thread: Pausing monitoring internally for restart.")
                        monitoring_paused_flag[0] = True
                        # No need to send command back to main loop, just update flag

                    print("UI Thread: Waiting 30 seconds for game to stabilize after restart.")
                    time.sleep(30) # Wait for game to launch and stabilize

                    print("UI Thread: Resuming monitoring internally after restart wait.")
                    monitoring_paused_flag[0] = False
                    # 删除 recent_texts.clear() 和 last_processed_bubble_info = None
                    print("UI Thread: Monitoring resumed after restart. Duplicate detection state preserved.")
                    # --- End Internal Sequence ---

                elif action == 'clear_history': # Added for F7
                    print("UI Thread: Processing clear_history command.")
                    recent_texts.clear()
                    deduplicator.clear_all() # Simultaneously clear deduplication records
                    
                    # Reset position removal lock (DISABLED)
                    # main.position_removal_used = False
                    # print("UI Thread: Position removal lock reset.")
                    
                    # --- 新增：清理氣泡去重記錄 ---
                    if 'bubble_deduplicator' in locals():
                        bubble_deduplicator.clear_all()
                    # --- 清理氣泡去重記錄結束 ---
                    
                    print("UI Thread: recent_texts and deduplicator records cleared.")

                elif action == 'reset_state': # Added for F8 resume
                    print("UI Thread: Processing reset_state command.")
                    recent_texts.clear()
                    last_processed_bubble_info = None
                    deduplicator.clear_all() # Simultaneously clear deduplication records
                    
                    # --- 新增：清理氣泡去重記錄 ---
                    if 'bubble_deduplicator' in locals():
                        bubble_deduplicator.clear_all()
                    
                    # --- 重置經濟模式狀態 ---
                    detector.eco_mode_enabled = False
                    detector.no_new_bubbles_count = 0
                    detector.last_eco_screenshot = None
                    # --- 清理氣泡去重記錄結束 ---
                    
                    print("UI Thread: recent_texts, last_processed_bubble_info, and deduplicator records reset.")

                else:
                    print(f"UI Thread: Received unknown command: {action}")

        except queue.Empty:
            # No more commands in the queue for this cycle
            # if commands_processed_this_cycle: # DEBUG REMOVED
            #      print("UI Thread: Finished processing commands for this cycle.") # DEBUG REMOVED
            pass
        except Exception as cmd_err:
            print(f"UI Thread: Error processing command queue: {cmd_err}")
            # Consider if pausing is needed on error, maybe not

        # --- Now, Check Pause State ---
        # print("[DEBUG] UI Loop: Checking pause state...") # DEBUG REMOVED
        if monitoring_paused_flag[0]:
            # print("[DEBUG] UI Loop: Monitoring is paused. Sleeping...") # DEBUG REMOVED
            # If paused, sleep and skip UI monitoring part
            time.sleep(0.1) # Sleep briefly while paused
            continue # Go back to check commands again

        # --- If not paused, proceed with UI Monitoring ---
        # print("[DEBUG] UI Loop: Monitoring is active. Proceeding...") # DEBUG REMOVED

        # --- 添加檢查 chat_option 狀態 ---
        try:
            chat_option_locs = detector._find_template('chat_option', confidence=0.8)
            if chat_option_locs:
                print("UI Thread: Detected chat_option overlay. Pressing ESC to dismiss...")
                interactor.press_key('esc')
                time.sleep(0.2)  # 給一點時間讓界面響應
                print("UI Thread: Pressed ESC to dismiss chat_option. Continuing...")
                continue  # 重新開始循環以確保界面已清除
        except Exception as chat_opt_err:
            print(f"UI Thread: Error checking for chat_option: {chat_opt_err}")
            # 繼續執行，不要中斷主流程

        # --- Check for Main Screen Navigation ---
        # print("[DEBUG] UI Loop: Checking for main screen navigation...") # DEBUG REMOVED
        try:
            base_locs = detector._find_template('base_screen', confidence=0.8)
            map_locs = detector._find_template('world_map_screen', confidence=0.8)
            if base_locs or map_locs:
                print(f"UI Thread: Detected main screen (Base or World Map). Counter: {main_screen_click_counter}")
                if main_screen_click_counter < 5:
                    main_screen_click_counter += 1
                    print(f"UI Thread: Attempting click #{main_screen_click_counter}/5 to return to chat...")
                    # Coordinates provided by user (adjust if needed based on actual screen resolution/layout)
                    target_x, target_y = 600, 1300
                    interactor.click_at(target_x, target_y)
                    time.sleep(0.1) # Short delay after click
                    print("UI Thread: Clicked. Re-checking screen state...")
                else:
                    print("UI Thread: Clicked 5 times, still on main screen. Pressing ESC...")
                    interactor.press_key('esc')
                    main_screen_click_counter = 0 # Reset counter after ESC
                    time.sleep(0.05) # Wait a bit longer after ESC
                    print("UI Thread: ESC pressed. Re-checking screen state...")
                continue # Skip the rest of the loop and re-evaluate state
            else:
                # Reset counter if not on the main screen
                if main_screen_click_counter > 0:
                    print("UI Thread: Not on main screen, resetting click counter.")
                    main_screen_click_counter = 0
        except Exception as nav_err:
            print(f"UI Thread: Error during main screen navigation check: {nav_err}")
            # Decide if you want to continue or pause after error
            main_screen_click_counter = 0 # Reset counter on error too

        # --- Verify Chat Room State Before Bubble Detection (Only if NOT paused) ---
        # print("[DEBUG] UI Loop: Verifying chat room state...") # DEBUG REMOVED
        try:
            # Use a slightly lower confidence maybe, or state_confidence
            chat_room_locs = detector._find_template('chat_room', confidence=detector.state_confidence)
            if not chat_room_locs:
                print("UI Thread: Not in chat room state before bubble detection. Checking for update confirm...")
                
                # 檢查是否存在更新確認按鈕
                update_confirm_locs = detector._find_template('update_confirm', confidence=0.8)
                if update_confirm_locs:
                    print("UI Thread: Detected update_confirm button. Clicking to proceed...")
                    interactor.click_at(update_confirm_locs[0][0], update_confirm_locs[0][1])
                    time.sleep(0.5)  # 給更新過程一些時間
                    print("UI Thread: Clicked update_confirm button. Continuing...")
                    continue  # 重新開始循環以重新檢查狀態
                
                # 沒有找到更新確認按鈕，繼續原有的清理邏輯
                print("UI Thread: No update_confirm button found. Attempting cleanup...")
                perform_state_cleanup(detector, interactor)
                # Regardless of cleanup success, restart the loop to re-evaluate state from the top
                print("UI Thread: Continuing loop after attempting chat room cleanup.")
                time.sleep(0.5) # Small pause after cleanup attempt
                continue
            # else: # Optional: Log if chat room is confirmed # DEBUG REMOVED
               # print("[DEBUG] UI Thread: Chat room state confirmed.") # DEBUG REMOVED

        except Exception as state_check_err:
             print(f"UI Thread: Error checking for chat room state: {state_check_err}")
             # Decide how to handle error - maybe pause and retry? For now, continue cautiously.
             time.sleep(1)


        # --- 經濟模式檢查 ---
        if detector.eco_mode_enabled:
            # 在經濟模式下，檢查固定區域是否有變化
            if detector.eco_mode_check_region_change():
                # 檢測到變化，退出經濟模式
                detector.eco_mode_enabled = False
                detector.no_new_bubbles_count = 0
                detector.last_eco_screenshot = None
                print("退出經濟模式，恢復正常泡泡檢測")
            else:
                # 無變化，繼續經濟模式
                time.sleep(detector.eco_mode_interval)
                continue

        # --- Then Perform UI Monitoring (Enhanced Bubble Detection) ---
        # print("[DEBUG] UI Loop: Starting enhanced bubble detection...") # DEBUG REMOVED
        try:
            # 1. Enhanced Bubble Detection with stability verification
            all_bubbles_data = detector.enhanced_bubble_detection() # Returns list of dicts with verification
            if not all_bubbles_data:
                # print("[DEBUG] UI Loop: No bubbles detected.") # DEBUG REMOVED
                # --- 經濟模式邏輯：無泡泡情況 ---
                detector.no_new_bubbles_count += 1
                if detector.no_new_bubbles_count >= detector.eco_mode_threshold:
                    detector.eco_mode_enabled = True
                    detector.no_new_bubbles_count = 0
                    print(f"連續{detector.eco_mode_threshold}次循環無新泡泡，進入經濟模式")
                time.sleep(2); continue

            # Filter out bot bubbles
            other_bubbles_data = [b_info for b_info in all_bubbles_data if not b_info['is_bot']]
            if not other_bubbles_data:
                # print("[DEBUG] UI Loop: No non-bot bubbles detected.") # DEBUG REMOVED
                # --- 經濟模式邏輯：只有bot泡泡情況 ---
                detector.no_new_bubbles_count += 1
                if detector.no_new_bubbles_count >= detector.eco_mode_threshold:
                    detector.eco_mode_enabled = True
                    detector.no_new_bubbles_count = 0
                    print(f"連續{detector.eco_mode_threshold}次循環無新泡泡（只有bot泡泡），進入經濟模式")
                time.sleep(0.2); continue

            # print(f"[DEBUG] UI Loop: Found {len(other_bubbles_data)} non-bot bubbles. Sorting...") # DEBUG REMOVED
            # Sort bubbles from bottom to top (based on bottom Y coordinate)
            sorted_bubbles = sorted(other_bubbles_data, key=lambda b_info: b_info['bbox'][3], reverse=True)

            # Iterate through sorted bubbles (bottom to top)
            # print("[DEBUG] UI Loop: Iterating through sorted bubbles...") # DEBUG REMOVED
            for i, target_bubble_info in enumerate(sorted_bubbles):
                # print(f"[DEBUG] UI Loop: Processing bubble #{i+1}") # DEBUG REMOVED
                target_bbox = target_bubble_info['bbox']
                # Ensure bubble_region uses standard ints
                bubble_region = (int(target_bbox[0]), int(target_bbox[1]), int(target_bbox[2]-target_bbox[0]), int(target_bbox[3]-target_bbox[1]))

                # --- 流程開始：截圖與第一層視覺去重 ---
                try:
                    # 確保 bubble_region_tuple 使用最新的 bbox 尺寸
                    bubble_region_tuple = (int(target_bbox[0]), int(target_bbox[1]), int(target_bbox[2]-target_bbox[0]), int(target_bbox[3]-target_bbox[1]))
                    if bubble_region_tuple[2] <= 0 or bubble_region_tuple[3] <= 0:
                        print(f"Warning: Invalid bubble region {bubble_region_tuple} for snapshot. Skipping this bubble.")
                        continue

                    # 1. 截取包含頭像的擴展快照
                    extended_bubble_snapshot, extension_used = capture_extended_bubble_screenshot(bubble_region_tuple)
                    if extended_bubble_snapshot is None:
                        print("Warning: Failed to capture extended bubble snapshot. Skipping this bubble.")
                        continue

                    # 2. 【第一層防護】執行視覺去重檢查
                    #    is_duplicate 方法會對包含頭像的圖片進行哈希計算，從而區分不同用戶
                    #    新版本：只檢查不立即添加，返回確認數據供後續使用
                    is_visual_duplicate, bubble_confirmation_data = bubble_deduplicator.is_duplicate(extended_bubble_snapshot, bubble_region_tuple)
                    if is_visual_duplicate:
                        print("--- VISUAL DUPLICATE DETECTED (L1). Skipping. ---")
                        continue  # 如果視覺重複，直接跳過，成本極低

                    # 3. 將 `bubble_snapshot` 變數指向擴展快照，供後續所有重新定位邏輯使用
                    bubble_snapshot = extended_bubble_snapshot
                    # 保存L1去重時的正確模板，供頭像點擊使用
                    l1_bubble_snapshot = extended_bubble_snapshot

                    # --- 保存除錯快照 ---
                    try:
                        screenshot_index = (screenshot_counter % MAX_DEBUG_SCREENSHOTS) + 1
                        screenshot_filename = f"debug_relocation_snapshot_{screenshot_index}.png"
                        screenshot_path = os.path.join(DEBUG_SCREENSHOT_DIR, screenshot_filename)
                        bubble_snapshot.save(screenshot_path)
                        screenshot_counter += 1
                    except Exception as save_err:
                        print(f"Error saving debug snapshot: {repr(save_err)}")

                except Exception as snapshot_err:
                     print(f"Error during snapshot/L1 deduplication phase: {repr(snapshot_err)}")
                     continue

                # --- 視覺去重通過，開始執行高成本操作 ---

                # 3. Enhanced Keyword Detection in Bubble with verification
                # print(f"[DEBUG] UI Loop: Enhanced keyword detection in region {bubble_region}...") # DEBUG REMOVED
                result = detector.enhanced_keyword_detection(bubble_region) # Enhanced method with verification

                if result: # 檢查是否真的找到了關鍵字
                    keyword_coords, detected_template_key = result # 解包得到座標和 key
                    # 在這裡可以更新或加入日誌，包含 detected_template_key
                    print(f"\n!!! Keyword '{detected_template_key}' detected in bubble {target_bbox} at {keyword_coords} !!!")

                    # --- 接下來是移除冗餘邏輯並使用新 key ---

                    # ------------ START: 刪除或註解掉以下區塊 ------------
                    # is_reply_keyword = False
                    # reply_keyword_keys = ['keyword_wolf_reply', 'keyword_wolf_reply_type2', 'keyword_wolf_reply_type3', 'keyword_wolf_reply_type4']
                    # for key in reply_keyword_keys:
                    #     reply_locs = detector._find_template(key, region=bubble_region, grayscale=False, confidence=detector.confidence)
                    #     if reply_locs:
                    #         for loc in reply_locs:
                    #             if abs(keyword_coords[0] - loc[0]) <= 2 and abs(keyword_coords[1] - loc[1]) <= 2:
                    #                 print(f"Confirmed detected keyword at {keyword_coords} matches reply keyword template '{key}' at {loc}.")
                    #                 is_reply_keyword = True
                    #                 break
                    #     if is_reply_keyword:
                    #         break
                    # ------------- END: 刪除或註解掉以上區塊 -------------

                    # 直接根據返回的 key 判斷是否為 reply
                    # Note: Dual method currently only returns 'keyword_wolf_reply' as a reply type key
                    is_reply_keyword = (detected_template_key == 'keyword_wolf_reply')

                    # Calculate click coordinates with potential offset
                    click_coords = keyword_coords
                    if is_reply_keyword:
                        click_coords = (keyword_coords[0], keyword_coords[1] + 25) # 假設 reply 需要 +25 Y 偏移
                        # 更新日誌，包含 key
                        print(f"Applying +25 Y-offset for reply keyword '{detected_template_key}'. Click target: {click_coords}")
                    else:
                         # 更新日誌，包含 key
                        print(f"Detected keyword '{detected_template_key}' is not a reply type. Click target: {click_coords}")

                    # --- 將剩餘的邏輯放在 if result: 區塊內 ---
                    # --- Variables needed later ---
                    bubble_snapshot = None
                    search_area = SCREENSHOT_REGION
                    if search_area is None:
                        print("Warning: SCREENSHOT_REGION not defined, searching full screen for bubble snapshot.")

                    # --- Take Snapshot for Re-location ---
                    # print("[DEBUG] UI Loop: Taking bubble snapshot...") # DEBUG REMOVED
                    try:
                        bubble_region_tuple = (int(bubble_region[0]), int(bubble_region[1]), int(bubble_region[2]), int(bubble_region[3]))
                        if bubble_region_tuple[2] <= 0 or bubble_region_tuple[3] <= 0:
                            print(f"Warning: Invalid bubble region {bubble_region_tuple} for snapshot. Skipping this bubble.")
                            continue # Skip to next bubble in the loop
                        bubble_snapshot, extension_used = capture_extended_bubble_screenshot(bubble_region_tuple)
                        if bubble_snapshot is None:
                             print("Warning: Failed to capture extended bubble snapshot. Skipping this bubble.")
                             continue # Skip to next bubble


                        # --- Save Snapshot for Debugging ---
                        try:
                            screenshot_index = (screenshot_counter % MAX_DEBUG_SCREENSHOTS) + 1
                            screenshot_filename = f"debug_relocation_snapshot_{screenshot_index}.png"
                            screenshot_path = os.path.join(DEBUG_SCREENSHOT_DIR, screenshot_filename)
                            print(f"Attempting to save bubble snapshot used for re-location to: {screenshot_path}")
                            bubble_snapshot.save(screenshot_path)
                            print(f"Successfully saved bubble snapshot: {screenshot_path}")
                            screenshot_counter += 1
                        except Exception as save_err:
                            print(f"Error saving bubble snapshot to {screenshot_path}: {repr(save_err)}")
                            
                    except Exception as snapshot_err:
                         print(f"Error taking initial bubble snapshot: {repr(snapshot_err)}")
                         continue # Skip to next bubble

                    # 4. Re-locate bubble *before* copying text
                    # print("[DEBUG] UI Loop: Re-locating bubble before copying text...") # DEBUG REMOVED
                    new_bubble_box_for_copy = None
                    if bubble_snapshot:
                        try:
                            # Use standard confidence for this initial critical step
                            temp_bubble_box = pyautogui.locateOnScreen(bubble_snapshot,
                                                                             region=search_area,
                                                                             confidence=BUBBLE_RELOCATE_CONFIDENCE)
                            if temp_bubble_box:
                                compensated_coords = compensate_coordinates_for_extended_screenshot(temp_bubble_box)
                                new_bubble_box_for_copy = type(temp_bubble_box)(compensated_coords[0], compensated_coords[1], compensated_coords[2], compensated_coords[3])
                            else:
                                new_bubble_box_for_copy = None
                        except Exception as e:
                            print(f"Exception during bubble location before copy: {e}")

                    if not new_bubble_box_for_copy:
                        print("Warning: Failed to re-locate bubble before copying text. Skipping this bubble.")
                        continue # Skip to the next bubble in the outer loop

                    print(f"Successfully re-located bubble for copy at: {new_bubble_box_for_copy}")
                    # Define the region based on the re-located bubble, casting to int
                    copy_bubble_region = (int(new_bubble_box_for_copy.left), int(new_bubble_box_for_copy.top),
                                          int(new_bubble_box_for_copy.width), int(new_bubble_box_for_copy.height))

                    # Find the keyword *again* within the *new* bubble region to get current coords
                    # print("[DEBUG] UI Loop: Finding keyword again in re-located region...") # DEBUG REMOVED
                    current_result = detector.find_keyword_in_region(copy_bubble_region) # Returns (coords, key) or None
                    if not current_result:
                        print("Warning: Keyword not found in the re-located bubble region. Skipping this bubble.")
                        continue # Skip to the next bubble

                    current_keyword_coords, current_detected_key = current_result
                    print(f"Keyword '{current_detected_key}' re-located at {current_keyword_coords}")

                    # Determine if it's a reply keyword based on the *new* location/key
                    # Use the key found in the *re-located* region for the most accurate offset decision
                    is_reply_keyword_current = (current_detected_key == 'keyword_wolf_reply')

                    click_coords_current = current_keyword_coords
                    if is_reply_keyword_current:
                        click_coords_current = (current_keyword_coords[0], current_keyword_coords[1] + 25)
                        print(f"Applying +25 Y-offset for reply keyword '{current_detected_key}' (current location). Click target: {click_coords_current}")
                    else:
                        print(f"Detected keyword '{current_detected_key}' is not a reply type (current location). Click target: {click_coords_current}")

                    # Interact: Get Bubble Text using current coordinates
                    # print("[DEBUG] UI Loop: Copying text...") # DEBUG REMOVED
                    bubble_text = interactor.copy_text_at(click_coords_current)
                    if not bubble_text:
                        print("Error: Could not get dialogue content for this bubble (after re-location).")
                        perform_state_cleanup(detector, interactor) # Attempt cleanup
                        continue # Skip to next bubble

                    # 5. Interact: Get Sender Name (uses re-location internally via retrieve_sender_name_interaction)
                    # print("[DEBUG] UI Loop: Retrieving sender name...") # DEBUG REMOVED
                    sender_name = None
                    try:
                        # --- Reuse Text Copy Bubble Box (OPTIMIZATION) ---
                        print("Reusing bubble box from successful text copy operation...")
                        # Use the same bubble_box that was successfully used for text copying
                        # This ensures perfect consistency between text copy and avatar click operations
                        new_bubble_box = new_bubble_box_for_copy
                        print(f"Reusing bubble box from text copy: {new_bubble_box}")
                        
                        if new_bubble_box:
                            new_tl_x, new_tl_y = new_bubble_box.left, new_bubble_box.top
                            print(f"Using text-copy bubble position at: ({new_tl_x}, {new_tl_y})")
                            new_avatar_coords = (new_tl_x + AVATAR_OFFSET_X_REPLY, new_tl_y + AVATAR_OFFSET_Y_REPLY)
                            print(f"Calculated avatar coordinates using text-copy bubble: {new_avatar_coords}")
                            sender_name = interactor.retrieve_sender_name_interaction(
                                initial_avatar_coords=new_avatar_coords,
                                bubble_snapshot=l1_bubble_snapshot,  # 使用L1去重時的正確模板
                                search_area=search_area
                            )
                        else:
                            print("Warning: Failed to re-locate bubble snapshot after multiple attempts.")
                            print("Trying direct approach with original bubble coordinates...")
                            original_tl_coords = target_bubble_info.get('tl_coords')
                            if original_tl_coords:
                                fallback_avatar_coords = (original_tl_coords[0] + AVATAR_OFFSET_X_REPLY,
                                                        original_tl_coords[1] + AVATAR_OFFSET_Y_REPLY)
                                print(f"Using fallback avatar coordinates from original detection: {fallback_avatar_coords}")
                                sender_name = interactor.retrieve_sender_name_interaction(
                                    initial_avatar_coords=fallback_avatar_coords,
                                    bubble_snapshot=l1_bubble_snapshot,  # 使用L1去重時的正確模板
                                    search_area=search_area
                                )
                                if not sender_name:
                                    print("Direct approach failed. Skipping this trigger.")
                                    perform_state_cleanup(detector, interactor)
                                    continue # Skip to next bubble
                            else:
                                print("No original coordinates available. Skipping sender name retrieval.")
                                perform_state_cleanup(detector, interactor)
                                continue # Skip to next bubble
                        # --- End Bubble Re-location Logic ---

                    except Exception as reloc_err:
                        print(f"Error during bubble re-location or subsequent interaction: {reloc_err}")
                        import traceback
                        traceback.print_exc()
                        perform_state_cleanup(detector, interactor)
                        continue # Skip to next bubble

                    # 6. Perform Cleanup
                    # print("[DEBUG] UI Loop: Performing cleanup after getting name...") # DEBUG REMOVED
                    cleanup_successful = perform_state_cleanup(detector, interactor)
                    if not cleanup_successful:
                        print("Error: Failed to return to chat screen after getting name. Skipping this bubble.")
                        continue # Skip to next bubble

                    if not sender_name or not bubble_text:
                        print("Error: Could not get sender name or bubble text, skipping.")
                        perform_state_cleanup(detector, interactor)
                        continue

                    # --- 【第二層防護】執行文字內容去重 ---
                    if deduplicator.is_duplicate(sender_name, bubble_text):
                        print(f"--- TEXT DUPLICATE DETECTED (L2). User: {sender_name}, Text: {bubble_text[:30]}... Skipping. ---")
                        # 因為已經執行了UI互動(獲取名稱)，所以這裡需要清理狀態
                        perform_state_cleanup(detector, interactor)
                        continue

                    # --- 所有檢查通過，這是一個全新的有效觸發 ---
                    print(">>> New trigger event (passed BOTH visual and text deduplication) <<<")
                    
                    # --- 【確認階段】將通過兩階段驗證的泡泡添加到視覺去重記錄中 ---
                    if bubble_confirmation_data:
                        # 更新發送者信息到確認數據中
                        bubble_confirmation_data['sender'] = sender_name
                        # 確認添加到視覺去重記錄
                        bubble_deduplicator.confirm_add_bubble(bubble_confirmation_data)
                    else:
                        print("Warning: No bubble confirmation data available for final confirmation")

                    # --- Attempt to activate reply context ---
                    # print("[DEBUG] UI Loop: Attempting to activate reply context...") # DEBUG REMOVED
                    reply_context_activated = False
                    try:
                        print("Attempting to activate reply context...")
                        if bubble_snapshot is None:
                             print("Warning: Bubble snapshot missing for reply context activation. Skipping.")
                             final_bubble_box_for_reply = None
                        else:
                             print(f"Attempting final re-location for reply context using search_area: {search_area}")
                             temp_bubble_box = pyautogui.locateOnScreen(bubble_snapshot, region=search_area, confidence=BUBBLE_RELOCATE_CONFIDENCE)
                             if temp_bubble_box:
                                 compensated_coords = compensate_coordinates_for_extended_screenshot(temp_bubble_box)
                                 final_bubble_box_for_reply = type(temp_bubble_box)(compensated_coords[0], compensated_coords[1], compensated_coords[2], compensated_coords[3])
                             else:
                                 final_bubble_box_for_reply = None

                        if final_bubble_box_for_reply:
                            print(f"Final re-location successful at: {final_bubble_box_for_reply}")
                            bubble_x_reply, bubble_y_reply = final_bubble_box_for_reply.left, final_bubble_box_for_reply.top
                            bubble_w_reply, bubble_h_reply = final_bubble_box_for_reply.width, final_bubble_box_for_reply.height
                            center_x_reply = bubble_x_reply + bubble_w_reply // 2
                            center_y_reply = bubble_y_reply + bubble_h_reply // 2

                            if is_reply_keyword:
                                center_y_reply += 15
                                print(f"Applying +15 Y-offset to bubble center click for reply keyword. Target Y: {center_y_reply}")

                            print(f"Clicking bubble center for reply at ({center_x_reply}, {center_y_reply})")
                            interactor.click_at(center_x_reply, center_y_reply)
                            time.sleep(0.15)

                            print("Searching for reply button...")
                            reply_button_locs = detector._find_template('reply_button', confidence=0.8)
                            if reply_button_locs:
                                reply_coords = reply_button_locs[0]
                                print(f"Found reply button at {reply_coords}. Clicking...")
                                interactor.click_at(reply_coords[0], reply_coords[1])
                                time.sleep(0.07)
                                reply_context_activated = True
                                print("Reply context activated.")
                            else:
                                print(">>> Reply button template ('reply_button') not found after clicking bubble center. <<<")
                        else:
                            print("Warning: Failed to re-locate bubble for activating reply context.")

                    except Exception as reply_context_err:
                        print(f"!!! Error during reply context activation: {reply_context_err} !!!")

                    # 7. Send Trigger Info to Main Thread
                    print("\n>>> Putting trigger info in Queue <<<")
                    try:
                        # 安全地處理和顯示發送者名稱
                        safe_sender_display = handle_text_encoding(sender_name, "[未知發送者]")
                        print(f"   Sender: {safe_sender_display}")
                        
                        # 安全地處理和顯示消息內容
                        if bubble_text:
                            display_text = bubble_text[:100] + "..." if len(bubble_text) > 100 else bubble_text
                            safe_content_display = handle_text_encoding(display_text, "[無法處理的文字內容]")
                            print(f"   Content: {safe_content_display}")
                        else:
                            print("   Content: [空]")
                    except Exception as e_display:
                        print(f"Error displaying message info: {str(e_display)}")
                    
                    print(f"   Bubble Region: {bubble_region}") # Original region for context
                    print(f"   Reply Context Activated: {reply_context_activated}")
                    try:
                        # 確保所有文字數據都經過安全處理
                        data_to_send = {
                            'sender': handle_text_encoding(sender_name, "[未知發送者]"),
                            'text': handle_text_encoding(bubble_text, "[無法處理的文字內容]"),
                            'bubble_region': bubble_region,
                            'reply_context_activated': reply_context_activated,
                            'bubble_snapshot': bubble_snapshot,
                            'search_area': search_area
                        }
                        trigger_queue.put(data_to_send)
                        found_new_bubble_this_cycle = True  # 標記找到新泡泡
                        print("Trigger info (with region, reply flag, snapshot, search_area) placed in Queue.")
                        
                        # --- 發送者信息已在確認階段統一處理，此處不再需要更新 ---

                        # --- CRITICAL: Break loop after successfully processing one trigger ---
                        print("--- Single bubble processing complete. Breaking scan cycle. ---")
                        break # Exit the 'for target_bubble_info in sorted_bubbles' loop

                    except Exception as q_err:
                        print(f"Error preparing or enqueueing data: {q_err}")
                        # 嘗試使用最小數據集合保證功能性
                        try:
                            minimal_data = {
                                'sender': "[數據處理錯誤]",
                                'text': handle_text_encoding(bubble_text[:100] if bubble_text else "[內容獲取失敗]"), # Apply encoding here too
                                'bubble_region': bubble_region,
                                'reply_context_activated': False, # Sensible default
                                'bubble_snapshot': bubble_snapshot, # Keep snapshot if available
                                'search_area': search_area
                            }
                            trigger_queue.put(minimal_data)
                            found_new_bubble_this_cycle = True  # 標記找到新泡泡（即便是fallback）
                            print("Minimal fallback data placed in Queue after error.")
                        except Exception as min_q_err:
                            print(f"Critical failure: Could not place any data in queue: {min_q_err}")
                        # Let's break here too, as something is wrong.
                        print("Breaking scan cycle due to queue error.")
                        break

                # End of keyword found block (if result:)
            # End of loop through sorted bubbles (for target_bubble_info...)

            # If the loop finished without breaking (i.e., no trigger processed), wait the full interval.
            # If it broke, the sleep still happens here before the next cycle.
            # print("[DEBUG] UI Loop: Finished bubble iteration or broke early. Sleeping...") # DEBUG REMOVED
            time.sleep(1.5) # Polling interval after checking all bubbles or processing one
            
            # --- 經濟模式邏輯：在循環結束時檢查是否有新泡泡被處理 ---
            if not found_new_bubble_this_cycle:
                detector.no_new_bubbles_count += 1
                if detector.no_new_bubbles_count >= detector.eco_mode_threshold:
                    detector.eco_mode_enabled = True
                    detector.no_new_bubbles_count = 0
                    print(f"連續{detector.eco_mode_threshold}次循環無新泡泡，進入經濟模式")
            else:
                # 有新泡泡被處理，重置計數
                detector.no_new_bubbles_count = 0

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
