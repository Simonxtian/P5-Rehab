import json
import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw 

# --- CONFIG ---
WIDTH, HEIGHT = 800, 600
ROD_Y = 20
ROD_SWEEP_SPEED = 4
ROPE_MAX_LEN = HEIGHT - 60
UPDATE_MS = 25
ARDUINO_BAUD = 460800

OBJECT_TYPES = [
    ("gold", "gold.png", +2),
    ("fish", "fish.png", +1),
    ("trash", "trash.png", -2)
]
NUM_OBJECTS = 2

# --- Global Variables ---
arduino = None
min_angle = 60.0
max_angle = 120.0
raw = None
Previous = None
ButtonPress = 0
last_button_state = 1
PotNumber = 0

# --- Patient Data Defaults ---
PATIENT_ID = "guest"
PATIENT_NAME = "Guest"

# Check command line args
if len(sys.argv) >= 2:
    PATIENT_ID = sys.argv[1]
if len(sys.argv) >= 3:
    PATIENT_NAME = sys.argv[2]

# --- HIGH SCORE FILE ---
HIGHSCORE_FILE = "Highscore_flex.json"
def get_highscore_file_path():
    return os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)

def load_patient_data():
    file_path = get_highscore_file_path()
    full_data = {}

    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                full_data = json.load(f)
        except:
            full_data = {}

    p_data = full_data.get(PATIENT_ID, {
        "name": PATIENT_NAME,
        "highscore": 0,
        "session_highscore": 0
    })
    
    return p_data.get("highscore", 0)

def reset_session_highscore_for_patient():
    file_path = get_highscore_file_path()
    full_data = {}

    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                full_data = json.load(f)
        except:
            full_data = {}

    p_data = full_data.get(PATIENT_ID, {
        "name": PATIENT_NAME,
        "highscore": 0,
        "session_highscore": 0
    })

    p_data["session_highscore"] = 0
    full_data[PATIENT_ID] = p_data

    try:
        tmp = file_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(full_data, f, indent=2)
        os.replace(tmp, file_path)
    except:
        pass

def save_score_data(current_score):
    file_path = get_highscore_file_path()
    full_data = {}

    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                full_data = json.load(f)
        except:
            full_data = {}

    p_data = full_data.get(PATIENT_ID, {
        "name": PATIENT_NAME,
        "highscore": 0,
        "session_highscore": 0
    })

    if current_score > p_data["highscore"]:
        p_data["highscore"] = int(current_score)

    if current_score > p_data["session_highscore"]:
        p_data["session_highscore"] = int(current_score)

    p_data["name"] = PATIENT_NAME
    full_data[PATIENT_ID] = p_data

    try:
        tmp = file_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(full_data, f, indent=2)
        os.replace(tmp, file_path)
    except:
        print("Error saving highscore")

    return p_data["highscore"]

reset_session_highscore_for_patient()
highscore = load_patient_data()

# --- CALIBRATION ---
def load_calibration():
    global val_recta, val_flexion
    try:
        game_dir = os.path.dirname(__file__)
        main_dir = os.path.dirname(game_dir)
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")

        with open(file_path, "r") as f:
            data = json.load(f)

        val_recta = float(data.get("neutral", 450))
        val_flexion = float(data.get("flexion", 120))

        print(f"Calibration Loaded: Neutral={val_recta}, Flexion={val_flexion}")

    except Exception as e:
        print("Error loading calibration:", e)

# --- IMAGE LOADER ---
def load_image(filename, size=None):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        img = Image.open(path).convert("RGBA")
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample)
        return ImageTk.PhotoImage(img)
    except:
        w, h = size if size else (60, 60)
        img = Image.new("RGBA", (w, h), (200, 200, 200, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w-1, h-1), outline=(0,0,0))
        d.text((10, h//2 - 8), "Img?", fill=(0,0,0))
        return ImageTk.PhotoImage(img)

# --- ARDUINO ---
def find_arduino_port():
    if sys.platform.startswith("win"):
        ports = [f"COM{i+1}" for i in range(20)]
    elif sys.platform.startswith("linux"):
        ports = glob.glob("/dev/tty[A-Za-z]*")
    elif sys.platform.startswith("darwin"):
        ports = glob.glob("/dev/cu.usb*")
    else:
        ports = []
    
    for p in ports:
        try:
            s = serial.Serial(p)
            s.close()
            return p
        except:
            continue
    return None

def connect_arduino():
    port = find_arduino_port()
    if not port:
        print("No Arduino detected")
        return None
    try:
        s = serial.Serial(port, ARDUINO_BAUD, timeout=0)
        time.sleep(2)
        s.reset_input_buffer()
        print("Connected:", port)
        return s
    except:
        return None
class FishingGame:
    def __init__(self, root):
        self.root = root
        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        self.bg_img = load_image("sea.png", (WIDTH, HEIGHT))
        self.rod_img = load_image("fishing_rod.png", (90, 90))
        self.obj_imgs = {
            "gold": load_image("gold.png", (60,60)),
            "fish": load_image("fish.png", (60,60)),
            "trash": load_image("trash.png", (60,60)),
        }

        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)
        self.rope_item = self.canvas.create_line(0, 0, 0, 0, width=3, fill="white")
        self.rod_item = self.canvas.create_image(100, ROD_Y, image=self.rod_img, anchor=NW)
        self.canvas.tag_raise(self.rope_item, self.rod_item)

        self.score_text = self.canvas.create_text(80, 24, text="Score: 0", font=("Arial", 16), fill="black")
        
        self.canvas.create_text(WIDTH - 350, 10, text=f"Player: {PATIENT_NAME}",
                                font=("Arial", 12), fill="black", anchor="ne")
        
        self.level_text = self.canvas.create_text(700, 24, text="Level: 1",
                                                  font=("Arial",16), fill="black")

        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET LEVEL", command=self.reset_round)
        self.reset_btn.pack(side="left", padx=10)

        if len(sys.argv) >= 2:
            self.back_btn = Button(root, text="← Back to Launcher", bg="#e74c3c", fg="white",
                                   command=lambda: root.destroy())
            self.back_btn.pack(side="right", padx=10)

        root.bind("<space>", lambda e: self.toggle_sweep())
        root.bind("<w>", self.adjust_rope)
        root.bind("<s>", self.adjust_rope)
        root.bind("<Up>", self.adjust_rope)
        root.bind("<Down>", self.adjust_rope)

        self.rod_x = 100
        self.rod_dir = 1
        self.rope_len = 0
        self.sweeping = True
        self.stopped = False
        self.score = 0 
        self.start_time = time.time()

        global arduino
        self.arduino = arduino 
        
        self.button_pressed = 0
        self.pot_normalized = 0
        self.objects = []
        self.sweep_speed = ROD_SWEEP_SPEED
        self.level = 1
        self.temp_texts = []
        self.game_over = False
        self.waiting_for_retraction = False
        
        # --- NUEVA VARIABLE ---
        self.was_extended = False 
        
        self.spawn_objects()
        self.root.after(UPDATE_MS, self.update)
        if self.arduino:
            self.root.after(100, self.update_from_arduino)

    # ---------- OBJECTS ----------
    def spawn_objects(self):
        for o in self.objects:
            self.canvas.delete(o["id"])
        self.objects.clear()

        for _ in range(NUM_OBJECTS):
            typ, imgname, pts = choice(OBJECT_TYPES)
            img = self.obj_imgs[typ]
            w, h = img.width(), img.height()
            x = randint(40, WIDTH - 100)
            y = randint(300, 550)
            oid = self.canvas.create_image(x, y, image=img, anchor=NW)
            self.objects.append({
                "id": oid, "type": typ,
                "x": x, "y": y, "w": w, "h": h,
                "pts": pts
            })

    def all_good_collected(self):
        return not any(o["type"] in ("gold","fish") for o in self.objects)

    # ---------- MOVEMENT ----------
    def toggle_sweep(self):
        if self.waiting_for_retraction: 
            return

        if self.sweeping:
            self.sweeping = False
            self.stopped = True
            # Evita que se reinicie solo si paramos con el botón
            self.was_extended = False 
        else:
            # Solo resume si la cuerda está arriba
            if self.rope_len <= 5:
                self.sweeping = True
                self.stopped = False

    def reset_round(self):
        self.start_time = time.time()
        self.rope_len = 0
        self.spawn_objects()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
        self.canvas.itemconfig(self.level_text, text=f"Level: {self.level}")

        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()

        self.waiting_for_retraction = False
        self.was_extended = False # Resetear bandera
        self.canvas.itemconfig(self.rope_item, state="normal")

    def adjust_rope(self, event):
        if self.arduino is not None or not self.stopped:
            return
        step = 15
        if event.keysym in ("w", "Up"):
            self.rope_len = max(0, self.rope_len - step)
        elif event.keysym in ("s", "Down"):
            self.rope_len = min(ROPE_MAX_LEN, self.rope_len + step)

        if not self.sweeping:
            self.check_hit()
        self.update_rope()

    # ---------- ROPE ----------
    def rod_tip(self):
        bx, by, _, _ = self.canvas.bbox(self.rod_item)
        w, h = self.rod_img.width(), self.rod_img.height()
        return bx + w - 8, by + h - 86

    def update_rope(self):
        tx, ty = self.rod_tip()
        self.canvas.coords(self.rope_item, tx, ty, tx, ty + self.rope_len)

    def set_rope(self, length):
        self.rope_len = max(0, min(ROPE_MAX_LEN, length))

        # 1. Si la cuerda baja significativamente, marcamos que hubo intento de pesca
        if self.rope_len > 20:
            self.was_extended = True

        # 2. Solo reanudar si la cuerda está arriba (<=5) Y si hubo intento previo (was_extended)
        if self.rope_len <= 5 and not self.sweeping and not self.game_over:
            if self.was_extended:
                self.sweeping = True
                self.stopped = False
                self.was_extended = False # Resetear bandera

    # ---------- COLLISIONS ----------
    def check_hit(self):
        tip_x, tip_y = self.rod_tip()
        end_y = tip_y + self.rope_len
        if self.rope_len < 5:
            return False

        for obj in list(self.objects):
            ox1, oy1 = obj["x"], obj["y"]
            ox2, oy2 = ox1 + obj["w"], oy1 + obj["h"]

            if ox1 <= tip_x <= ox2 and end_y >= oy1:

                # Remove object
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)

                # Score
                self.score += obj["pts"]
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")

                tid = self.canvas.create_text(
                    (ox1+ox2)//2, oy1-20,
                    text=f"{obj['pts']:+}",
                    font=("Arial",14,"bold"), fill="black"
                )
                self.temp_texts.append(tid)

                self.waiting_for_retraction = True
                self.sweeping = False
                self.stopped = True
                self.was_extended = False # Resetear aquí también por seguridad

                if self.all_good_collected():
                    self.game_over = True
                    self.root.after(600, self.show_end_menu)
                return True
        return False

    # ---------- ARDUINO ----------
    def update_from_arduino(self):
        global ButtonPress, PotNumber, last_button_state, val_recta, val_flexion

        if self.arduino:
            try:
                raw = self.arduino.readline()
                s = raw.decode("utf-8", errors="ignore").strip()
                split = s.split(",")

                if len(split) >= 2:
                    PotNumber = float(split[0])
                    Button = int(split[1])
                else:
                    Button = 1

                # Button logic (0 = pressed)
                if Button == 0 and last_button_state != 0:
                    self.toggle_sweep()

                last_button_state = Button

                # Pot normalization
                cal_min = min(val_recta, val_flexion)
                cal_max = max(val_recta, val_flexion)
                angle = PotNumber
                clamped = max(cal_min, min(cal_max, angle))

                if (val_flexion - val_recta) != 0:
                    norm = (clamped - val_recta) / (val_flexion - val_recta)
                else:
                    norm = 0

                norm = max(0, min(1, norm))

                rope = int(norm * ROPE_MAX_LEN)
                
                # Solo actualizar cuerda si estamos parados
                if not self.sweeping:
                    self.set_rope(rope)

            except:
                pass

        self.root.after(25, self.update_from_arduino)

    # ---------- UPDATE LOOP ----------
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over:
            return

        if self.waiting_for_retraction:
            if self.rope_len <= 2:
                self.waiting_for_retraction = False
                # Aquí también forzamos el reinicio si acabamos de pescar algo
                self.sweeping = True
                self.stopped = False
            return

        if self.sweeping:
            self.rod_x += self.rod_dir * self.sweep_speed
            if self.rod_x < 0: 
                self.rod_dir = 1
            if self.rod_x > WIDTH - self.rod_img.width():
                self.rod_dir = -1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            # Forzar cuerda a 0 mientras se mueve horizontalmente
            self.set_rope(0)
        else:
            self.check_hit()

        self.update_rope()

    # ---------- ENDING ----------
    def exit_and_save(self):
        save_score_data(self.score)
        self.root.destroy()

    def show_end_menu(self):
        self.sweeping = False
        self.stopped = True

        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()

        total_time = round(time.time() - self.start_time, 1)
        
        new_high = save_score_data(self.score)

        win = Toplevel(self.root)
        win.title("Level Complete!")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=350)
        c.pack()

        msg = (f" You caught all good items!\n\nYour Score: {self.score}"
               f"\nAll-Time Highscore: {new_high}\nTime: {total_time}s")
        c.create_text(200, 120, text=msg, font=("Comic Sans MS", 18, "bold"),
                      fill="black", justify="center")

        def _play_again():
            win.destroy()
            self.level += 1
            self.sweep_speed = ROD_SWEEP_SPEED + (self.level - 1) * 1.2
            self.reset_round()
            self.rod_x = 100
            self.rod_dir = 1
            self.set_rope(0)
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            self.game_over = False
            self.sweeping = True
            self.stopped = False

        Button(win, text="NEXT LEVEL", bg="green", fg="white",
               font=("Arial", 14, "bold"), command=_play_again).place(x=70, y=250, width=120, height=40)

        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
               command=self.exit_and_save).place(x=210, y=250, width=120, height=40)
        
    # ---------- START MENU ----------
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#a9d8ff", outline="")
    canvas.create_text(WIDTH//2, 150, text="🎣 Fishing Flexion Game 🎣",
                       font=("Comic Sans MS", 36, "bold"), fill="navy")
    
    canvas.create_text(WIDTH//2, 220, text=f"Welcome, {PATIENT_NAME}!",
                       font=("Arial", 20, "bold"), fill="navy")
    
    canvas.create_text(WIDTH//2, 320,
                       text=("Move the rod left and right automatically.\n"
                             "Press the button to stop the rod.\n"
                             "Move your wrist downward to lower the fishing line.\n"
                             "Catch gold and fish, avoid trash.\n"
                             "When you collect all good items, you win!"),
                       font=("Comic Sans MS", 16), fill="black", justify="center")
    
    def check_button_press():
        global last_button_state

        if arduino:
            try:
                raw = arduino.readline()
                s = raw.decode("utf-8", errors="ignore").strip()
                split = s.split(",")

                if len(split) >= 2:
                    Button = int(split[1])
                else:
                    Button = 1

                if Button == 0 and last_button_state != 0:
                    start_game()
                    return

                last_button_state = Button

            except:
                pass

        canvas.after(50, check_button_press)

    def start_game():
        for widget in root.winfo_children():
            widget.destroy()
        FishingGame(root)

    Button(root, text="PLAY", bg="green", fg="white",
           font=("Comic Sans MS", 24, "bold"), command=start_game).place(x=340, y=500)

    canvas.after(50, check_button_press)


# ---------- MAIN ----------
if __name__ == "__main__":
    root = Tk()
    root.title("Fishing Flexion Game")
    arduino = connect_arduino()
    load_calibration()
    start_menu(root)
    root.mainloop()
