import serial
import time
import sys
import glob
from tkinter import Tk, Toplevel, Canvas
import json
import os

CALIBRATION_FILE = "calibration_data.json"
arduino = None

root = Tk()
root.withdraw() 

# --- Funciones de Arduino  ---
def find_arduino_port():
    """Detecta automáticamente el puerto serial del Arduino."""
    if sys.platform.startswith('win'):
        ports = [f'COM{i + 1}' for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.usb*')
    else:
        raise EnvironmentError('Unsupported platform')

    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            return port
        except (OSError, serial.SerialException):
            pass
    return None

def connect_arduino():
    """Intenta conectarse al Arduino."""
    global arduino
    port = find_arduino_port()
    if not port:
        print("No se encontró Arduino.")
        return None
    try:
        arduino = serial.Serial(port, 9600, timeout=0)
        time.sleep(2) # Esperar al reseteo de la placa
        try:
            arduino.reset_input_buffer()
        except AttributeError:
            arduino.flushInput()
        print(f"Conectado al Arduino en {port}")
        return arduino
    except Exception as e:
        print(f"No se pudo abrir el puerto serial: {e}")
        arduino = None
        return None


def save_calibration(min_v, max_v):
    """Guarda los valores min/max en el archivo JSON."""
    global min_val, max_val
    min_val, max_val = min_v, max_v # Actualiza globales por si acaso
    data = {"min": min_v, "max": max_v}
    try:
        # Guarda el JSON en el mismo directorio que el script
        file_path = os.path.join(os.path.dirname(__file__), CALIBRATION_FILE)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Calibración guardada: {data}")
    except Exception as e:
        print(f"Error al guardar la calibración: {e}")

def calibrate_potentiometer():
    """Muestra la ventana de calibración, lee valores y guarda al final."""
    
    # Valores locales para esta calibración
    cal_min, cal_max = 9999, -9999 

    cal_win = Toplevel(root)
    cal_win.title("Calibración de Sensor")
    cal_win.geometry("400x250")
    cal_win.resizable(False, False)
    cal_canvas = Canvas(cal_win, width=400, height=250)
    cal_canvas.pack()

    msg = cal_canvas.create_text(
        200, 50,
        text="Mueve el sensor a sus posiciones MÍNIMA y MÁXIMA.\nPulsa ESPACIO cuando termines.",
        font=("Arial", 12),
        fill="black",
        width=380,
        justify="center"
    )
    raw_text = cal_canvas.create_text(
        200, 110,
        text="Valor Raw: --",
        font=("Arial", 24, "bold"),
        fill="blue"
    )
    range_text = cal_canvas.create_text(
        200, 170,
        text="Rango detectado: [----, ----]",
        font=("Arial", 14),
        fill="gray"
    )
    
    status_text = cal_canvas.create_text(
        200, 210,
        text="Esperando datos del Arduino...",
        font=("Arial", 10, "italic"),
        fill="red"
    )

    if arduino:
        try:
            arduino.reset_input_buffer()
        except Exception:
            arduino.flushInput()
        time.sleep(0.5)
        cal_canvas.itemconfig(status_text, text="Leyendo datos...", fill="green")
    else:
        cal_canvas.itemconfig(status_text, text="Error: Arduino no conectado.", fill="red")
        return # No se puede calibrar sin Arduino

    cal_done = {"done": False}

    def finish_calibration(event=None):
        cal_done["done"] = True

    cal_win.bind("<space>", finish_calibration)
    cal_win.focus_set() # Asegurar que la ventana reciba el input

    def update_calibration():
        nonlocal cal_min, cal_max # Usar las variables locales
        latest_raw = None

        if arduino:
            try:
                # --- ¡AQUÍ ESTÁ LA LÓGICA DE LECTURA! ---
                while arduino.in_waiting > 0:
                    line = arduino.readline()
                    if not line:
                        continue
                    s = line.decode('utf-8', errors='ignore').strip()
                    if not s:
                        continue
                    
                    # Asumimos formato "Button: XXXX Pot: YYYY"
                    split = s.split(" ")
                    if len(split) >= 4 and split[2] == "Pot:":
                        try:
                            latest_raw = float(split[3])
                        except ValueError:
                            continue # Ignorar datos corruptos
            except Exception:
                pass 

        if latest_raw is not None:
            # Actualizar display en vivo
            cal_canvas.itemconfig(raw_text, text=f"Valor Raw: {latest_raw:.0f}")
            
            # Actualizar min/max dinámicamente
            if latest_raw < cal_min:
                cal_min = latest_raw
            if latest_raw > cal_max:
                cal_max = latest_raw
            
            cal_canvas.itemconfig(range_text, text=f"Rango detectado: [{cal_min:.0f}, {cal_max:.0f}]")

        if cal_done["done"]:
            total_range = cal_max - cal_min

            # Asegurar un rango mínimo
            if total_range < 50: # (ej. 50 unidades de 1023)
                print("⚠️ Rango de calibración muy pequeño. Usando 0–1023.")
                cal_min, cal_max = 0, 1023
            
            # 1. Guardar en el archivo JSON
            save_calibration(cal_min, cal_max)
            
            cal_canvas.itemconfig(msg, text=f"✅ ¡Hecho!\nValores guardados: {cal_min:.0f} - {cal_max:.0f}")
            cal_canvas.itemconfig(raw_text, text="")
            cal_canvas.itemconfig(range_text, text="")
            cal_canvas.itemconfig(status_text, text=f"Guardado en {CALIBRATION_FILE}", fill="blue")
            
            root.after(2000, root.destroy) # Cerrar todo después de 2 seg
            return # Detener el bucle

        cal_win.after(20, update_calibration) # Comprobar de nuevo en 20ms

    update_calibration() # Iniciar el bucle

# --- Ejecución Principal ---
connect_arduino()
if arduino:
    calibrate_potentiometer()
else:
    print("No se pudo conectar al Arduino. Saliendo.")
    root.destroy()

root.mainloop()