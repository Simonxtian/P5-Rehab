import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw

# --- CONFIG ---
HEIGHT, WIDTH = 800, 600
STAR_Y = 80
PLATFORM_COUNT = 12
PLATFORM_WIDTH, PLATFORM_HEIGHT = 180, 50
PLATFORM_MIN_SPEED, PLATFORM_MAX_SPEED = 1.5, 3.5
ARDUINO_BAUD = 9600
ROCKET_SIZE = (50, 70)
BOTTOM_MARGIN = 120
TOP_MARGIN = 180
JUMP_HEIGHT = (HEIGHT - BOTTOM_MARGIN - TOP_MARGIN) / (PLATFORM_COUNT - 1)
JUMP_SPEED = 25
UPDATE_MS = 25
ANGLE_MIN, ANGLE_MAX = 40.0, 150.0


# --- IMAGE LOADER ---
def load_image(path, size=None):
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception:
        w, h = size if size else (50, 50)
        img = Image.new("RGBA", (w, h), (200, 200, 200, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w - 1, h - 1), outline=(0, 0, 0))
        d.text((10, h // 2 - 8), "miss", fill=(0, 0, 0))
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


# --- GAME CLASS ---
class RocketGame:
    def __init__(self, root):
        self.root = root
        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        # Load assets
        self.bg_img = load_image(r"Game 3 - Extension\space.png", (WIDTH, HEIGHT))
        self.rocket_img = load_image(r"Game 3 - Extension\rocket.png", ROCKET_SIZE)
        self.star_img = load_image(r"Game 3 - Extension\star.png", (50, 50))
        self.platform_img = load_image(r"Game 3 - Extension\platform.png", (PLATFORM_WIDTH, PLATFORM_HEIGHT))

        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)

        # Rocket
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = HEIGHT - ROCKET_SIZE[1] - 10
        self.rocket_item = self.canvas.create_image(self.rocket_x, self.rocket_y, image=self.rocket_img, anchor=NW)

        # Star
        self.star_item = self.canvas.create_image(WIDTH // 2 - 25, STAR_Y - 25, image=self.star_img, anchor=NW)

        # Score
        self.score_text = self.canvas.create_text(60, 24, text="Plataforma: 0/12", font=("Arial", 16), fill="white")

        # Buttons
        self.jump_btn = Button(root, text="JUMP (Space)", command=self.attempt_jump)
        self.jump_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET", command=self.reset_game)
        self.reset_btn.pack(side="left", padx=10)

        # Controls
        root.bind("<space>", lambda e: self.attempt_jump())
        root.bind("<Left>", self.keyboard_move)
        root.bind("<Right>", self.keyboard_move)

        # Game variables
        self.current_platform_index = 0  # start on platform 0 (ground)
        self.game_over = False
        self.is_jumping = False
        self.vertical_offset = 0
        self.jump_end_offset = 0
        self.platforms = []
        self.rocket_w, self.rocket_h = ROCKET_SIZE
        self.pot_normalized = 1.0
        self.arduino = connect_arduino()

        self.spawn_platforms()

        self.root.after(UPDATE_MS, self.update)
        if self.arduino:
            self.root.after(50, self.update_from_arduino)

    # --- PLATFORMS ---
    def spawn_platforms(self):
        for p in self.platforms:
            self.canvas.delete(p["id"])
            self.canvas.delete(p["id_img"])
        self.platforms.clear()

        bottom_y = HEIGHT - PLATFORM_HEIGHT - 10

        # Remaining platforms
        for i in range(1, PLATFORM_COUNT + 1):
            y = bottom_y - i * JUMP_HEIGHT
            x = randint(0, WIDTH - PLATFORM_WIDTH)
            speed = randint(int(PLATFORM_MIN_SPEED * 10), int(PLATFORM_MAX_SPEED * 10)) / 10.0
            direction = choice([-1, 1])

            pid_img = self.canvas.create_image(x, y, image=self.platform_img, anchor=NW)
            pid_rect = self.canvas.create_rectangle(x, y, x + PLATFORM_WIDTH, y + PLATFORM_HEIGHT, fill="", outline="")

            self.platforms.append({
                "id": pid_rect,
                "id_img": pid_img,
                "x": x, "y": y, "w": PLATFORM_WIDTH, "h": PLATFORM_HEIGHT,
                "speed": speed, "dir": direction
            })


    def update_platforms(self):
        for p in self.platforms:
            if p["speed"] == 0:
                continue  # bottom platform doesn’t move
            p["x"] += p["dir"] * p["speed"]
            if p["x"] <= 0:
                p["x"] = 0; p["dir"] = 1
            elif p["x"] >= WIDTH - p["w"]:
                p["x"] = WIDTH - p["w"]; p["dir"] = -1

            y_adjusted = p["y"] - self.vertical_offset
            self.canvas.coords(p["id_img"], p["x"], y_adjusted)
            self.canvas.coords(p["id"], p["x"], y_adjusted, p["x"] + p["w"], y_adjusted + p["h"])

    # --- CONTROLS ---
    def keyboard_move(self, event):
        if self.game_over or self.is_jumping: return
        step = 15
        if event.keysym == 'Left':
            self.rocket_x = max(0, self.rocket_x - step)
        elif event.keysym == 'Right':
            self.rocket_x = min(WIDTH - self.rocket_w, self.rocket_x + step)
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)

    def check_platform_alignment(self, platform):
        rocket_left = self.rocket_x
        rocket_right = self.rocket_x + self.rocket_w
        platform_left = platform["x"]
        platform_right = platform["x"] + platform["w"]
        return rocket_right > platform_left and rocket_left < platform_right

    # --- JUMP LOGIC ---
    def attempt_jump(self):
        if self.is_jumping or self.game_over:
            return

        next_index = self.current_platform_index + 1
        if next_index >= len(self.platforms):
            self.game_over = True
            self.show_end_menu()
            return

        next_p = self.platforms[next_index]

        # Must be horizontally aligned
        if not self.check_platform_alignment(next_p):
            self.return_to_current_platform()
            return

        self.is_jumping = True
        self.current_platform_index = next_index
    def ascend(self):
        if not self.is_jumping: return

        target_platform = self.platforms[self.current_platform_index]
        target_y = target_platform["y"]

        if self.rocket_y > target_y - ROCKET_SIZE[1]:
            self.rocket_y -= JUMP_SPEED
            self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
        else:
            self.is_jumping = False
            # Land on platform and stop its movement
            target_platform["speed"] = 0
            self.rocket_y = target_y - ROCKET_SIZE[1]
            self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
            self.canvas.itemconfig(self.score_text,
                                   text=f"Plataforma: {self.current_platform_index}/{PLATFORM_COUNT}")

    def return_to_current_platform(self):
        if self.current_platform_index == -1:
            # Fall back to the bottom of the screen
            self.rocket_y = HEIGHT - self.rocket_h - 10
        else:
            platform = self.platforms[self.current_platform_index]
            self.rocket_y = platform["y"] - self.rocket_h
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)

    # --- ARDUINO ---
    def update_from_arduino(self):
        if self.arduino:
            try:
                raw = self.arduino.readline().decode("utf-8").strip()
                if raw:
                    angle = float(raw)
                    angle = max(ANGLE_MIN, min(ANGLE_MAX, angle))
                    self.pot_normalized = (angle - ANGLE_MIN) / (ANGLE_MAX - ANGLE_MIN)
                    max_x = WIDTH - self.rocket_w
                    self.rocket_x = int(max_x * self.pot_normalized)
                    self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
            except:
                pass
        self.root.after(50, self.update_from_arduino)

    # --- UPDATE LOOP ---
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return

        self.update_platforms()
        if self.is_jumping:
            self.ascend()

    # --- RESET ---
    def reset_game(self):
        self.current_platform_index = 0
        self.is_jumping = False
        self.vertical_offset = 0
        self.game_over = False
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = HEIGHT - ROCKET_SIZE[1] - 10
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
        self.spawn_platforms()
        self.canvas.itemconfig(self.score_text, text=f"Plataforma: 0/{PLATFORM_COUNT}")

    # --- END MENU ---
    def show_end_menu(self):
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300)
        c.pack()
        c.create_text(200, 100, text="🌟 ¡Misión Cumplida! 🌟", font=("Comic Sans MS", 18, "bold"), fill="black")
        Button(win, text="REINICIAR", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_game())).place(x=150, y=180)


# --- START MENU ---
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#2c3e50", outline="")
    canvas.create_text(WIDTH//2, 200, text="🚀 Rocket Extension Game 🌟",
                        font=("Comic Sans MS", 30, "bold"), fill="white")

    canvas.create_text(WIDTH // 2, 300,
                       text=("Use wrist or arrow keys to align horizontally.\n"
                             "Press SPACE (or wrist extension) to jump.\n"
                             "If you miss, you’ll fall back to your previous platform."),
                       font=("Comic Sans MS", 16), fill="white", justify="center")
    Button(root, text="JUGAR", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), RocketGame(root))).place(x=WIDTH // 2 - 60, y=500)


# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Rocket Extension Game")
    start_menu(root)
    root.mainloop()
