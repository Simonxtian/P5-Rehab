import json
import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw

# --- CONFIG ---
HEIGHT, WIDTH = 700, 600
STAR_Y = 5 
PLATFORM_COUNT = 9 
PLATFORM_WIDTH, PLATFORM_HEIGHT = 180, 50
PLATFORM_MIN_SPEED, PLATFORM_MAX_SPEED = 1.5, 3.5
ARDUINO_BAUD = 115200
ROCKET_SIZE = (50, 70)  # (width, height)
Y_REF_BOTTOM = HEIGHT - 10  
Y_REF_TOP = STAR_Y          
TOTAL_VERTICAL_DISTANCE = (Y_REF_BOTTOM - Y_REF_TOP) 
JUMP_HEIGHT = (TOTAL_VERTICAL_DISTANCE / PLATFORM_COUNT) 
JUMP_SPEED = 25
UPDATE_MS = 25
val_recta = 0       
val_extension = 1023 
arduino = None
last_button_state = 0
ButtonPress = 0
extension_pct = 0.0

# --- Patient Data Defaults ---
PATIENT_ID = "guest"
PATIENT_NAME = "Guest"

# Check command line args: python extension.py <id> <name>
if len(sys.argv) >= 2:
    PATIENT_ID = sys.argv[1]
if len(sys.argv) >= 3:
    PATIENT_NAME = sys.argv[2]

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_extension.json"

def get_highscore_file_path():
    return os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)

def load_patient_data():
    """
    Loads the entire JSON, returns the specific data for PATIENT_ID.
    """
    file_path = get_highscore_file_path()
    full_data = {}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                full_data = json.load(f)
        except Exception as e:
            print("Error reading highscore file:", e)
            full_data = {}

    # Get patient entry or default
    p_data = full_data.get(PATIENT_ID, {
        "name": PATIENT_NAME, 
        "highscore": 0, 
        "session_highscore": 0
    })
    
    return p_data.get("highscore", 0)

def reset_session_highscore_for_patient():
    """
    Resets the session highscore for the current patient to 0 at game launch.
    """
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
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(full_data, f, indent=2)
        os.replace(tmp_path, file_path)
    except Exception as e:
        print("Error resetting session score:", e)

def save_score_data(current_score):
    """
    Updates the JSON file for PATIENT_ID.
    """
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

    # Update all-time highscore
    if current_score > p_data["highscore"]:
        p_data["highscore"] = int(current_score)
    
    # Update session highscore (track max of this session)
    if current_score > p_data["session_highscore"]:
        p_data["session_highscore"] = int(current_score)
    
    p_data["name"] = PATIENT_NAME
    full_data[PATIENT_ID] = p_data

    try:
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(full_data, f, indent=2)
        os.replace(tmp_path, file_path)
    except Exception as e:
        print("Error saving highscore:", e)

    return p_data["highscore"]

# Initialize scores
reset_session_highscore_for_patient()
highscore = load_patient_data()
current_session_highscore = 0  # Tracked in memory

# --- CALIBRATION LOADING ---
def load_calibration():
    global val_recta, val_extension
    val_recta = 0
    val_extension = 1023
    try:
        game_dir = os.path.dirname(__file__)
        main_dir = os.path.dirname(game_dir)
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")
        print(f"Looking for calibration at: {file_path}") 
        with open(file_path, "r") as f:
            data = json.load(f)
            val_recta = data.get("neutral", 0)
            val_extension = data.get("extension", 1023)
            print(f"Calibration Loaded: Initial Position={val_recta}, Extension={val_extension}")
    except FileNotFoundError:
        print(f"ERROR: File not found at: {file_path}")
    except Exception as e:
        print(f"Error loading calibration: {e}")

# --- IMAGE LOADER ---
def load_image(filename, size=None):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        img = Image.open(path).convert("RGBA")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
        if size:
            img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
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
        s = serial.Serial(port, ARDUINO_BAUD, timeout=0.1)
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
        self.last_button_state = 1
        self.root = root
        # --- FIX: Cancel all previous timers to prevent stacking and lag ---
        for after_id in self.root.tk.call("after", "info"):
            try:
                self.root.after_cancel(after_id)
            except:
                pass

        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        self.bg_img = load_image("space.png", (WIDTH, HEIGHT))
        self.rocket_img = load_image("rocket.png", ROCKET_SIZE)
        self.star_img = load_image("star.png", (50, 50))
        self.platform_img = load_image("platform.png", (PLATFORM_WIDTH, PLATFORM_HEIGHT))
        
        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)
        self.restart_count = 0 
        self.Y_Ground = Y_REF_BOTTOM
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = self.Y_Ground - ROCKET_SIZE[1] 
        self.rocket_item = self.canvas.create_image(self.rocket_x, self.rocket_y, image=self.rocket_img, anchor=NW)
        self.star_item = self.canvas.create_image(WIDTH // 2 - 25, STAR_Y, image=self.star_img, anchor=NW) 

        self.lives = 3
        self.current_score = 0  
        self.score_text = self.canvas.create_text(
            25, 10, text="Score: 0", font=("Arial", 16), fill="white", anchor=NW
        )
        self.lives_text = self.canvas.create_text(
            WIDTH - 90, 10, text=f"Lives: {self.lives}", font=("Arial", 16), fill="white", anchor=NW
        )
        
        # Display Patient Name
        self.canvas.create_text(WIDTH/2, 10, text=f"Player: {PATIENT_NAME}", 
                              font=("Arial", 12, "bold"), fill="yellow", anchor="n")

        root.bind("<space>", lambda e: self.attempt_jump())
        root.bind("<Left>", self.keyboard_move)
        root.bind("<Right>", self.keyboard_move)

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

    def spawn_platforms(self):
        for p in self.platforms:
            self.canvas.delete(p["id"])
            self.canvas.delete(p["id_img"])
        self.platforms.clear()
        bottom_y = self.Y_Ground
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

    def attempt_jump(self):
        if self.is_jumping or self.game_over: return
        current_time = time.time() * 1000
        if current_time - self.jump_cooldown < self.JUMP_COOLDOWN_MS: pass
        self.jump_cooldown = current_time
        next_index = self.current_platform_index + 1
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
        if not self.is_jumping: return
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

    def update_from_arduino(self):
        global val_recta, val_extension, ButtonPress, last_button_state, extension_pct
        try:
            if not self.arduino:
                return

            latest = None

            # Check if data is available before reading
            if self.arduino.in_waiting > 0:
                raw = self.arduino.readline()
                if not raw:
                    return
                s = raw.decode('utf-8', errors='ignore').strip()
                if not s:
                    return

                split = s.split(",")

                try:
                    if len(split) >= 4:
                        ButtonNumber = int(float(split[1]))
                        val = float(split[2])
                        #print("arduino:", ButtonNumber, val)
                        if ButtonNumber == 0 and self.last_button_state != 0:
                            ButtonPress = 1
                        elif ButtonNumber == 1:
                            ButtonPress = 0
                        self.last_button_state = ButtonNumber
                    else:
                        val = float(split[-1])
                except ValueError:
                    return
                latest = val

            if latest is not None:
                angle = latest
                cal_range = val_extension - val_recta
                if abs(cal_range) < 1:
                    extension_pct = 0.0
                else:
                    extension_pct = (angle - val_recta) / cal_range

                # threshold logic
                if extension_pct >= 0.7:
                    if self._jump_ready and not self.is_jumping:
                        self.attempt_jump()
                        self._jump_ready = False
                elif extension_pct < 0.7:
                    self._jump_ready = True

        except Exception as e:
            pass
        # schedule next poll
        self.root.after(UPDATE_MS, self.update_from_arduino)

    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return 
        self.update_platforms()
        if self.is_jumping:
            self.ascend()

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
        save_score_data(self.current_score)
        self.root.destroy()
    
    def show_game_over_menu(self):
        global highscore, ButtonPress, last_button_state
        new_hs = save_score_data(self.current_score)
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300) 
        c.pack()
        c.create_text(200, 60, text="GAME OVER!", font=("Comic Sans MS", 24, "bold"), fill="red")
        c.create_text(200, 110, text=f"Your Final Score: {self.current_score}", font=("Arial", 16), fill="black")
        c.create_text(200, 150, text=f"All-Time Highscore: {new_hs}", font=("Arial", 16), fill="blue")
        Button(win, text="PLAY AGAIN", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_game_full())).place(x=70, y=230, width=120, height=40)
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.root.destroy())).place(x=210, y=230, width=120, height=40)
        
        def poll_end_menu():
            global ButtonPress, extension_pct
            #print("Polling end menu:", ButtonPress, extension_pct)
            if ButtonPress == 1:
                if extension_pct >= 0.5:
                    self.exit_and_save()
                elif extension_pct < 0.5:
                    win.destroy()
                    self.reset_game_full()
            else:
                win.after(50, poll_end_menu)
        
        poll_end_menu()

    def show_end_menu(self):
        global ButtonPress, extension_pct, highscore
        new_hs = save_score_data(self.current_score)
        win = Toplevel(self.root)
        win.title("Level Complete!")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300) 
        c.pack()
        c.create_text(200, 60, text=" Mission Done! ", font=("Comic Sans MS", 18, "bold"), fill="black")
        c.create_text(200, 110, text=f"Your Current Score: {self.current_score}", font=("Arial", 16), fill="black")
        c.create_text(200, 150, text=f"All-Time Highscore: {new_hs}", font=("Arial", 16), fill="blue")
        Button(win, text="CONTINUE", bg="green", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.reset_level())).place(x=70, y=230, width=120, height=40)
        Button(win, text="EXIT", bg="red", fg="white", font=("Arial", 14, "bold"),
               command=lambda: (win.destroy(), self.exit_and_save())).place(x=210, y=230, width=120, height=40)
        
        def poll_end_menu():
            global ButtonPress, extension_pct
            #print("Polling end menu:", ButtonPress, extension_pct)
            if ButtonPress == 1:
                if extension_pct >= 0.5:
                    self.exit_and_save()
                elif extension_pct < 0.5:
                    win.destroy()
                    self.reset_level()
            else:
                win.after(50, poll_end_menu)
        
        poll_end_menu()

def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#2c3e50", outline="")
    canvas.create_text(WIDTH//2, 200, text=" Rocket Extension Game 🚀 ",
                        font=("Comic Sans MS", 30, "bold"), fill="white")
    
    # Display Patient Name
    canvas.create_text(WIDTH//2, 260, text=f"Welcome, {PATIENT_NAME}!", 
                       font=("Arial", 20, "bold"), fill="yellow")

    canvas.create_text(WIDTH // 2, 350,
                        text=("Extend your wrist to jump.\n"
                              "Land on all platforms to reach the star!\n"
                             "Each successful landing gives you 1 point.\n"
                             "If you fail, you lose a life.\n"
                             "You have 3 lives. Good luck!"),
                        font=("Arial", 16), fill="white")
    
    if len(sys.argv) >= 2:
        Button(canvas, text="← Back to Launcher", bg="#e74c3c", fg="white",
               font=("Arial", 12, "bold"),
               command=lambda: root.destroy()).place(x=10, y=10)
    
    Button(root, text="PLAY", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), RocketGame(root))).place(x=WIDTH // 2 - 60, y=500)
    
    def check_button_press():
        global ButtonPress, last_button_state
        
        if arduino:
            try:
                latest_line = None
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                latest_line = line

                if latest_line:
                    parts = latest_line.split(",")
                    if len(parts) >= 4:
                        ButtonNumber = int(float(parts[1]))
                        if ButtonNumber == 0 and last_button_state != 0:
                            ButtonPress = 1
                        elif ButtonNumber == 1:
                            ButtonPress = 0
                        last_button_state = ButtonNumber
            except Exception as e:
                print("Woopsy Daysies")

        if ButtonPress == 1:
            canvas.destroy()
            RocketGame(root)
        else:
            canvas.after(50, check_button_press)
    
    check_button_press()


if __name__ == "__main__":
    root = Tk()
    root.title("Rocket Extension Game")
    arduino = connect_arduino()
    load_calibration() 
    start_menu(root)
    root.mainloop()