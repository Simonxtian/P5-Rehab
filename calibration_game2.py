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
ButtonPress = 0
normalized = 0

# --- Calibration values ---
min_angle = 0
max_angle = 180

# --- Tkinter setup ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore.json"

def load_highscore():
    try:
        file_path = os.path.join(os.path.dirname(__file__), "highscore.json")
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
    if score >= highscore:
        try:
            file_path = os.path.join(os.path.dirname(__file__), "highscore.json")
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump({"highscore": int(score)}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception as e:
            print("Error saving highscore:", e)

highscore = load_highscore()

# --- Image loading ---
def load_image(path, size, fallback="rect"):
    try:
        img = Image.open(path).resize(size)
        return ImageTk.PhotoImage(img)
    except Exception:
        from PIL import ImageDraw
        img = Image.new("RGBA", size, (200, 200, 200, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, size[0]-1, size[1]-1), outline=(0, 0, 0), width=2)
        draw.text((10, size[1]//2 - 10), fallback, fill=(0, 0, 0))
        return ImageTk.PhotoImage(img)

bg_photo         = load_image("game_background.jpg", (WIDTH, HEIGHT))
basket_photo     = load_image("basket.png", (80, 100))
blue_bird_photo  = load_image("blue_bird.png", (70, 50))
bomb_photo       = load_image("Bomb.png", (50, 50))
explosion_photo  = load_image("Explosion.png", (80, 80))

# --- Arduino detection ---
def find_arduino_port():
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

# --- Classes ---
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
        bird_coords = canvas.coords(self.bird)
        if not bird_coords:
            return
        bird_x, bird_y = bird_coords[0], bird_coords[1]
        if bird_x <= 50:
            if dist - 15 <= bird_y <= dist + 100 + 15:
                if self.color == "blue":
                    change_score(+1)
                else:
                    change_lives(-1)
                    self.place_explosion(10, bird_y)
            else:
                if self.color == "blue":
                    change_lives(-1)
                    self.place_explosion(10, bird_y)
            canvas.delete(self.bird)
            bird_set()
            return
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
    canvas.itemconfig(Total_lives_text, text=f"Lives: {lives}")
    if lives == 0:
        game_active = False
        bar_obj.delete_basket()
        score_board("No lives left! Game Over!")
        save_highscore(total_score)

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
    elif event.keysym in ("Down", "s", "S"):
        dist = min(HEIGHT - 120, dist + 30)
    bar_obj.set_position(dist)

def score_board(message="Game Over!"):
    top = Toplevel(root)
    top.title("Game Over")
    c2 = Canvas(top, width=400, height=350)
    c2.pack()
    c2.create_text(200, 120, text=f"{message}\n\nYour score: {total_score}\n\nHighscore: {highscore}\n\n",
                   font=("Comic Sans MS", 17, "bold"), fill="black", justify="center")
    Button(c2, text="PLAY AGAIN", bg="green", fg="white",
           font=("Arial", 16, "bold"), command=lambda: [top.destroy(), main()]).place(x=130, y=220)
    Button(c2, text="EXIT", bg="red", fg="white",
           font=("Arial", 16, "bold"), command=lambda: root.destroy()).place(x=170, y=280)
    
def calibrate_potentiometer():
    """Manual calibration: user moves potentiometer freely; system detects min/max automatically."""
    global min_angle, max_angle
    min_angle, max_angle = 9999, -9999  # start with extreme values

    cal_win = Toplevel(root)
    cal_win.title("Potentiometer Calibration")
    cal_win.geometry("400x200")
    cal_win.resizable(False, False)
    cal_canvas = Canvas(cal_win, width=400, height=200)
    cal_canvas.pack()

    msg = cal_canvas.create_text(
        200, 50,
        text=" Move wrist freely\nPress SPACE when done",
        font=("Arial", 12),
        fill="black",
        width=380,
        justify="center"
    )
    angle_text = cal_canvas.create_text(
        200, 110,
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

    def update_calibration():
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
            # Update live display
            cal_canvas.itemconfig(angle_text, text=f"Angle: {latest:.2f}°")
            # Update min/max dynamically
            if latest < min_angle:
                min_angle = latest
            if latest > max_angle:
                max_angle = latest

        if cal_done["done"]:
            # Ensure a minimum range
            if max_angle - min_angle < 10:
                print(" Calibration range too small. Using default 0–180° range.")
                min_angle, max_angle = 0, 180
            cal_canvas.itemconfig(msg, text=f"✅ Done!\nMin: {min_angle:.2f}°, Max: {max_angle:.2f}°")
            root.after(1000, cal_win.destroy)
            print(f" Calibration done! Min: {min_angle:.2f}°, Max: {max_angle:.2f}°")
            return

        cal_win.after(20, update_calibration)

    update_calibration()
    root.wait_window(cal_win)

    
def update_from_arduino():
    global normalized
    if arduino:
        latest = None
        try:
            while True:
                raw = arduino.readline()
                if not raw:
                    break
                s = raw.decode('utf-8', errors='ignore').strip()
                if not s:
                    continue
                latest = float(s)
            if latest is not None:
                # Normalize using calibrated range
                normalized = (latest - min_angle) / (max_angle - min_angle)
                normalized = max(0, min(1, normalized))
                y_pos = (HEIGHT - 120) - normalized * (HEIGHT - 120)
                bar_obj.set_position(int(y_pos))
        except Exception:
            pass
    root.after(50, update_from_arduino)

def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")
    canvas.create_text(WIDTH // 2, 100, text="Catch the Bird Game",
                       font=("Comic Sans MS", 40, "bold"), fill="black")
    canvas.create_text(WIDTH // 2, 250, text="Move potentiometer to control basket.\nPress SPACE to start!",
                       font=("Comic Sans MS", 20), fill="black", justify="center")
    root.bind("<space>", lambda e: start_game())

def start_game():
    global speed_value, base_speed, level
    base_speed = 3
    speed_value = base_speed
    level = 1
    for widget in menu_widgets:
        widget.destroy()
    menu_widgets.clear()
    main()

def main():
    global bar_obj, total_score, score, dist, Total_score_text, Level_score_text, Total_lives_text, game_active, highscore
    game_active = True
    score = 0
    dist = 350
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")
    highscore = load_highscore()
    Total_lives_text = canvas.create_text(100, 30, text=f"Lives: {lives}", font=("Comic Sans MS", 20, "bold"))
    Total_score_text = canvas.create_text(480, 30, text=f"Total Score: {total_score}", font=("Comic Sans MS", 20, "bold"))
    Level_score_text = canvas.create_text(700, 30, text=f"Level Score: {score}", font=("Comic Sans MS", 20, "bold"))
    bar_obj = Basket(canvas, 10, dist)
    root.bind("<Up>", on_key_press)
    root.bind("<Down>", on_key_press)
    root.bind("<w>", on_key_press)
    root.bind("<s>", on_key_press)
    bird_set()
    root.after(100, update_from_arduino)

# --- Run ---
connect_arduino()
if arduino:
    calibrate_potentiometer()
start_menu()
root.mainloop()

