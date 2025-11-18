# Requirements: Python 3.9+, tkinter (built-in), pyserial (pip install pyserial)
# Optional: numpy (for convenience)
# Usage:
#   1) pip install pyserial
#   2) Adjust DEFAULT_PORT if you want, or pick in GUI.
#   3) Run: python rehab_gui.py
#   4) Connect, enter user weight (kg) and difficulty (0.1..1), click "Set Mass" then "Run MVC Test".
#   5) The app will compute J,B,K and push them to the Arduino via "adm J B K", then enable admittance.

import threading
import time
import csv
from datetime import datetime
import queue
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

DEFAULT_BAUD = 115200
DEFAULT_PORT = None  # set like 'COM6' or '/dev/ttyACM0' if you wish

# Telemetry columns emitted by firmware:
# theta_pot, theta_enc, w_user, w_meas, u_pwm, force_filt, tau_ext, w_adm
COLS = ["theta_pot","theta_enc","w_user","w_meas","u_pwm","force_filt","tau_ext","w_adm"]

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

class RehabGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wrist Rehab – Session Console")
        self.ser_thread = None
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.raw_queue = queue.Queue()
        self.ser = None
        self.connected = False
        self.session_file = None
        self.csv_writer = None
        self.last_params = None

        self._build_widgets()
        self._populate_ports()
        self._poll_queues()

    def _build_widgets(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Connection
        con = ttk.LabelFrame(frm, text="Connection")
        con.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(con, text="Port:").grid(row=0, column=0)
        self.port_cmb = ttk.Combobox(con, width=20, state="readonly")
        self.port_cmb.grid(row=0, column=1, padx=3)
        ttk.Label(con, text="Baud:").grid(row=0, column=2)
        self.baud_cmb = ttk.Combobox(con, width=8, values=(115200, 57600, 230400))
        self.baud_cmb.set(str(DEFAULT_BAUD))
        self.baud_cmb.grid(row=0, column=3, padx=3)
        ttk.Button(con, text="Refresh", command=self._populate_ports).grid(row=0, column=4, padx=3)
        self.btn_connect = ttk.Button(con, text="Connect", command=self.on_connect)
        self.btn_connect.grid(row=0, column=5, padx=3)

        # Patient / session
        sess = ttk.LabelFrame(frm, text="Patient & Session")
        sess.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(sess, text="Weight (kg):").grid(row=0, column=0)
        self.weight_var = tk.StringVar(value="70")
        ttk.Entry(sess, textvariable=self.weight_var, width=8).grid(row=0, column=1)
        ttk.Label(sess, text="Wrist mass = 0.006 * weight").grid(row=0, column=2, padx=6)
        self.mass_label = ttk.Label(sess, text="→ 0.420 kg")
        self.mass_label.grid(row=0, column=3)

        ttk.Label(sess, text="Difficulty (0.1..1.0):").grid(row=1, column=0)
        self.diff_var = tk.StringVar(value="0.6")
        ttk.Entry(sess, textvariable=self.diff_var, width=8).grid(row=1, column=1)
        ttk.Button(sess, text="Set Mass on Device", command=self.on_set_mass).grid(row=0, column=4, padx=6)

        # MVC test controls
        mvc = ttk.LabelFrame(frm, text="MVC Test (extension)")
        mvc.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(mvc, text="θ_target (deg):").grid(row=0, column=0)
        self.theta_target_var = tk.StringVar(value="60")
        ttk.Entry(mvc, textvariable=self.theta_target_var, width=8).grid(row=0, column=1)
        ttk.Label(mvc, text="a_max (deg/s²):").grid(row=0, column=2)
        self.amax_var = tk.StringVar(value="100")
        ttk.Entry(mvc, textvariable=self.amax_var, width=8).grid(row=0, column=3)
        ttk.Button(mvc, text="Run MVC Test (5 s)", command=self.on_run_mvc).grid(row=0, column=4, padx=6)
        self.mvc_label = ttk.Label(mvc, text="τ_ref: -, J: -, B: -, K: -")
        self.mvc_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=4)

        # Live readouts
        live = ttk.LabelFrame(frm, text="Live")
        live.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        self.lbl_tau = ttk.Label(live, text="tau_ext: 0.000 N·m")
        self.lbl_tau.grid(row=0, column=0, padx=6)
        self.lbl_w = ttk.Label(live, text="w_meas: 0.000 rad/s")
        self.lbl_w.grid(row=0, column=1, padx=6)
        self.lbl_u = ttk.Label(live, text="u_pwm: 0")
        self.lbl_u.grid(row=0, column=2, padx=6)

        # Log box
        logf = ttk.LabelFrame(frm, text="Log")
        logf.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
        frm.rowconfigure(4, weight=1)
        self.txt = tk.Text(logf, height=12)
        self.txt.grid(row=0, column=0, sticky="nsew")
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)

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
        # mass label update
        try:
            w = float(self.weight_var.get())
            m = 0.006 * w
            self.mass_label.config(text=f"→ {m:.3f} kg")
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
        else:
            self.stop_event.set()
            self.connected = False
            self.btn_connect.config(text="Connect")
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
                self.lbl_tau.config(text=f"tau_ext: {rec['tau_ext']:.3f} N·m")
                self.lbl_w.config(text=f"w_meas: {rec['w_meas']:.3f} rad/s")
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
        try:
            w = float(self.weight_var.get())
            mass = 0.006 * w
        except:
            messagebox.showerror("Mass","Enter a valid weight")
            return
        # Note: Mass is now set via the 'totalmass' command
        self._send(f"totalmass {mass:.4f}")
        self._log(f"# Setting total mass to {mass:.4f} kg for gravity compensation")

    def on_run_mvc(self):
        # Sequence: adm off; vd 0; tare; eq hold; collect tau_ext max 5 s while asking user to extend
        try:
            diff = float(self.diff_var.get())
            if not (0.1 <= diff <= 1.0):
                raise ValueError
        except:
            messagebox.showerror("Difficulty","Enter 0.1..1.0")
            return
        try:
            th_deg = float(self.theta_target_var.get())
            amax_d = float(self.amax_var.get())
        except:
            messagebox.showerror("Params","Enter numeric theta_target and a_max")
            return

        # Proper sequence: disable admittance, stop motion, tare force sensor, set equilibrium
        self._send("adm off")
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
        import math
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

        # Push parameters to device FIRST, then enable admittance
        self._send(f"adm {J:.6f} {B:.6f} {K:.6f}")
        time.sleep(0.1)
        self._send("eq hold")  # Reset equilibrium after params are set
        time.sleep(0.1)
        self._send("adm on")
        self._log(f"# Set admittance: J={J:.6f}, B={B:.6f}, K={K:.6f} | wn={wn:.2f} rad/s")


def main():
    root = tk.Tk()
    app = RehabGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
