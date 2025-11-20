import json
import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw

# --- CONFIG ---
HEIGHT, WIDTH = 700, 600
STAR_Y = 5  # Y coordinate of the top edge of the star
PLATFORM_COUNT = 9  # Total steps needed (8 platforms + 1 star)
PLATFORM_WIDTH, PLATFORM_HEIGHT = 180, 50
PLATFORM_MIN_SPEED, PLATFORM_MAX_SPEED = 1.5, 3.5
ARDUINO_BAUD = 9600
ROCKET_SIZE = (50, 70)  # (width, height)

# Vertical layout constants
Y_REF_BOTTOM = HEIGHT - 10  
Y_REF_TOP = STAR_Y          

TOTAL_VERTICAL_DISTANCE = (Y_REF_BOTTOM - Y_REF_TOP) 
JUMP_HEIGHT = (TOTAL_VERTICAL_DISTANCE / PLATFORM_COUNT) 

JUMP_SPEED = 25
UPDATE_MS = 25

# --- Calibration Globals ---
# Default values (will be overwritten by load_calibration)
val_recta = 0       # Start / Straight
val_extension = 1023 # Max Extension

arduino = None

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_extension.json"

def load_highscore():
    """Load highscore from a JSON file located next to this script; create if missing."""
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
    """Load session highscore from a JSON file located next to this script; create if missing."""
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

    # Load existing data
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Update global highscore
    if score >= highscore:
        data["highscore"] = int(score)

    # Update session highscore
    if score >= current_session_highscore:
        data["session_highscore"] = int(score)

    # Save updated dictionary atomically
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

    # Load existing data
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Reset session highscore
    data["session_highscore"] = 0

    # Save updated dictionary atomically
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
    """Loads calibration values from the sibling 'Calibration' folder."""
    global val_recta, val_extension
    
    # Default values
    val_recta = 0
    val_extension = 1023

    try:
        # 1. Get current folder
        game_dir = os.path.dirname(__file__)
        # 2. Go up one level
        main_dir = os.path.dirname(game_dir)
        # 3. Build path to Calibration folder
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")
        
        print(f"Looking for calibration at: {file_path}") 

        with open(file_path, "r") as f:
            data = json.load(f)
            # Load specifically Straight and Extension for this game
            val_recta = data.get("neutral", 0)
            val_extension = data.get("extension", 1023)
            print(f"Calibration Loaded: Initial Position={val_recta}, Extension={val_extension}")
            
    except FileNotFoundError:
        print(f"ERROR: File not found at: {file_path}")
        print("Using default values.")
    except Exception as e:
        print(f"Error loading calibration: {e}")


# --- IMAGE LOADER ---
def load_image(path, size=None):
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
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

        # Load assets (Paths kept as provided)
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

        # --- Lives and Score ---
        self.lives = 3
        self.current_score = 0  
        self.score_text = self.canvas.create_text(
            25, 10, text="Score: 0", font=("Arial", 16), fill="white", anchor=NW
        )
        self.lives_text = self.canvas.create_text(
            WIDTH - 90, 10, text=f"Lives: {self.lives}", font=("Arial", 16), fill="white", anchor=NW
        )

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
        self._jump_ready = True
        self.on_screen_message_id = None 

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

        # Generate 8 platforms (for steps 1 to 8)
        for i in range(1, PLATFORM_COUNT): 
            platform_top_y = bottom_y - (i * JUMP_HEIGHT)-30
            
            x = randint(0, WIDTH - PLATFORM_WIDTH)
            speed_boost = 1 + (self.restart_count * 0.1)
            speed = randint(int(PLATFORM_MIN_SPEED * 10), int(PLATFORM_MAX_SPEED * 10)) / 10.0
            speed *= speed_boost
            direction = choice([-1, 1])

            y = platform_top_y 

            pid_img = self.canvas.create_image(x, y, image=self.platform_img, anchor=NW)
            pid_rect = self.canvas.create_rectangle(x, y, x + PLATFORM_WIDTH, y + PLATFORM_HEIGHT, fill="", outline="")

            self.platforms.append({
                "id": pid_rect, "id_img": pid_img,
                "x": x, "y": y, "w": PLATFORM_WIDTH, "h": PLATFORM_HEIGHT,
                "speed": speed, "dir": direction
            })

        x_star = WIDTH // 2 - 25
        self.canvas.coords(self.star_item, x_star, Y_REF_TOP)


    def update_platforms(self):
        for p in self.platforms:
            if p["speed"] == 0: continue 
            p["x"] += p["dir"] * p["speed"]
            if p["x"] <= 0:
                p["x"] = 0; p["dir"] = 1
            elif p["x"] >= WIDTH - p["w"]:
                p["x"] = WIDTH - p["w"]; p["dir"] = -1

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
 
        # Check alignment
        if next_index < PLATFORM_COUNT: 
            next_p = self.platforms[next_index - 1] 
            if not self.check_platform_alignment(next_p):
                self.handle_failed_aim() 
                return
        
        elif next_index == PLATFORM_COUNT:
            star_x, star_y = self.canvas.coords(self.star_item)
            star_w, star_h = (50, 50)
            rocket_left = self.rocket_x
            rocket_right = self.rocket_x + self.rocket_w
            star_left = star_x
            star_right = star_x + star_w
            
            if not (rocket_right > star_left + 5 and rocket_left < star_right - 5):
                self.handle_failed_aim() 
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
                self.current_score += 1
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.current_score}")
                self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
                if target_index == PLATFORM_COUNT:
                    self.game_over = True 
                    self.show_end_menu() 
            else:
                self.handle_failed_landing() 

        if self.is_jumping:
            self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)

    # --- ARDUINO POLLING (UPDATED FOR EXTENSION) ---
    def update_from_arduino(self):
        global val_recta, val_extension

        if self.arduino:
            latest = None
            try:
                # 1. Read Raw Data
                while self.arduino.in_waiting > 0:
                    raw = self.arduino.readline()
                    if not raw: continue
                    s = raw.decode('utf-8', errors='ignore').strip()
                    if not s: continue
                    
                    # Robust number finding
                    split = s.split(" ")
                    try:
                        if len(split) >= 4 and split[2] == "Pot:":
                             val = float(split[3])
                        else:
                             val = float(s)
                        latest = val
                    except ValueError:
                        continue

                if latest is not None:
                    angle = latest
                    
                    # 2. Calculate Extension Percentage
                    cal_range = val_extension - val_recta
                    
                    # Avoid division by zero
                    if abs(cal_range) < 1: 
                        extension_pct = 0.0
                    else:
                        # This logic works regardless if extension > straight or extension < straight
                        # 0.0 = Straight (Start), 1.0 = Extended (End)
                        extension_pct = (angle - val_recta) / cal_range

                    # 3. Trigger Logic based on Percentage
                    # If extended more than 50% -> Trigger Jump
                    if extension_pct >= 0.5:
                         if self._jump_ready and not self.is_jumping:
                             self.attempt_jump()
                             self._jump_ready = False
                    
                    # If returned to near start (less than 20% extension) -> Reset Ready
                    elif extension_pct <= 0.2:
                         self._jump_ready = True

            except Exception as e:
                pass

        self.root.after(UPDATE_MS, self.update_from_arduino)

    # --- UPDATE LOOP ---
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return 

        self.update_platforms()
        if self.is_jumping:
            self.ascend()

    # --- HELPERS & MENUS ---
    def show_on_screen_message(self, text_to_show):
        if self.on_screen_message_id:
            self.canvas.delete(self.on_screen_message_id)
            self.on_screen_message_id = None 

        msg_id = self.canvas.create_text(
            WIDTH // 2, HEIGHT // 2 - 100, 
            text=text_to_show, font=("Arial", 28, "bold"),
            fill="red", justify="center"
        )
        self.on_screen_message_id = msg_id
        
        def clear_message():
            if self.on_screen_message_id == msg_id:
                self.canvas.delete(msg_id)
                self.on_screen_message_id = None
        self.root.after(1000, clear_message) 

    def handle_failed_aim(self):
        if self.is_jumping or self.game_over: return
        self.lives -= 1
        self.show_on_screen_message("MISSED!\n One life less") 
        self.canvas.itemconfig(self.lives_text, text=f"Lives: {self.lives}")
        if self.lives == 0:
            self.game_over = True
            self.show_game_over_menu()
    
    def handle_failed_landing(self):
        # This logic handles when the rocket jumps but misses the platform vertically or similar
        # For simplicity in this version, we treat it same as failed aim
        self.handle_failed_aim()

    def reset_level(self):
        self.game_over = False 
        self.is_jumping = False
        self.current_platform_index = 0
        self.jump_cooldown = 0
        self._jump_ready = True 
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = self.Y_Ground - ROCKET_SIZE[1]
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
        self.spawn_platforms()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.current_score}")

    def reset_game_full(self):
        self.lives = 3
        self.current_score = 0
        self.restart_count = 0
        self.canvas.itemconfig(self.lives_text, text=f"Lives: {self.lives}")
        self.canvas.itemconfig(self.score_text, text="Score: 0")
        self.reset_level() 

    def exit_and_save(self):
        save_highscore(self.current_score)
        self.root.destroy()
    
    def show_game_over_menu(self):
        global highscore
        save_highscore(self.current_score) 
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300) 
        c.pack()
        c.create_text(200, 60, text="GAME OVER!", font=("Comic Sans MS", 24, "bold"), fill="red")
        c.create_text(200, 110, text=f"Your Final Score: {self.current_score}", font=("Arial", 16), fill="black")
        c.create_text(200, 150, text=f"All-Time Highscore: {highscore}", font=("Arial", 16), fill="blue")
        Button(win, text="PLAY AGAIN", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_game_full())).place(x=70, y=230, width=120, height=40)
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.root.destroy())).place(x=210, y=230, width=120, height=40)

    def show_end_menu(self):
        global highscore
        if self.current_score > highscore:
            highscore = self.current_score
        win = Toplevel(self.root)
        win.title("Level Complete!")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300) 
        c.pack()
        c.create_text(200, 60, text=" Mision Done! ", font=("Comic Sans MS", 18, "bold"), fill="black")
        c.create_text(200, 110, text=f"Your Current Score: {self.current_score}", font=("Arial", 16), fill="black")
        c.create_text(200, 150, text=f"All-Time Highscore: {highscore}", font=("Arial", 16), fill="blue")
        Button(win, text="RESTART", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_level())).place(x=70, y=230, width=120, height=40)
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.exit_and_save())).place(x=210, y=230, width=120, height=40)


# --- START MENU ---
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#2c3e50", outline="")
    canvas.create_text(WIDTH//2, 200, text=" Rocket Extension Game 🚀 ",
                        font=("Comic Sans MS", 30, "bold"), fill="white")

    canvas.create_text(WIDTH // 2, 300,
                        text=("Extend your wrist to jump.\n"
                              "Land on all platforms to reach the star!\n"
                             "Each successful landing gives you 1 point.\n"
                             "If you fail, you lose a life.\n"
                             "You have 3 lives. Good luck!"),
                        font=("Arial", 16), fill="white")
    
    # Add Back to Launcher button if launched from game launcher
    if len(sys.argv) >= 3:
        Button(canvas, text="← Back to Launcher", bg="#e74c3c", fg="white",
               font=("Arial", 12, "bold"),
               command=lambda: root.destroy()).place(x=10, y=10)
    
    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), RocketGame(root))).place(x=WIDTH // 2 - 60, y=500)

# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Rocket Extension Game")
    arduino = connect_arduino()
    load_calibration() # Load shared calibration
    
    start_menu(root)
    root.mainloop()