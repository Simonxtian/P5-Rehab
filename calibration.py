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
ARDUINO_BAUD = 9600

OBJECT_TYPES = [
    ("gold", "gold.png", +5),
    ("fish", "fish.png", +2),
    ("trash", "trash.png", -3)
]
NUM_OBJECTS = 20

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
        d.rectangle((0, 0, w-1, h-1), outline=(0, 0, 0))
        d.text((10, h//2-8), "missing", fill=(0,0,0))
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
        except:
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

def read_arduino_latest(arduino):
    val = None
    if arduino:
        while arduino.in_waiting:
            try:
                line = arduino.readline().decode().strip()
                if line.startswith("Angle:"):
                    val = float(line.split(":")[1].strip())
            except:
                continue
    return val

# --- CALIBRATION WINDOW ---
class CalibrationWindow:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        self.values = {}
        self.step = 0

        self.win = Toplevel(root)
        self.win.title("Calibration")
        self.win.resizable(False, False)
        self.label = Label(self.win, text="Hold wrist at FLEXION (bottom) and press 'Next'", font=("Arial", 14))
        self.label.pack(pady=20)

        self.next_btn = Button(self.win, text="Next", command=self.next_step, font=("Arial", 14))
        self.next_btn.pack(pady=10)

        self.arduino = connect_arduino()
        self.current_val = None
        self.update_pot_value()

    def update_pot_value(self):
        val = read_arduino_latest(self.arduino)
        if val is not None:
            self.current_val = val
        self.label.config(text=f"Step {self.step+1}: Current angle = {self.current_val}")
        self.win.after(50, self.update_pot_value)

    def next_step(self):
        if self.current_val is None:
            self.label.config(text="No value read from Arduino")
            return
        if self.step == 0:
            self.values['min'] = self.current_val
            self.label.config(text="Hold wrist at EXTENSION (top) and press 'Next'")
        elif self.step == 1:
            self.values['max'] = self.current_val
            self.win.destroy()
            self.callback(self.values['min'], self.values['max'])
        self.step += 1

# --- GAME CLASS ---
class FishingGame:
    def __init__(self, root, angle_min, angle_max):
        self.root = root
        self.angle_min = angle_min
        self.angle_max = angle_max

        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        # Load assets
        self.bg_img = load_image(r"Game 1 - Flexion\sea.png", (WIDTH, HEIGHT))
        self.rod_img = load_image(r"Game 1 - Flexion\fishing_rod.png", (90, 90))
        self.obj_imgs = {typ: load_image(f"Game 1 - Flexion\\{typ}.png", (60,60)) for typ,_ ,_ in OBJECT_TYPES}

        self.canvas.create_image(0,0,image=self.bg_img,anchor=NW)
        self.rope_item = self.canvas.create_line(0,0,0,0,width=3,fill="white")
        self.rod_item = self.canvas.create_image(100,ROD_Y,image=self.rod_img,anchor=NW)
        self.canvas.tag_raise(self.rope_item, self.rod_item)

        self.score_text = self.canvas.create_text(80, 24, text="Score: 0", font=("Arial", 16), fill="black")

        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET", command=self.reset_round)
        self.reset_btn.pack(side="left", padx=10)

        # Game variables
        self.rod_x = 100
        self.rod_dir = 1
        self.rope_len = ROPE_MAX_LEN  # start at bottom
        self.sweeping = True
        self.stopped = False
        self.score = 0
        self.start_time = time.time()
        self.arduino = connect_arduino()
        self.objects = []
        self.spawn_objects()
        self.root.after(UPDATE_MS, self.update)
        self.sweep_speed = ROD_SWEEP_SPEED
        self.temp_texts = []
        self.game_over = False

        # Bind space bar
        self.root.bind("<space>", lambda e: self.toggle_sweep())

        # Continuous rope update
        self.update_rope_from_pot()

    def spawn_objects(self):
        for obj in self.objects:
            self.canvas.delete(obj["id"])
        self.objects.clear()
        for _ in range(NUM_OBJECTS):
            typ, _, pts = choice(OBJECT_TYPES)
            img = self.obj_imgs[typ]
            w, h = img.width(), img.height()
            x = randint(40, WIDTH-100)
            y = randint(300,550)
            oid = self.canvas.create_image(x,y,image=img,anchor=NW)
            self.objects.append(dict(id=oid,type=typ,x=x,y=y,w=w,h=h,pts=pts))

    def toggle_sweep(self):
        self.sweeping = not self.sweeping

    def rod_tip(self):
        bx, by, _, _ = self.canvas.bbox(self.rod_item)
        w,h = self.rod_img.width(), self.rod_img.height()
        return bx+w-8, by+h-86

    def update_rope(self):
        tx, ty = self.rod_tip()
        self.canvas.coords(self.rope_item, tx, ty, tx, ty+self.rope_len)

    def check_hit(self):
        tip_x, tip_y = self.rod_tip()
        end_y = tip_y + self.rope_len
        for obj in list(self.objects):
            ox1, oy1, ox2, oy2 = obj["x"], obj["y"], obj["x"]+obj["w"], obj["y"]+obj["h"]
            if ox1 <= tip_x <= ox2 and end_y >= oy1:
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
                self.score += obj["pts"]
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
        return False

    def angle_to_rope(self, angle):
        angle = max(self.angle_min, min(self.angle_max, angle))
        return (self.angle_max - angle) / (self.angle_max - self.angle_min) * ROPE_MAX_LEN

    def update_rope_from_pot(self):
        if self.arduino:
            val = read_arduino_latest(self.arduino)
            if val is not None:
                self.rope_len = self.angle_to_rope(val)
                self.update_rope()
        self.root.after(25, self.update_rope_from_pot)

    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over:
            return
        if self.sweeping:
            self.rod_x += self.rod_dir*self.sweep_speed
            if self.rod_x<0: self.rod_dir=1
            if self.rod_x>WIDTH-self.rod_img.width(): self.rod_dir=-1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)
            self.check_hit()
        self.update_rope()

    def reset_round(self):
        self.score = 0
        self.start_time = time.time()
        self.spawn_objects()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
        self.rope_len = ROPE_MAX_LEN

# --- START MENU ---
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0,0,WIDTH,HEIGHT,fill="#a9d8ff", outline="")
    canvas.create_text(WIDTH//2,150,text="🎣 Fishing Flexion Game 🎣",
                       font=("Comic Sans MS",36,"bold"),fill="navy")
    canvas.create_text(WIDTH//2,300,
                       text="Move wrist to control fishing line.\nCatch fish/gold, avoid trash.",
                       font=("Comic Sans MS",16),fill="black", justify="center")

    def start_calibration():
        # Remove the start menu canvas
        canvas.destroy()
        # Start calibration window
        CalibrationWindow(root, lambda amin, amax: FishingGame(root, amin, amax))

    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS",24,"bold"),
           command=start_calibration).place(x=340,y=500)
# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Fishing Flexion Game")
    start_menu(root)
    root.mainloop()
