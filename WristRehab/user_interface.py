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
#DEFAULT_BAUD = 115200 # Original baud rate
DEFAULT_BAUD = 460800 #Correcrted baud rate

DEFAULT_PORT = None 
PATIENT_DB_FILE = "patients_db.json"
CALIBRATION_FILE = r"WristRehab\calibration_data.json"

# --- GAME PATHS ---
GAME_1_PATH = r"Game 1 - Flexion\flexion_game.py"
GAME_2_PATH = r"Game 2 - All\Flex_and_ext_game.py"
GAME_3_PATH = r"Game 3 - Extension\extension.py"

# Telemetry columns - Updated to match current Arduino output
COLS = ["theta_pot","button_state","tau_ext"]

# Safety threshold for minimum tau_ref (Nm)
MIN_TAU_REF = 0.05  # Minimum torque reference for safety

# CLASS 1: Serial Worker (Background Thread)
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

# CLASS 2: Patient Database in a json file
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
    # adding the patient with all the details
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

# CLASS 3: Main GUI
class RehabGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wrist Rehab – Unified System")
        self.root.geometry("900x700")
        
        self.ser_thread = None
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.raw_queue = queue.Queue()
        self.connected = False
        self.session_file = None
        self.csv_writer = None
        self.session_active = False 
        self.current_game_process = None
        self.current_game_json_path = None  # Store json path for current game
        
        self.current_theta_deg = 0.0
        self.patient_db = PatientDatabase()
        self.current_patient_id = None
        self.current_patient = None
        
        self.cal_step = 0
        self.cal_data = {}
        
        # Store MVC-calculated admittance parameters
        self.last_J = None
        self.last_B = None
        self.last_K = None
        
        self.pages = {}
        self.current_page = None
        
        self._build_pages()
        self._show_page("patient_select")
        self._poll_queues()

    # GUI Building methods unchanged for brevity, they are the same
    def _build_pages(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self._build_patient_page()
        self._build_therapy_page()
        self._build_game_page()
    
    def _build_patient_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["patient_select"] = page
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)
        
        title = ttk.Label(page, text="Patient Management", font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, pady=(0, 20))
        
        content = ttk.Frame(page)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        # selecting existing patient already created
        select_frm = ttk.LabelFrame(content, text="Select Existing Patient", padding=10)
        select_frm.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
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
        info_lbl = ttk.Label(select_frm, textvariable=self.patient_info_var, relief="sunken", padding=10)
        info_lbl.grid(row=2, column=0, sticky="ew", pady=10)
        ttk.Button(select_frm, text="Load Patient", command=self._load_selected_patient).grid(row=3, column=0, pady=5)
        # registering a new patient and adding their details
        register_frm = ttk.LabelFrame(content, text="Register New Patient", padding=10)
        register_frm.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(register_frm, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.new_name_var = tk.StringVar()
        ttk.Entry(register_frm, textvariable=self.new_name_var, width=25).grid(row=0, column=1, pady=5)
        ttk.Label(register_frm, text="Weight (kg):").grid(row=1, column=0, sticky="w", pady=5)
        self.new_weight_var = tk.StringVar(value="70")
        ttk.Entry(register_frm, textvariable=self.new_weight_var, width=25).grid(row=1, column=1, pady=5)
        ttk.Label(register_frm, text="Difficulty (0.1-1.0):").grid(row=2, column=0, sticky="w", pady=5)
        self.new_diff_var = tk.StringVar(value="0.6")
        ttk.Entry(register_frm, textvariable=self.new_diff_var, width=25).grid(row=2, column=1, pady=5)
        ttk.Button(register_frm, text="Register & Continue", command=self._register_new_patient).grid(row=4, column=0, columnspan=2, pady=20)

    def _build_therapy_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["therapy"] = page
        page.rowconfigure(5, weight=1)
        page.columnconfigure(0, weight=1)
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.patient_header_var = tk.StringVar(value="No patient loaded")
        ttk.Label(header, textvariable=self.patient_header_var, font=("Arial", 12, "bold")).pack(side="left")
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side="right")
        # stop therapy button
        self.btn_stop_session = ttk.Button(btn_frame, text="Stop Therapy", command=self._stop_session, state="disabled")
        self.btn_stop_session.pack(side="left", padx=5)
        # proceed to games button
        self.btn_goto_games = ttk.Button(btn_frame, text="Proceed to Games >>", command=self._go_to_game_page, state="disabled")
        self.btn_goto_games.pack(side="left", padx=5)
        # change patient button
        ttk.Button(btn_frame, text="← Change Patient", command=self._go_to_patient_page).pack(side="left")
        con = ttk.LabelFrame(page, text="Connection")
        con.grid(row=1, column=0, sticky="ew", pady=5)
        # serial port connection controls
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
        # therapy parameters
        params = ttk.LabelFrame(page, text="Parameters")
        params.grid(row=2, column=0, sticky="ew", pady=5)
        self.therapy_weight_var = tk.StringVar()
        self.therapy_diff_var = tk.StringVar()
        ttk.Label(params, text="Weight:").grid(row=0, column=0, padx=5)
        ttk.Entry(params, textvariable=self.therapy_weight_var, width=10).grid(row=0, column=1, padx=3)
        ttk.Label(params, text="Diff:").grid(row=0, column=2, padx=5)
        ttk.Entry(params, textvariable=self.therapy_diff_var, width=10).grid(row=0, column=3, padx=3)
        ttk.Button(params, text="Send Mass", command=self.on_set_mass).grid(row=0, column=6, padx=10)
        ttk.Button(params, text="Remove Spring (K=0)", command=self.on_remove_spring).grid(row=0, column=7, padx=10)
        # maximum voluntary contraction (MVC) test controls
        mvc = ttk.LabelFrame(page, text="MVC Test (Start of Session)")
        mvc.grid(row=3, column=0, sticky="ew", pady=5)
        ttk.Label(mvc, text="θ_target:").grid(row=0, column=0, padx=5)
        self.theta_target_var = tk.StringVar(value="60")
        ttk.Entry(mvc, textvariable=self.theta_target_var, width=8).grid(row=0, column=1, padx=3)
        ttk.Label(mvc, text="a_max:").grid(row=0, column=2, padx=5)
        self.amax_var = tk.StringVar(value="100")
        ttk.Entry(mvc, textvariable=self.amax_var, width=8).grid(row=0, column=3, padx=3)
        ttk.Button(mvc, text="Run MVC (5s)", command=self.on_run_mvc).grid(row=0, column=4, padx=10)
        self.mvc_label = ttk.Label(mvc, text="Results: -", foreground="blue")
        self.mvc_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=5, padx=5)
        # telemetry display for seeing the results
        live = ttk.LabelFrame(page, text="Telemetry")
        live.grid(row=4, column=0, sticky="ew", pady=5)
        self.lbl_theta_pot = ttk.Label(live, text="Angle: 0.00°", font=("Arial", 10))
        self.lbl_theta_pot.grid(row=0, column=0, padx=10, pady=5)
        self.lbl_tau = ttk.Label(live, text="tau: 0.00", font=("Arial", 10))
        self.lbl_tau.grid(row=0, column=1, padx=10, pady=5)
        logf = ttk.LabelFrame(page, text="Log")
        logf.grid(row=5, column=0, sticky="nsew", pady=5)
        log_scroll = ttk.Scrollbar(logf)
        log_scroll.pack(side="right", fill="y")
        self.txt = tk.Text(logf, height=8, yscrollcommand=log_scroll.set)
        self.txt.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.txt.yview)
    
    # Calibration page and game selection page
    def _build_game_page(self):
        page = ttk.Frame(self.root, padding=10)
        self.pages["game_launcher"] = page
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)
        top_bar = ttk.Frame(page)
        top_bar.grid(row=0, column=0, sticky="ew", pady=10)
        ttk.Button(top_bar, text="<< Back to Therapy", command=lambda: self._show_page("therapy")).pack(side="left")
        ttk.Label(top_bar, text="Calibration & Games", font=("Arial", 16, "bold")).pack(side="left", padx=20)
        val_frame = ttk.Frame(page, relief="sunken", borderwidth=1)
        val_frame.grid(row=1, column=0, sticky="ew", pady=10)
        # seeing the current angle during calibration
        ttk.Label(val_frame, text="Current Angle:", font=("Arial", 12)).pack(pady=5)
        self.lbl_cal_value = ttk.Label(val_frame, text="0.00°", font=("Arial", 40, "bold"), foreground="#2c3e50")
        self.lbl_cal_value.pack(pady=10)
        self.cal_container = ttk.Frame(page)
        self.cal_container.grid(row=2, column=0, sticky="nsew")
        self.frm_cal_wizard = ttk.LabelFrame(self.cal_container, text="Calibration Wizard", padding=20)
        # starting calibration button
        self.btn_start_cal = ttk.Button(self.frm_cal_wizard, text="START NEW CALIBRATION", command=self.start_calibration)
        self.frm_cal_steps = ttk.Frame(self.frm_cal_wizard)
        self.lbl_cal_instr = tk.Label(self.frm_cal_steps, text="...", font=("Arial", 14), wraplength=400, justify="center")
        self.lbl_cal_instr.pack(pady=20)
        # capture the three values during calibration and saved it
        self.btn_cal_action = ttk.Button(self.frm_cal_steps, text="CAPTURE VALUE", command=self.next_calibration_step)
        self.btn_cal_action.pack(fill="x", padx=40, pady=10, ipady=10)
        ttk.Button(self.frm_cal_steps, text="Cancel", command=self.cancel_calibration).pack(pady=5)
        # Selection of the games after calibration
        self.frm_game_select = ttk.LabelFrame(self.cal_container, text="Select Game", padding=20)
        tk.Label(self.frm_game_select, text="Calibration Complete!", font=("Arial", 14, "bold"), fg="green").pack(pady=(10, 5))
        ttk.Button(self.frm_game_select, text="GAME 1: Flexion", command=lambda: self.launch_game(GAME_1_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_game_select, text="GAME 2: Flex & Ext", command=lambda: self.launch_game(GAME_2_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Button(self.frm_game_select, text="GAME 3: Extension", command=lambda: self.launch_game(GAME_3_PATH)).pack(fill="x", pady=5, ipady=10)
        ttk.Separator(self.frm_game_select, orient="horizontal").pack(fill="x", pady=20)
        ttk.Button(self.frm_game_select, text="Re-Calibrate Device", command=self.reset_to_calibration).pack(pady=5)
        self.reset_to_calibration()

    def _show_page(self, page_name):
        if self.current_page: self.pages[self.current_page].grid_forget()
        self.pages[page_name].grid(row=0, column=0, sticky="nsew")
        self.current_page = page_name
        if page_name == "patient_select": self._refresh_patient_list()
    # navigation between pages
    def _go_to_game_page(self):
        self._show_page("game_launcher")
        self.reset_to_calibration()

    def _go_to_patient_page(self):
        if self.connected:
            if not messagebox.askyesno("Warning", "Disconnect and change patient?"): return
            self.on_connect()
        self._show_page("patient_select")

    def _refresh_patient_list(self):
        self.patient_listbox.delete(0, tk.END)
        patients = self.patient_db.get_all_patients()
        for p_id, data in patients.items():
            self.patient_listbox.insert(tk.END, f"{data['name']} (W:{data['weight']}kg)")
    
    def _on_patient_select(self, event):
        selection = self.patient_listbox.curselection()
        if not selection: return
        idx = selection[0]
        p_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            p = self.patient_db.get_patient(p_ids[idx])
            self.patient_info_var.set(f"Name: {p['name']}\nWeight: {p['weight']} kg\nSessions: {len(p['sessions'])}")
    # loading the selected patient        
    def _load_selected_patient(self):
        selection = self.patient_listbox.curselection()
        if not selection: return
        idx = selection[0]
        p_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(p_ids):
            self.current_patient_id = p_ids[idx]
            self.current_patient = self.patient_db.get_patient(self.current_patient_id)
            self._update_therapy_page_with_patient()
            self._show_page("therapy")

    # new patient registration
    def _register_new_patient(self):
        name = self.new_name_var.get().strip()
        if not name: return
        try:
            w = float(self.new_weight_var.get())
            d = float(self.new_diff_var.get())
        except: return
        self.current_patient_id = self.patient_db.add_patient(name, w, d)
        self.current_patient = self.patient_db.get_patient(self.current_patient_id)
        self._update_therapy_page_with_patient()
        self._show_page("therapy")

    def _update_therapy_page_with_patient(self):
        if not self.current_patient: return
        self.patient_header_var.set(f"Patient: {self.current_patient['name']}")
        self.therapy_weight_var.set(str(self.current_patient['weight']))
        self.therapy_diff_var.set(str(self.current_patient['difficulty']))

    def _populate_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cmb['values'] = ports
        if ports: self.port_cmb.set(ports[0])

    # Connect ports
    def on_connect(self):
        if not self.connected:
            port = self.port_cmb.get()
            if not port: return
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
            self.btn_goto_games.config(state="disabled")
            if self.session_file: self.session_file.close()

    def _send(self, cmd):
        try:
            if self.ser_thread and self.ser_thread.ser and self.ser_thread.ser.is_open:
                self.ser_thread.ser.write((cmd + "\n").encode("utf-8"))
                self._log(f">> {cmd}")
        except: pass

    def _poll_queues(self):
        try:
            while True:
                tag, msg = self.msg_queue.get_nowait()
                self._log(f"{tag}: {msg}")
        except queue.Empty: pass
        try:
            while True:
                line = self.raw_queue.get_nowait()
                self._handle_line(line)
        except queue.Empty: pass
        self.root.after(50, self._poll_queues)

    def _handle_line(self, s):
        if s.startswith("#"):
            self._log(s)
            return
        parts = s.split(',')
        if len(parts) >= 1:
            try:
                raw_angle = float(parts[0])
                self.current_theta_deg = raw_angle
                if hasattr(self, 'lbl_cal_value'):
                    self.lbl_cal_value.config(text=f"{raw_angle:.2f}°")
                if hasattr(self, 'lbl_theta_pot'):
                    self.lbl_theta_pot.config(text=f"Angle: {raw_angle:.2f}°")
                if len(parts) == len(COLS):
                    vals = [float(x) for x in parts]
                    if hasattr(self, 'lbl_tau'):
                        # tau_ext is now at index 2 (theta_pot, button_state, tau_ext)
                        self.lbl_tau.config(text=f"tau: {vals[2]:.3f}")
                    if self.csv_writer:
                        self.csv_writer.writerow([time.time()] + vals)
            except: pass

    def _log(self, msg):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
    
    # setting the mass based on patient weight
    def on_set_mass(self):
        if not self.current_patient: return
        try:
            w = float(self.therapy_weight_var.get())
            mass = 0.006 * w
            self.patient_db.update_patient(self.current_patient_id, weight=w)
            self._send(f"totalmass {mass:.4f}")
            self._log(f"# Mass set: {mass:.4f}")
        except: messagebox.showerror("Error", "Invalid weight")
    # running the MVC test and calculating parameters
    def on_run_mvc(self):
        if not self.current_patient or not self.connected:
            messagebox.showerror("Error", "Connect & Load Patient")
            return
        if self.session_active:
            self._send("adm off")
            time.sleep(0.2)
            self.session_active = False
        self._log("MVC Started...")
        self._send("adm off")
        self._send("w 0")
        self._send("tare")
        time.sleep(0.5)
        self._send("eq hold")
        t_end = time.time() + 5.0
        tau_max = 0.0
        while time.time() < t_end:
            self.root.update()
            try:
                line = self.raw_queue.get(timeout=0.1)
                self._handle_line(line)
                parts = line.split(',')
                if len(parts) == len(COLS):
                    # tau_ext is now at index 2
                    t = float(parts[2])
                    if t > tau_max: tau_max = t
            except: pass
        if tau_max <= 0: tau_max = 1.0
        diff = float(self.therapy_diff_var.get())
        tau_ref = diff * tau_max
        
        # Apply safety threshold
        if tau_ref < MIN_TAU_REF:
            self._log(f"# WARNING: tau_ref {tau_ref:.2f} below minimum. Using {MIN_TAU_REF}")
            tau_ref = MIN_TAU_REF
        
        J = tau_ref / 27.9 
        K = tau_ref / 1.0472
        B = 2 * 1.5 * math.sqrt(J * K)
        
        # Store these values for later use (e.g., removing spring)
        self.last_J = J
        self.last_B = B
        self.last_K = K
        
        self.mvc_label.config(text=f"Max: {tau_max:.2f} | Ref: {tau_ref:.2f}")
        # all the session data saved here, including calibration data and highscores
        master_session = {
            'timestamp': datetime.now().isoformat(),
            'type': 'THERAPY_SESSION',
            'mvc_tau_max': tau_max,
            'mvc_tau_ref': tau_ref,
            'flexion_rom': 0.0,
            'extension_rom': 0.0,
            'session_highscore_flex': 0,
            'session_highscore_all': 0,
            'session_highscore_ext': 0
        }
        self.patient_db.create_new_session(self.current_patient_id, master_session)
        self._log("# Session Created. MVC saved.")
        self._send(f"adm {J:.4f} {B:.4f} {K:.4f}")
        time.sleep(0.1)
        self._send("eq hold")
        time.sleep(0.1)
        self._send("adm on")
        self.session_active = True
        self.btn_stop_session.config(state="normal")
        self.btn_goto_games.config(state="normal")
        messagebox.showinfo("MVC Done", "Therapy Active. Go to Games.")

    def _stop_session(self):
        if not self.connected: return
        self._send("adm off")
        self._send("w 0")
        self.session_active = False
        self.btn_stop_session.config(state="disabled")
        self._log("Session Stopped")
    
    def on_remove_spring(self):
        """Remove spring effect by setting K=0, keeping MVC-calculated J and B values."""
        if not self.connected:
            messagebox.showerror("Error", "Connect to device first")
            return
        if not self.current_patient:
            messagebox.showerror("Error", "Load a patient first")
            return
        
        # Check if MVC has been run
        if self.last_J is None or self.last_B is None:
            messagebox.showerror("Error", "Run MVC test first to calculate J and B values")
            return
        
        try:
            # Use MVC-calculated J and B, set K to 0
            J = self.last_J
            B = self.last_B
            K = 0.0  # Remove spring
            
            self._send(f"adm {J:.4f} {B:.4f} {K:.4f}")
            self._log(f"# Spring removed: K=0, J={J:.4f}, B={B:.4f} (from MVC)")
            messagebox.showinfo("Success", f"Spring effect removed (K=0)\nUsing MVC values: J={J:.4f}, B={B:.4f}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove spring: {e}")

    # CALIBRATION METHODS
    def reset_to_calibration(self):
        self.frm_cal_wizard.pack(fill="both", expand=True, padx=10, pady=10)
        self.frm_game_select.pack_forget()
        self.cancel_calibration()

    def start_calibration(self):
        if not self.connected:
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
    # Capturing the three calibration steps
    def next_calibration_step(self):
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
            self.frm_cal_wizard.pack_forget()
            self.frm_game_select.pack(fill="both", expand=True, padx=10, pady=10)
    # Updating the UI during calibration steps
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
    # Saving calibration data to json and updating patient session
    def save_calibration_json(self):
        try:
            with open(CALIBRATION_FILE, 'w') as f:
                json.dump(self.cal_data, f, indent=4)
            if self.current_patient_id:
                f_rom = self.cal_data.get('flexion', 0.0)
                e_rom = self.cal_data.get('extension', 0.0)
                self.patient_db.update_active_session(self.current_patient_id, {
                    "flexion_rom": round(f_rom, 2),
                    "extension_rom": round(e_rom, 2)
                })
            self._log(f"# Calibration Saved.")
            messagebox.showinfo("Success", "Calibration saved to Session.")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    def launch_game(self, script_path):
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"File not found: {script_path}")
            return

        game_dir = os.path.dirname(script_path)
        game_filename = os.path.basename(script_path)
        
        # Determine score key based on which game file it is, each game has its own json file
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

        # Auto-Disconnect to free up serial port
        if self.connected:
            self.on_connect()
            time.sleep(0.5)

        try:
            p_id = self.current_patient_id if self.current_patient_id else "guest"
            p_name = self.current_patient['name'] if self.current_patient else "Guest"

            # Pass both ID and Name to the game script
            self.current_game_process = subprocess.Popen(
                [sys.executable, game_filename, p_id, p_name],
                cwd=game_dir 
            )
            
            self.btn_goto_games.config(state="disabled")
            self._log(f"Launched {game_title}")
            
            self._monitor_game(game_title, score_key)
        except Exception as e:
            messagebox.showerror("Launch Error", str(e))
            self.on_connect()

    def _monitor_game(self, game_title, score_key):
        if self.current_game_process.poll() is None:
            self.root.after(500, lambda: self._monitor_game(game_title, score_key))
            return
        
        self._log(f"# {game_title} finished.")
        
        final_session_score = 0
        
        # READ from the specific game's JSON file using the patient ID
        if self.current_game_json_path and os.path.exists(self.current_game_json_path):
            try:
                with open(self.current_game_json_path, "r") as f:
                    full_data = json.load(f)
                    
                p_id = self.current_patient_id if self.current_patient_id else "guest"
                
                # Extract score if exists
                if p_id in full_data:
                    final_session_score = full_data[p_id].get("session_highscore", 0)
                    self._log(f"# Retrieved score for {p_id}: {final_session_score}")
                else:
                    self._log(f"# No score data found for {p_id}")

            except Exception as e:
                self._log(f"# Error reading game results: {e}")
        
        # UPDATE Patient Database
        if self.current_patient_id:
            self.patient_db.update_active_session(self.current_patient_id, {
                score_key: final_session_score
            })
            messagebox.showinfo("Game Over", f"Session Updated!\nScore: {final_session_score}")

        self.current_game_process = None
        self.on_connect()
        self.btn_goto_games.config(state="normal")

def main():
    root = tk.Tk()
    app = RehabGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()