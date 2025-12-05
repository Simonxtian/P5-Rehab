import threading
import time
import csv
import json
import os
import sys
import subprocess
import queue
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox
import math
from datetime import datetime

# --- CONFIGURATION ---
DEFAULT_BAUD = 460800
DEFAULT_PORT = None 

# Get the script's directory and construct absolute paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PATIENT_DB_FILE = os.path.join(PROJECT_ROOT, "patients_db.json")
CALIBRATION_FILE = os.path.join(SCRIPT_DIR, "calibration_data.json")

# --- GAME PATHS ---
GAME_1_PATH = os.path.join(PROJECT_ROOT, "Game 1 - Flexion", "flexion_game.py")
GAME_2_PATH = os.path.join(PROJECT_ROOT, "Game 2 - All", "Flex_and_ext_game.py")
GAME_3_PATH = os.path.join(PROJECT_ROOT, "Game 3 - Extension", "extension.py")

# Telemetry columns
COLS = ["theta_pot", "button_state","theta_pot_rad", "wUser_", "tau_ext"]
MIN_TAU_REF = 0.05  # Minimum torque reference for safety


# ============================================================================
# SERIAL WORKER (Background Thread)
# ============================================================================
class SerialWorker(threading.Thread):
    def __init__(self, port, baud, line_queue, raw_queue, stop_event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.line_queue = line_queue
        self.raw_queue = raw_queue
        self.stop_event = stop_event
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
        except Exception as e:
            self.line_queue.put(("#ERROR", f"Serial open failed: {e}"))
            return
        self.line_queue.put(("#INFO", f"Connected to {self.port} @ {self.baud}"))
        
        buf = b""
        while not self.stop_event.is_set():
            try:
                chunk = self.ser.read(1024)
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            s = line.decode("utf-8", errors="ignore").strip()
                        except:
                            s = str(line)
                        self.raw_queue.put(s)
            except Exception as e:
                self.line_queue.put(("#ERROR", f"Serial read error: {e}"))
                break
        
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except:
            pass
        self.line_queue.put(("#INFO", "Disconnected"))


# ============================================================================
# PATIENT DATABASE
# ============================================================================
class PatientDatabase:
    def __init__(self, db_file=PATIENT_DB_FILE):
        self.db_file = db_file
        print(f"[DEBUG] Loading database from: {os.path.abspath(self.db_file)}")
        self.patients = self._load_db()
        print(f"[DEBUG] Loaded {len(self.patients)} patients: {list(self.patients.keys())}")
    
    def _load_db(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    data = json.load(f)
                    print(f"[DEBUG] Successfully loaded database with {len(data)} patients")
                    return data
            except Exception as e:
                print(f"[ERROR] Failed to load database: {e}")
                return {}
        else:
            print(f"[WARNING] Database file not found: {self.db_file}")
        return {}
    
    def _save_db(self):
        with open(self.db_file, 'w') as f:
            json.dump(self.patients, f, indent=2)
    
    def add_patient(self, name, weight, difficulty):
        p_id = name.lower().replace(' ', '_')
        self.patients[p_id] = {
            'name': name,
            'weight': weight,
            'difficulty': difficulty,
            'created': datetime.now().isoformat(),
            'sessions': []
        }
        self._save_db()
        return p_id
    
    def get_patient(self, p_id):
        return self.patients.get(p_id)
    
    def get_all_patients(self):
        return self.patients

    def update_patient(self, p_id, **kwargs):
        if p_id in self.patients:
            for k, v in kwargs.items():
                self.patients[p_id][k] = v
            self._save_db()

    def create_new_session(self, p_id, initial_data):
        if p_id in self.patients:
            self.patients[p_id]['sessions'].append(initial_data)
            self._save_db()

    def update_active_session(self, p_id, update_data):
        if p_id in self.patients and self.patients[p_id]['sessions']:
            last_session = self.patients[p_id]['sessions'][-1]
            for key, value in update_data.items():
                last_session[key] = value
            self._save_db()


# ============================================================================
# BASE PAGE CLASS
# ============================================================================
class BasePage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
    
    def show(self):
        """Called when the page becomes visible"""
        pass
    
    def hide(self):
        """Called when the page is hidden"""
        pass


# ============================================================================
# PATIENT SELECTION PAGE
# ============================================================================
class PatientPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build_ui()
    
    def _build_ui(self):
        # Title
        title = ttk.Label(self, text="Patient Management", font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, pady=(0, 20), sticky="n")
        
        # Content frame
        content = ttk.Frame(self)
        content.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        
        # Left: Select existing patient
        self._build_patient_selector(content)
        
        # Right: Register new patient
        self._build_patient_registration(content)
    
    def _build_patient_selector(self, parent):
        select_frm = ttk.LabelFrame(parent, text="Select Existing Patient", padding=10)
        select_frm.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        select_frm.rowconfigure(1, weight=1)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(select_frm)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=5)
        select_frm.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.patient_listbox = tk.Listbox(list_frame, height=10, yscrollcommand=scrollbar.set)
        self.patient_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.patient_listbox.yview)
        self.patient_listbox.bind('<<ListboxSelect>>', self._on_patient_select)
        
        # Info display
        self.patient_info_var = tk.StringVar(value="No patient selected")
        info_lbl = ttk.Label(select_frm, textvariable=self.patient_info_var, 
                            relief="sunken", padding=10)
        info_lbl.grid(row=1, column=0, sticky="ew", pady=10)
        
        # Load button
        ttk.Button(select_frm, text="Load Patient", 
                  command=self._load_selected_patient).grid(row=2, column=0, pady=5)
    
    def _build_patient_registration(self, parent):
        register_frm = ttk.LabelFrame(parent, text="Register New Patient", padding=10)
        register_frm.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        # Name
        ttk.Label(register_frm, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.new_name_var = tk.StringVar()
        ttk.Entry(register_frm, textvariable=self.new_name_var, width=25).grid(
            row=0, column=1, pady=5, sticky="ew")
        
        # Weight
        ttk.Label(register_frm, text="Weight (kg):").grid(row=1, column=0, sticky="w", pady=5)
        self.new_weight_var = tk.StringVar(value="70")
        ttk.Entry(register_frm, textvariable=self.new_weight_var, width=25).grid(
            row=1, column=1, pady=5, sticky="ew")
        
        # Difficulty slider
        ttk.Label(register_frm, text="Difficulty (0.1-1.0):").grid(
            row=2, column=0, sticky="w", pady=5)
        diff_frame = ttk.Frame(register_frm)
        diff_frame.grid(row=2, column=1, pady=5, sticky="ew")
        
        self.new_diff_var = tk.DoubleVar(value=0.6)
        self.new_diff_slider = ttk.Scale(diff_frame, from_=0.1, to=1.0, 
                                         orient="horizontal", variable=self.new_diff_var,
                                         command=self._update_diff_label)
        self.new_diff_slider.pack(side="left", fill="x", expand=True)
        
        self.new_diff_label = ttk.Label(diff_frame, text="0.60", width=6)
        self.new_diff_label.pack(side="left", padx=5)
        
        # Register button
        ttk.Button(register_frm, text="Register & Continue", 
                  command=self._register_new_patient).grid(
            row=4, column=0, columnspan=2, pady=20)
        
        register_frm.columnconfigure(1, weight=1)
    
    def _update_diff_label(self, val):
        self.new_diff_label.config(text=f"{float(val):.2f}")
    
    def _on_patient_select(self, event):
        selection = self.patient_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        p_ids = list(self.app.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            p = self.app.patient_db.get_patient(p_ids[idx])
            self.patient_info_var.set(
                f"Name: {p['name']}\nWeight: {p['weight']} kg\nSessions: {len(p['sessions'])}")
    
    def _load_selected_patient(self):
        selection = self.patient_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        p_ids = list(self.app.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            self.app.load_patient(p_ids[idx])
    
    def _register_new_patient(self):
        name = self.new_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a patient name")
            return
        try:
            w = float(self.new_weight_var.get())
            d = self.new_diff_var.get()
        except ValueError:
            messagebox.showerror("Error", "Invalid weight value")
            return
        
        p_id = self.app.patient_db.add_patient(name, w, d)
        self.app.load_patient(p_id)
    
    def show(self):
        self.refresh_patient_list()
    
    def refresh_patient_list(self):
        self.patient_listbox.delete(0, tk.END)
        patients = self.app.patient_db.get_all_patients()
        for p_id, data in patients.items():
            self.patient_listbox.insert(tk.END, f"{data['name']} (W:{data['weight']}kg)")


# ============================================================================
# THERAPY PAGE
# ============================================================================
class TherapyPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build_ui()
    
    def _build_ui(self):
        # Header with patient info and navigation
        self._build_header()
        
        # Connection controls
        self._build_connection_section()
        
        # Parameters
        self._build_parameters_section()
        
        # MVC test
        self._build_mvc_section()
        
        # Telemetry
        self._build_telemetry_section()
        
        # Log
        self._build_log_section()
    
    def _build_header(self):
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.patient_header_var = tk.StringVar(value="No patient loaded")
        ttk.Label(header, textvariable=self.patient_header_var, 
                 font=("Arial", 12, "bold")).pack(side="left")
        
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side="right")
        
        self.btn_stop_session = ttk.Button(btn_frame, text="Stop Therapy", 
                                           command=self.app.stop_session, state="disabled")
        self.btn_stop_session.pack(side="left", padx=5)
        
        self.btn_goto_games = ttk.Button(btn_frame, text="Proceed to Games >>", 
                                        command=lambda: self.app.show_page("game"), 
                                        state="disabled")
        self.btn_goto_games.pack(side="left", padx=5)
        
        ttk.Button(btn_frame, text="← Change Patient", 
                  command=lambda: self.app.show_page("patient")).pack(side="left")
    
    def _build_connection_section(self):
        con = ttk.LabelFrame(self, text="Connection")
        con.grid(row=1, column=0, sticky="ew", pady=5)
        
        ttk.Label(con, text="Port:").grid(row=0, column=0, padx=5)
        self.port_cmb = ttk.Combobox(con, width=15, state="readonly")
        self.port_cmb.grid(row=0, column=1, padx=3)
        
        ttk.Label(con, text="Baud:").grid(row=0, column=2, padx=5)
        self.baud_cmb = ttk.Combobox(con, width=8, values=(115200, 230400, 460800))
        self.baud_cmb.set(str(DEFAULT_BAUD))
        self.baud_cmb.grid(row=0, column=3, padx=3)
        
        ttk.Button(con, text="Refresh", command=self._populate_ports).grid(
            row=0, column=4, padx=3)
        
        self.btn_connect = ttk.Button(con, text="Connect", command=self.app.toggle_connection)
        self.btn_connect.grid(row=0, column=5, padx=3)
        
        self._populate_ports()
    
    def _build_parameters_section(self):
        params = ttk.LabelFrame(self, text="Parameters")
        params.grid(row=2, column=0, sticky="ew", pady=5)
        
        # Row 0: Patient parameters
        ttk.Label(params, text="Weight (kg):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.therapy_weight_var = tk.StringVar()
        ttk.Entry(params, textvariable=self.therapy_weight_var, width=10).grid(
            row=0, column=1, padx=3, pady=5, sticky="w")
        
        ttk.Label(params, text="Difficulty:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        diff_frame = ttk.Frame(params)
        diff_frame.grid(row=0, column=3, padx=3, pady=5, sticky="w")
        
        self.therapy_diff_var = tk.DoubleVar()
        self.therapy_diff_slider = ttk.Scale(diff_frame, from_=0.1, to=1.0, 
                                            orient="horizontal", 
                                            variable=self.therapy_diff_var,
                                            command=self._update_therapy_diff_label, 
                                            length=120)
        self.therapy_diff_slider.pack(side="left")
        
        self.therapy_diff_label = ttk.Label(diff_frame, text="0.60", width=6)
        self.therapy_diff_label.pack(side="left", padx=2)
        
        ttk.Label(params, text="Arm Length (m):").grid(row=0, column=4, padx=5, pady=5, sticky="e")
        self.arm_length_var = tk.StringVar(value="0.09")
        ttk.Entry(params, textvariable=self.arm_length_var, width=10).grid(
            row=0, column=5, padx=3, pady=5, sticky="w")
        
        # Row 1: Device configuration buttons
        btn_frame1 = ttk.Frame(params)
        btn_frame1.grid(row=1, column=0, columnspan=6, pady=5, padx=10)
        
        ttk.Button(btn_frame1, text="Send Mass", command=self.app.send_mass, 
                  width=20).pack(side="left", padx=5)
        ttk.Button(btn_frame1, text="Send Arm Length", command=self.app.send_arm_length,
                  width=20).pack(side="left", padx=5)
        
        # Row 2: Control buttons
        btn_frame2 = ttk.Frame(params)
        btn_frame2.grid(row=2, column=0, columnspan=6, pady=5, padx=10)
        
        self.btn_toggle_spring = ttk.Button(btn_frame2, text="Spring: ON", 
                                           command=self.app.toggle_spring, width=20)
        self.btn_toggle_spring.pack(side="left", padx=5)
        
        ttk.Button(btn_frame2, text="Admittance OFF", command=self.app.force_admittance_off,
                  width=20).pack(side="left", padx=5)
        
        ttk.Button(btn_frame2, text="Clear Fault", command=self.app.clear_fault,
                  width=20).pack(side="left", padx=5)
    
    def _build_mvc_section(self):
        mvc = ttk.LabelFrame(self, text="MVC Test (Start of Session)")
        mvc.grid(row=3, column=0, sticky="ew", pady=5)
        
        ttk.Button(mvc, text="Run MVC (5s)", command=self.app.run_mvc).grid(
            row=0, column=0, padx=10, pady=5)
        
        self.mvc_label = ttk.Label(mvc, text="Results: -", foreground="blue")
        self.mvc_label.grid(row=1, column=0, sticky="w", pady=5, padx=5)
    
    def _build_telemetry_section(self):
        live = ttk.LabelFrame(self, text="Telemetry")
        live.grid(row=4, column=0, sticky="ew", pady=5)
        
        self.lbl_theta_pot = ttk.Label(live, text="Angle: 0.00°", font=("Arial", 10))
        self.lbl_theta_pot.grid(row=0, column=0, padx=10, pady=5)
        
        self.lbl_tau = ttk.Label(live, text="tau: 0.00", font=("Arial", 10))
        self.lbl_tau.grid(row=0, column=1, padx=10, pady=5)
    
    def _build_log_section(self):
        logf = ttk.LabelFrame(self, text="Log")
        logf.grid(row=5, column=0, sticky="nsew", pady=5)
        self.rowconfigure(5, weight=1)
        
        log_scroll = ttk.Scrollbar(logf)
        log_scroll.pack(side="right", fill="y")
        
        self.txt = tk.Text(logf, height=8, yscrollcommand=log_scroll.set)
        self.txt.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.txt.yview)
    
    def _populate_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cmb['values'] = ports
        if ports:
            self.port_cmb.set(ports[0])
    
    def _update_therapy_diff_label(self, val):
        self.therapy_diff_label.config(text=f"{float(val):.2f}")
    
    def update_patient_info(self, patient):
        if patient:
            self.patient_header_var.set(f"Patient: {patient['name']}")
            self.therapy_weight_var.set(str(patient['weight']))
            self.therapy_diff_var.set(float(patient['difficulty']))
            self._update_therapy_diff_label(patient['difficulty'])
    
    def log(self, msg):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")


# ============================================================================
# GAME/CALIBRATION PAGE
# ============================================================================
class GamePage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.cal_step = 0
        self.cal_data = {}
        self._build_ui()
    
    def _build_ui(self):
        # Top bar
        top_bar = ttk.Frame(self)
        top_bar.grid(row=0, column=0, sticky="ew", pady=10)
        
        ttk.Button(top_bar, text="<< Back to Therapy", 
                  command=lambda: self.app.show_page("therapy")).pack(side="left")
        ttk.Label(top_bar, text="Calibration & Games", 
                 font=("Arial", 16, "bold")).pack(side="left", padx=20)
        
        # Current angle display
        val_frame = ttk.Frame(self, relief="sunken", borderwidth=1)
        val_frame.grid(row=1, column=0, sticky="ew", pady=10)
        
        ttk.Label(val_frame, text="Current Angle:", font=("Arial", 12)).pack(pady=5)
        self.lbl_cal_value = ttk.Label(val_frame, text="0.00°", 
                                       font=("Arial", 40, "bold"), foreground="#2c3e50")
        self.lbl_cal_value.pack(pady=10)
        
        # Calibration/Game container
        self.cal_container = ttk.Frame(self)
        self.cal_container.grid(row=2, column=0, sticky="nsew")
        self.rowconfigure(2, weight=1)
        
        # Calibration wizard
        self._build_calibration_wizard()
        
        # Game selection
        self._build_game_selection()
        
        self.reset_to_calibration()
    
    def _build_calibration_wizard(self):
        self.frm_cal_wizard = ttk.LabelFrame(self.cal_container, 
                                            text="Calibration Wizard", padding=20)
        
        self.btn_start_cal = ttk.Button(self.frm_cal_wizard, 
                                       text="START NEW CALIBRATION", 
                                       command=self.start_calibration)
        
        self.frm_cal_steps = ttk.Frame(self.frm_cal_wizard)
        
        self.lbl_cal_instr = tk.Label(self.frm_cal_steps, text="...", 
                                     font=("Arial", 14), wraplength=400, justify="center")
        self.lbl_cal_instr.pack(pady=20)
        
        self.btn_cal_action = ttk.Button(self.frm_cal_steps, text="CAPTURE VALUE", 
                                        command=self.next_calibration_step)
        self.btn_cal_action.pack(fill="x", padx=40, pady=10, ipady=10)
        
        ttk.Button(self.frm_cal_steps, text="Cancel", 
                  command=self.cancel_calibration).pack(pady=5)
    
    def _build_game_selection(self):
        self.frm_game_select = ttk.LabelFrame(self.cal_container, 
                                             text="Select Game", padding=20)
        
        tk.Label(self.frm_game_select, text="Calibration Complete!", 
                font=("Arial", 14, "bold"), fg="green").pack(pady=(10, 5))
        
        ttk.Button(self.frm_game_select, text="GAME 1: Flexion", 
                  command=lambda: self.app.launch_game(GAME_1_PATH)).pack(
            fill="x", pady=5, ipady=10)
        
        ttk.Button(self.frm_game_select, text="GAME 2: Flex & Ext", 
                  command=lambda: self.app.launch_game(GAME_2_PATH)).pack(
            fill="x", pady=5, ipady=10)
        
        ttk.Button(self.frm_game_select, text="GAME 3: Extension", 
                  command=lambda: self.app.launch_game(GAME_3_PATH)).pack(
            fill="x", pady=5, ipady=10)
        
        ttk.Separator(self.frm_game_select, orient="horizontal").pack(fill="x", pady=20)
        
        ttk.Button(self.frm_game_select, text="Re-Calibrate Device", 
                  command=self.reset_to_calibration).pack(pady=5)
    
    def reset_to_calibration(self):
        self.frm_cal_wizard.pack(fill="both", expand=True, padx=10, pady=10)
        self.frm_game_select.pack_forget()
        self.cancel_calibration()
    
    def start_calibration(self):
        if not self.app.connected:
            messagebox.showerror("Error", "Connect serial port first")
            return
        self.cal_step = 1
        self.cal_data = {}
        self.btn_start_cal.pack_forget()
        self.frm_cal_steps.pack(fill="both", expand=True)
        self.update_wizard_ui()
    
    def cancel_calibration(self):
        self.cal_step = 0
        self.frm_cal_steps.pack_forget()
        self.btn_start_cal.pack(fill="x", pady=40, ipady=15)
    
    def next_calibration_step(self):
        val = self.app.current_theta_deg
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
            self.save_calibration_json()
            self.frm_cal_wizard.pack_forget()
            self.frm_game_select.pack(fill="both", expand=True, padx=10, pady=10)
    
    def update_wizard_ui(self):
        if self.cal_step == 1:
            self.lbl_cal_instr.config(text="STEP 1: Straight (Neutral)", fg="blue")
            self.btn_cal_action.config(text="CAPTURE NEUTRAL")
        elif self.cal_step == 2:
            self.lbl_cal_instr.config(text="STEP 2: Bend Down (Flexion)", fg="#d35400")
            self.btn_cal_action.config(text="CAPTURE FLEXION")
        elif self.cal_step == 3:
            self.lbl_cal_instr.config(text="STEP 3: Bend Up (Extension)", fg="#c0392b")
            self.btn_cal_action.config(text="CAPTURE EXTENSION")
    
    def save_calibration_json(self):
        try:
            with open(CALIBRATION_FILE, 'w') as f:
                json.dump(self.cal_data, f, indent=4)
            
            if self.app.current_patient_id:
                f_rom = self.cal_data.get('flexion', 0.0)
                e_rom = self.cal_data.get('extension', 0.0)
                self.app.patient_db.update_active_session(self.app.current_patient_id, {
                    "flexion_rom": round(f_rom, 2),
                    "extension_rom": round(e_rom, 2)
                })
            
            self.app.log("# Calibration Saved.")
            messagebox.showinfo("Success", "Calibration saved to Session.")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")
    
    def update_angle_display(self, angle_deg):
        self.lbl_cal_value.config(text=f"{angle_deg:.2f}°")


# ============================================================================
# MAIN APPLICATION
# ============================================================================
class RehabGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wrist Rehab – Unified System")
        self.root.geometry("900x700")
        
        # Serial communication
        self.ser_thread = None
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.raw_queue = queue.Queue()
        self.connected = False
        
        # Session data
        self.session_file = None
        self.csv_writer = None
        self.session_active = False
        self.current_theta_deg = 0.0
        
        # Patient data
        self.patient_db = PatientDatabase()
        self.current_patient_id = None
        self.current_patient = None
        
        # MVC parameters
        self.last_J = None
        self.last_B = None
        self.last_K = None
        self.spring_enabled = True
        
        # Game tracking
        self.current_game_process = None
        self.current_game_json_path = None
        
        # Build UI
        self.container = ttk.Frame(root)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)
        
        # Create pages
        self.pages = {}
        self.pages["patient"] = PatientPage(self.container, self)
        self.pages["therapy"] = TherapyPage(self.container, self)
        self.pages["game"] = GamePage(self.container, self)
        
        # Show initial page
        self.current_page = None
        self.show_page("patient")
        
        # Start polling
        self._poll_queues()
    
    def show_page(self, page_name):
        """Switch to a different page"""
        if self.current_page:
            self.pages[self.current_page].grid_forget()
            self.pages[self.current_page].hide()
        
        self.pages[page_name].grid(row=0, column=0, sticky="nsew")
        self.pages[page_name].show()
        self.current_page = page_name
    
    def load_patient(self, p_id):
        """Load a patient and switch to therapy page"""
        self.current_patient_id = p_id
        self.current_patient = self.patient_db.get_patient(p_id)
        self.pages["therapy"].update_patient_info(self.current_patient)
        self.show_page("therapy")
    
    def toggle_connection(self):
        """Connect or disconnect from serial port"""
        if not self.connected:
            self._connect()
        else:
            self._disconnect()
    
    def _connect(self):
        port = self.pages["therapy"].port_cmb.get()
        if not port:
            return
        
        baud = int(self.pages["therapy"].baud_cmb.get())
        self.stop_event.clear()
        self.ser_thread = SerialWorker(port, baud, self.msg_queue, self.raw_queue, self.stop_event)
        self.ser_thread.start()
        self.connected = True
        self.pages["therapy"].btn_connect.config(text="Disconnect")
        
        # CSV logging will be started when MVC test creates a session
        self.session_file = None
        self.csv_writer = None
        
        # Initialize Arduino
        time.sleep(1.0)
        self._send("adm off")
        time.sleep(0.2)
        self.log("# Admittance disabled on connect")
    
    def _disconnect(self):
        self.stop_event.set()
        self.connected = False
        self.pages["therapy"].btn_connect.config(text="Connect")
        self.session_active = False
        self.pages["therapy"].btn_stop_session.config(state="disabled")
        self.pages["therapy"].btn_goto_games.config(state="disabled")
        if self.session_file:
            self.session_file.close()
    
    def _send(self, cmd):
        """Send command to Arduino"""
        try:
            if self.ser_thread and self.ser_thread.ser and self.ser_thread.ser.is_open:
                self.ser_thread.ser.write((cmd + "\n").encode("utf-8"))
                self.log(f">> {cmd}")
        except:
            pass
    
    def _poll_queues(self):
        """Poll serial queues for incoming data"""
        try:
            while True:
                tag, msg = self.msg_queue.get_nowait()
                self.log(f"{tag}: {msg}")
        except queue.Empty:
            pass
        
        try:
            while True:
                line = self.raw_queue.get_nowait()
                self._handle_line(line)
        except queue.Empty:
            pass
        
        self.root.after(50, self._poll_queues)
    
    def _handle_line(self, s):
        """Process incoming serial line"""
        if s.startswith("#"):
            self.log(s)
            return
        
        parts = s.split(',')
        if len(parts) >= 1:
            try:
                raw_angle = float(parts[0])
                self.current_theta_deg = raw_angle
                
                # Update angle displays
                if self.current_page == "game":
                    self.pages["game"].update_angle_display(raw_angle)
                
                if self.current_page == "therapy":
                    self.pages["therapy"].lbl_theta_pot.config(text=f"Angle: {raw_angle:.2f}°")
                
                # Process full telemetry
                if len(parts) == len(COLS):
                    vals = [float(x) for x in parts]
                    if self.current_page == "therapy":
                        self.pages["therapy"].lbl_tau.config(text=f"tau: {vals[4]:.3f}")
                    
                    if self.csv_writer:
                        self.csv_writer.writerow([time.time()] + vals)
            except:
                pass
    
    def log(self, msg):
        """Log message to therapy page"""
        if self.current_page == "therapy" or True:  # Always log
            self.pages["therapy"].log(msg)
    
    # ===== THERAPY COMMANDS =====
    
    def send_mass(self):
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        if not self.current_patient:
            messagebox.showerror("Error", "Load a patient first")
            return
        
        try:
            self._send("tare")
            time.sleep(0.3)
            self.log("# Load cell tared")
            
            w = float(self.pages["therapy"].therapy_weight_var.get())
            mass = 0.006 * w + 0.072
            self.patient_db.update_patient(self.current_patient_id, weight=w)
            self._send(f"totalmass {mass:.4f}")
            time.sleep(0.1)
            self.log(f"# Mass set: {mass:.4f} kg (from weight: {w} kg)")
            messagebox.showinfo("Success", f"Mass set to {mass:.4f} kg")
        except ValueError:
            messagebox.showerror("Error", "Invalid weight value")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set mass: {e}")
    
    def send_arm_length(self):
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        
        try:
            length = float(self.pages["therapy"].arm_length_var.get())
            if length <= 0:
                messagebox.showerror("Error", "Arm length must be positive")
                return
            self._send(f"armlength {length:.4f}")
            time.sleep(0.1)
            self.log(f"# Arm length set: {length:.4f} m")
            messagebox.showinfo("Success", f"Arm length set to {length:.4f} m")
        except ValueError:
            messagebox.showerror("Error", "Invalid arm length value")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set arm length: {e}")
    
    def run_mvc(self):
        if not self.current_patient or not self.connected:
            messagebox.showerror("Error", "Connect & Load Patient")
            return
        
        if self.session_active:
            self._send("adm off")
            time.sleep(0.2)
            self.session_active = False
        
        self.log("MVC Started...")
        self._send("adm off")
        time.sleep(0.5)
        self._send("eq hold")
        time.sleep(0.2)
        
        t_end = time.time() + 5.0
        tau_max = 0.0
        
        while time.time() < t_end:
            self.root.update()
            try:
                line = self.raw_queue.get(timeout=0.1)
                self._handle_line(line)
                parts = line.split(',')
                if len(parts) == len(COLS):
                    t = float(parts[4])
                    if t > tau_max:
                        tau_max = t
            except:
                pass
        
        if tau_max <= 0:
            tau_max = 1.0
        
        diff = self.pages["therapy"].therapy_diff_var.get()
        tau_ref = diff * tau_max
        
        if tau_ref < MIN_TAU_REF:
            self.log(f"# WARNING: tau_ref {tau_ref:.2f} below minimum. Using {MIN_TAU_REF}")
            tau_ref = MIN_TAU_REF
        
        J = tau_ref / 27.9253
        K = tau_ref / 1.0472
        B = 2 * 1 * math.sqrt(J * K)
        
        self.last_J = J
        self.last_B = B
        self.last_K = K
        self.spring_enabled = True
        self.pages["therapy"].btn_toggle_spring.config(text="Spring: ON")
        
        self.pages["therapy"].mvc_label.config(
            text=f"Max: {tau_max:.2f} | Ref: {tau_ref:.2f} | Diff: {diff:.2f}")
        
        master_session = {
            'timestamp': datetime.now().isoformat(),
            'type': 'THERAPY_SESSION',
            'mvc_tau_max': tau_max,
            'mvc_tau_ref': tau_ref,
            'difficulty': diff,
            'flexion_rom': 0.0,
            'extension_rom': 0.0,
            'session_highscore_flex': 0,
            'session_highscore_all': 0,
            'session_highscore_ext': 0
        }
        self.patient_db.create_new_session(self.current_patient_id, master_session)
        
        # Create CSV file with patient name and session number
        patient_name = self.current_patient['name'].replace(' ', '_')
        session_num = len(self.current_patient['sessions'])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"{patient_name}_session{session_num:03d}_{ts}.csv"
        
        # Start CSV logging
        if self.session_file:
            self.session_file.close()
        self.session_file = open(csv_filename, "w", newline="")
        self.csv_writer = csv.writer(self.session_file)
        self.csv_writer.writerow(["timestamp"] + COLS)
        
        self.log(f"# Session Created. MVC saved. Logging to: {csv_filename}")
        
        self._send(f"adm {J:.4f} {B:.4f} {K:.4f}")
        time.sleep(0.2)
        self._send("eq hold")
        time.sleep(0.2)
        self._send("adm on")
        time.sleep(0.2)
        self.log("# Admittance enabled after MVC")
        
        self.session_active = True
        self.pages["therapy"].btn_stop_session.config(state="normal")
        self.pages["therapy"].btn_goto_games.config(state="normal")
        messagebox.showinfo("MVC Done", "Admittance Active. Therapy session started. Go to Games.")
    
    def stop_session(self):
        if not self.connected:
            return
        self._send("adm off")
        self._send("w 0")
        self.session_active = False
        self.pages["therapy"].btn_stop_session.config(state="disabled")
        self.log("Session Stopped")
    
    def toggle_spring(self):
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        if not self.current_patient:
            messagebox.showerror("Error", "Load a patient first")
            return
        
        if self.last_J is None or self.last_B is None or self.last_K is None:
            messagebox.showerror("Error", "Run MVC test first to calculate admittance parameters")
            return
        
        try:
            J = self.last_J
            B = self.last_B
            
            if self.spring_enabled:
                K = 0.0
                self.spring_enabled = False
                self.pages["therapy"].btn_toggle_spring.config(text="Spring: OFF")
                self._send(f"adm {J:.4f} {B:.4f} {K:.4f}")
                self.log(f"# Spring disabled: K=0, J={J:.4f}, B={B:.4f}")
                messagebox.showinfo("Success", "Spring effect disabled (K=0)")
            else:
                K = self.last_K
                self.spring_enabled = True
                self.pages["therapy"].btn_toggle_spring.config(text="Spring: ON")
                self._send(f"adm {J:.4f} {B:.4f} {K:.4f}")
                self.log(f"# Spring enabled: K={K:.4f}, J={J:.4f}, B={B:.4f}")
                messagebox.showinfo("Success", f"Spring effect enabled (K={K:.4f})")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle spring: {e}")
    
    def force_admittance_off(self):
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        
        self._send("adm off")
        time.sleep(0.2)
        self.log("# ADMITTANCE FORCED OFF")
        self.session_active = False
        self.pages["therapy"].btn_stop_session.config(state="disabled")
        messagebox.showinfo("Admittance OFF", "Admittance control has been disabled")
    
    def clear_fault(self):
        """Clear the latched fault from the Arduino"""
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        
        self._send("clearfault")
        time.sleep(0.2)
        self.log("# Fault cleared - system ready to resume")
        messagebox.showinfo("Fault Cleared", "Proactive fault stop has been released")
    
    # ===== GAME LAUNCHING =====
    
    def launch_game(self, script_path):
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"File not found: {script_path}")
            return
        
        game_dir = os.path.dirname(script_path)
        game_filename = os.path.basename(script_path)
        
        # Determine game info
        game_title = "Unknown"
        score_key = "score_generic"
        json_filename = None
        
        if "flexion" in script_path.lower():
            game_title = "Game 1: Flexion"
            score_key = "session_highscore_flex"
            json_filename = "Highscore_flex.json"
        elif "game 2" in script_path.lower() or "potentiometer" in script_path.lower():
            game_title = "Game 2: Mixed"
            score_key = "session_highscore_all"
            json_filename = "highscore_all.json"
        elif "extension" in script_path.lower():
            game_title = "Game 3: Extension"
            score_key = "session_highscore_ext"
            json_filename = "highscore_extension.json"
        
        if json_filename:
            self.current_game_json_path = os.path.join(game_dir, json_filename)
        else:
            self.current_game_json_path = None
        
        # Disconnect to free serial port
        if self.connected:
            self._disconnect()
            time.sleep(0.5)
        
        try:
            p_id = self.current_patient_id if self.current_patient_id else "guest"
            p_name = self.current_patient['name'] if self.current_patient else "Guest"
            
            self.current_game_process = subprocess.Popen(
                [sys.executable, game_filename, p_id, p_name],
                cwd=game_dir
            )
            
            self.pages["therapy"].btn_goto_games.config(state="disabled")
            self.log(f"Launched {game_title}")
            
            self._monitor_game(game_title, score_key)
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))
            self._connect()
    
    def _monitor_game(self, game_title, score_key):
        if self.current_game_process.poll() is None:
            self.root.after(500, lambda: self._monitor_game(game_title, score_key))
            return
        
        self.log(f"# {game_title} finished.")
        
        final_session_score = 0
        
        if self.current_game_json_path and os.path.exists(self.current_game_json_path):
            try:
                with open(self.current_game_json_path, "r") as f:
                    full_data = json.load(f)
                
                p_id = self.current_patient_id if self.current_patient_id else "guest"
                
                if p_id in full_data:
                    final_session_score = full_data[p_id].get("session_highscore", 0)
                    self.log(f"# Retrieved score for {p_id}: {final_session_score}")
                else:
                    self.log(f"# No score data found for {p_id}")
            except Exception as e:
                self.log(f"# Error reading game results: {e}")
        
        if self.current_patient_id:
            self.patient_db.update_active_session(self.current_patient_id, {
                score_key: final_session_score
            })
            messagebox.showinfo("Game Over", f"Session Updated!\nScore: {final_session_score}")
        
        self.current_game_process = None
        self._connect()
        self.pages["therapy"].btn_goto_games.config(state="normal")


def main():
    root = tk.Tk()
    app = RehabGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
