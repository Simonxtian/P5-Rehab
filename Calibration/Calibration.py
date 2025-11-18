import serial
import time
import sys
import glob
from tkinter import Tk, Toplevel, Canvas
import json
import os

# --- Configuration ---
CALIBRATION_FILE = "calibration_data.json"
arduino = None

# --- Tkinter (Hidden root window) ---
root = Tk()
root.withdraw()

# --- Serial Connection ---
def find_arduino_port():
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

def connect_arduino():
    global arduino
    port = find_arduino_port()
    if not port:
        print("Arduino not found.")
        return None
    try:
        # Timeout set to 0.1s to ensure non-blocking read
        arduino = serial.Serial(port, 9600, timeout=0.1) 
        time.sleep(2) 
        arduino.reset_input_buffer()
        print(f"--- CONNECTED ON {port} ---")
        return arduino
    except Exception as e:
        print(f"Error connecting: {e}")
        return None

# --- Calibration Logic ---
def calibrate_full_range():
    cal_win = Toplevel(root)
    cal_win.title("Simple Calibration")
    cal_win.geometry("500x300")
    cal_canvas = Canvas(cal_win, width=500, height=300)
    cal_canvas.pack()

    # Text Elements
    instr_text = cal_canvas.create_text(250, 50, text="STEP 1: Wrist STRAIGHT\nPress SPACE", font=("Arial", 14, "bold"), justify="center", fill="blue")
    val_text = cal_canvas.create_text(250, 130, text="0.00", font=("Arial", 40, "bold"))
    debug_text = cal_canvas.create_text(250, 200, text="Waiting for data...", font=("Arial", 10), fill="gray")

    # Variables
    cal_stage = 1
    # We keep the keys in Spanish to maintain compatibility with the Game code
    cal_values = {"posicion_recta": 0, "posicion_flexion": 0, "posicion_extension": 0}
    current_val = 0.0

    def read_serial():
        """Reads ONLY numbers from the serial port."""
        nonlocal current_val
        if not arduino: return

        try:
            while arduino.in_waiting > 0:
                line = arduino.readline()
                if not line: continue
                
                # Decode and clean whitespace
                raw_str = line.decode('utf-8', errors='ignore').strip()

                # Attempt to convert to decimal number
                try:
                    current_val = float(raw_str)
                except ValueError:
                    # If garbage or non-numeric text arrives, ignore it
                    continue
                    
        except Exception:
            pass

    def update_ui():
        read_serial()
        # Update the large number on screen
        cal_canvas.itemconfig(val_text, text=f"{current_val:.2f}")
        cal_win.after(50, update_ui)

    def next_step(event=None):
        nonlocal cal_stage
        
        # Ensure one last read
        read_serial()
        
        if cal_stage == 1:
            cal_values["posicion_recta"] = current_val
            print(f"--> SAVED STRAIGHT: {current_val}")
            cal_canvas.itemconfig(instr_text, text="STEP 2: MAX FLEXION (Down)\nPress SPACE", fill="green")
            cal_stage = 2
            
        elif cal_stage == 2:
            cal_values["posicion_flexion"] = current_val
            print(f"--> SAVED FLEXION: {current_val}")
            cal_canvas.itemconfig(instr_text, text="STEP 3: MAX EXTENSION (Up)\nPress SPACE", fill="red")
            cal_stage = 3
            
        elif cal_stage == 3:
            cal_values["posicion_extension"] = current_val
            print(f"--> SAVED EXTENSION: {current_val}")
            
            # Save file
            save_json()
            cal_canvas.itemconfig(instr_text, text="✅ CALIBRATION SAVED!", fill="black")
            root.after(1500, root.destroy)

    def save_json():
        try:
            path = os.path.join(os.path.dirname(__file__), CALIBRATION_FILE)
            with open(path, "w") as f:
                json.dump(cal_values, f, indent=4)
            print(f"File saved at: {path}")
            print(cal_values)
        except Exception as e:
            print(f"Error saving JSON: {e}")

    # Start
    cal_win.bind("<space>", next_step)
    cal_win.focus_set()
    update_ui()

# --- Main ---
if connect_arduino():
    calibrate_full_range()
    root.mainloop()
else:
    print("Could not connect.")