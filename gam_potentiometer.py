import serial
import time
import sys
import glob
from tkinter import Tk, Canvas, Button, Scale, HORIZONTAL
from random import randint
from PIL import Image, ImageTk

# --- Game constants ---
WIDTH, HEIGHT = 800, 600
speed_value = 3
limit = 0
dist = 350  # basket position
score = 0
bar_obj = None
score_text = None
menu_widgets = []
arduino = None  # serial connection


# --- Load images ---
bg_image = Image.open("game_background.jpg").resize((WIDTH, HEIGHT))
blue_bird_photo = Image.open("blue_bird.png").resize((70, 50))
red_bird_photo = Image.open("red_bird.png").resize((70, 50))
basket_image = Image.open("basket.png").resize((80, 100))

# --- Tkinter setup ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

bg_photo = ImageTk.PhotoImage(bg_image)
basket_photo = ImageTk.PhotoImage(basket_image)
blue_bird_photo = ImageTk.PhotoImage(blue_bird_photo)
red_bird_photo = ImageTk.PhotoImage(red_bird_photo)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Arduino detection ---
def find_arduino_port():
    """Automatically detect the Arduino serial port on any OS."""
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
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
    """Try to connect to Arduino."""
    global arduino
    port = find_arduino_port()
    if not port:
        print("No Arduino found. Basket will use keyboard control.")
        return None
    try:
        arduino = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)
        print(f"Connected to Arduino on {port}")
        return arduino
    except Exception as e:
        print(f"Could not open serial port: {e}")
        return None


# --- Game Classes ---
class Bird:
    def __init__(self, canvas, x, y, color):
        self.canvas = canvas
        self.color = color
        self.image = blue_bird_photo if color == "blue" else red_bird_photo
        self.bird = canvas.create_image(x, y, image=self.image, anchor="nw")

    def move_bird(self):
        global limit, score, dist
        offset = 15
        bird_coords = canvas.coords(self.bird)
        bird_x, bird_y = bird_coords[0], bird_coords[1]

        if bird_x <= 50:
            if dist - offset <= bird_y <= dist + 100 + offset:
                if self.color == "blue":
                    change_score(+1)
                    canvas.delete(self.bird)
                    bird_set()
                else:
                    change_score(-1)
                    canvas.delete(self.bird)
                    bar_obj.delete_basket()
                    score_board("You caught a red bird! ")
            else:
                canvas.delete(self.bird)
                if self.color == "blue":
                    bar_obj.delete_basket()
                    score_board("You missed a blue bird! ")
                else:
                    bird_set()
            return

        limit += 1
        self.canvas.move(self.bird, -speed_value, 0)
        self.canvas.after(10, self.move_bird)


class Basket:
    def __init__(self, canvas, x, y):
        self.canvas = canvas
        self.basket = canvas.create_image(x, y, image=basket_photo, anchor="nw")

    def set_position(self, y):
        """Move basket to a specific y-coordinate."""
        global dist
        dist = y
        self.canvas.coords(self.basket, 10, dist)

    def delete_basket(self):
        canvas.delete(self.basket)


# --- Functions ---
def bird_set():
    global limit
    limit = 0
    y_value = randint(50, HEIGHT - 100)
    color = "blue" if randint(1, 10) <= 7 else "red"
    bird = Bird(canvas, WIDTH - 80, y_value, color)
    bird.move_bird()


def change_score(amount):
    global score
    score += amount
    canvas.itemconfig(score_text, text=f"Score: {score}")


def on_key_press(event):
    if event.keysym in ("Up", "w", "W"):
        bar_obj.set_position(max(0, dist - 30))
    elif event.keysym in ("Down", "s", "S"):
        bar_obj.set_position(min(HEIGHT - 120, dist + 30))


def score_board(message="Game Over!"):
    from tkinter import Label
    root2 = Tk()
    root2.title("Game Over")
    root2.resizable(False, False)
    canvas2 = Canvas(root2, width=400, height=300)
    canvas2.pack()

    Label(canvas2, text=f"{message}\n\nYour score: {score}\n\n",
          font=("Comic Sans MS", 17, "bold")).pack()

    Button(canvas2, text="PLAY AGAIN", bg="green", fg="white", font=("Arial",16,"bold"),
           command=lambda: [root2.destroy(), main()]).pack(pady=10)
    Button(canvas2, text="EXIT", bg="red", fg="white", font=("Arial",16,"bold"),
           command=lambda: [root2.destroy(), root.destroy()]).pack(pady=10)


def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    canvas.create_text(WIDTH // 2, 100, text=" Catch the Bird Game ",
                       font=("Comic Sans MS", 40, "bold"), fill="black")

    canvas.create_text(WIDTH // 2, 220,
                       text="\nBlue bird = +1 point\nRed bird = -1 point and ends game\n\nCatch blue birds, avoid red ones!",
                       font=("Comic Sans MS", 18), fill="black", justify="center")

    canvas.create_text(WIDTH // 2, 400, text="Select bird speed (0 - 6):",
                       font=("Comic Sans MS", 20), fill="black")

    speed_slider = Scale(canvas, from_=0, to=6, orient=HORIZONTAL, length=400, font=("Comic Sans MS", 16))
    speed_slider.set(3)
    speed_slider.place(x=200, y=440)
    menu_widgets.append(speed_slider)

    play_button = Button(canvas, text="PLAY", font=("Comic Sans MS", 24, "bold"),
                         bg="green", fg="white", command=lambda: start_game(speed_slider.get()))
    play_button.place(x=320, y=520)
    menu_widgets.append(play_button)


def start_game(selected_speed):
    global speed_value
    speed_value = selected_speed
    for widget in menu_widgets:
        widget.destroy()
    menu_widgets.clear()
    main()


def update_from_arduino():
    """Read potentiometer and move basket."""
    if arduino and arduino.in_waiting > 0:
        try:
            str_line = arduino.readline().decode('utf-8', errors='ignore').strip()
            if str_line:
                angle = float(str_line)
                angle = max(40, min(150, angle))  # limit range
                normalized = (angle - 40) / (150 - 40)  # normalize to 0–1
                y_pos = HEIGHT - (normalized * (HEIGHT - 120))  # map to screen height
                bar_obj.set_position(int(y_pos))  # move basket
        except ValueError:
            pass
    root.after(50, update_from_arduino) 

def main():
    global bar_obj, score, dist, score_text
    score = 0
    dist = 350

    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    score_text = canvas.create_text(700, 30, text=f"Score: {score}",
                                    font=("Comic Sans MS", 20, "bold"), fill="black")

    bar_obj = Basket(canvas, 10, dist)

    root.bind("<Up>", on_key_press)
    root.bind("<Down>", on_key_press)
    root.bind("<w>", on_key_press)
    root.bind("<s>", on_key_press)

    bird_set()
    root.after(100, update_from_arduino)  # start reading potentiometer


# --- Run ---
connect_arduino()
start_menu()
root.mainloop()