import serial
import time
import sys
import glob
from tkinter import Tk, Toplevel, Canvas
import json
import os

# --- Configuración ---
CALIBRATION_FILE = "calibration_data.json"
arduino = None

# --- Tkinter (Ventana invisible de fondo) ---
root = Tk()
root.withdraw()

# --- Conexión Serial ---
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
        print("No se encontró Arduino.")
        return None
    try:
        # Timeout en 1 segundo para asegurar lectura
        arduino = serial.Serial(port, 9600, timeout=0.1) 
        time.sleep(2) 
        arduino.reset_input_buffer()
        print(f"--- CONECTADO EN {port} ---")
        return arduino
    except Exception as e:
        print(f"Error conectando: {e}")
        return None

# --- Lógica de Calibración ---
def calibrate_full_range():
    cal_win = Toplevel(root)
    cal_win.title("Calibración Simple")
    cal_win.geometry("500x300")
    cal_canvas = Canvas(cal_win, width=500, height=300)
    cal_canvas.pack()

    # Elementos de texto
    instr_text = cal_canvas.create_text(250, 50, text="PASO 1: Muñeca RECTA\nPulsa ESPACIO", font=("Arial", 14, "bold"), justify="center", fill="blue")
    val_text = cal_canvas.create_text(250, 130, text="0.00", font=("Arial", 40, "bold"))
    debug_text = cal_canvas.create_text(250, 200, text="Esperando datos...", font=("Arial", 10), fill="gray")

    # Variables
    cal_stage = 1
    cal_values = {"posicion_recta": 0, "posicion_flexion": 0, "posicion_extension": 0}
    current_val = 0.0

    def read_serial():
        """Lee SOLO números del puerto serial."""
        nonlocal current_val
        if not arduino: return

        try:
            while arduino.in_waiting > 0:
                line = arduino.readline()
                if not line: continue
                
                # Decodificar y limpiar espacios
                raw_str = line.decode('utf-8', errors='ignore').strip()

                # Intentar convertir a numero decimal
                try:
                    current_val = float(raw_str)
                except ValueError:
                    # Si llega basura o texto que no es número, ignorar
                    continue
                    
        except Exception:
            pass

    def update_ui():
        read_serial()
        # Actualizar el número grande en pantalla
        cal_canvas.itemconfig(val_text, text=f"{current_val:.2f}")
        cal_win.after(50, update_ui)

    def next_step(event=None):
        nonlocal cal_stage
        
        # Asegurar última lectura
        read_serial()
        
        if cal_stage == 1:
            cal_values["posicion_recta"] = current_val
            print(f"--> GUARDADO RECTA: {current_val}")
            cal_canvas.itemconfig(instr_text, text="PASO 2: FLEXIÓN MÁXIMA (Abajo)\nPulsa ESPACIO", fill="green")
            cal_stage = 2
            
        elif cal_stage == 2:
            cal_values["posicion_flexion"] = current_val
            print(f"--> GUARDADO FLEXIÓN: {current_val}")
            cal_canvas.itemconfig(instr_text, text="PASO 3: EXTENSIÓN MÁXIMA (Arriba)\nPulsa ESPACIO", fill="red")
            cal_stage = 3
            
        elif cal_stage == 3:
            cal_values["posicion_extension"] = current_val
            print(f"--> GUARDADO EXTENSIÓN: {current_val}")
            
            # Guardar archivo
            save_json()
            cal_canvas.itemconfig(instr_text, text="✅ ¡CALIBRACIÓN GUARDADA!", fill="black")
            root.after(1500, root.destroy)

    def save_json():
        try:
            path = os.path.join(os.path.dirname(__file__), CALIBRATION_FILE)
            with open(path, "w") as f:
                json.dump(cal_values, f, indent=4)
            print(f"Archivo guardado en: {path}")
            print(cal_values)
        except Exception as e:
            print(f"Error guardando JSON: {e}")

    # Iniciar
    cal_win.bind("<space>", next_step)
    cal_win.focus_set()
    update_ui()

# --- Main ---
if connect_arduino():
    calibrate_full_range()
    root.mainloop()
else:
    print("No se pudo conectar.")