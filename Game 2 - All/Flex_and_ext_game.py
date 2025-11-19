import serial
import time
import sys
import glob
from tkinter import Tk, Toplevel, Canvas, Button, Scale, HORIZONTAL
from random import randint
from PIL import Image, ImageTk
import json
import os

# --- Calibration Globals ---
# Default values (will be overwritten by load_calibration)
val_flexion = 0     # Bottom of screen
val_extension = 1023 # Top of screen

# --- Game constants ---
WIDTH, HEIGHT = 800, 600
speed_value = 3
base_speed = 3
limit = 0
dist = 350  # basket position (y)
score = 0
total_score = 0
bar_obj = None
Total_score_text = None
score_text = None
menu_widgets = []
arduino = None  # serial connection
level = 1
game_active = True
lives = 3
Total_lives_text = None
total_lives = 3
ButtonPress = 0
normalized = 0
raw = None
Previous = None
angle = None
current_session_highscore = 0

# --- Tkinter setup ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_all.json"

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

def save_highscore(score):
    global highscore, current_session_highscore
    """Save highscore to a JSON file located next to this script."""
    if score >= highscore:
        try:
            file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump({"highscore": int(score)}, f)
                f.flush()
                try: os.fsync(f.fileno())
                except Exception: pass
            os.replace(tmp_path, file_path)
        except Exception as e:
            print("Error saving highscore:", e)
    """save session highscore if higher than previous"""
    if score >= current_session_highscore: #currently overwrites highscore and only saves session highscore
        try:
            file_path = os.path.join(os.path.dirname(__file__), HIGHSCORE_FILE)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump({"session_highscore": int(score)}, f)
                f.flush()
                try: os.fsync(f.fileno())
                except Exception: pass
            os.replace(tmp_path, file_path)
        except Exception as e:
            print("Error saving highscore:", e)

highscore = load_highscore()

# --- CALIBRATION LOADING ---
def load_calibration():
    """Loads calibration values from the sibling 'Calibration' folder."""
    global val_flexion, val_extension
    
    val_flexion = 0
    val_extension = 1023

    try:
        # 1. Get folder of this script
        game_dir = os.path.dirname(__file__)
        # 2. Go up to main folder
        main_dir = os.path.dirname(game_dir)
        # 3. Build path to Calibration
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")
        
        print(f"Looking for calibration at: {file_path}")

        with open(file_path, "r") as f:
            data = json.load(f)
            # For this game we use the Full Range (Flexion -> Extension)
            val_flexion = data.get("flexion", 0)
            val_extension = data.get("extension", 1023)
            print(f"Calibration Loaded: Flexion={val_flexion}, Extension={val_extension}")
            
    except FileNotFoundError:
        print(f"ERROR: File not found at: {file_path}")
        print("Using defaults.")
    except Exception as e:
        print(f"Error loading calibration: {e}")
# --- Image loading (with safe fallbacks) ---

def load_image(path, size, fallback="rect"):
    try:
        img = Image.open(path).resize(size)
        return ImageTk.PhotoImage(img)
    except Exception:
        # simple fallback drawing to avoid crashes if file is missing
        from PIL import ImageDraw
        img = Image.new("RGBA", size, (200, 200, 200, 255))
        draw = ImageDraw.Draw(img)
        if fallback == "basket":
            draw.rectangle((0, 0, size[0]-1, size[1]-1), outline=(50, 50, 50), width=3)
            draw.text((10, size[1]//2 - 10), "Basket", fill=(0, 0, 0))
        elif fallback == "blue":
            draw.ellipse((0, 0, size[0]-1, size[1]-1), outline=(0, 0, 180), width=3)
            draw.text((10, size[1]//2 - 10), "Blue", fill=(0, 0, 180))
        elif fallback == "red":
            draw.ellipse((0, 0, size[0]-1, size[1]-1), outline=(180, 0, 0), width=3)
            draw.text((15, size[1]//2 - 10), "Red", fill=(180, 0, 0))
        else:
            draw.rectangle((0, 0, size[0]-1, size[1]-1), outline=(0, 0, 0), width=2)
        return ImageTk.PhotoImage(img)

bg_photo         = load_image(r"Game 2 - All\game_background.jpg", (WIDTH, HEIGHT))
basket_photo     = load_image(r"Game 2 - All\basket.png", (80, 100), fallback="basket")
blue_bird_photo  = load_image(r"Game 2 - All\blue_bird.png", (70, 50), fallback="blue")
bomb_photo       = load_image(r"Game 2 - All\Bomb.png", (50, 50), fallback="red")
explosion_photo  = load_image(r"Game 2 - All\Explosion.png", (80, 80), fallback="Explosion")


# --- Arduino detection ---
def find_arduino_port():
    if sys.platform.startswith('win'):
        ports = [f'COM{i + 1}' for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.usb*')
    else:
        return None

    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            return port
        except (OSError, serial.SerialException):
            pass
    return None

def connect_arduino():
    global arduino
    port = find_arduino_port()
    if not port:
        print("No Arduino found. Basket will use keyboard control.")
        return None
    try:
        arduino = serial.Serial(port, 9600, timeout=0)
        time.sleep(2)
        arduino.reset_input_buffer()
        print(f"Connected to Arduino on {port}")
        return arduino
    except Exception as e:
        print(f"Could not open serial port: {e}")
        arduino = None
        return None

# --- Game Classes ---
class Bird:
    def __init__(self, canvas_obj, x, y, color):
        self.canvas = canvas_obj
        self.color = color
        self.image = blue_bird_photo if color == "blue" else bomb_photo
        self.bird = canvas_obj.create_image(x, y, image=self.image, anchor="nw")
        self.explosion = None
    
    def place_explosion(self, Xcoord, Ycoord):
        self.explosion = canvas.create_image(Xcoord, Ycoord, anchor="nw", image=explosion_photo)
        self.canvas.update()
        self.canvas.after(500, lambda: self.canvas.delete(self.explosion))

    def move_bird(self):
        global limit, dist, game_active
        if not game_active:
            return
        offset = 15
        bird_coords = canvas.coords(self.bird)
        if not bird_coords:
            return
        bird_x, bird_y = bird_coords[0], bird_coords[1]

        # Reached the basket (left edge)
        if bird_x <= 50:
            if dist - offset <= bird_y <= dist + 100 + offset:
                if self.color == "blue":
                    change_score(+1)
                else:
                    change_lives(-1)
                    self.place_explosion(10, bird_y)
                canvas.delete(self.bird)
                bird_set()
            else:
                canvas.delete(self.bird)
                if self.color == "blue":
                    change_lives(-1)
                    self.place_explosion(10, bird_y)
                bird_set()
            return

        limit += 1
        self.canvas.move(self.bird, -speed_value, 0)
        self.canvas.after(10, self.move_bird)

class Basket:
    def __init__(self, canvas_obj, x, y):
        self.canvas = canvas_obj
        self.basket = canvas_obj.create_image(x, y, image=basket_photo, anchor="nw")
        self.canvas.tag_raise(self.basket)

    def set_position(self, y):
        global dist
        dist = int(y)
        self.canvas.coords(self.basket, 10, dist)

    def delete_basket(self):
        canvas.delete(self.basket)

# --- Functions ---
def bird_set():
    y_value = randint(50, HEIGHT - 100)
    color = "blue" if randint(1, 10) <= 7 else "red"
    bird = Bird(canvas, WIDTH - 80, y_value, color)
    bird.move_bird()
    canvas.tag_raise(bar_obj.basket)

def change_lives(amount):
    global lives, game_active, Total_lives_text, total_score, speed_value
    if not game_active:
        return
    
    lives += amount
    if Total_lives_text is not None:
        canvas.itemconfig(Total_lives_text, text=f"Lives: {lives}")

    if lives == 0:
        game_active = False
        bar_obj.delete_basket()
        score_board("No lives left! Game Over!")
        save_highscore(total_score)
        total_score = 0
        lives = 3 
        speed_value = base_speed
        return

def change_score(amount):
    global score, total_score, speed_value, game_active, level, base_speed

    if not game_active:
        return

    previous_score = score
    score += amount
    total_score += amount
    canvas.itemconfig(Level_score_text, text=f"Level Score: {score}")
    canvas.itemconfig(Total_score_text, text=f"Total Score: {total_score}")

    if score == 0 and previous_score >= 0:
        game_active = False
        bar_obj.delete_basket()
        score_board("You reached 0 points again! Game Over!")
        total_score = 0
        level = 1
        speed_value = base_speed

    elif score >= 30:
        game_active = False
        level += 1
        speed_value = base_speed + level - 1
        bar_obj.delete_basket()
        score_board(f"You reached {total_score} points!\nNext level unlocked!\n(Level {level})")

def on_key_press(event):
    global dist
    if event.keysym in ("Up", "w", "W"):
        dist = max(0, dist - 30)
        bar_obj.set_position(dist)
    elif event.keysym in ("Down", "s", "S"):
        dist = min(HEIGHT - 120, dist + 30)
        bar_obj.set_position(dist)

def score_board(message="Game Over!"):
    top = Toplevel(root)
    top.title("Game Over")
    top.resizable(False, False)
    c2 = Canvas(top, width=400, height=350)
    c2.pack()

    c2.create_text(
        200, 120,
        text=f"{message}\n\nYour score: {total_score}\n\nHighscore: {highscore}\n\n",
        font=("Comic Sans MS", 17, "bold"),
        fill="black",
        justify="center"
    )

    def _play_again():
        top.destroy()
        main()

    def _exit():
        top.destroy()
        root.destroy()

    btn_play = Button(c2, text="PLAY AGAIN", bg="green", fg="white",
                      font=("Arial", 16, "bold"), command=_play_again)
    btn_exit = Button(c2, text="EXIT", bg="red", fg="white",
                      font=("Arial", 16, "bold"), command=_exit)
    c2.create_window(200, 220, window=btn_play)
    c2.create_window(200, 280, window=btn_exit)

    def check_button_press_after():
        global ButtonPress, normalized
        update_from_arduino()
        if normalized > 0.5:
            if ButtonPress == 1:
                _play_again()
            else:
                root.after(50, check_button_press_after)
        else:
            if ButtonPress == 1:
                _exit()
            else:
                root.after(50, check_button_press_after)
    check_button_press_after()

def start_menu():
    global ButtonPress
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    canvas.create_text(WIDTH // 2, 100, text=" Catch the Bird Game ",
                        font=("Comic Sans MS", 40, "bold"), fill="black")

    canvas.create_text(WIDTH // 2, 220,
                        text="\n Blue bird = +1 point\nHit the bomb or miss a bird = -1 life\nYou have 3 lives\nIf you reach 30 points you level up!\nCatch blue birds, avoid bombs!",
                        font=("Comic Sans MS", 18), fill="black", justify="center")

    canvas.create_text(WIDTH // 2, 400, text="Select bird speed (1 - 6):",
                        font=("Comic Sans MS", 20), fill="black")

    speed_slider = Scale(canvas, from_=1, to=6, orient=HORIZONTAL, length=400,
                         font=("Comic Sans MS", 16))
    speed_slider.set(3)
    speed_slider.place(x=200, y=440)
    menu_widgets.append(speed_slider)

    play_button = Button(canvas, text="PLAY", font=("Comic Sans MS", 24, "bold"),
                         bg="green", fg="white",
                         command=lambda: start_game(speed_slider.get()))
    play_button.place(x=320, y=520)
    menu_widgets.append(play_button)
    
    # Back to Launcher button
    if len(sys.argv) >= 3:
        back_button = Button(canvas, text="← Back to Launcher", font=("Comic Sans MS", 14),
                             bg="#e74c3c", fg="white",
                             command=lambda: root.destroy())
        back_button.place(x=10, y=10)
        menu_widgets.append(back_button)

    def check_button_press_start():
        global ButtonPress
        update_from_arduino()
        
        if normalized < 1/6:
            speed_slider.set(1)
        elif normalized < 2/6:
            speed_slider.set(2)
        elif normalized < 3/6:
            speed_slider.set(3)
        elif normalized < 4/6:
            speed_slider.set(4)
        elif normalized < 5/6:
            speed_slider.set(5)
        elif normalized <= 6/6:
            speed_slider.set(6)

        if ButtonPress == 1:
            start_game(speed_slider.get())
        else:
            canvas.after(50, check_button_press_start)
    check_button_press_start()

def start_game(selected_speed):
    global speed_value, base_speed, level, ButtonPress
    base_speed = selected_speed
    speed_value = base_speed
    level = 1
    for widget in menu_widgets:
        widget.destroy()
    menu_widgets.clear()
    main()

def update_from_arduino():
    global ButtonPress, normalized, Previous, raw, angle, val_flexion, val_extension
    
    if arduino:
        latest = None
        try:
            while arduino.in_waiting > 0:
                raw = arduino.readline()
                if not raw: break
                s = raw.decode('utf-8', errors='ignore').strip()
                if not s: continue
                
                # Parsing logic (handles "Button: X Pot: Y" or just numbers)
                split = s.split(" ")
                try:
                    if len(split) >= 4 and split[2] == "Pot:":
                        PotNumber = float(split[3])
                        ButtonNumber = float(split[1])
                    else:
                        PotNumber = float(s)
                        ButtonNumber = 0 # Default if no button data
                    
                    latest = PotNumber
                    
                    if ButtonNumber == 2001:
                         ButtonPress = 1
                    elif ButtonNumber == 2000:
                         ButtonPress = 0
                except ValueError:
                    continue

            if latest is not None:
                angle = latest

                # --- MAPPING LOGIC ---
                # Calculate Total Range (Flexion to Extension)
                cal_range = val_extension - val_flexion
                
                if cal_range == 0:
                    normalized = 0.5
                else:
                    # 0.0 = Flexion (Bottom), 1.0 = Extension (Top)
                    # Clamp angle to calibrated limits
                    cal_min = min(val_flexion, val_extension)
                    cal_max = max(val_flexion, val_extension)
                    clamped_angle = max(cal_min, min(cal_max, angle))
                    
                    normalized = (clamped_angle - val_flexion) / cal_range

                # Map normalized value to Screen Y
                # normalized=0 (Flexion) -> Y=Bottom (Height - 120)
                # normalized=1 (Extension) -> Y=Top (0)
                top_limit = 0
                bottom_limit = HEIGHT - 120
                
                y_pos = bottom_limit - normalized * (bottom_limit - top_limit)

                # Clamp final position
                y_pos = max(top_limit, min(bottom_limit, y_pos))
                
                if bar_obj:
                    bar_obj.set_position(int(y_pos))

        except Exception:
            pass

    root.after(50, update_from_arduino)

def main():
    global bar_obj, total_score, score, dist, Total_score_text, Level_score_text, Total_lives_text, game_active, highscore
    game_active = True
    score = 0
    dist = 350

    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    highscore = load_highscore()

    Total_lives_text = canvas.create_text(100, 30, text=f"Lives: {lives}",
                                        font=("Comic Sans MS", 20, "bold"), fill="black")

    Total_score_text = canvas.create_text(480, 30, text=f"Total Score: {total_score}",
                                        font=("Comic Sans MS", 20, "bold"), fill="black")

    Level_score_text = canvas.create_text(700, 30, text=f"Level Score: {score}",
                                        font=("Comic Sans MS", 20, "bold"), fill="black")
    
    Highscore_text = canvas.create_text(260, 30, text=f"Highscore: {highscore}",
                                        font=("Comic Sans MS", 20, "bold"), fill="black")

    bar_obj = Basket(canvas, 10, dist)

    root.bind("<Up>", on_key_press)
    root.bind("<Down>", on_key_press)
    root.bind("<w>", on_key_press)
    root.bind("<s>", on_key_press)

    if arduino:
        try:
            arduino.reset_input_buffer()
        except AttributeError:
            arduino.flushInput()

    bird_set()
    root.after(100, update_from_arduino)

# --- Run ---
connect_arduino()
load_calibration() # Load centralized calibration

start_menu()
root.mainloop()