import serial
import time
import sys
import glob
from tkinter import Tk, Toplevel, Canvas, Button, Scale, HORIZONTAL
from random import randint
from PIL import Image, ImageTk
import json
import os


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


# --- Tkinter setup ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore.json"

def load_highscore():
    print("Saving to:", os.path.join(os.path.dirname(__file__), "highscore.json"))
    """Load highscore from a JSON file located next to this script; create if missing."""
    try:
        file_path = os.path.join(os.path.dirname(__file__), "highscore.json")
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
    if score >= highscore:
        """Save highscore to a JSON file located next to this script using an atomic replace."""
        try:
            file_path = os.path.join(os.path.dirname(__file__), "highscore.json")
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
        except Exception as e:
            print("Error saving highscore:", e)
    else:
        # No update needed
        pass



highscore = load_highscore()


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

bg_photo         = load_image("game_background.jpg", (WIDTH, HEIGHT))
basket_photo     = load_image("basket.png", (80, 100), fallback="basket")
blue_bird_photo  = load_image("blue_bird.png", (70, 50), fallback="blue")
bomb_photo   = load_image("Bomb.png", (50, 50), fallback="red")

# --- Arduino detection ---
def find_arduino_port():
    """Automatically detect the Arduino serial port on any OS."""
    if sys.platform.startswith('win'):
        ports = [f'COM{i + 1}' for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.usb*')
    else:
        raise EnvironmentError('Unsupported platform')

    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            return port
        except (OSError, serial.SerialException):
            pass
    return None

def connect_arduino():
    """Try to connect to Arduino (non-blocking; flush startup backlog)."""
    global arduino
    port = find_arduino_port()
    if not port:
        print("No Arduino found. Basket will use keyboard control.")
        return None
    try:
        # timeout=0 makes reads non-blocking; readline() returns immediately if nothing available
        arduino = serial.Serial(port, 9600, timeout=0)
        time.sleep(2)  # allow board reset
        # Clear any noise/backlog accumulated during reset
        try:
            arduino.reset_input_buffer()
        except AttributeError:
            arduino.flushInput()
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
                canvas.delete(self.bird)
                bird_set()
            else:
                canvas.delete(self.bird)
                if self.color == "blue":
                    change_lives(-1)
                bird_set()
            return

        limit += 1
        self.canvas.move(self.bird, -speed_value, 0)
        self.canvas.after(10, self.move_bird)

class Basket:
    def __init__(self, canvas_obj, x, y):
        self.canvas = canvas_obj
        self.basket = canvas_obj.create_image(x, y, image=basket_photo, anchor="nw")

    def set_position(self, y):
        """Move basket to a specific y-coordinate."""
        global dist
        dist = int(y)
        self.canvas.coords(self.basket, 10, dist)

    def delete_basket(self):
        canvas.delete(self.basket)

# --- Functions ---
def bird_set():
    """Spawn a bird at a random y, blue 70% / red 30%."""
    y_value = randint(50, HEIGHT - 100)
    color = "blue" if randint(1, 10) <= 7 else "red"
    bird = Bird(canvas, WIDTH - 80, y_value, color)
    bird.move_bird()

def change_lives(amount):
    """Change lives and handle game over logic."""
    global lives, game_active, Total_lives_text, total_score, speed_value
    if not game_active:
        return
    
    lives += amount
    # Only update the canvas text if the text item exists
    if Total_lives_text is not None:
        canvas.itemconfig(Total_lives_text, text=f"Lives: {lives}")

    if lives == 0:
        game_active = False
        bar_obj.delete_basket()
        score_board("No lives left! Game Over!")
        save_highscore(total_score)
        total_score = 0
        lives = 3  # reset lives for next game
        speed_value = base_speed
        return
  
    

def change_score(amount):
    """Change score and handle win/lose logic."""
    global score, total_score, speed_value, game_active, level, base_speed

    if not game_active:
        return

    previous_score = score
    score += amount
    total_score += amount
    canvas.itemconfig(Level_score_text, text=f"Level Score: {score}")
    canvas.itemconfig(Total_score_text, text=f"Total Score: {total_score}")

    # Lose condition: score returns to 0 after having been >0
    if score == 0 and previous_score >= 0:
        game_active = False
        bar_obj.delete_basket()
        score_board("You reached 0 points again! Game Over!")
        total_score = 0
        level = 1
        speed_value = base_speed

    # Win condition: reach 30 points → next level
    elif score >= 30:
        game_active = False
        level += 1
        # Increase speed based on base speed from slider
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
    # Use Toplevel instead of a second Tk root
    top = Toplevel(root)
    top.title("Game Over")
    top.resizable(False, False)
    c2 = Canvas(top, width=400, height=350)
    c2.pack()

    # Text label and add a highscore line
    c2.create_text(
        200, 120,
        text=f"{message}\n\nYour score: {total_score}\n\nHighscore: {highscore}\n\n",
        font=("Comic Sans MS", 17, "bold"),
        fill="black",
        justify="center"
    )

    # Buttons
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
    # Place buttons
    c2.create_window(200, 220, window=btn_play)
    c2.create_window(200, 280, window=btn_exit)

def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    canvas.create_text(WIDTH // 2, 100, text=" Catch the Bird Game ",
                       font=("Comic Sans MS", 40, "bold"), fill="black")
#The player has three lives and they lose a life, if they are hit by bombs, or if they miss a bird
    canvas.create_text(WIDTH // 2, 220,
                       text="\n Blue bird = +1 point\nHit the bomb or miss a bird = -1 life\nYou have 3 lives\nIf you reach 30 points you level up!\nCatch blue birds, avoid bombs!",
                       font=("Comic Sans MS", 18), fill="black", justify="center")

    canvas.create_text(WIDTH // 2, 400, text="Select bird speed (0 - 6):",
                       font=("Comic Sans MS", 20), fill="black")

    speed_slider = Scale(canvas, from_=0, to=6, orient=HORIZONTAL, length=400,
                         font=("Comic Sans MS", 16))
    speed_slider.set(3)
    speed_slider.place(x=200, y=440)
    menu_widgets.append(speed_slider)

    play_button = Button(canvas, text="PLAY", font=("Comic Sans MS", 24, "bold"),
                         bg="green", fg="white",
                         command=lambda: start_game(speed_slider.get()))
    play_button.place(x=320, y=520)
    menu_widgets.append(play_button)

def start_game(selected_speed):
    global speed_value, base_speed, level
    base_speed = selected_speed
    speed_value = base_speed
    level = 1
    for widget in menu_widgets:
        widget.destroy()
    menu_widgets.clear()
    main()

def update_from_arduino():
    """Read potentiometer and move basket (consume backlog, use latest)."""
    if arduino:
        latest = None
        try:
            # Drain all currently queued lines and keep only the newest valid numeric one
            while True:
                if hasattr(arduino, "in_waiting"):
                    if arduino.in_waiting == 0:
                        break
                raw = arduino.readline()  # non-blocking due to timeout=0
                if not raw:
                    break
                s = raw.decode('utf-8', errors='ignore').strip()
                if not s:
                    continue
                try:
                    latest = float(s)
                except ValueError:
                    # Ignore partial / non-numeric lines
                    pass

            if latest is not None:
                angle = latest

                # Clamp to range (safety)
                angle = max(40, min(150, angle))

                # --- Screen mapping ---
                top_limit = 0
                bottom_limit = HEIGHT - 120  # basket height = 120

                # Normalize 40° → 0, 150° → 1
                normalized = (angle - 40) / (150 - 40)

                # Invert so higher angle = higher (top of screen)
                y_pos = bottom_limit - normalized * (bottom_limit - top_limit)

                # Clamp and apply
                y_pos = max(top_limit, min(bottom_limit, y_pos))
                bar_obj.set_position(int(y_pos))

        except Exception:
            # Keep loop alive on serial hiccups
            pass

    root.after(50, update_from_arduino)
def main():
    global bar_obj, total_score, score, dist, Total_score_text, Level_score_text, Total_lives_text, game_active, highscore
    game_active = True  # reset so birds move again
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

    # Clear any residual bytes before polling begins (belt & suspenders)
    if arduino:
        try:
            arduino.reset_input_buffer()
        except AttributeError:
            arduino.flushInput()

    bird_set()
    root.after(100, update_from_arduino)  # start reading potentiometer
    root.after(100, update_from_arduino)  # start reading potentiometer

# --- Run ---
connect_arduino()
start_menu()
root.mainloop()