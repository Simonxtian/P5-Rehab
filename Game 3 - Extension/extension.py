import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw

# --- CONFIG ---
HEIGHT, WIDTH = 700, 600
STAR_Y = 5  # Y coordinate of the top edge of the star
PLATFORM_COUNT = 9  # Total steps needed (10 platforms + 1 star)
PLATFORM_WIDTH, PLATFORM_HEIGHT = 180, 50
PLATFORM_MIN_SPEED, PLATFORM_MAX_SPEED = 1.5, 3.5
ARDUINO_BAUD = 9600  # 🚀 FIXED: Higher baud rate to remove delay
ROCKET_SIZE = (50, 70)  # (width, height)

# Vertical layout constants
Y_REF_BOTTOM = HEIGHT - 10  # 690: baseline (rocket feet on platform 0)
Y_REF_TOP = STAR_Y           # 5: line where the top of the star aligns

# Calculate JUMP_HEIGHT for 10 uniform vertical steps
TOTAL_VERTICAL_DISTANCE = (Y_REF_BOTTOM - Y_REF_TOP)  # 685
JUMP_HEIGHT = (TOTAL_VERTICAL_DISTANCE / PLATFORM_COUNT)  # 68.5

JUMP_SPEED = 25
UPDATE_MS = 25
ANGLE_MIN, ANGLE_MAX = 40.0, 70.0

arduino = None
min_angle = 30.0
max_angle = 70.0

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
        # 🚀 FIXED: Use fast baud rate
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
    min_angle, max_angle = 9999, -9999  # FIXED: max_angle must start at -9999

    cal_win = Toplevel(root)
    cal_win.title("Potentiometer Calibration")
    cal_win.geometry("420x220")
    cal_win.resizable(False, False)
    cal_canvas = Canvas(cal_win, width=420, height=220)
    cal_canvas.pack()

    msg = cal_canvas.create_text(
        210, 60,
        text="✋ Slowly move your wrist to maximum extension\nPress SPACE when done",
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
        self.restart_count = 0 

        # Rocket
        self.Y_Ground = Y_REF_BOTTOM
        
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        
        self.rocket_y = self.Y_Ground - ROCKET_SIZE[1] 
        self.rocket_item = self.canvas.create_image(self.rocket_x, self.rocket_y, image=self.rocket_img, anchor=NW)

        # Star
        self.star_item = self.canvas.create_image(WIDTH // 2 - 25, STAR_Y, image=self.star_img, anchor=NW) 

        # Score
        self.score_text = self.canvas.create_text(75, 24, text="Platform: 0/9", font=("Arial", 16), fill="white")


        # Controls
        root.bind("<space>", lambda e: self.attempt_jump())
        root.bind("<Left>", self.keyboard_move)
        root.bind("<Right>", self.keyboard_move)

        # Game variables
        self.current_platform_index = 0
        self.game_over = False
        self.is_jumping = False
        self.platforms = []
        self.rocket_w, self.rocket_h = ROCKET_SIZE
        self.arduino = arduino
        self._jump_ready = True  # Flag for Arduino jump

        # Cooldown for SPACE (not needed for Arduino)
        self.jump_cooldown = 0
        self.JUMP_COOLDOWN_MS = 300 

        self.spawn_platforms()

        self.root.after(UPDATE_MS, self.update)
        if self.arduino:
            self.root.after(UPDATE_MS, self.update_from_arduino)

    # --- PLATFORMS ---
    def spawn_platforms(self):
        for p in self.platforms:
            self.canvas.delete(p["id"])
            self.canvas.delete(p["id_img"])
        self.platforms.clear()

        bottom_y = self.Y_Ground

        # Generate 9 platforms (for steps 1 to 9)
        for i in range(1, PLATFORM_COUNT): 
            # This is the Y where the rocket FEET should land.
            platform_top_y = bottom_y - (i * JUMP_HEIGHT)-30
            
            x = randint(0, WIDTH - PLATFORM_WIDTH)
            speed_boost = 1 + (self.restart_count * 0.1)
            speed = randint(int(PLATFORM_MIN_SPEED * 10), int(PLATFORM_MAX_SPEED * 10)) / 10.0
            speed *= speed_boost
            direction = choice([-1, 1])

            # y is the NW coordinate of the platform image
            y = platform_top_y 

            pid_img = self.canvas.create_image(x, y, image=self.platform_img, anchor=NW)
            pid_rect = self.canvas.create_rectangle(x, y, x + PLATFORM_WIDTH, y + PLATFORM_HEIGHT, fill="", outline="")

            self.platforms.append({
                "id": pid_rect,
                "id_img": pid_img,
                "x": x, "y": y, "w": PLATFORM_WIDTH, "h": PLATFORM_HEIGHT,
                "speed": speed, "dir": direction
            })

        # Reposition the star
        y_star_feet = bottom_y - PLATFORM_COUNT * JUMP_HEIGHT 
        x_star = WIDTH // 2 - 25
        # Draw the star in its final position (Y_REF_TOP)
        self.canvas.coords(self.star_item, x_star, Y_REF_TOP)


    def update_platforms(self):
        for p in self.platforms:
            if p["speed"] == 0:
                continue 
                
            p["x"] += p["dir"] * p["speed"]
            if p["x"] <= 0:
                p["x"] = 0; p["dir"] = 1
            elif p["x"] >= WIDTH - p["w"]:
                p["x"] = WIDTH - p["w"]; p["dir"] = -1

            # No scrolling, Y is static
            y_adjusted = p["y"]
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
        # Margin of 15px to land
        return rocket_right > platform_left + 15 and rocket_left < platform_right - 15

    # --- JUMP LOGIC ---
    def attempt_jump(self):
        if self.is_jumping or self.game_over:
            return

        current_time = time.time() * 1000
        if current_time - self.jump_cooldown < self.JUMP_COOLDOWN_MS:
             pass
        self.jump_cooldown = current_time
        

        next_index = self.current_platform_index + 1
  
        if next_index < PLATFORM_COUNT: 
            next_p = self.platforms[next_index - 1] 

            if not self.check_platform_alignment(next_p):
                self.reset_game(reset_count=False) 
                return
        
        elif next_index == PLATFORM_COUNT:
            star_x, star_y = self.canvas.coords(self.star_item)
            star_w, star_h = (50, 50)
            
            rocket_left = self.rocket_x
            rocket_right = self.rocket_x + self.rocket_w
            star_left = star_x
            star_right = star_x + star_w
            
            if not (rocket_right > star_left + 5 and rocket_left < star_right - 5):
                self.reset_game(reset_count=False)
                return

        self.is_jumping = True
        self.current_platform_index = next_index
        
    def ascend(self):
        if not self.is_jumping: 
            return

        target_index = self.current_platform_index
        Y_Ground = self.Y_Ground
        
        target_y_landing = Y_Ground - target_index * JUMP_HEIGHT 
        landing_y_top_of_rocket = target_y_landing - ROCKET_SIZE[1] 
        self.rocket_y -= JUMP_SPEED

        if self.rocket_y <= landing_y_top_of_rocket:
            self.rocket_y = landing_y_top_of_rocket 
            self.is_jumping = False

            landed = False
            if target_index < PLATFORM_COUNT:
                target_platform = self.platforms[target_index - 1]
                if self.check_platform_alignment(target_platform):
                    landed = True
                    target_platform["speed"] = 0  
            elif target_index == PLATFORM_COUNT:
                landed = True

            if landed:
                self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
                self.canvas.itemconfig(
                    self.score_text, text=f"Plataform: {target_index}/9"
                )

                if target_index == PLATFORM_COUNT:
                    self.canvas.itemconfig(self.score_text, text="YOU WIN!")
                    self.game_over = True
                    self.show_end_menu()
            else:
                self.reset_game(reset_count=False)

        if self.is_jumping:
            self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)

    # --- ARDUINO ---
    def update_from_arduino(self):
        if self.arduino:
            try:
                latest_raw = None
                while self.arduino.in_waiting > 0:
                    latest_raw = self.arduino.readline().decode("utf-8").strip()

                if latest_raw is None:
                    self.root.after(UPDATE_MS, self.update_from_arduino)
                    return 
                
                
                try:
                    angle = float(latest_raw)
                except ValueError:
                    self.root.after(UPDATE_MS, self.update_from_arduino)
                    return 

                angle = max(min_angle, min(max_angle, angle))

                if angle <= min_angle + 5:  #margin
                    if self._jump_ready and not self.is_jumping: 
                        self.attempt_jump()
                        self._jump_ready = False 
                else:
                    self._jump_ready = True      

            except Exception:
                pass

        self.root.after(UPDATE_MS, self.update_from_arduino)

    # --- UPDATE LOOP ---
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return

        self.update_platforms()
        if self.is_jumping:
            self.ascend()

    # --- RESET ---
    def reset_game(self, reset_count=True):
        if reset_count:
            self.restart_count += 1 

        self.game_over = False
        self.is_jumping = False
        self.current_platform_index = 0
        self.jump_cooldown = 0
        self._jump_ready = True 

        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = self.Y_Ground - ROCKET_SIZE[1]
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)

        self.canvas.itemconfig(self.score_text, text="Plataform: 0/9")
        self.spawn_platforms()


    # --- END MENU ---
    def show_end_menu(self):
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300)
        c.pack()
        c.create_text(200, 100, text=" Mision Done! ", font=("Comic Sans MS", 18, "bold"), fill="black")
        Button(win, text="RESTART", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_game())).place(x=150, y=180)


# --- START MENU ---
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#2c3e50", outline="")
    canvas.create_text(WIDTH//2, 200, text="🚀 Rocket Extension Game 🌟",
                       font=("Comic Sans MS", 30, "bold"), fill="white")


    canvas.create_text(WIDTH // 2, 300,
                       text=("Extend your wrist to jump.\n"
                             "Land on all platforms to reach the star!\n"
                             "If you fail, you return to the starting position.\n"),                       
                        font=("Comic Sans MS", 16), fill="white", justify="center")
    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), RocketGame(root))).place(x=WIDTH // 2 - 60, y=500)

# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Rocket Extension Game")
    arduino = connect_arduino()
    if arduino:
        calibrate_potentiometer()
    else:
        print(" No Arduino detected. The game will use the space bar to play.")

    start_menu(root)
    root.mainloop()