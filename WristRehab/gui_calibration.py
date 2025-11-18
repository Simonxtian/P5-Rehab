import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import queue
import time
import json
import subprocess
import sys
import os

# --- CONFIGURATION ---
BAUD_RATE = 115200
CALIBRATION_FILE = r"WristRehab\calibration_data.json"

# --- GAME FILE NAMES ---
# Ensure these files exist in the same folder, or provide full paths (e.g., "Game 1/flexion_game.py")
GAME_1_PATH = r"Game 1 - Flexion\flexion_game.py"
GAME_2_PATH = r"Game 2 - All\flex_and_ext_game.py"
GAME_3_PATH = r"Game 3 - Extension\extension.py"
print("--- STARTING LAUNCHER ---")

class SimpleCalibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rehab Launcher")
        self.root.geometry("450x600")
        
        # --- STATE VARIABLES ---
        self.serial_port = None
        self.is_connected = False
        self.queue = queue.Queue()
        self.current_angle = 0.0
        
        # Calibration State
        self.cal_step = 0
        self.cal_data = {}

        self._setup_ui()
        
        # Start initial tasks
        self.refresh_ports()
        self.process_serial_data()

    def _setup_ui(self):
        # --- 1. CONNECTION PANEL ---
        frm_conn = ttk.LabelFrame(self.root, text="Connection", padding=10)
        frm_conn.pack(fill="x", padx=10, pady=5)
        
        self.cmb_ports = ttk.Combobox(frm_conn, width=20)
        self.cmb_ports.pack(side="left", padx=5)
        
        self.btn_refresh = ttk.Button(frm_conn, text="Refresh", command=self.refresh_ports)
        self.btn_refresh.pack(side="left", padx=5)
        
        self.btn_connect = ttk.Button(frm_conn, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=5)

        # --- 2. LIVE DATA PANEL ---
        frm_data = ttk.LabelFrame(self.root, text="Live Sensor Data", padding=10)
        frm_data.pack(fill="x", padx=10, pady=5)
        
        # IMPORTANT: Defined as ttk.Label, so we must use 'foreground' not 'fg' later
        self.lbl_status = ttk.Label(frm_data, text="Disconnected", foreground="red")
        self.lbl_status.pack(pady=5)
        
        self.lbl_value = ttk.Label(frm_data, text="0.00°", font=("Arial", 40, "bold"))
        self.lbl_value.pack(pady=10)
        
        # --- 3. CALIBRATION PANEL (Visible Initially) ---
        self.frm_cal = ttk.LabelFrame(self.root, text="Calibration Wizard", padding=10)
        self.frm_cal.pack(fill="both", expand=True, padx=10, pady=10)

        # A) Start Button 
        self.btn_start_cal = ttk.Button(self.frm_cal, text="START NEW CALIBRATION", command=self.start_calibration, state="disabled")
        self.btn_start_cal.pack(fill="x", pady=40, ipady=15)

        # B) Wizard Controls (Hidden inside frm_cal initially)
        self.frm_wizard = ttk.Frame(self.frm_cal)
        
        self.lbl_instruction = tk.Label(self.frm_wizard, text="...", font=("Arial", 12), wraplength=350, justify="center")
        self.lbl_instruction.pack(pady=20)
        
        self.btn_action = ttk.Button(self.frm_wizard, text="CAPTURE VALUE", command=self.next_calibration_step)
        self.btn_action.pack(fill="x", padx=20, pady=10, ipady=10)
        
        self.btn_cancel = ttk.Button(self.frm_wizard, text="Cancel", command=self.cancel_calibration)
        self.btn_cancel.pack(pady=10)

        # --- 4. GAME SELECTION PANEL (Hidden Initially) ---
        self.frm_games = ttk.LabelFrame(self.root, text="Select Game", padding=10)
        
        tk.Label(self.frm_games, text="Calibration Complete!", font=("Arial", 14, "bold"), fg="green").pack(pady=(10, 5))
        tk.Label(self.frm_games, text="Select a game to launch:", font=("Arial", 10)).pack(pady=(0, 20))
        
        ttk.Button(self.frm_games, text="GAME 1: Flexion", command=lambda: self.launch_game(GAME_1_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_games, text="GAME 2: Flex & Ext", command=lambda: self.launch_game(GAME_2_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_games, text="GAME 3: Extension", command=lambda: self.launch_game(GAME_3_PATH)).pack(fill="x", pady=5, ipady=10)
        
        ttk.Separator(self.frm_games, orient="horizontal").pack(fill="x", pady=20)
        ttk.Button(self.frm_games, text="Re-Calibrate Device", command=self.reset_to_menu).pack(pady=5)

    # --- SERIAL LOGIC ---
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.cmb_ports['values'] = ports
        if ports: self.cmb_ports.current(0)

    def toggle_connection(self):
        if not self.is_connected:
            port = self.cmb_ports.get()
            if not port: return
            try:
                self.serial_port = serial.Serial(port, BAUD_RATE, timeout=0.1)
                self.is_connected = True
                self.btn_connect.config(text="Disconnect")
                self.lbl_status.config(text=f"Connected to {port}", foreground="green")
                self.btn_start_cal.config(state="normal")
                
                self.thread = threading.Thread(target=self.serial_reader, daemon=True)
                self.thread.start()
            except Exception as e:
                messagebox.showerror("Error", str(e))
        else:
            self.is_connected = False
            if self.serial_port: self.serial_port.close()
            self.btn_connect.config(text="Connect")
            self.lbl_status.config(text="Disconnected", foreground="red")
            self.btn_start_cal.config(state="disabled")

    def serial_reader(self):
        while self.is_connected:
            try:
                if self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if line: self.queue.put(line)
                else:
                    time.sleep(0.01)
            except: break

    def process_serial_data(self):
        while not self.queue.empty():
            line = self.queue.get()
            try:
                parts = line.split(',')
                if len(parts) >= 1:
                    self.current_angle = float(parts[0])
                    self.lbl_value.config(text=f"{self.current_angle:.2f}°")
            except: pass
        self.root.after(50, self.process_serial_data)

    # --- TRANSITION LOGIC ---
    def show_game_selection(self):
        self.frm_cal.pack_forget()
        self.frm_games.pack(fill="both", expand=True, padx=10, pady=10)

    def reset_to_menu(self):
        self.frm_games.pack_forget()
        self.frm_cal.pack(fill="both", expand=True, padx=10, pady=10)
        self.cancel_calibration()

    # --- CALIBRATION LOGIC ---
    def start_calibration(self):
        self.cal_step = 1
        self.cal_data = {}
        self.btn_start_cal.pack_forget()
        self.frm_wizard.pack(fill="both", expand=True)
        self.update_wizard_ui()

    def cancel_calibration(self):
        self.cal_step = 0
        self.frm_wizard.pack_forget()
        self.btn_start_cal.pack(fill="x", pady=40, ipady=15)

    def next_calibration_step(self):
        val = self.current_angle
        if self.cal_step == 1:
            self.cal_data['neutral'] = val
            self.cal_step = 2
            self.update_wizard_ui()
        elif self.cal_step == 2:
            self.cal_data['flexion'] = val
            self.cal_step = 3
            self.update_wizard_ui()
        elif self.cal_step == 3:
            self.cal_data['extension'] = val
            self.save_json()
            self.show_game_selection()

    def update_wizard_ui(self):
        if self.cal_step == 1:
            self.lbl_instruction.config(text="STEP 1: Keep Wrist STRAIGHT (Neutral).\nClick Capture.", fg="blue")
            self.btn_action.config(text="CAPTURE NEUTRAL")
        elif self.cal_step == 2:
            self.lbl_instruction.config(text="STEP 2: Bend Wrist DOWN (Max Flexion).\nClick Capture.", fg="#d35400")
            self.btn_action.config(text="CAPTURE FLEXION")
        elif self.cal_step == 3:
            self.lbl_instruction.config(text="STEP 3: Bend Wrist UP (Max Extension).\nClick Capture.", fg="#c0392b")
            self.btn_action.config(text="CAPTURE EXTENSION")

    def save_json(self):
        try:
            with open(CALIBRATION_FILE, 'w') as f:
                json.dump(self.cal_data, f, indent=4)
            print("Saved:", self.cal_data)
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    # --- GAME LAUNCHING LOGIC ---
    def launch_game(self, script_name):
        # 1. Check file exists
        if not os.path.exists(script_name):
            messagebox.showerror("Error", f"File not found:\n{script_name}\n\nPlease check the 'GAME_PATHS' at the top of the script.")
            return

        # 2. Disconnect Serial so the game can use it
        if self.is_connected:
            self.toggle_connection()
            # !!! FIX: Use 'foreground' for ttk labels !!!
            self.lbl_status.config(text="Disconnected (Game Running)", foreground="orange")
        
        # 3. Launch Game
        try:
            subprocess.Popen([sys.executable, script_name])
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleCalibrationApp(root)
    root.mainloop()