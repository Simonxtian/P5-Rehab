import json
import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw # Moved ImageDraw here for consistency

# --- CONFIG ---
WIDTH, HEIGHT = 800, 600
ROD_Y = 20
ROD_SWEEP_SPEED = 4
ROPE_MAX_LEN = HEIGHT - 60
UPDATE_MS = 25
ARDUINO_BAUD = 9600

OBJECT_TYPES = [
    ("gold", "gold.png", +3),
    ("fish", "fish.png", +2),
    ("trash", "trash.png", -3)
]
NUM_OBJECTS = 5

# --- Variables Globales ---
# Se conectará al inicio
arduino = None

# Accept ROM calibration from command line
if len(sys.argv) >= 3:
    min_angle = float(sys.argv[1])
    max_angle = float(sys.argv[2])
    print(f"ROM Calibration loaded: {min_angle}° to {max_angle}°")
else:
    # Default values if not provided
    min_angle = 60.0
    max_angle = 120.0

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_flex.json"

def load_highscore():
    print("Saving to:", os.path.join(os.path.dirname(__file__), "highscore_flex.json"))
    """Load highscore from a JSON file located next to this script; create if missing."""
    try:
        file_path = os.path.join(os.path.dirname(__file__), "highscore_flex.json")
        # If file doesn't exist, create it with default highscore 0
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                json.dump({"highscore": 0}, f)
            return 0

        with open(file_path, "r+") as f:
            data = json.load(f)
            return int(data.get("highscore", 0))
    except Exception as e:
        # Log and return 0 on any error to keep game running
        print("Error loading highscore:", e)
        return 0
    


def save_highscore(score):
    global highscore # Ensure we are comparing against the loaded highscore
    if score > highscore: # Only save if it's a new highscore
        """Save highscore to a JSON file located next to this script using an atomic replace."""
        try:
            file_path = os.path.join(os.path.dirname(__file__), "highscore_flex.json")
            # Ensure directory exists (usually it's the script dir, but be safe)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            tmp_path = file_path + ".tmp"
            # Write to a temp file and atomically replace the target to avoid partial writes
            with open(tmp_path, "w") as f:
                json.dump({"highscore": int(score)}, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    # os.fsync may not be available on some platforms or file descriptors
                    pass
            os.replace(tmp_path, file_path)
            highscore = score # Update the global variable
            print(f"New highscore ({score}) saved!")
        except Exception as e:
            print("Error saving highscore:", e)
    else:
        # No update needed
        pass


# Load the highscore once at the start
highscore = load_highscore()


# --- IMAGE LOADER ---
def load_image(path, size=None):
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception:
        w, h = size if size else (60, 60)
        img = Image.new("RGBA", (w, h), (200, 200, 200, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w - 1, h - 1), outline=(0, 0, 0))
        d.text((10, h // 2 - 8), "missing", fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

# --- SERIAL UTILS ---
def find_arduino_port():
    if sys.platform.startswith('win'):
        ports = [f'COM{i+1}' for i in range(20)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
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


def calibrate_potentiometer():
    """Calibrate wrist extension range."""
    global min_angle, max_angle
    min_angle, max_angle = 9999, -9999

    cal_win = Toplevel(root)
    cal_win.title("Potentiometer Calibration")
    cal_win.geometry("420x220")
    cal_win.resizable(False, False)
    cal_canvas = Canvas(cal_win, width=420, height=220)
    cal_canvas.pack()

    msg = cal_canvas.create_text(
        210, 60,
        text=" Slowly move your wrist to maximum flexion\nPress SPACE when done",
        font=("Arial", 12),
        fill="black",
        width=380,
        justify="center"
    )
    angle_text = cal_canvas.create_text(
        210, 130,
        text="Angle: --°",
        font=("Arial", 24, "bold"),
        fill="blue"
    )

    if arduino:
        arduino.reset_input_buffer()
        time.sleep(0.5)

    cal_done = {"done": False}

    def finish_calibration(event=None):
        cal_done["done"] = True

    cal_win.bind("<space>", finish_calibration)

    def read_potentiometer_during_calibration():
            global min_angle, max_angle
            latest = None

            if arduino:
                try:
                    while arduino.in_waiting > 0:
                        raw = arduino.readline()
                        if raw:
                            try:
                                latest = float(raw.decode('utf-8').strip())
                            except ValueError:
                                continue
                except Exception:
                    pass

            if latest is not None:
                cal_canvas.itemconfig(angle_text, text=f"Angle: {latest:.2f}°")
                if latest < min_angle:
                    min_angle = latest
                if latest > max_angle:
                    max_angle = latest

            if cal_done["done"]:
                total_range = max_angle - min_angle
                if max_angle - min_angle < 10:
                    print("⚠️ Range too small, using 30–70° default.")
                    min_angle, max_angle = 30, 70
                    total_range = max_angle - min_angle
                cal_canvas.itemconfig(msg, text=f" Calibrated!\nTotal Range: {total_range:.2f}°")        
                root.after(1000, cal_win.destroy)
                print(f" Calibration completed: Total range of {total_range:.2f}°")        
                return

            cal_win.after(50, read_potentiometer_during_calibration)

    read_potentiometer_during_calibration()
    root.wait_window(cal_win)



# --- GAME CLASS ---
class FishingGame:
    def __init__(self, root):
        self.root = root
        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()
        
        # Load assets
        self.bg_img = load_image(r"Game 1 - Flexion\sea.png", (WIDTH, HEIGHT))
        self.rod_img = load_image(r"Game 1 - Flexion\fishing_rod.png", (90, 90))
        self.obj_imgs = {
            "gold": load_image(r"Game 1 - Flexion\gold.png", (60,60)),
            "fish": load_image(r"Game 1 - Flexion\fish.png", (60,60)),
            "trash": load_image(r"Game 1 - Flexion\trash.png", (60,60)),
        }

        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)
        self.rope_item = self.canvas.create_line(0,0,0,0, width=3, fill="white")
        self.rod_item = self.canvas.create_image(100, ROD_Y, image=self.rod_img, anchor=NW)
        self.canvas.tag_raise(self.rope_item, self.rod_item)

        # Score display
        self.score_text = self.canvas.create_text(80, 24, text="Score: 0", font=("Arial", 16), fill="black")
        self.level_text = self.canvas.create_text(700, 24, text=f"Level: 1", font=("Arial",16), fill="black")

        # Buttons
        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET LEVEL", command=self.reset_round) # Changed text for clarity
        self.reset_btn.pack(side="left", padx=10)
        
        # Add Back to Launcher button if launched from game launcher
        if len(sys.argv) >= 3:
            self.back_btn = Button(root, text="← Back to Launcher", bg="#e74c3c", fg="white",
                                  command=lambda: root.destroy())
            self.back_btn.pack(side="right", padx=10)

        # Controls
        root.bind("<space>", lambda e: self.toggle_sweep())
        root.bind("<w>", self.adjust_rope)
        root.bind("<s>", self.adjust_rope)
        root.bind("<Up>", self.adjust_rope)
        root.bind("<Down>", self.adjust_rope)

        # Game variables
        self.rod_x = 100
        self.rod_dir = 1
        self.rope_len = 0
        self.sweeping = True
        self.stopped = False
        self.rope_extending = False
        self.score = 0 # This will be the total session score
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

        # Start Arduino polling if connected
        if self.arduino:
            self.root.after(100, self.update_from_arduino)

    # --- OBJECTS ---
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

    # --- CONTROLS ---
    def toggle_sweep(self):
        """Toggles the rod sweeping left and right."""
        # Don't allow toggling while hook is retracting
        if self.waiting_for_retraction:
            return

        if self.sweeping:
            # Stop the sweep
            self.sweeping = False
            self.stopped = True
        else:
            # Resume the sweep
            self.sweeping = True
            self.stopped = False

    def reset_round(self):
        """Resets the current level, but keeps the total score."""
        # self.score = 0  <-- REMOVED. Score is now persistent.
        self.start_time = time.time() # Reset level timer
        self.rope_len = 0
        self.spawn_objects()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}") # Update text
        self.canvas.itemconfig(self.level_text, text=f"Level: {self.level}")
        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()
        self.waiting_for_retraction = False

    def adjust_rope(self, event):
        if self.arduino is not None or not self.stopped:
            return  
        step = 15
        if event.keysym in ('w', 'Up'):
            self.rope_len = max(0, self.rope_len - step)
        elif event.keysym in ('s', 'Down'):
            self.rope_len = min(ROPE_MAX_LEN, self.rope_len + step)
        
        if not self.sweeping:
            self.check_hit()
        
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

        if self.rope_len < 5:
            return False

        for obj in list(self.objects):
            ox1, oy1, ox2, oy2 = obj["x"], obj["y"], obj["x"] + obj["w"], obj["y"] + obj["h"]
            
            if ox1 <= tip_x <= ox2 and end_y >= oy1:
                
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
                self.score += obj["pts"] # Add to persistent score
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
                text_id = self.canvas.create_text(
                    (ox1 + ox2) // 2, oy1 - 20,
                    text=f"{obj['pts']:+}", font=("Arial", 14, "bold"), fill="black"
                )
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
        """Se llama después de una captura. Muestra la cuerda y espera la retracción."""
        self.canvas.itemconfig(self.rope_item, state="normal")
        self.waiting_for_retraction = True
    
    # --- ARDUINO POLLING ---
    def update_from_arduino(self):
        if self.arduino:
            latest = None
            try:
                while self.arduino.in_waiting > 0:
                    raw = self.arduino.readline()
                    if not raw: continue
                    s = raw.decode('utf-8', errors='ignore').strip()
                    if not s: continue
                    try:
                        angle = float(s)
                        latest = angle
                    except ValueError:
                        continue

                if latest is not None:
                    angle = max(min_angle, min(max_angle, latest))
                    self.pot_normalized = (angle - min_angle) / (max_angle - min_angle)

                    if not self.sweeping:
                        y_pos = self.pot_normalized * ROPE_MAX_LEN
                        self.set_rope(int(y_pos))

            except Exception as e:
                print(f"Error en update_from_arduino: {e}")
                pass

        self.root.after(50, self.update_from_arduino)

    # --- UPDATE LOOP ---
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return

        if self.waiting_for_retraction:
        
            if self.rope_len < 10:  
                self.waiting_for_retraction = False
                self.sweeping = True
                self.stopped = False

        elif self.sweeping:
            self.rod_x += self.rod_dir * self.sweep_speed
            if self.rod_x < 0: self.rod_dir = 1
            if self.rod_x > WIDTH - self.rod_img.width(): self.rod_dir = -1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            
            self.set_rope(0)
        
        else:
            if self.check_hit():
                pass #
        self.update_rope()

    # --- NEW FUNCTION TO SAVE AND EXIT ---
    def exit_and_save(self):
        """Saves the highscore if needed, then closes the game."""
        save_highscore(self.score)
        self.root.destroy()

    # --- END MENU ---
    def show_end_menu(self):
        self.sweeping = False
        self.stopped = True
        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()
        
        total_time = round(time.time() - self.start_time, 1)
        
        # --- HIGHSCORE LOGIC ---
        global highscore
        # Update highscore in memory if it's beaten (for display)
        if self.score > highscore:
            highscore = self.score
            save_highscore(highscore)
        # --- END HIGHSCORE LOGIC ---

        win = Toplevel(self.root)
        win.title("Level Complete!")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=350) # Made window taller
        c.pack()
        
        # --- UPDATED MESSAGE ---
        msg = f" You caught all good items!\n\nYour Score: {self.score}\nAll-Time Highscore: {highscore}\nTime: {total_time}s"
        c.create_text(200, 120, text=msg, font=("Comic Sans MS", 18, "bold"), fill="black", justify="center")
        # --- END UPDATED MESSAGE ---

        def _play_again():
            win.destroy()
            self.level += 1
            self.sweep_speed = ROD_SWEEP_SPEED + (self.level - 1) * 1.2
            self.reset_round() # This no longer resets score
            self.rod_x = 100
            self.rod_dir = 1
            self.set_rope(0)
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            self.game_over = False
            self.sweeping = True
            self.stopped = False

        Button(win, text="NEXT LEVEL", bg="green", fg="white",
            font=("Arial", 14, "bold"), command=_play_again).place(x=70, y=250, width=120, height=40)
        
        # --- UPDATED EXIT BUTTON ---
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
            command=self.exit_and_save).place(x=210, y=250, width=120, height=40)
        # --- END UPDATED EXIT BUTTON ---

# --- START MENU ---
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
    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), FishingGame(root))).place(x=340, y=500)

# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Fishing Flexion Game")
    
    arduino = connect_arduino() 
    if arduino:
        calibrate_potentiometer()
    else: 
        print(" Arduino not connected, using keyboard controls.")
    
    start_menu(root)
    root.mainloop()