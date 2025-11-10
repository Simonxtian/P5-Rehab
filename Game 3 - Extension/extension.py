"""
Wrist-flexion jump trainer game (Tkinter).
- Uses an Arduino potentiometer (serial float values, e.g. "72.3\n")
- Calibration for min/max wrist positions saved to calibration.json
- Keyboard fallback: Space / Up to jump, Left/Right to move horizontally
"""

import serial
import sys
import glob
import time
import json
import os
from random import randint, choice
from tkinter import Tk, Canvas, Button, Label, Toplevel, StringVar
from tkinter import NW
from PIL import Image, ImageTk

# ---------- Config ----------
WIDTH, HEIGHT = 600, 700  # Portrait mode
PLAYER_X = WIDTH//2 - 35  # fixed horizontal position
GROUND_Y = HEIGHT - 100
GRAVITY = 1.0
BASE_JUMP_VEL = -12
MAX_EXTRA_JUMP = -18
OBSTACLE_SPEED_BASE = 4
OBSTACLE_SPAWN_MS = 1500
CALIB_FILE = "calibration.json"
HIGHSCORE_FILE = "highscore.json"
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 0
# ---------- Globals ----------
root = Tk()
root.title("Wrist Jump Trainer")
canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()
serial_conn = None
calibration = {"min": 40.0, "max": 150.0}  # defaults if no calibration
player = None
player_image = None
bg_image = None
obstacles = []
score = 0
lives = 3
game_running = False
highscore = 0
last_spawn = 0
speed_multiplier = 0
angle_latest = None  # latest numeric value read from serial

# ---------- Utility: load/save files ----------
def safe_load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def safe_save_json(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
    except Exception as e:
        print("Could not save", path, e)

# load calibration & highscore
calibration = safe_load_json(CALIB_FILE, calibration)
highscore = safe_load_json(HIGHSCORE_FILE, {"highscore": 0}).get("highscore", 0)

# ---------- Serial helper ----------
def find_arduino_port():
    if sys.platform.startswith("win"):
        ports = [f"COM{i+1}" for i in range(256)]
    elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
        ports = glob.glob("/dev/tty[A-Za-z]*")
    elif sys.platform.startswith("darwin"):
        ports = glob.glob("/dev/tty.*")
    else:
        return None
    for p in ports:
        try:
            s = serial.Serial(p)
            s.close()
            return p
        except Exception:
            pass
    return None

def connect_serial():
    global serial_conn
    try:
        port = find_arduino_port()
        if not port:
            print("No Arduino detected.")
            return None
        serial_conn = serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT)
        time.sleep(2)
        try:
            serial_conn.reset_input_buffer()
        except Exception:
            pass
        print("Connected to", port)
        return serial_conn
    except Exception as e:
        print("Could not open serial:", e)
        serial_conn = None
        return None

# ---------- Image helpers (safe fallbacks) ----------
def load_or_placeholder(path, size, text):
    try:
        img = Image.open(path).resize(size)
        return ImageTk.PhotoImage(img)
    except Exception:
        from PIL import ImageDraw, ImageFont
        im = Image.new("RGBA", size, (230,230,230,255))
        draw = ImageDraw.Draw(im)
        draw.rectangle((1,1,size[0]-2,size[1]-2), outline=(100,100,100))
        draw.text((10, size[1]//2 - 10), text, fill=(0,0,0))
        return ImageTk.PhotoImage(im)

player_image = load_or_placeholder(r"Game 3 - Extension\rocket.png", (70,70), "You")
bg_image = load_or_placeholder(r"Game 3 - Extension\space.png", (WIDTH, HEIGHT), "Background")
canvas.create_image(0,0, image=bg_image, anchor=NW)

# ---------- Player class ----------
class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vy = 0
        self.width = 70
        self.height = 70
        self.on_ground = True
        self.canvas_id = canvas.create_image(self.x, self.y, image=player_image, anchor=NW)

    def update(self):
        self.vy += GRAVITY
        self.y += self.vy
        if self.y >= GROUND_Y - self.height:
            self.y = GROUND_Y - self.height
            self.vy = 0
            self.on_ground = True
        else:
            self.on_ground = False
        canvas.coords(self.canvas_id, self.x, int(self.y))

    def set_y_from_angle(self, normalized):
        # Map wrist flexion directly to vertical position
        # normalized=0 → bottom; normalized=1 → top
        top_limit = 50
        bottom_limit = GROUND_Y - self.height
        self.y = bottom_limit - normalized * (bottom_limit - top_limit)
        canvas.coords(self.canvas_id, self.x, int(self.y))

    def jump_keyboard(self):
        if self.on_ground:
            self.vy = BASE_JUMP_VEL
            self.on_ground = False
    
# ---------- Obstacles ----------
class Obstacle:
    def __init__(self, x, y, w, h, kind="block"):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.kind = kind
        color = "red" if kind == "spike" else "brown"
        self.id = canvas.create_rectangle(self.x, self.y, self.x+self.w, self.y+self.h, fill=color)

    def update(self, speed):
        self.x -= speed
        canvas.coords(self.id, self.x, self.y, self.x+self.w, self.y+self.h)

    def offscreen(self):
        return (self.x + self.w) < -50

    def bbox(self):
        return (self.x, self.y, self.x+self.w, self.y+self.h)

# ---------- Game functions ----------
def spawn_obstacle():
    # different obstacle sizes and heights
    h = randint(40, 120)
    kind = choice(["block"]*7 + ["spike"]*3)
    y = GROUND_Y - h
    w = randint(40, 90)
    obs = Obstacle(WIDTH + 20, y, w, h, kind)
    obstacles.append(obs)

def check_collision(a_bbox, b_bbox):
    ax1, ay1, ax2, ay2 = a_bbox
    bx1, by1, bx2, by2 = b_bbox
    return not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)

def game_over(message="Game Over"):
    global game_running, highscore, score
    game_running = False
    if score > highscore:
        highscore = score
        safe_save_json(HIGHSCORE_FILE, {"highscore": highscore})
    top = Toplevel(root)
    top.title("Game Over")
    Label(top, text=f"{message}\nScore: {score}\nHighscore: {highscore}", font=("Arial", 14)).pack(padx=10, pady=10)
    def restart():
        top.destroy()
        start_game()
    Button(top, text="Play Again", command=restart).pack(pady=5)
    Button(top, text="Quit", command=root.destroy).pack(pady=5)

def update_score_text():
    canvas.delete("hud")
    canvas.create_text(80,20, text=f"Score: {score}", font=("Arial", 14, "bold"), tag="hud")
    canvas.create_text(240,20, text=f"Lives: {lives}", font=("Arial", 14, "bold"), tag="hud")
    canvas.create_text(420,20, text=f"High: {highscore}", font=("Arial", 14, "bold"), tag="hud")
def game_loop():
    global last_spawn, score, lives, game_running, speed_multiplier, angle_latest

    if not game_running:
        return

    now = int(time.time()*1000)
    if now - last_spawn > OBSTACLE_SPAWN_MS:
        spawn_obstacle()
        last_spawn = now

    read_serial_latest()

    # map angle to normalized value (0..1)
    if angle_latest is not None:
        mn = calibration.get("min", 40.0)
        mx = calibration.get("max", 150.0)
        val = max(mn, min(mx, angle_latest))
        normalized = (val - mn) / (mx - mn)
        normalized = max(0.0, min(1.0, normalized))
        player.set_y_from_angle(normalized)

    # update obstacles horizontally
    for o in list(obstacles):
        o.update(OBSTACLE_SPEED_BASE + speed_multiplier)
        if o.offscreen():
            canvas.delete(o.id)
            obstacles.remove(o)
            score += 1
        elif check_collision(player.get_bbox(), o.bbox()):
            canvas.delete(o.id)
            obstacles.remove(o)
            lives -= 1
            if lives <= 0:
                game_over("No lives left")
                return

    update_score_text()
    speed_multiplier = min(8, score // 10)
    root.after(20, game_loop)

# ---------- Serial reading: read all available lines and keep latest numeric ----------
def read_serial_latest():
    global serial_conn, angle_latest
    if serial_conn:
        try:
            latest = None
            while True:
                if hasattr(serial_conn, "in_waiting") and serial_conn.in_waiting == 0:
                    break
                raw = serial_conn.readline()
                if not raw:
                    break
                try:
                    s = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    s = ""
                if not s:
                    continue
                try:
                    latest = float(s)
                except Exception:
                    # ignore non-numeric lines
                    pass
            if latest is not None:
                angle_latest = float(latest)
        except Exception:
            # keep silent on serial hiccups
            pass

# ---------- Controls ----------
def on_key(event):
    k = event.keysym
    if k in ("space", "Up"):
        player.jump_keyboard()
    elif k in ("Left",):
        player.x = max(10, player.x - 20)
    elif k in ("Right",):
        player.x = min(WIDTH - player.width - 10, player.x + 20)

def calibrate_min():
    # capture current Arduino reading as min (relaxed)
    if angle_latest is None:
        msg = "No Arduino reading available; ensure device is connected and pot moved."
    else:
        calibration["min"] = float(angle_latest)
        safe_save_json(CALIB_FILE, calibration)
        msg = f"Calibrated MIN to {calibration['min']:.1f}"
    popup_message(msg)

def calibrate_max():
    if angle_latest is None:
        msg = "No Arduino reading available; ensure device is connected and pot moved."
    else:
        calibration["max"] = float(angle_latest)
        safe_save_json(CALIB_FILE, calibration)
        msg = f"Calibrated MAX to {calibration['max']:.1f}"
    popup_message(msg)

def popup_message(txt):
    t = Toplevel(root)
    t.title("Info")
    Label(t, text=txt, padx=20, pady=10).pack()
    Button(t, text="OK", command=t.destroy).pack(pady=5)

# ---------- UI: main menu and start ----------
def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_image, anchor=NW)
    canvas.create_text(WIDTH//2, 80, text="Wrist Flexion Jump Trainer", font=("Arial", 28, "bold"), fill="white")
    canvas.create_text(WIDTH//2, 140, text="Use wrist flexion (potentiometer) to jump.",
                       font=("Arial", 14), fill="white")
    btn_play = Button(root, text="Play", command=start_game, width=10)
    btn_cal_min = Button(root, text="Calibrate MIN", command=calibrate_min, width=12)
    btn_cal_max = Button(root, text="Calibrate MAX", command=calibrate_max, width=12)
    canvas.create_window(WIDTH//2 - 120, 220, window=btn_play)
    canvas.create_window(WIDTH//2 + 20, 220, window=btn_cal_min)
    canvas.create_window(WIDTH//2 + 160, 220, window=btn_cal_max)
    canvas.create_text(WIDTH//2, 300,
                       text=f"Current calibration: min={calibration.get('min'):.1f}, max={calibration.get('max'):.1f}",
                       font=("Arial", 12), fill="white")

def start_game():
    global player, obstacles, score, lives, game_running, serial_conn, last_spawn, speed_multiplier, angle_latest
    # Reset
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_image, anchor=NW)
    player = Player(PLAYER_X, GROUND_Y - 70)
    obstacles = []
    score = 0
    lives = 3
    speed_multiplier = 0
    last_spawn = int(time.time()*1000)
    angle_latest = None
    game_running = True

    # start serial if not connected yet
    if serial_conn is None:
        connect_serial()

    # draw ground
    canvas.create_rectangle(0, GROUND_Y, WIDTH, HEIGHT, fill="#7fbf7f", outline="", tag="ground")
    update_score_text()
    root.bind("<Key>", on_key)
    root.after(20, game_loop)

# ---------- Startup ----------
start_menu()
root.mainloop()