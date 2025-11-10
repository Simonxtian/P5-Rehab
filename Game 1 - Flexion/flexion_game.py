import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel, Label
from PIL import Image, ImageTk

# --- CONFIG ---
WIDTH, HEIGHT = 800, 600
ROD_Y = 20
ROD_SWEEP_SPEED = 4
ROPE_MAX_LEN = HEIGHT - 60
UPDATE_MS = 25
ANGLE_MIN, ANGLE_MAX = 40.0, 150.0
ARDUINO_BAUD = 9600

OBJECT_TYPES = [
    ("gold", "gold.png", +5),
    ("fish", "fish.png", +2),
    ("trash", "trash.png", -3)
]
NUM_OBJECTS = 20  # fewer items

# --- IMAGE LOADER ---
def load_image(path, size=None):
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception:
        from PIL import ImageDraw
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
        print("No Arduino found (test mode only).")
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

        # NEW LINE ⬇️
        self.score_text = self.canvas.create_text(80, 24, text="Score: 0", font=("Arial", 16), fill="black")
        self.level_text = self.canvas.create_text(700, 24, text=f"Level: 1", font=("Arial",16), fill="black")


        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET", command=self.reset_round)
        self.reset_btn.pack(side="left", padx=10)

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
        self.score = 0
        self.start_time = time.time()
        self.arduino = connect_arduino()
        self.objects = []
        self.spawn_objects()
        self.root.after(UPDATE_MS, self.update)
        self.sweep_speed = ROD_SWEEP_SPEED  # Start speed (base speed)
        self.level = 1
        self.temp_texts = []
        self.game_over = False



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
        if self.sweeping:
            self.sweeping = False
            self.stopped = True
        elif self.stopped:
            self.set_rope(0)  # retract rope completely
            self.canvas.itemconfig(self.rope_item, state="normal")
            self.sweeping = True
            self.stopped = False

    def reset_round(self):
        self.score = 0
        self.start_time = time.time()
        self.rope_len = 0
        self.spawn_objects()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
        self.canvas.itemconfig(self.level_text, text=f"Level: {self.level}")
        
        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()



    def adjust_rope(self, event):
        if self.arduino is not None or not self.stopped:
            return
        step = 15
        if event.keysym in ('w', 'Up'):
            self.rope_len = max(0, self.rope_len - step)
        elif event.keysym in ('s', 'Down'):
            self.rope_len = min(ROPE_MAX_LEN, self.rope_len + step)
        if self.check_hit():
            self.root.after(700, self.finish_catch_and_resume)
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
        for obj in list(self.objects):
            ox1, oy1, ox2, oy2 = obj["x"], obj["y"], obj["x"] + obj["w"], obj["y"] + obj["h"]
            if ox1 <= tip_x <= ox2 and end_y >= oy1:
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
                self.score += obj["pts"]
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
                text_id = self.canvas.create_text(
                    (ox1 + ox2) // 2, oy1 - 20,
                    text=f"{obj['pts']:+}", font=("Arial", 14, "bold"), fill="black"
                )
                self.temp_texts.append(text_id)


                # Hide rope immediately (caught something)
                self.canvas.itemconfig(self.rope_item, state="hidden")

                # Check if game is finished
                if self.all_good_collected():
                    self.sweeping = False
                    self.stopped = True
                    self.game_over = True
                    self.root.after(500, self.show_end_menu)
                else:
                    # Start automatic retract & resume
                    self.root.after(500, self.finish_catch_and_resume)
                return True
        return False
    
    def set_rope(self, length):
        """Safely set rope length and update its position."""
        self.rope_len = max(0, min(ROPE_MAX_LEN, length))
        self.update_rope()

    def finish_catch_and_resume(self):
        """Retract rope, make it follow the rod, and resume sweeping."""
        self.set_rope(0)
        self.canvas.itemconfig(self.rope_item, state="normal")
        self.sweeping = True
        self.stopped = False

    def update(self):
        # Always schedule the next update
        self.root.after(UPDATE_MS, self.update)

        if self.game_over:
            return  # do nothing, rod frozen

        if self.sweeping:
            self.rod_x += self.rod_dir * self.sweep_speed
            if self.rod_x < 0: self.rod_dir = 1
            if self.rod_x > WIDTH - self.rod_img.width(): self.rod_dir = -1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)

            if self.check_hit():
                if not self.game_over:
                    self.sweeping = False
                    self.stopped = True
                return

        self.update_rope()
    
    def all_good_collected(self):
        return not any(o["type"] in ("gold","fish") for o in self.objects)

    # --- MENUS ---
    def show_end_menu(self):
        # Stop rod
        self.sweeping = False
        self.stopped = True

        # Clear floating texts
        for tid in self.temp_texts:
            self.canvas.delete(tid)
        self.temp_texts.clear()

        total_time = round(time.time() - self.start_time, 1)
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300)
        c.pack()
        msg = f"🎣 You caught all good items!\n\nScore: {self.score}\nTime: {total_time}s"
        c.create_text(200, 100, text=msg, font=("Comic Sans MS", 18, "bold"), fill="black")

        def _play_again():
            win.destroy()
            self.level += 1
            self.sweep_speed = ROD_SWEEP_SPEED + (self.level - 1) * 1.2

            # Reset round completely
            self.reset_round()

            # Reset rod
            self.rod_x = 100
            self.rod_dir = 1
            self.set_rope(0)
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)

            # Resume game
            self.game_over = False
            self.sweeping = True
            self.stopped = False

        Button(win, text="PLAY AGAIN", bg="green", fg="white",
            font=("Arial", 14, "bold"), command=_play_again).place(x=120, y=180)
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
            command=self.root.destroy).place(x=250, y=180)

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
    start_menu(root)
    root.mainloop()
