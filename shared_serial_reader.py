"""
Shared Serial Reader - Replacement for direct serial communication in games.
This reads angle data from a shared JSON file that the GUI continuously updates.
"""
import json
import time
import os

SHARED_DATA_FILE = os.path.join(os.path.dirname(__file__), "WristRehab", "live_angle_data.json")

class SharedSerialReader:
    """
    Drop-in replacement for serial communication that reads from shared file.
    Compatible with existing game code.
    """
    def __init__(self):
        self.last_angle = 0.0
        self.last_button = 1.0
        self.last_update = 0
        
    def read_angle_and_button(self):
        """
        Read angle and button state from shared file.
        Returns: (angle_degrees, button_state)
        """
        try:
            if os.path.exists(SHARED_DATA_FILE):
                with open(SHARED_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.last_angle = data.get('angle', self.last_angle)
                    self.last_button = data.get('button', self.last_button)
                    self.last_update = data.get('timestamp', time.time())
        except:
            pass  # If file is being written, just use last known values
        
        return self.last_angle, self.last_button
    
    def read_angle(self):
        """Read just the angle."""
        angle, _ = self.read_angle_and_button()
        return angle
    
    def is_data_fresh(self, max_age=1.0):
        """Check if data is recent (within max_age seconds)."""
        return (time.time() - self.last_update) < max_age
    
    def close(self):
        """Compatibility method - does nothing."""
        pass


def get_serial_reader(use_shared_data=False):
    """
    Factory function to get appropriate serial reader.
    
    Args:
        use_shared_data: If True, returns SharedSerialReader. 
                        If False, returns None (game should use direct serial).
    
    Returns:
        SharedSerialReader instance or None
    """
    if use_shared_data:
        return SharedSerialReader()
    return None
