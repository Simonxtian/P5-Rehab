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
DEFAULT_BAUD = 115200
DEFAULT_PORT = None 
PATIENT_DB_FILE = "patients_db.json"
CALIBRATION_FILE = "calibration_data.json"

# --- GAME PATHS (Adjust these to your actual file locations) ---
# Use raw strings (r"path") or forward slashes
GAME_1_PATH = r"Game 1 - Flexion\flexion_game.py"
GAME_2_PATH = r"Game 2 - All\flex_and_ext_game.py"
GAME_3_PATH = r"Game 3 - Extension\extension.py"

# Telemetry columns emitted by firmware:
COLS = ["theta_pot","theta_enc","w_user","w_meas","u_pwm","force_filt","tau_ext","w_adm"]

# -----------------------------------------------------------------------------
# CLASS 1: Serial Worker (Background Thread for Comms)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# CLASS 2: Patient Database
# -----------------------------------------------------------------------------
class PatientDatabase:
    def __init__(self, db_file=PATIENT_DB_FILE):
        self.db_file = db_file
        self.patients = self._load_db()
    
    def _load_db(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_db(self):
        with open(self.db_file, 'w') as f:
            json.dump(self.patients, f, indent=2)
    
    def add_patient(self, name, weight, difficulty):
        patient_id = name.lower().replace(' ', '_')
        self.patients[patient_id] = {
            'name': name,
            'weight': weight,
            'difficulty': difficulty,
            'created': datetime.now().isoformat(),
            'sessions': []
        }
        self._save_db()
        return patient_id
    
    def update_patient(self, patient_id, weight=None, difficulty=None):
        if patient_id in self.patients:
            if weight is not None:
                self.patients[patient_id]['weight'] = weight
            if difficulty is not None:
                self.patients[patient_id]['difficulty'] = difficulty
            self._save_db()
    
    def get_patient(self, patient_id):
        return self.patients.get(patient_id)
    
    def get_all_patients(self):
        return self.patients
    
    def add_session(self, patient_id, session_data):
        if patient_id in self.patients:
            self.patients[patient_id]['sessions'].append(session_data)
            self._save_db()

# -----------------------------------------------------------------------------
# CLASS 3: Main GUI (Merged)
# -----------------------------------------------------------------------------
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
        self.session_file = None
        self.csv_writer = None
        self.session_active = False 
        
        # Live Data (Shared between Therapy and Calibration)
        self.current_theta_deg = 0.0
        
        # Patient management
        self.patient_db = PatientDatabase()
        self.current_patient_id = None
        self.current_patient = None
        
        # Calibration State (From Second Code)
        self.cal_step = 0
        self.cal_data = {}
        
        # Pages container
        self.pages = {}
        self.current_page = None
        
        self._build_pages()
        self._show_page("patient_select")
        self._poll_queues()

    def _build_pages(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        # Page 1: Patient Selection
        self._build_patient_page()
        
        # Page 2: Therapy Session (MVC + Control)
        self._build_therapy_page()

        # Page 3: Calibration & Games (Merged Logic)
        self._build_game_page()
    
    # -------------------------------------------------------------------------
    # PAGE 1: PATIENT SELECTION
    # -------------------------------------------------------------------------
    def _build_patient_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["patient_select"] = page
        
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        
        # Title
        title = ttk.Label(page, text="Patient Management", font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, pady=(0, 20))
        
        # Main content
        content = ttk.Frame(page)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # Left: Select existing patient
        select_frm = ttk.LabelFrame(content, text="Select Existing Patient", padding=10)
        select_frm.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        ttk.Label(select_frm, text="Choose a patient:").grid(row=0, column=0, sticky="w", pady=5)
        
        list_frame = ttk.Frame(select_frm)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        select_frm.rowconfigure(1, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.patient_listbox = tk.Listbox(list_frame, height=10, yscrollcommand=scrollbar.set)
        self.patient_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.patient_listbox.yview)
        self.patient_listbox.bind('<<ListboxSelect>>', self._on_patient_select)
        
        self.patient_info_var = tk.StringVar(value="No patient selected")
        info_lbl = ttk.Label(select_frm, textvariable=self.patient_info_var, 
                             relief="sunken", padding=10, wraplength=250)
        info_lbl.grid(row=2, column=0, sticky="ew", pady=10)
        
        ttk.Button(select_frm, text="Load Patient", 
                   command=self._load_selected_patient).grid(row=3, column=0, pady=5)
        
        # Right: Register new patient
        register_frm = ttk.LabelFrame(content, text="Register New Patient", padding=10)
        register_frm.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        ttk.Label(register_frm, text="Patient Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.new_name_var = tk.StringVar()
        ttk.Entry(register_frm, textvariable=self.new_name_var, width=25).grid(row=0, column=1, pady=5)
        
        ttk.Label(register_frm, text="Weight (kg):").grid(row=1, column=0, sticky="w", pady=5)
        self.new_weight_var = tk.StringVar(value="70")
        ttk.Entry(register_frm, textvariable=self.new_weight_var, width=25).grid(row=1, column=1, pady=5)
        
        ttk.Label(register_frm, text="Difficulty (0.1-1.0):").grid(row=2, column=0, sticky="w", pady=5)
        self.new_diff_var = tk.StringVar(value="0.6")
        ttk.Entry(register_frm, textvariable=self.new_diff_var, width=25).grid(row=2, column=1, pady=5)
        
        ttk.Label(register_frm, text="Wrist mass:").grid(row=3, column=0, sticky="w", pady=5)
        self.new_mass_label = ttk.Label(register_frm, text="0.420 kg")
        self.new_mass_label.grid(row=3, column=1, sticky="w", pady=5)
        
        ttk.Button(register_frm, text="Register & Continue", 
                   command=self._register_new_patient).grid(row=4, column=0, columnspan=2, pady=20)

    # -------------------------------------------------------------------------
    # PAGE 2: THERAPY & MVC
    # -------------------------------------------------------------------------
    def _build_therapy_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["therapy"] = page
        
        page.rowconfigure(5, weight=1)
        page.columnconfigure(0, weight=1)
        
        # Header
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.patient_header_var = tk.StringVar(value="No patient loaded")
        ttk.Label(header, textvariable=self.patient_header_var, 
                  font=("Arial", 12, "bold")).pack(side="left")
        
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side="right")
        
        self.btn_stop_session = ttk.Button(btn_frame, text="Stop Therapy", 
                                           command=self._stop_session, state="disabled")
        self.btn_stop_session.pack(side="left", padx=5)

        # --- NEW BUTTON TO GO TO GAMES ---
        self.btn_goto_games = ttk.Button(btn_frame, text="Proceed to Games >>", 
                                         command=self._go_to_game_page, state="disabled")
        self.btn_goto_games.pack(side="left", padx=5)
        
        ttk.Button(btn_frame, text="← Change Patient", 
                   command=self._go_to_patient_page).pack(side="left")
        
        # Connection
        con = ttk.LabelFrame(page, text="Connection")
        con.grid(row=1, column=0, sticky="ew", pady=5)
        ttk.Label(con, text="Port:").grid(row=0, column=0, padx=5)
        self.port_cmb = ttk.Combobox(con, width=15, state="readonly")
        self.port_cmb.grid(row=0, column=1, padx=3)
        ttk.Label(con, text="Baud:").grid(row=0, column=2, padx=5)
        self.baud_cmb = ttk.Combobox(con, width=8, values=(115200, 57600, 230400))
        self.baud_cmb.set(str(DEFAULT_BAUD))
        self.baud_cmb.grid(row=0, column=3, padx=3)
        ttk.Button(con, text="Refresh", command=self._populate_ports).grid(row=0, column=4, padx=3)
        self.btn_connect = ttk.Button(con, text="Connect", command=self.on_connect)
        self.btn_connect.grid(row=0, column=5, padx=3)
        
        # Parameters
        params = ttk.LabelFrame(page, text="Patient Parameters")
        params.grid(row=2, column=0, sticky="ew", pady=5)
        self.therapy_weight_var = tk.StringVar()
        self.therapy_diff_var = tk.StringVar()
        ttk.Label(params, text="Weight (kg):").grid(row=0, column=0, padx=5)
        ttk.Entry(params, textvariable=self.therapy_weight_var, width=10).grid(row=0, column=1, padx=3)
        ttk.Label(params, text="Difficulty:").grid(row=0, column=2, padx=5)
        ttk.Entry(params, textvariable=self.therapy_diff_var, width=10).grid(row=0, column=3, padx=3)
        ttk.Label(params, text="Mass:").grid(row=0, column=4, padx=5)
        self.mass_label = ttk.Label(params, text="0.420 kg")
        self.mass_label.grid(row=0, column=5, padx=5)
        ttk.Button(params, text="Send Mass", command=self.on_set_mass).grid(row=0, column=6, padx=10)

        # MVC
        mvc = ttk.LabelFrame(page, text="MVC Test (Maximum Voluntary Contraction)")
        mvc.grid(row=3, column=0, sticky="ew", pady=5)
        ttk.Label(mvc, text="θ_target (deg):").grid(row=0, column=0, padx=5)
        self.theta_target_var = tk.StringVar(value="60")
        ttk.Entry(mvc, textvariable=self.theta_target_var, width=8).grid(row=0, column=1, padx=3)
        ttk.Label(mvc, text="a_max (deg/s²):").grid(row=0, column=2, padx=5)
        self.amax_var = tk.StringVar(value="100")
        ttk.Entry(mvc, textvariable=self.amax_var, width=8).grid(row=0, column=3, padx=3)
        ttk.Button(mvc, text="Run MVC Test (5 s)", command=self.on_run_mvc).grid(row=0, column=4, padx=10)
        self.mvc_label = ttk.Label(mvc, text="τ_ref: -, J: -, B: -, K: -", foreground="blue")
        self.mvc_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=5, padx=5)

        # Live
        live = ttk.LabelFrame(page, text="Live Telemetry")
        live.grid(row=4, column=0, sticky="ew", pady=5)
        self.lbl_theta_pot = ttk.Label(live, text="theta_pot: 0.00°", font=("Arial", 10))
        self.lbl_theta_pot.grid(row=0, column=0, padx=10, pady=5)
        self.lbl_tau = ttk.Label(live, text="tau_ext: 0.000 N·m", font=("Arial", 10))
        self.lbl_tau.grid(row=0, column=1, padx=10, pady=5)
        self.lbl_w = ttk.Label(live, text="w_meas: 0.000 rad/s", font=("Arial", 10))
        self.lbl_w.grid(row=0, column=2, padx=10, pady=5)
        self.lbl_u = ttk.Label(live, text="u_pwm: 0", font=("Arial", 10))
        self.lbl_u.grid(row=0, column=3, padx=10, pady=5)

        # Log
        logf = ttk.LabelFrame(page, text="System Log")
        logf.grid(row=5, column=0, sticky="nsew", pady=5)
        
        log_scroll = ttk.Scrollbar(logf)
        log_scroll.pack(side="right", fill="y")
        
        self.txt = tk.Text(logf, height=8, yscrollcommand=log_scroll.set)
        self.txt.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.txt.yview)

    # -------------------------------------------------------------------------
    # PAGE 3: CALIBRATION & GAMES (From Second Code)
    # -------------------------------------------------------------------------
    def _build_game_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["game_launcher"] = page
        
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        # Top Bar
        top_bar = ttk.Frame(page)
        top_bar.grid(row=0, column=0, sticky="ew", pady=10)
        ttk.Button(top_bar, text="<< Back to Therapy", command=lambda: self._show_page("therapy")).pack(side="left")
        ttk.Label(top_bar, text="Calibration & Game Launcher", font=("Arial", 16, "bold")).pack(side="left", padx=20)

        # Live Value Display (Big)
        val_frame = ttk.Frame(page, relief="sunken", borderwidth=1)
        val_frame.grid(row=1, column=0, sticky="ew", pady=10)
        ttk.Label(val_frame, text="Current Wrist Angle:", font=("Arial", 12)).pack(pady=5)
        self.lbl_cal_value = ttk.Label(val_frame, text="0.00°", font=("Arial", 40, "bold"), foreground="#2c3e50")
        self.lbl_cal_value.pack(pady=10)
        
        # Content Area (Swaps between Wizard and Games)
        self.cal_container = ttk.Frame(page)
        self.cal_container.grid(row=2, column=0, sticky="nsew")
        
        # --- SUB-FRAME: CALIBRATION WIZARD ---
        self.frm_cal_wizard = ttk.LabelFrame(self.cal_container, text="Calibration Wizard", padding=20)
        # (We don't pack it yet, handled by state logic)

        self.btn_start_cal = ttk.Button(self.frm_cal_wizard, text="START NEW CALIBRATION", 
                                        command=self.start_calibration)
        
        # Wizard Steps Container
        self.frm_cal_steps = ttk.Frame(self.frm_cal_wizard)
        self.lbl_cal_instr = tk.Label(self.frm_cal_steps, text="...", font=("Arial", 14), wraplength=400, justify="center")
        self.lbl_cal_instr.pack(pady=20)
        self.btn_cal_action = ttk.Button(self.frm_cal_steps, text="CAPTURE VALUE", command=self.next_calibration_step)
        self.btn_cal_action.pack(fill="x", padx=40, pady=10, ipady=10)
        ttk.Button(self.frm_cal_steps, text="Cancel", command=self.cancel_calibration).pack(pady=5)

        # --- SUB-FRAME: GAME SELECTION ---
        self.frm_game_select = ttk.LabelFrame(self.cal_container, text="Select Game", padding=20)
        
        tk.Label(self.frm_game_select, text="Calibration Complete!", font=("Arial", 14, "bold"), fg="green").pack(pady=(10, 5))
        tk.Label(self.frm_game_select, text="Launching a game will temporarily disconnect the Serial Port.", font=("Arial", 10)).pack(pady=(0, 20))
        
        ttk.Button(self.frm_game_select, text="GAME 1: Flexion", command=lambda: self.launch_game(GAME_1_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_game_select, text="GAME 2: Flex & Ext", command=lambda: self.launch_game(GAME_2_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_game_select, text="GAME 3: Extension", command=lambda: self.launch_game(GAME_3_PATH)).pack(fill="x", pady=5, ipady=10)
        
        ttk.Separator(self.frm_game_select, orient="horizontal").pack(fill="x", pady=20)
        ttk.Button(self.frm_game_select, text="Re-Calibrate Device", command=self.reset_to_calibration).pack(pady=5)

        # Initial State: Show Calibration Start Button
        self.reset_to_calibration()

    # -------------------------------------------------------------------------
    # PAGE NAVIGATION
    # -------------------------------------------------------------------------
    def _show_page(self, page_name):
        if self.current_page:
            self.pages[self.current_page].grid_forget()
        
        self.pages[page_name].grid(row=0, column=0, sticky="nsew")
        self.current_page = page_name
        
        if page_name == "patient_select":
            self._refresh_patient_list()
    
    def _go_to_game_page(self):
        self._show_page("game_launcher")
        self.reset_to_calibration()

    def _go_to_patient_page(self):
        if self.connected:
            if not messagebox.askyesno("Warning", "Disconnect and change patient?"):
                return
            self.on_connect() # Disconnect
        self._show_page("patient_select")

    # -------------------------------------------------------------------------
    # PATIENT & SERIAL LOGIC (From First Code)
    # -------------------------------------------------------------------------
    def _refresh_patient_list(self):
        self.patient_listbox.delete(0, tk.END)
        patients = self.patient_db.get_all_patients()
        for p_id, data in patients.items():
            display = f"{data['name']} (W:{data['weight']}kg, D:{data['difficulty']})"
            self.patient_listbox.insert(tk.END, display)
    
    def _on_patient_select(self, event):
        selection = self.patient_listbox.curselection()
        if not selection: return
        idx = selection[0]
        p_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            p = self.patient_db.get_patient(p_ids[idx])
            info = f"Name: {p['name']}\nWeight: {p['weight']} kg\nDiff: {p['difficulty']}\nSessions: {len(p['sessions'])}"
            self.patient_info_var.set(info)
            
    def _load_selected_patient(self):
        selection = self.patient_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection", "Select a patient first")
            return
        idx = selection[0]
        p_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            self.current_patient_id = p_ids[idx]
            self.current_patient = self.patient_db.get_patient(self.current_patient_id)
            self._update_therapy_page_with_patient()
            self._show_page("therapy")

    def _register_new_patient(self):
        name = self.new_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Enter name")
            return
        try:
            w = float(self.new_weight_var.get())
            d = float(self.new_diff_var.get())
        except:
            messagebox.showerror("Error", "Invalid numbers")
            return
        self.current_patient_id = self.patient_db.add_patient(name, w, d)
        self.current_patient = self.patient_db.get_patient(self.current_patient_id)
        self.new_name_var.set("")
        self._update_therapy_page_with_patient()
        self._show_page("therapy")

    def _update_therapy_page_with_patient(self):
        if not self.current_patient: return
        self.patient_header_var.set(f"Patient: {self.current_patient['name']}")
        self.therapy_weight_var.set(str(self.current_patient['weight']))
        self.therapy_diff_var.set(str(self.current_patient['difficulty']))
        mass = 0.006 * self.current_patient['weight']
        self.mass_label.config(text=f"{mass:.3f} kg")

    def _populate_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cmb['values'] = ports
        if DEFAULT_PORT and DEFAULT_PORT in ports:
            self.port_cmb.set(DEFAULT_PORT)
        elif ports:
            self.port_cmb.set(ports[0])

    def on_connect(self):
        if not self.connected:
            port = self.port_cmb.get()
            if not port:
                messagebox.showerror("Connect", "Select a port")
                return
            self.stop_event.clear()
            self.ser_thread = SerialWorker(port, int(self.baud_cmb.get()), self.msg_queue, self.raw_queue, self.stop_event)
            self.ser_thread.start()
            self.connected = True
            self.btn_connect.config(text="Disconnect")
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_file = open(f"session_{ts}.csv", "w", newline="")
            self.csv_writer = csv.writer(self.session_file)
            self.csv_writer.writerow(["timestamp"] + COLS)
            
            time.sleep(0.5)
            self._send("adm off")
            self._send("w 0")
        else:
            self.stop_event.set()
            self.connected = False
            self.btn_connect.config(text="Connect")
            self.session_active = False
            self.btn_stop_session.config(state="disabled")
            # Also disable game button if disconnected
            self.btn_goto_games.config(state="disabled")
            if self.session_file: 
                try: self.session_file.close()
                except: pass

    def _send(self, cmd):
        try:
            if self.ser_thread and self.ser_thread.ser and self.ser_thread.ser.is_open:
                self.ser_thread.ser.write((cmd + "\n").encode("utf-8"))
                self._log(f">> {cmd}")
        except Exception as e:
            self._log(f"#ERROR write: {e}")

    def _poll_queues(self):
        # 1. System Messages
        try:
            while True:
                tag, msg = self.msg_queue.get_nowait()
                self._log(f"{tag}: {msg}")
        except queue.Empty:
            pass
        
        # 2. Telemetry Data
        try:
            while True:
                line = self.raw_queue.get_nowait()
                self._handle_line(line)
        except queue.Empty:
            pass
        
        # 3. Update Mass Labels
        try:
            w = float(self.new_weight_var.get())
            self.new_mass_label.config(text=f"{0.006*w:.3f} kg")
        except: pass
        try:
            w = float(self.therapy_weight_var.get())
            self.mass_label.config(text=f"{0.006*w:.3f} kg")
        except: pass
        
        self.root.after(50, self._poll_queues)

    def _handle_line(self, s):
        if s.startswith("#"):
            self._log(s)
            return
        parts = s.split(',')
        if len(parts) == len(COLS):
            try:
                vals = [float(x) for x in parts]
                rec = dict(zip(COLS, vals))
                
                # --- CRITICAL: Update Shared Angle Variable for Calibration ---
                theta_rad = rec["theta_pot"]
                self.current_theta_deg = math.degrees(theta_rad)
                
                # Update Therapy Page Labels
                self.lbl_theta_pot.config(text=f"theta_pot: {self.current_theta_deg:.2f}°")
                self.lbl_tau.config(text=f"tau_ext: {rec['tau_ext']:.3f} N·m")
                self.lbl_w.config(text=f"w_meas: {rec['w_meas']:.3f} rad/s")
                self.lbl_u.config(text=f"u_pwm: {rec['u_pwm']:.0f}")
                
                # Update Game/Calibration Page Labels
                self.lbl_cal_value.config(text=f"{self.current_theta_deg:.2f}°")

                if self.csv_writer:
                    self.csv_writer.writerow([time.time()] + vals)
                return
            except:
                pass
        self._log(s)

    def _log(self, msg):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    # -------------------------------------------------------------------------
    # THERAPY LOGIC
    # -------------------------------------------------------------------------
    def on_set_mass(self):
        if not self.current_patient: return
        try:
            w = float(self.therapy_weight_var.get())
            mass = 0.006 * w
            self.patient_db.update_patient(self.current_patient_id, weight=w)
            self.current_patient['weight'] = w
            self._send(f"totalmass {mass:.4f}")
            self._log(f"# Mass set: {mass:.4f} kg")
        except:
            messagebox.showerror("Error", "Invalid weight")

    def on_run_mvc(self):
        if not self.current_patient:
            messagebox.showerror("Error", "No patient loaded")
            return
        if not self.connected:
            messagebox.showerror("Error", "Not connected")
            return
        
        # Stop active session first
        if self.session_active:
            self._send("adm off")
            time.sleep(0.2)
            self.session_active = False

        try:
            diff = float(self.therapy_diff_var.get())
            th_deg = float(self.theta_target_var.get())
            amax_d = float(self.amax_var.get())
        except:
            messagebox.showerror("Error", "Check numeric inputs")
            return

        self.patient_db.update_patient(self.current_patient_id, difficulty=diff)
        
        # MVC Sequence
        self._log("# Starting MVC sequence...")
        self._send("adm off")
        self._send("w 0")
        self._send("tare")
        time.sleep(0.5)
        self._send("eq hold")
        
        self._log("# MVC: PUSH NOW (5s)")
        t_end = time.time() + 5.0
        tau_max = None
        
        # Simple blocking loop for MVC 
        while time.time() < t_end:
            self.root.update() # Keep GUI responsive
            try:
                line = self.raw_queue.get(timeout=0.1)
                self._handle_line(line) # Process normally
                # Extract tau for calculation
                parts = line.split(',')
                if len(parts) == len(COLS):
                    tau = float(parts[6]) # tau_ext
                    if tau_max is None or tau > tau_max:
                        tau_max = tau
            except queue.Empty:
                pass
        
        if tau_max is None:
            messagebox.showerror("Error", "No data received during MVC")
            return
        
        # Calculations
        tau_ref = max(0.0, diff * tau_max)
        theta_target = math.radians(th_deg)
        amax = math.radians(amax_d)
        J = tau_ref / amax if amax > 1e-6 else 0.0
        K = tau_ref / theta_target if theta_target > 1e-6 else 0.0
        zeta = 1.1
        B = 2 * zeta * math.sqrt(max(K*J, 0.0))
        
        self.mvc_label.config(text=f"τ_ref={tau_ref:.2f} | J={J:.5f}, B={B:.5f}, K={K:.5f}")
        
        # Save Session
        sess = {
            'timestamp': datetime.now().isoformat(),
            'tau_max': tau_max, 'tau_ref': tau_ref,
            'J': J, 'B': B, 'K': K, 'difficulty': diff
        }
        self.patient_db.add_session(self.current_patient_id, sess)
        
        # Send Admittance Params
        self._send(f"adm {J:.6f} {B:.6f} {K:.6f}")
        time.sleep(0.1)
        self._send("eq hold")
        time.sleep(0.1)
        self._send("adm on")
        
        self.session_active = True
        self.btn_stop_session.config(state="normal")
        # Enable the button to go to game page
        self.btn_goto_games.config(state="normal")
        
        messagebox.showinfo("MVC Done", "Therapy Active.\nUse 'Stop Therapy' or 'Proceed to Games'.")

    def _stop_session(self):
        if not self.connected: return
        self._send("adm off")
        self._send("w 0")
        self.session_active = False
        self.btn_stop_session.config(state="disabled")
        self.mvc_label.config(text="Session Stopped", foreground="red")
        self._log("# Session stopped")

    # -------------------------------------------------------------------------
    # CALIBRATION LOGIC (Merged from Code 2)
    # -------------------------------------------------------------------------
    def reset_to_calibration(self):
        self.frm_cal_wizard.pack(fill="both", expand=True, padx=10, pady=10)
        self.frm_game_select.pack_forget()
        self.cancel_calibration()

    def start_calibration(self):
        if not self.connected:
            messagebox.showerror("Error", "Connect serial port first (on Therapy page)")
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
        # Use the shared variable populated by _handle_line
        val = self.current_theta_deg
        
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
            self.show_game_selection()

    def update_wizard_ui(self):
        if self.cal_step == 1:
            self.lbl_cal_instr.config(text="STEP 1: Keep Wrist STRAIGHT (Neutral).", fg="blue")
            self.btn_cal_action.config(text="CAPTURE NEUTRAL")
        elif self.cal_step == 2:
            self.lbl_cal_instr.config(text="STEP 2: Bend Wrist DOWN (Max Flexion).", fg="#d35400")
            self.btn_cal_action.config(text="CAPTURE FLEXION")
        elif self.cal_step == 3:
            self.lbl_cal_instr.config(text="STEP 3: Bend Wrist UP (Max Extension).", fg="#c0392b")
            self.btn_cal_action.config(text="CAPTURE EXTENSION")

    def save_calibration_json(self):
        try:
            with open(CALIBRATION_FILE, 'w') as f:
                json.dump(self.cal_data, f, indent=4)
            self._log(f"# Calibration saved: {self.cal_data}")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    def show_game_selection(self):
        self.frm_cal_wizard.pack_forget()
        self.frm_game_select.pack(fill="both", expand=True, padx=10, pady=10)

    def launch_game(self, script_name):
        if not os.path.exists(script_name):
            messagebox.showerror("Error", f"Game file not found:\n{script_name}")
            return
        
        # CRITICAL: Disconnect serial so the game can use it
        if self.connected:
            if messagebox.askokcancel("Disconnecting", "The GUI must disconnect so the game can use the Serial Port.\n\nLaunch game?"):
                self.on_connect() # This toggles it OFF
            else:
                return

        try:
            # Launch external script
            subprocess.Popen([sys.executable, script_name])
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))

# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = RehabGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()