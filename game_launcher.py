"""
Wrist Rehab Game Launcher
Multi-page interface for ROM calibration and game selection
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import time
import glob
import serial
from PIL import Image, ImageTk, ImageDraw

# --- Configuration ---
ROM_CALIBRATION_FILE = "rom_calibration.json"

class ROMCalibration:
    """Manages ROM (Range of Motion) calibration data"""
    def __init__(self, cal_file=ROM_CALIBRATION_FILE):
        self.cal_file = cal_file
        self.min_angle = 0.0
        self.max_angle = 180.0
        self.is_calibrated = False
        self._load_calibration()
    
    def _load_calibration(self):
        """Load calibration from file if it exists"""
        if os.path.exists(self.cal_file):
            try:
                with open(self.cal_file, 'r') as f:
                    data = json.load(f)
                    self.min_angle = float(data.get('min_angle', 0.0))
                    self.max_angle = float(data.get('max_angle', 180.0))
                    self.is_calibrated = bool(data.get('is_calibrated', False))
                    return True
            except:
                pass
        return False
    
    def save_calibration(self, min_angle, max_angle):
        """Save calibration to file"""
        try:
            with open(self.cal_file, 'w') as f:
                json.dump({
                    'min_angle': float(min_angle),
                    'max_angle': float(max_angle),
                    'is_calibrated': True
                }, f, indent=2)
            self.min_angle = min_angle
            self.max_angle = max_angle
            self.is_calibrated = True
            return True
        except Exception as e:
            print(f"Error saving calibration: {e}")
            return False
    
    def get_range(self):
        """Get the calibrated range"""
        return self.max_angle - self.min_angle

class SerialConnection:
    """Manages Arduino serial connection"""
    def __init__(self):
        self.arduino = None
        self.port = None
    
    def find_arduino_port(self):
        """Automatically detect Arduino serial port"""
        if sys.platform.startswith('win'):
            ports = [f'COM{i + 1}' for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/cu.usb*')
        else:
            return None
        
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                return port
            except (OSError, serial.SerialException):
                pass
        return None
    
    def connect(self):
        """Connect to Arduino"""
        if self.arduino and self.arduino.is_open:
            return True
        
        self.port = self.find_arduino_port()
        if not self.port:
            return False
        
        try:
            self.arduino = serial.Serial(self.port, 9600, timeout=0)
            time.sleep(2)  # Allow board reset
            try:
                self.arduino.reset_input_buffer()
            except AttributeError:
                self.arduino.flushInput()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            self.arduino = None
            return False
    
    def disconnect(self):
        """Disconnect from Arduino"""
        if self.arduino and self.arduino.is_open:
            try:
                self.arduino.close()
            except:
                pass
        self.arduino = None
    
    def read_angle(self):
        """Read angle from Arduino (non-blocking)"""
        if not self.arduino or not self.arduino.is_open:
            return None
        
        try:
            while self.arduino.in_waiting > 0:
                raw = self.arduino.readline()
                if raw:
                    try:
                        return float(raw.decode('utf-8').strip())
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

class GameLauncher:
    """Main application with multi-page interface"""
    def __init__(self, root):
        self.root = root
        self.root.title("Wrist Rehab - Game Launcher")
        self.root.geometry("900x700")
        self.root.resizable(False, False)
        
        # Core components
        self.rom_cal = ROMCalibration()
        self.serial_conn = SerialConnection()
        
        # Page management
        self.pages = {}
        self.current_page = None
        
        # Build all pages
        self._build_pages()
        
        # Start with appropriate page
        if self.rom_cal.is_calibrated:
            self._show_page("game_select")
        else:
            self._show_page("rom_calibration")
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _build_pages(self):
        """Build all application pages"""
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        self._build_rom_page()
        self._build_game_select_page()
    
    def _build_rom_page(self):
        """Build ROM calibration page"""
        page = ttk.Frame(self.root, padding=20)
        self.pages["rom_calibration"] = page
        
        # Title
        title = tk.Label(page, text="Range of Motion Calibration", 
                        font=("Arial", 20, "bold"), fg="#2c3e50")
        title.pack(pady=(0, 20))
        
        # Instructions
        info_frame = ttk.LabelFrame(page, text="Instructions", padding=15)
        info_frame.pack(fill="x", pady=10)
        
        instructions = """
1. Connect your Arduino wrist controller
2. Click 'Connect to Device' button below
3. Move your wrist through its FULL range of motion (up and down)
4. The system will automatically track minimum and maximum angles
5. When ready, click 'Save Calibration' to proceed to games
        """
        tk.Label(info_frame, text=instructions, justify="left", 
                font=("Arial", 11)).pack()
        
        # Connection frame
        conn_frame = ttk.LabelFrame(page, text="Device Connection", padding=15)
        conn_frame.pack(fill="x", pady=10)
        
        self.conn_status_var = tk.StringVar(value="Not Connected")
        tk.Label(conn_frame, textvariable=self.conn_status_var, 
                font=("Arial", 12, "bold"), fg="red").pack(pady=5)
        
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(pady=10)
        
        self.btn_connect = ttk.Button(btn_frame, text="Connect to Device", 
                                      command=self._connect_device)
        self.btn_connect.pack(side="left", padx=5)
        
        self.btn_disconnect = ttk.Button(btn_frame, text="Disconnect", 
                                         command=self._disconnect_device, 
                                         state="disabled")
        self.btn_disconnect.pack(side="left", padx=5)
        
        # Calibration display
        cal_frame = ttk.LabelFrame(page, text="Current Readings", padding=15)
        cal_frame.pack(fill="both", expand=True, pady=10)
        
        # Current angle display
        self.current_angle_var = tk.StringVar(value="--°")
        tk.Label(cal_frame, text="Current Angle:", font=("Arial", 12)).pack()
        tk.Label(cal_frame, textvariable=self.current_angle_var, 
                font=("Arial", 36, "bold"), fg="#3498db").pack(pady=10)
        
        # Min/Max display
        range_frame = ttk.Frame(cal_frame)
        range_frame.pack(pady=20)
        
        tk.Label(range_frame, text="Minimum:", font=("Arial", 11)).grid(row=0, column=0, padx=20)
        self.min_angle_var = tk.StringVar(value="--°")
        tk.Label(range_frame, textvariable=self.min_angle_var, 
                font=("Arial", 24, "bold"), fg="#e74c3c").grid(row=1, column=0, padx=20)
        
        tk.Label(range_frame, text="Maximum:", font=("Arial", 11)).grid(row=0, column=1, padx=20)
        self.max_angle_var = tk.StringVar(value="--°")
        tk.Label(range_frame, textvariable=self.max_angle_var, 
                font=("Arial", 24, "bold"), fg="#27ae60").grid(row=1, column=1, padx=20)
        
        tk.Label(range_frame, text="Range:", font=("Arial", 11)).grid(row=0, column=2, padx=20)
        self.range_var = tk.StringVar(value="--°")
        tk.Label(range_frame, textvariable=self.range_var, 
                font=("Arial", 24, "bold"), fg="#9b59b6").grid(row=1, column=2, padx=20)
        
        # Action buttons
        action_frame = ttk.Frame(page)
        action_frame.pack(pady=20)
        
        self.btn_save_cal = ttk.Button(action_frame, text="Save Calibration & Continue", 
                                       command=self._save_calibration, 
                                       state="disabled")
        self.btn_save_cal.pack(side="left", padx=10)
        
        if self.rom_cal.is_calibrated:
            ttk.Button(action_frame, text="Skip to Games →", 
                      command=lambda: self._show_page("game_select")).pack(side="left", padx=10)
        
        # Calibration tracking
        self.cal_min = 9999
        self.cal_max = -9999
        self.cal_active = False
    
    def _build_game_select_page(self):
        """Build game selection page"""
        page = ttk.Frame(self.root, padding=20)
        self.pages["game_select"] = page
        
        # Title
        title = tk.Label(page, text="Select a Game", 
                        font=("Arial", 24, "bold"), fg="#2c3e50")
        title.pack(pady=(0, 20))
        
        # Calibration status
        status_frame = ttk.Frame(page)
        status_frame.pack(fill="x", pady=10)
        
        if self.rom_cal.is_calibrated:
            cal_range = self.rom_cal.get_range()
            status_text = f"✓ ROM Calibrated: {self.rom_cal.min_angle:.1f}° to {self.rom_cal.max_angle:.1f}° (Range: {cal_range:.1f}°)"
            tk.Label(status_frame, text=status_text, font=("Arial", 11), 
                    fg="#27ae60").pack(side="left")
        else:
            tk.Label(status_frame, text="⚠ ROM Not Calibrated", font=("Arial", 11), 
                    fg="#e74c3c").pack(side="left")
        
        ttk.Button(status_frame, text="Re-Calibrate ROM", 
                  command=lambda: self._show_page("rom_calibration")).pack(side="right", padx=10)
        
        # Games container
        games_frame = ttk.Frame(page)
        games_frame.pack(fill="both", expand=True, pady=20)
        
        # Game 1: Flexion
        game1_frame = ttk.LabelFrame(games_frame, text="Game 1: Gold Miner (Flexion)", padding=15)
        game1_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        tk.Label(game1_frame, text="🎣", font=("Arial", 48)).pack(pady=10)
        tk.Label(game1_frame, text="Catch gold and fish while avoiding trash!\n"
                                  "Focus on FLEXION movements.",
                wraplength=250, justify="center").pack(pady=10)
        ttk.Button(game1_frame, text="Play Game 1", 
                  command=self._launch_game1).pack(pady=10)
        
        # Game 2: Full Range
        game2_frame = ttk.LabelFrame(games_frame, text="Game 2: Bird Catcher (Full Range)", padding=15)
        game2_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        tk.Label(game2_frame, text="🐦", font=("Arial", 48)).pack(pady=10)
        tk.Label(game2_frame, text="Catch blue birds, avoid bombs!\n"
                                  "Uses FULL range of motion.",
                wraplength=250, justify="center").pack(pady=10)
        ttk.Button(game2_frame, text="Play Game 2", 
                  command=self._launch_game2).pack(pady=10)
        
        # Game 3: Extension
        game3_frame = ttk.LabelFrame(games_frame, text="Game 3: Rocket Launch (Extension)", padding=15)
        game3_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        
        tk.Label(game3_frame, text="🚀", font=("Arial", 48)).pack(pady=10)
        tk.Label(game3_frame, text="Launch a rocket by landing on platforms!\n"
                                  "Focus on EXTENSION movements.",
                wraplength=500, justify="center").pack(pady=10)
        ttk.Button(game3_frame, text="Play Game 3", 
                  command=self._launch_game3).pack(pady=10)
        
        games_frame.columnconfigure(0, weight=1)
        games_frame.columnconfigure(1, weight=1)
        games_frame.rowconfigure(0, weight=1)
        games_frame.rowconfigure(1, weight=1)
    
    def _show_page(self, page_name):
        """Show specific page"""
        if self.current_page:
            self.pages[self.current_page].pack_forget()
        
        self.pages[page_name].pack(fill="both", expand=True)
        self.current_page = page_name
        
        # Start calibration monitoring if on ROM page
        if page_name == "rom_calibration" and not self.cal_active:
            self._update_calibration()
    
    def _connect_device(self):
        """Connect to Arduino device"""
        if self.serial_conn.connect():
            self.conn_status_var.set(f"Connected to {self.serial_conn.port}")
            self.conn_status_var.trace_vdelete("w", self.conn_status_var.trace_info()[0][1])  # Clear trace
            self.root.after(100, lambda: self.root.nametowidget(
                str(self.conn_status_var)).config(fg="green"))
            self.btn_connect.config(state="disabled")
            self.btn_disconnect.config(state="normal")
            self.btn_save_cal.config(state="normal")
            self.cal_min = 9999
            self.cal_max = -9999
            messagebox.showinfo("Success", f"Connected to Arduino on {self.serial_conn.port}")
        else:
            messagebox.showerror("Connection Error", 
                               "Could not find Arduino device.\n"
                               "Please check connection and try again.")
    
    def _disconnect_device(self):
        """Disconnect from Arduino"""
        self.serial_conn.disconnect()
        self.conn_status_var.set("Not Connected")
        # Find the label widget and update color
        for widget in self.pages["rom_calibration"].winfo_children():
            if isinstance(widget, ttk.LabelFrame) and "Device Connection" in str(widget.cget("text")):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Label) and child.cget("textvariable") == str(self.conn_status_var):
                        child.config(fg="red")
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        self.btn_save_cal.config(state="disabled")
    
    def _update_calibration(self):
        """Update calibration readings"""
        if self.current_page != "rom_calibration":
            self.cal_active = False
            return
        
        self.cal_active = True
        angle = self.serial_conn.read_angle()
        
        if angle is not None:
            # Update current angle
            self.current_angle_var.set(f"{angle:.1f}°")
            
            # Update min/max
            if angle < self.cal_min:
                self.cal_min = angle
                self.min_angle_var.set(f"{self.cal_min:.1f}°")
            
            if angle > self.cal_max:
                self.cal_max = angle
                self.max_angle_var.set(f"{self.cal_max:.1f}°")
            
            # Update range
            if self.cal_min < 9999 and self.cal_max > -9999:
                cal_range = self.cal_max - self.cal_min
                self.range_var.set(f"{cal_range:.1f}°")
        
        # Continue updating
        self.root.after(20, self._update_calibration)
    
    def _save_calibration(self):
        """Save calibration and proceed to game selection"""
        if self.cal_min >= self.cal_max or (self.cal_max - self.cal_min) < 10:
            messagebox.showerror("Invalid Calibration", 
                               "Please move your wrist through a wider range.\n"
                               "Minimum range: 10 degrees")
            return
        
        if self.rom_cal.save_calibration(self.cal_min, self.cal_max):
            cal_range = self.rom_cal.get_range()
            messagebox.showinfo("Calibration Saved", 
                              f"ROM calibrated successfully!\n\n"
                              f"Range: {self.rom_cal.min_angle:.1f}° to {self.rom_cal.max_angle:.1f}°\n"
                              f"Total: {cal_range:.1f}°")
            self._show_page("game_select")
        else:
            messagebox.showerror("Error", "Failed to save calibration")
    
    def _launch_game1(self):
        """Launch Game 1: Flexion"""
        if not self.rom_cal.is_calibrated:
            messagebox.showwarning("Not Calibrated", "Please calibrate ROM first")
            return
        
        # Pass calibration to game
        game_path = os.path.join(os.path.dirname(__file__), "Game 1 - Flexion", "flexion_game.py")
        if os.path.exists(game_path):
            # Hide launcher and run game
            self.root.withdraw()
            os.system(f'python "{game_path}" {self.rom_cal.min_angle} {self.rom_cal.max_angle}')
            self.root.deiconify()
        else:
            messagebox.showerror("Error", "Game 1 not found")
    
    def _launch_game2(self):
        """Launch Game 2: Full Range"""
        if not self.rom_cal.is_calibrated:
            messagebox.showwarning("Not Calibrated", "Please calibrate ROM first")
            return
        
        game_path = os.path.join(os.path.dirname(__file__), "Game 2 - All", "gam_potentiometer.py")
        if os.path.exists(game_path):
            self.root.withdraw()
            os.system(f'python "{game_path}" {self.rom_cal.min_angle} {self.rom_cal.max_angle}')
            self.root.deiconify()
        else:
            messagebox.showerror("Error", "Game 2 not found")
    
    def _launch_game3(self):
        """Launch Game 3: Extension"""
        if not self.rom_cal.is_calibrated:
            messagebox.showwarning("Not Calibrated", "Please calibrate ROM first")
            return
        
        game_path = os.path.join(os.path.dirname(__file__), "Game 3 - Extension", "extension.py")
        if os.path.exists(game_path):
            self.root.withdraw()
            os.system(f'python "{game_path}" {self.rom_cal.min_angle} {self.rom_cal.max_angle}')
            self.root.deiconify()
        else:
            messagebox.showerror("Error", "Game 3 not found")
    
    def _on_closing(self):
        """Handle window close event"""
        self.serial_conn.disconnect()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = GameLauncher(root)
    root.mainloop()

if __name__ == "__main__":
    main()
