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
ARDUINO_BAUD = 115200

# FIXED: Removed folder paths, just use filenames
OBJECT_TYPES = [
    ("gold", "gold.png", +2),
    ("fish", "fish.png", +1),
    ("trash", "trash.png", -2)
]
NUM_OBJECTS = 2

# --- Variables Globales ---
arduino = None
min_angle = 60.0
max_angle = 120.0
raw = None
Previous = None


# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_flex.json"

def load_highscore():
    try:
        file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                json.dump({"highscore": 0}, f)
            return 0

        with open(file_path, "r+") as f:
            data = json.load(f)
            return int(data.get("highscore", 0))
    except Exception as e:
        print("Error loading highscore:", e)
        return 0

def load_session_highscore():
    try:
        file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                json.dump({"session_highscore": 0}, f)
            return 0

        with open(file_path, "r+") as f:
            data = json.load(f)
            return int(data.get("session_highscore", 0))
    except Exception as e:
        print("Error loading session highscore:", e)
        return 0

def save_highscore(score):
    global highscore, current_session_highscore
    file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

    if score >= highscore:
        data["highscore"] = int(score)
    if score >= current_session_highscore:
        data["session_highscore"] = int(score)

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp_path, file_path)
    except Exception as e:
        print("Error saving highscore:", e)

def reset_session_highscore():
    file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["session_highscore"] = 0
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp_path, file_path)
    except Exception as e:
        print("Error resetting session highscore:", e)

reset_session_highscore()
highscore = load_highscore()
current_session_highscore = load_session_highscore()

# --- CALIBRATION LOADING ---
def load_calibration():
    global val_recta, val_flexion
    val_recta = 0
    val_flexion = 1023
    try:
        game_dir = os.path.dirname(__file__)
        main_dir = os.path.dirname(game_dir)
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")
        print(f"Searching for calibration at: {file_path}") 
        with open(file_path, "r") as f:
            data = json.load(f)
            val_recta = data.get("neutral", 450)
            val_flexion = data.get("flexion", 120)
            print(f"Calibration Loaded: Neutral={val_recta}, Flexion={val_flexion}")
    except FileNotFoundError:
        print(f"ERROR: File not found at: {file_path}")
    except Exception as e:
        print(f"Error loading calibration: {e}")
        
# --- IMAGE LOADER ---
def load_image(filename, size=None):
    # FIXED: Construct path relative to this script file
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        w, h = size if size else (60, 60)
        img = Image.new("RGBA", (w, h), (200, 200, 200, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w - 1, h - 1), outline=(0, 0, 0))
        d.text((10, h // 2 - 8), "Img?", fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

# --- SERIAL UTILS ---
def find_arduino_port():
    if sys.platform.startswith('win'):
        ports = [f'COM{i+1}' for i in range(20)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.usb*')
    else:
        ports = []
    for p in ports:
        try:
            s = serial.Serial(p); s.close()
            return p
        except Exception:
            continue
    return None

def connect_arduino():
    port = find_arduino_port()
    if not port:
        print("No Arduino found (keyboard only).")
        return None
    try:
        s = serial.Serial(port, ARDUINO_BAUD, timeout=0) 
        time.sleep(2) 
        s.reset_input_buffer()
        print("Connected to Arduino:", port)
        return s
    except Exception as e:
        print("Serial error:", e)
        return None

# --- GAME CLASS ---
class FishingGame:
    def __init__(self, root):
        self.last_button_state = 0
        self.root = root
        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()
        
        # FIXED: Use just filenames
        self.bg_img = load_image("sea.png", (WIDTH, HEIGHT))
        self.rod_img = load_image("fishing_rod.png", (90, 90))
        self.obj_imgs = {
            "gold": load_image("gold.png", (60,60)),
            "fish": load_image("fish.png", (60,60)),
            "trash": load_image("trash.png", (60,60)),
        }

        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)
        self.rope_item = self.canvas.create_line(0,0,0,0, width=3, fill="white")
        self.rod_item = self.canvas.create_image(100, ROD_Y, image=self.rod_img, anchor=NW)
        self.canvas.tag_raise(self.rope_item, self.rod_item)

        self.score_text = self.canvas.create_text(80, 24, text="Score: 0", font=("Arial", 16), fill="black")
        self.level_text = self.canvas.create_text(700, 24, text=f"Level: 1", font=("Arial",16), fill="black")

        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET LEVEL", command=self.reset_round)
        self.reset_btn.pack(side="left", padx=10)
        
        if len(sys.argv) >= 3:
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
        
        self.spawn_objects()
        self.root.after(UPDATE_MS, self.update)
        if self.arduino:
            self.root.after(100, self.update_from_arduino)

    def spawn_objects(self):
        for obj in self.objects:
            self.canvas.delete(obj["id"])
        self.objects.clear()
        for _ in range(NUM_OBJECTS):
            typ, imgname, pts = choice(OBJECT_TYPES)
            img = self.obj_imgs[typ]
            w, h = img.width(), img.height()
            x = randint(40, WIDTH - 100)
            y = randint(300, 550)
            oid = self.canvas.create_image(x, y, image=img, anchor=NW)
            self.objects.append(dict(id=oid, type=typ, x=x, y=y, w=w, h=h, pts=pts))

    def all_good_collected(self):
        return not any(o["type"] in ("gold","fish") for o in self.objects)

    def toggle_sweep(self):
        if self.waiting_for_retraction: return
        if self.sweeping:
            self.sweeping = False
            self.stopped = True
        else:
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
            self.canvas.itemconfig(self.rope_item, state="normal")

    def adjust_rope(self, event):
        if self.arduino is not None or not self.stopped: return  
        step = 15
        if event.keysym in ('w', 'Up'):
            self.rope_len = max(0, self.rope_len - step)
        elif event.keysym in ('s', 'Down'):
            self.rope_len = min(ROPE_MAX_LEN, self.rope_len + step)
        
        if not self.sweeping: self.check_hit()
        self.update_rope()

    def rod_tip(self):
        bx, by, _, _ = self.canvas.bbox(self.rod_item)
        w, h = self.rod_img.width(), self.rod_img.height()
        return bx + w - 8, by + h - 86

    def update_rope(self):
        tx, ty = self.rod_tip()
        self.canvas.coords(self.rope_item, tx, ty, tx, ty + self.rope_len)

    def check_hit(self):
        tip_x, tip_y = self.rod_tip()
        end_y = tip_y + self.rope_len
        if self.rope_len < 5: return False

        for obj in list(self.objects):
            ox1, oy1, ox2, oy2 = obj["x"], obj["y"], obj["x"] + obj["w"], obj["y"] + obj["h"]
            if ox1 <= tip_x <= ox2 and end_y >= oy1:
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
                self.score += obj["pts"]
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
                text_id = self.canvas.create_text((ox1 + ox2) // 2, oy1 - 20,
                    text=f"{obj['pts']:+}", font=("Arial", 14, "bold"), fill="black")
                self.temp_texts.append(text_id)
                self.canvas.itemconfig(self.rope_item, state="hidden")
                
                if self.all_good_collected():
                    self.sweeping = False
                    self.stopped = True
                    self.game_over = True
                    self.root.after(500, self.show_end_menu)
                else:
                    self.sweeping = False
                    self.stopped = True
                    self.root.after(500, self.finish_catch_and_resume)
                return True
        return False
    
    def set_rope(self, length):
        self.rope_len = max(0, min(ROPE_MAX_LEN, length))

    def finish_catch_and_resume(self):
        self.canvas.itemconfig(self.rope_item, state="normal")
        self.waiting_for_retraction = True
    
    def update_from_arduino(self):
        global angle, val_recta, val_flexion
        if self.arduino:
            try:
                latest_line = None
                while True:
                    line = self.arduino.readline().decode('utf-8', errors='ignore').strip()
                    if not line: break
                    latest_line = line

                if latest_line:
                    print("Received:", latest_line)
                    parts = latest_line.split(" ")
                    if len(parts) >= 4:
                        ButtonNumber = int(float(parts[1]))
                        PotNumber = float(parts[3])
                        if ButtonNumber == 2001 and self.last_button_state != 2001:
                            self.toggle_sweep()
                        self.last_button_state = ButtonNumber
                        angle = PotNumber
                        cal_range = val_flexion - val_recta
                        if cal_range != 0:
                            clamped = max(min(angle, max(val_recta, val_flexion)), min(val_recta, val_flexion))
                            self.pot_normalized = (clamped - val_recta) / cal_range
                        else:
                            self.pot_normalized = 0
                        if not self.sweeping:
                            self.set_rope(int(self.pot_normalized * ROPE_MAX_LEN))
            except Exception as e:
                print("Arduino read error:", e)
        self.root.after(25, self.update_from_arduino)

    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return
        if self.waiting_for_retraction:
            if self.rope_len < 10: self.waiting_for_retraction = False
            return
        elif self.sweeping:
            self.rod_x += self.rod_dir * self.sweep_speed
            if self.rod_x < 0: self.rod_dir = 1
            if self.rod_x > WIDTH - self.rod_img.width(): self.rod_dir = -1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            self.set_rope(0)
        else:
            if self.check_hit(): pass 
        self.update_rope()

    def exit_and_save(self):
        save_highscore(self.score)
        self.root.destroy()

    def show_end_menu(self):
        self.sweeping = False
        self.stopped = True
        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()
        
        total_time = round(time.time() - self.start_time, 1)
        global highscore  
        display_highscore = max(self.score, highscore)
        
        win = Toplevel(self.root)
        win.title("Level Complete!")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=350)
        c.pack()
        
        msg = f" You caught all good items!\n\nYour Score: {self.score}\nAll-Time Highscore: {display_highscore}\nTime: {total_time}s"
        c.create_text(200, 120, text=msg, font=("Comic Sans MS", 18, "bold"), fill="black", justify="center")

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
        
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#a9d8ff", outline="")
    canvas.create_text(WIDTH//2, 150, text="🎣 Fishing Flexion Game 🎣",
                        font=("Comic Sans MS", 36, "bold"), fill="navy")
    canvas.create_text(WIDTH//2, 300,
                        text=("Move the rod left and right automatically.\n"
                              "Press the button to stop the rod.\n"
                              "Move your wrist downward (flexion) to lower the fishing line.\n"
                              "Catch fish and gold, avoid trash.\n"
                              "When you catch all the good items, you win!"),
                        font=("Comic Sans MS", 16), fill="black", justify="center")

    def start_game():
        for widget in root.winfo_children():
            widget.destroy()
        FishingGame(root)

    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=start_game).place(x=340, y=500)

if __name__ == "__main__":
    root = Tk()
    root.title("Fishing Flexion Game")
    arduino = connect_arduino()
    load_calibration()
    start_menu(root)
    root.mainloop()