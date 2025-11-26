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
val_flexion = 0
val_extension = 1023

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
arduino = None
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

# --- Patient Data Defaults ---
PATIENT_ID = "guest"
PATIENT_NAME = "Guest"

# Check command line args
if len(sys.argv) >= 2:
    PATIENT_ID = sys.argv[1]
if len(sys.argv) >= 3:
    PATIENT_NAME = sys.argv[2]

# --- Tkinter setup ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Highscore handling ---
HIGHSCORE_FILE = "highscore_all.json"


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

    p_data = full_data.get(
        PATIENT_ID,
        {
            "name": PATIENT_NAME,
            "highscore": 0,
            "session_highscore": 0,
        },
    )

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
        except Exception:
            full_data = {}

    p_data = full_data.get(
        PATIENT_ID,
        {
            "name": PATIENT_NAME,
            "highscore": 0,
            "session_highscore": 0,
        },
    )

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
        except Exception:
            full_data = {}

    p_data = full_data.get(
        PATIENT_ID,
        {
            "name": PATIENT_NAME,
            "highscore": 0,
            "session_highscore": 0,
        },
    )

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


# --- CALIBRATION LOADING ---
def load_calibration():
    global val_flexion, val_extension
    try:
        game_dir = os.path.dirname(__file__)
        main_dir = os.path.dirname(game_dir)
        file_path = os.path.join(main_dir, "WristRehab", "calibration_data.json")
        with open(file_path, "r") as f:
            data = json.load(f)
            val_flexion = data.get("flexion", -45)
            val_extension = data.get("extension", 45)
    except Exception:
        val_flexion = -45
        val_extension = 45


# --- Image loading ---
def load_image(filename, size, fallback="rect"):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        img = Image.open(path).resize(size)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"Error loading image {filename}: {e}")
        from PIL import ImageDraw

        img = Image.new("RGBA", size, (200, 200, 200, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, size[0] - 1, size[1] - 1), outline=(0, 0, 0))
        return ImageTk.PhotoImage(img)


# FIXED: Just filenames
bg_photo = load_image("game_background.jpg", (WIDTH, HEIGHT))
basket_photo = load_image("basket.png", (80, 100), fallback="basket")
blue_bird_photo = load_image("blue_bird.png", (70, 50), fallback="blue")
bomb_photo = load_image("Bomb.png", (50, 50), fallback="red")
explosion_photo = load_image("Explosion.png", (80, 80), fallback="Explosion")


# --- Arduino detection ---
def find_arduino_port():
    if sys.platform.startswith("win"):
        ports = [f"COM{i + 1}" for i in range(256)]
    elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
        ports = glob.glob("/dev/tty[A-Za-z]*")
    elif sys.platform.startswith("darwin"):
        ports = glob.glob("/dev/cu.usb*")
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
        # Make serial reads non-blocking
        arduino = serial.Serial(port, 460800, timeout=0)
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
        self.explosion = canvas.create_image(
            Xcoord, Ycoord, anchor="nw", image=explosion_photo
        )
        self.canvas.update()
        self.canvas.after(500, lambda: self.canvas.delete(self.explosion))

    def move_bird(self):
        global limit, dist, game_active
        try:
            if not game_active:
                return
            offset = 15
            bird_coords = canvas.coords(self.bird)
            if not bird_coords:
                return
            bird_x, bird_y = bird_coords[0], bird_coords[1]

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
        except Exception:
            print("Not Worky")


class Basket:
    def __init__(self, canvas_obj, x, y):
        self.canvas = canvas_obj
        self.basket = canvas_obj.create_image(
            x, y, image=basket_photo, anchor="nw"
        )
        self.canvas.tag_raise(self.basket)

    def set_position(self, y):
        global dist
        dist = int(y)
        self.canvas.coords(self.basket, 10, dist)

    def delete_basket(self):
        canvas.delete(self.basket)


# --- Functions ---
def bird_set():
    if not game_active:
        return
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
        save_score_data(total_score)
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
        score_board(
            f"You reached {total_score} points!\nNext level unlocked!\n(Level {level})"
        )


def on_key_press(event):
    global dist
    if event.keysym in ("Up", "w", "W"):
        dist = max(0, dist - 30)
        bar_obj.set_position(dist)
    elif event.keysym in ("Down", "s", "S"):
        dist = min(HEIGHT - 120, dist + 30)
        bar_obj.set_position(dist)


def score_board(message="Game Over!"):
    # Use new saving logic
    new_hs = save_score_data(total_score)

    top = Toplevel(root)
    top.title("Game Over")
    top.resizable(False, False)
    c2 = Canvas(top, width=400, height=350)
    c2.pack()
    c2.create_text(
        200,
        120,
        text=f"{message}\n\nYour score: {total_score}\n\nHighscore: {new_hs}\n\n",
        font=("Comic Sans MS", 17, "bold"),
        fill="black",
        justify="center",
    )

    def _play_again():
        top.destroy()
        main()

    def _exit():
        top.destroy()
        root.destroy()

    btn_play = Button(
        c2,
        text="PLAY AGAIN",
        bg="green",
        fg="white",
        font=("Arial", 16, "bold"),
        command=_play_again,
    )
    btn_exit = Button(
        c2,
        text="EXIT",
        bg="red",
        fg="white",
        font=("Arial", 16, "bold"),
        command=_exit,
    )
    c2.create_window(200, 220, window=btn_play)
    c2.create_window(200, 280, window=btn_exit)

    def check_button_press_after():
        global ButtonPress, normalized
        # Do NOT call update_from_arduino() here; it already runs in its own loop
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
    canvas.create_text(
        WIDTH // 2,
        80,
        text=" Catch the Bird Game ",
        font=("Comic Sans MS", 40, "bold"),
        fill="black",
    )

    # Display Patient Name
    canvas.create_text(
        WIDTH // 2,
        150,
        text=f"Welcome, {PATIENT_NAME}!",
        font=("Arial", 24, "bold"),
        fill="darkblue",
    )

    canvas.create_text(
        WIDTH // 2,
        260,
        text=(
            "\n Blue bird = +1 point"
            "\nHit the bomb or miss a bird = -1 life"
            "\nYou have 3 lives"
            "\nIf you reach 30 points you level up!"
            "\nCatch blue birds, avoid bombs!"
        ),
        font=("Comic Sans MS", 18),
        fill="black",
        justify="center",
    )

    canvas.create_text(
        WIDTH // 2,
        400,
        text="Select bird speed (1 - 6):",
        font=("Comic Sans MS", 20),
        fill="black",
    )
    speed_slider = Scale(
        canvas,
        from_=1,
        to=6,
        orient=HORIZONTAL,
        length=400,
        font=("Comic Sans MS", 16),
    )
    speed_slider.set(3)
    speed_slider.place(x=200, y=440)
    menu_widgets.append(speed_slider)

    play_button = Button(
        canvas,
        text="PLAY",
        font=("Comic Sans MS", 24, "bold"),
        bg="green",
        fg="white",
        command=lambda: start_game(speed_slider.get()),
    )
    play_button.place(x=320, y=520)
    menu_widgets.append(play_button)

    if len(sys.argv) >= 2:
        back_button = Button(
            canvas,
            text="← Back to Launcher",
            font=("Comic Sans MS", 14),
            bg="#e74c3c",
            fg="white",
            command=lambda: root.destroy(),
        )
        back_button.place(x=10, y=10)
        menu_widgets.append(back_button)

    def check_auto():
        global ButtonPress, normalized


        speed_slider.set(max(1, min(6, int(normalized * 6) + 1)))


        if ButtonPress == 1:
            start_game(speed_slider.get())
        else:
            canvas.after(50, check_auto)

    check_auto()

    # Start Arduino polling loop ONCE from here
    canvas.after(50, update_from_arduino)


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
    global ButtonPress, normalized, angle, val_flexion, val_extension


    if arduino:
        try:
            raw = arduino.readline().decode('utf-8', errors='ignore').strip()
            if not raw:
                root.after(50, update_from_arduino)
                return


            split = raw.split(',')


            if len(split) >= 2:
                angle = float(split[0]) # grados reales, positivos o negativos
                btn = int(split[1]) # botón (0=presionado, 1=no presionado)
            else:
                angle = float(raw)
                btn = 1 # no presionado por defecto


            # --- BOTÓN CORREGIDO según tu lógica ---
            ButtonPress = 1 if btn == 0 else 0


            # --- Normalización usando calibración personalizada ---
            cal_min = min(val_flexion, val_extension)
            cal_max = max(val_flexion, val_extension)


            clamped = max(cal_min, min(cal_max, angle))
            normalized = (clamped - cal_min) / (cal_max - cal_min)


            # convertir normalized a posición vertical
            top_limit = 0
            bot_limit = HEIGHT - 120
            y_pos = bot_limit - normalized * (bot_limit - top_limit)
            y_pos = max(top_limit, min(bot_limit, y_pos))


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

    # Load patient specific highscore
    highscore = load_patient_data()

    Total_lives_text = canvas.create_text(
        100,
        30,
        text=f"Lives: {lives}",
        font=("Comic Sans MS", 20, "bold"),
        fill="black",
    )
    Total_score_text = canvas.create_text(
        480,
        30,
        text=f"Total Score: {total_score}",
        font=("Comic Sans MS", 20, "bold"),
        fill="black",
    )
    Level_score_text = canvas.create_text(
        700,
        30,
        text=f"Level Score: {score}",
        font=("Comic Sans MS", 20, "bold"),
        fill="black",
    )
    Highscore_text = canvas.create_text(
        260,
        30,
        text=f"Highscore: {highscore}",
        font=("Comic Sans MS", 20, "bold"),
        fill="black",
    )

    # Player Name in HUD
    canvas.create_text(
        WIDTH / 2,
        70,
        text=f"Player: {PATIENT_NAME}",
        font=("Arial", 12),
        fill="black",
    )

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
    # Do NOT start update_from_arduino() here; it's already running from start_menu()


connect_arduino()
load_calibration()
start_menu()
root.mainloop()
