# Requirements: Python 3.9+, tkinter (built-in), pyserial (pip install pyserial)
# Optional: numpy (for convenience)
# Usage:
#   1) pip install pyserial
#   2) Adjust DEFAULT_PORT if you want, or pick in GUI.
#   3) Run: python gui.py
#   4) Register or select a patient, then run MVC test and therapy sessions.

import threading
import time
import csv
import json
import os
from datetime import datetime
import queue
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math  # <---- added for degree conversion

DEFAULT_BAUD = 115200
DEFAULT_PORT = None  # set like 'COM6' or '/dev/ttyACM0' if you wish
PATIENT_DB_FILE = "patients_db.json"

# Telemetry columns emitted by firmware:
# theta_pot, theta_enc, w_user, w_meas, u_pwm, force_filt, tau_ext, w_adm
COLS = ["theta_pot","theta_enc","w_user","w_measured","u_pwm","force_filt","tau_ext","w_adm"]


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


class PatientDatabase:
    """Manages patient records in JSON file"""
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
            'sessions': [],
            'highscore_flex': 0,
            'highscore_all': 0,
            'highscore_extend': 0
            
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


class RehabGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wrist Rehab – Patient Management & Therapy")
        self.root.geometry("800x600")
        
        # Serial communication
        self.ser_thread = None
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.raw_queue = queue.Queue()
        self.ser = None
        self.connected = False
        self.session_file = None
        self.csv_writer = None
        self.last_params = None
        self.session_active = False  # Track if admittance session is running
        
        # Patient management
        self.patient_db = PatientDatabase()
        self.current_patient_id = None
        self.current_patient = None
        
        # Pages container
        self.pages = {}
        self.current_page = None
        
        self._build_pages()
        self._show_page("patient_select")
        self._poll_queues()

    def _build_pages(self):
        """Build all pages"""
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        # Page 1: Patient Selection/Registration
        self._build_patient_page()
        
        # Page 2: Therapy Session (MVC + Control)
        self._build_therapy_page()
    
    def _build_patient_page(self):
        """Patient selection and registration page"""
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
        
        # Patient listbox
        list_frame = ttk.Frame(select_frm)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        select_frm.rowconfigure(1, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.patient_listbox = tk.Listbox(list_frame, height=10, yscrollcommand=scrollbar.set)
        self.patient_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.patient_listbox.yview)
        
        self.patient_listbox.bind('<<ListboxSelect>>', self._on_patient_select)
        
        # Patient info display
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
        
        # Refresh patient list
        self._refresh_patient_list()
    
    def _build_therapy_page(self):
        """Therapy session page with connection, MVC, and control"""
        page = ttk.Frame(self.root, padding=10)
        self.pages["therapy"] = page
        
        page.rowconfigure(5, weight=1)
        page.columnconfigure(0, weight=1)
        
        # Header with patient info and navigation
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.patient_header_var = tk.StringVar(value="No patient loaded")
        ttk.Label(header, textvariable=self.patient_header_var, 
                 font=("Arial", 12, "bold")).pack(side="left")
        
        # Session control buttons
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side="right")
        self.btn_stop_session = ttk.Button(btn_frame, text="Stop Session", 
                                           command=self._stop_session, state="disabled")
        self.btn_stop_session.pack(side="left", padx=5)
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
        
        # Patient parameters
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
        ttk.Button(params, text="Send Mass to Device", command=self.on_set_mass).grid(row=0, column=6, padx=10)

        # MVC test controls
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

        # Live readouts
        live = ttk.LabelFrame(page, text="Live Telemetry")
        live.grid(row=4, column=0, sticky="ew", pady=5)

        # ---------- ADDED: potentiometer live label ----------
        self.lbl_theta_pot = ttk.Label(live, text="theta_pot: 0.00°", font=("Arial", 10))
        self.lbl_theta_pot.grid(row=0, column=0, padx=10, pady=5)
        # ------------------------------------------------------

        self.lbl_tau = ttk.Label(live, text="tau_ext: 0.000 N·m", font=("Arial", 10))
        self.lbl_tau.grid(row=0, column=1, padx=10, pady=5)
        self.lbl_w = ttk.Label(live, text="w_measured: 0.000 rad/s", font=("Arial", 10))
        self.lbl_w.grid(row=0, column=2, padx=10, pady=5)
        self.lbl_u = ttk.Label(live, text="u_pwm: 0", font=("Arial", 10))
        self.lbl_u.grid(row=0, column=3, padx=10, pady=5)

        # Log box
        logf = ttk.LabelFrame(page, text="System Log")
        logf.grid(row=5, column=0, sticky="nsew", pady=5)
        page.rowconfigure(5, weight=1)
        
        log_scroll = ttk.Scrollbar(logf)
        log_scroll.pack(side="right", fill="y")
        
        self.txt = tk.Text(logf, height=12, yscrollcommand=log_scroll.set)
        self.txt.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.txt.yview)
    
    def _show_page(self, page_name):
        """Show a specific page and hide others"""
        if self.current_page:
            self.pages[self.current_page].grid_forget()
        
        self.pages[page_name].grid(row=0, column=0, sticky="nsew")
        self.current_page = page_name
        
        if page_name == "patient_select":
            self._refresh_patient_list()
    
    def _refresh_patient_list(self):
        """Refresh the patient listbox"""
        self.patient_listbox.delete(0, tk.END)
        patients = self.patient_db.get_all_patients()
        for patient_id, data in patients.items():
            display = f"{data['name']} (W:{data['weight']}kg, D:{data['difficulty']})"
            self.patient_listbox.insert(tk.END, display)
    
    def _on_patient_select(self, event):
        """Handle patient selection in listbox"""
        selection = self.patient_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        patient_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(patient_ids):
            patient_id = patient_ids[idx]
            patient = self.patient_db.get_patient(patient_id)
            info = f"Name: {patient['name']}\n"
            info += f"Weight: {patient['weight']} kg\n"
            info += f"Difficulty: {patient['difficulty']}\n"
            info += f"Sessions: {len(patient['sessions'])}"
            self.patient_info_var.set(info)
    
    def _load_selected_patient(self):
        """Load selected patient and go to therapy page"""
        selection = self.patient_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection", "Please select a patient first")
            return
        
        idx = selection[0]
        patient_ids = list(self.patient_db.get_all_patients().keys())
        if idx < len(patient_ids):
            self.current_patient_id = patient_ids[idx]
            self.current_patient = self.patient_db.get_patient(self.current_patient_id)
            self._update_therapy_page_with_patient()
            self._show_page("therapy")
    
    def _register_new_patient(self):
        """Register new patient and go to therapy page"""
        name = self.new_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter patient name")
            return
        
        try:
            weight = float(self.new_weight_var.get())
            difficulty = float(self.new_diff_var.get())
            
            if weight <= 0 or weight > 300:
                raise ValueError("Weight out of range")
            if not (0.1 <= difficulty <= 1.0):
                raise ValueError("Difficulty must be 0.1-1.0")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
            return
        
        # Add to database
        self.current_patient_id = self.patient_db.add_patient(name, weight, difficulty)
        self.current_patient = self.patient_db.get_patient(self.current_patient_id)
        
        # Clear form
        self.new_name_var.set("")
        self.new_weight_var.set("70")
        self.new_diff_var.set("0.6")
        
        self._update_therapy_page_with_patient()
        self._show_page("therapy")
    
    def _update_therapy_page_with_patient(self):
        """Update therapy page with current patient data"""
        if not self.current_patient:
            return
        
        self.patient_header_var.set(f"Patient: {self.current_patient['name']}")
        self.therapy_weight_var.set(str(self.current_patient['weight']))
        self.therapy_diff_var.set(str(self.current_patient['difficulty']))
        
        # Update mass label
        mass = 0.006 * self.current_patient['weight']
        self.mass_label.config(text=f"{mass:.3f} kg")
    
    def _stop_session(self):
        """Stop current therapy session - disable admittance and prepare for next session"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "No active connection")
            return
        
        if not self.session_active:
            messagebox.showinfo("Info", "No active session to stop")
            return
        
        # Disable admittance and stop motion
        self._send("Patient assistance - off")
        time.sleep(0.1)
        self._send("w 0")
        self._log("# Session stopped - Admittance disabled")
        
        self.session_active = False
        self.btn_stop_session.config(state="disabled")
        self.mvc_label.config(text="Session stopped. Run new MVC test to start again.", foreground="red")
        
        messagebox.showinfo("Session Stopped", 
                          "Therapy session stopped.\nAdmittance is now OFF.\nRun a new MVC test to start another session.")
    
    def _go_to_patient_page(self):
        """Navigate back to patient selection"""
        if self.connected:
            if not messagebox.askyesno("Warning", 
                "You are still connected. Disconnect and change patient?"):
                return
            self.on_connect()  # Disconnect
        
        self._show_page("patient_select")

    def _populate_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cmb['values'] = ports
        if DEFAULT_PORT and DEFAULT_PORT in ports:
            self.port_cmb.set(DEFAULT_PORT)
        elif ports:
            self.port_cmb.set(ports[0])

    def _poll_queues(self):
        # messages
        try:
            while True:
                tag, msg = self.msg_queue.get_nowait()
                self._log(f"{tag}: {msg}")
        except queue.Empty:
            pass
        # raw telemetry lines
        try:
            while True:
                line = self.raw_queue.get_nowait()
                self._handle_line(line)
        except queue.Empty:
            pass
        # mass label update (for registration page)
        try:
            w = float(self.new_weight_var.get())
            m = 0.006 * w
            self.new_mass_label.config(text=f"{m:.3f} kg")
        except:
            pass
        
        # mass label update (for therapy page)
        try:
            w = float(self.therapy_weight_var.get())
            m = 0.006 * w
            self.mass_label.config(text=f"{m:.3f} kg")
        except:
            pass
        self.root.after(50, self._poll_queues)

    def on_connect(self):
        if not self.connected:
            port = self.port_cmb.get()
            try:
                baud = int(self.baud_cmb.get())
            except:
                baud = DEFAULT_BAUD
            if not port:
                messagebox.showerror("Connect", "Select a port")
                return
            self.stop_event.clear()
            self.ser_thread = SerialWorker(port, baud, self.msg_queue, self.raw_queue, self.stop_event)
            self.ser_thread.start()
            self.connected = True
            self.btn_connect.config(text="Disconnect")
            # start a new session log
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_file = open(f"session_{ts}.csv", "w", newline="")
            self.csv_writer = csv.writer(self.session_file)
            self.csv_writer.writerow(["timestamp"] + COLS)
            
            # Ensure admittance is OFF when starting
            time.sleep(0.5)  # Give device time to initialize
            self._send("Patient assistance - off")
            self._send("w 0")
            self._log("# Connection established - Admittance disabled")
        else:
            self.stop_event.set()
            self.connected = False
            self.btn_connect.config(text="Connect")
            self.session_active = False
            if hasattr(self, 'btn_stop_session'):
                self.btn_stop_session.config(state="disabled")
            try:
                if self.session_file: self.session_file.close()
            except:
                pass
            self.session_file = None
            self.csv_writer = None

    def _send(self, cmd):
        # write via the worker's serial handle if available
        try:
            if self.ser_thread and self.ser_thread.ser and self.ser_thread.ser.is_open:
                self.ser_thread.ser.write((cmd + "\n").encode("utf-8"))
                self._log(f">> {cmd}")
        except Exception as e:
            self._log(f"#ERROR write: {e}")

    def _handle_line(self, s):
        # log raw lines; parse CSV telemetry if matches
        if s.startswith("#"):
            self._log(s)
            return
        parts = s.split(',')
        if len(parts) == len(COLS):
            try:
                vals = [float(x) for x in parts]
                rec = dict(zip(COLS, vals))

                # ---------------------- DEGREE CONVERSION ----------------------
                theta_deg = math.degrees(rec["theta_pot"])
                self.lbl_theta_pot.config(text=f"theta_pot: {theta_deg:.2f}°")
                # ----------------------------------------------------------------

                self.lbl_tau.config(text=f"tau_ext: {rec['tau_ext']:.3f} N·m")
                self.lbl_w.config(text=f"w_measured: {rec['w_measured']:.3f} rad/s")
                self.lbl_u.config(text=f"u_pwm: {rec['u_pwm']:.0f}")

                if self.csv_writer:
                    self.csv_writer.writerow([time.time()] + vals)
                return
            except:
                pass
        # not a telemetry row; log it
        self._log(s)

    def _log(self, msg):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    def on_set_mass(self):
        if not self.current_patient:
            messagebox.showerror("Error", "No patient loaded")
            return
        
        try:
            w = float(self.therapy_weight_var.get())
            mass = 0.006 * w
        except:
            messagebox.showerror("Mass","Enter a valid weight")
            return
        
        # Update patient record if weight changed
        if w != self.current_patient['weight']:
            self.patient_db.update_patient(self.current_patient_id, weight=w)
            self.current_patient['weight'] = w
        
        # Note: Mass is now set via the 'totalmass' command
        self._send(f"totalmass {mass:.4f}")
        self._log(f"# Setting total mass to {mass:.4f} kg for gravity compensation")

    def on_run_mvc(self):
        if not self.current_patient:
            messagebox.showerror("Error", "No patient loaded")
            return
        
        if not self.connected:
            messagebox.showerror("Error", "Please connect to device first")
            return
        
        # Stop any active session first
        if self.session_active:
            if not messagebox.askyesno("Active Session", 
                "A session is currently active. Stop it and run new MVC test?"):
                return
            self._send("Patient assistance - off")
            time.sleep(0.2)
        
        # Sequence: adm off; vd 0; tare; eq hold; collect tau_ext max 5 s while asking user to extend
        try:
            diff = float(self.therapy_diff_var.get())
            if not (0.1 <= diff <= 1.0):
                raise ValueError
        except:
            messagebox.showerror("Difficulty","Enter 0.1..1.0")
            return
        
        # Update patient difficulty if changed
        if diff != self.current_patient['difficulty']:
            self.patient_db.update_patient(self.current_patient_id, difficulty=diff)
            self.current_patient['difficulty'] = diff
        try:
            th_deg = float(self.theta_target_var.get())
            amax_d = float(self.amax_var.get())
        except:
            messagebox.showerror("Params","Enter numeric theta_target and a_max")
            return

        # Proper sequence: disable admittance, stop motion, tare force sensor, set equilibrium
        self._log("# Starting MVC test preparation...")
        self._send("Patient assistance - off")
        time.sleep(0.1)
        self._send("w 0")
        time.sleep(0.1)
        self._send("tare")
        time.sleep(0.5)
        self._send("eq hold")
        time.sleep(0.1)

        # collect tau_ext for 5 seconds
        self._log("# MVC: start — apply maximum EXTENSION torque now")
        t_end = time.time() + 5.0
        tau_max = None
        while time.time() < t_end:
            try:
                # Peek latest telemetry value from text labels (not perfect); better: keep last parsed
                line = None
                try:
                    line = self.raw_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                parts = line.split(',')
                if len(parts) == len(COLS):
                    vals = [float(x) for x in parts]
                    rec = dict(zip(COLS, vals))
                    tau = rec['tau_ext']
                    if tau_max is None or tau > tau_max:
                        tau_max = tau
            except Exception as e:
                self._log(f"#WARN parse during MVC: {e}")
        if tau_max is None:
            messagebox.showerror("MVC","No telemetry seen; ensure the device is streaming")
            return

        tau_ref = max(0.0, diff * tau_max)  # difficulty scaling
        # Compute J,B,K per your policy
        theta_target = math.radians(th_deg)
        amax = math.radians(amax_d)
        J = tau_ref / amax if amax > 1e-6 else 0.0
        K = tau_ref / theta_target if theta_target > 1e-6 else 0.0
        zeta = 1.1  # slight overdamp
        B = 2 * zeta * math.sqrt(max(K*J, 0.0))
        wn = math.sqrt(K/J) if J>1e-9 and K>0 else 0.0
        self.last_params = dict(J=J,B=B,K=K,wn=wn,zeta=B/(2*math.sqrt(K*J)) if K>0 and J>0 else 0.0,
                                tau_ref=tau_ref, tau_max=tau_max, diff=diff,
                                theta_target_deg=th_deg, amax_deg_s2=amax_d)
        self.mvc_label.config(text=(f"τ_ref={tau_ref:.3f} N·m | J={J:.5f} kg·m², "
                                    f"B={B:.5f} N·m·s/rad, K={K:.5f} N·m/rad"))

        # Save session data to patient record
        session_data = {
            'timestamp': datetime.now().isoformat(),
            'tau_max': tau_max,
            'tau_ref': tau_ref,
            'J': J, 'B': B, 'K': K,
            'theta_target_deg': th_deg,
            'amax_deg_s2': amax_d,
            'difficulty': diff
        }
        self.patient_db.add_session(self.current_patient_id, session_data)

        # Push parameters to device FIRST, then enable admittance
        self._send(f"adm {J:.6f} {B:.6f} {K:.6f}")
        time.sleep(0.1)
        self._send("eq hold")  # Reset equilibrium after params are set
        time.sleep(0.1)
        self._send("adm on")
        self._log(f"# Set admittance: J={J:.6f}, B={B:.6f}, K={K:.6f} | wn={wn:.2f} rad/s")
        self._log(f"# Session data saved to patient record")
        self._log("# *** THERAPY SESSION ACTIVE - Use 'Stop Session' button when done ***")
        
        # Mark session as active and enable stop button
        self.session_active = True
        self.btn_stop_session.config(state="normal")
        
        messagebox.showinfo("Session Started", 
                          f"MVC test complete!\n\nTherapy session is now ACTIVE.\n"
                          f"Admittance control is ON.\n\n"
                          f"Click 'Stop Session' when therapy is complete.")


def main():
    root = tk.Tk()
    app = RehabGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
