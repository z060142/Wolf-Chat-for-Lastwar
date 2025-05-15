import os
import json
import collections
import threading
from PIL import Image
import imagehash
import numpy as np
import io

class SimpleBubbleDeduplication:
    def __init__(self, storage_file="simple_bubble_dedup.json", max_bubbles=5, threshold=5, hash_size=16):
        self.storage_file = storage_file
        self.max_bubbles = max_bubbles  # Keep the most recent 5 bubbles
        self.threshold = threshold  # Hash difference threshold (lower values are more strict)
        self.hash_size = hash_size  # Hash size
        self.lock = threading.Lock()
        
        # Use OrderedDict to maintain order
        self.recent_bubbles = collections.OrderedDict()
        # Load stored bubble hashes
        self._load_storage()
        
    def _load_storage(self):
        """Load processed bubble hash values from file"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                
                # Convert stored data to OrderedDict and load
                self.recent_bubbles.clear()
                # Use loaded_count to track loaded items, ensuring we don't exceed max_bubbles
                loaded_count = 0
                for bubble_id, bubble_data in data.items():
                    if loaded_count >= self.max_bubbles:
                        break
                    self.recent_bubbles[bubble_id] = {
                        'hash': imagehash.hex_to_hash(bubble_data['hash']),
                        'sender': bubble_data.get('sender', 'Unknown')
                    }
                    loaded_count += 1
                
                print(f"Loaded {len(self.recent_bubbles)} bubble hash records")
            except Exception as e:
                print(f"Failed to load bubble hash records: {e}")
                self.recent_bubbles.clear()
        
    def _save_storage(self):
        """Save bubble hashes to file"""
        try:
            # Create temporary dictionary for saving
            data_to_save = {}
            for bubble_id, bubble_data in self.recent_bubbles.items():
                data_to_save[bubble_id] = {
                    'hash': str(bubble_data['hash']),
                    'sender': bubble_data.get('sender', 'Unknown')
                }
            
            with open(self.storage_file, 'w') as f:
                json.dump(data_to_save, f, indent=2)
            print(f"Saved {len(data_to_save)} bubble hash records")
        except Exception as e:
            print(f"Failed to save bubble hash records: {e}")
    
    def compute_image_hash(self, bubble_snapshot):
        """Calculate perceptual hash of bubble image"""
        try:
            # If bubble_snapshot is a PIL.Image object
            if isinstance(bubble_snapshot, Image.Image):
                img = bubble_snapshot
            # If bubble_snapshot is a PyAutoGUI screenshot
            elif hasattr(bubble_snapshot, 'save'):
                img = bubble_snapshot
            # If it's bytes or BytesIO
            elif isinstance(bubble_snapshot, (bytes, io.BytesIO)):
                img = Image.open(io.BytesIO(bubble_snapshot) if isinstance(bubble_snapshot, bytes) else bubble_snapshot)
            # If it's a numpy array
            elif isinstance(bubble_snapshot, np.ndarray):
                img = Image.fromarray(bubble_snapshot)
            else:
                print(f"Unrecognized image format: {type(bubble_snapshot)}")
                return None
                
            # Calculate perceptual hash
            phash = imagehash.phash(img, hash_size=self.hash_size)
            return phash
        except Exception as e:
            print(f"Failed to calculate image hash: {e}")
            return None
    
    def generate_bubble_id(self, bubble_region):
        """Generate ID based on bubble region"""
        return f"bubble_{bubble_region[0]}_{bubble_region[1]}_{bubble_region[2]}_{bubble_region[3]}"
        
    def is_duplicate(self, bubble_snapshot, bubble_region, sender_name=""):
        """Check if bubble is a duplicate"""
        with self.lock:
            if bubble_snapshot is None:
                return False
                
            # Calculate hash of current bubble
            current_hash = self.compute_image_hash(bubble_snapshot)
            if current_hash is None:
                print("Unable to calculate bubble hash, cannot perform deduplication")
                return False
                
            # Generate ID for current bubble
            bubble_id = self.generate_bubble_id(bubble_region)
            
            # Check if similar to any known bubbles
            for stored_id, bubble_data in self.recent_bubbles.items():
                stored_hash = bubble_data['hash']
                hash_diff = current_hash - stored_hash
                
                if hash_diff <= self.threshold:
                    print(f"Detected duplicate bubble (ID: {stored_id}, Hash difference: {hash_diff})")
                    if sender_name:
                        print(f"Sender: {sender_name}, Recorded sender: {bubble_data.get('sender', 'Unknown')}")
                    return True
            
            # Not a duplicate, add to recent bubbles list
            self.recent_bubbles[bubble_id] = {
                'hash': current_hash, 
                'sender': sender_name
            }
            
            # If exceeding maximum count, remove oldest item
            while len(self.recent_bubbles) > self.max_bubbles:
                self.recent_bubbles.popitem(last=False)  # Remove first item (oldest)
                
            self._save_storage()
            return False
    
    def clear_all(self):
        """Clear all records"""
        with self.lock:
            count = len(self.recent_bubbles)
            self.recent_bubbles.clear()
            self._save_storage()
            print(f"Cleared all {count} bubble records")
            return count

    def save_debug_image(self, bubble_snapshot, bubble_id, hash_value):
        """Save debug image (optional feature)"""
        try:
            debug_dir = "bubble_debug"
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)
            
            # Save original image
            img_path = os.path.join(debug_dir, f"{bubble_id}_{hash_value}.png")
            bubble_snapshot.save(img_path)
            print(f"Saved debug image: {img_path}")
        except Exception as e:
            print(f"Failed to save debug image: {e}")