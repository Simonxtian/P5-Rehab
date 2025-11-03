from tkinter import Tk, Canvas, Button, Scale, HORIZONTAL
from random import randint
from PIL import Image, ImageTk

# --- Global variables ---
WIDTH, HEIGHT = 800, 600
speed_value = 3
limit = 0
dist = 350
score = 0
bar_obj = None
score_text = None
menu_widgets = []

# --- Load images ---
bg_image = Image.open("game_background.jpg").resize((WIDTH, HEIGHT))
blue_bird_photo = Image.open("blue_bird.png").resize((70, 50))
red_bird_photo = Image.open("red_bird.png").resize((70, 50))
basket_image = Image.open("basket.png").resize((80, 100))

# --- Tkinter window ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

bg_photo = ImageTk.PhotoImage(bg_image)
basket_photo = ImageTk.PhotoImage(basket_image)
blue_bird_photo = ImageTk.PhotoImage(blue_bird_photo)
red_bird_photo = ImageTk.PhotoImage(red_bird_photo)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Classes ---
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

        # When bird reaches the basket zone
        if bird_x <= 50:
            if dist - offset <= bird_y <= dist + 100 + offset:
                # Blue bird adds points and keeps playing
                if self.color == "blue":
                    change_score(+1)
                    canvas.delete(self.bird)
                    bird_set()
                # Red bird subtracts points and ends game
                else:
                    change_score(-1)
                    canvas.delete(self.bird)
                    bar_obj.delete_basket()
                    score_board("You caught a red bird! ")
            else:
                # If missed bird
                canvas.delete(self.bird)
                if self.color == "blue":
                    # Missing blue bird = game over
                    bar_obj.delete_basket()
                    score_board("You missed a blue bird! ")
                else:
                    # Missing red bird = safe, continue
                    bird_set()
            return

        limit += 1
        self.canvas.move(self.bird, -speed_value, 0)
        self.canvas.after(10, self.move_bird)

class Basket:
    def __init__(self, canvas, x, y):
        self.canvas = canvas
        self.basket = canvas.create_image(x, y, image=basket_photo, anchor="nw")

    def move_basket(self, direction):
        global dist
        if direction == 1 and dist > 0:
            self.canvas.move(self.basket, 0, -30)
            dist -= 30
        elif direction == 0 and dist < HEIGHT - 120:
            self.canvas.move(self.basket, 0, 30)
            dist += 30

    def delete_basket(self):
        canvas.delete(self.basket)

# --- Functions ---
# More probable to be blue bird than red bird
def bird_set():
    global limit
    limit = 0
    y_value = randint(50, HEIGHT - 100)

    # Weighted probability: 70% blue, 30% red
    color = "blue" if randint(1, 10) <= 7 else "red"

    bird = Bird(canvas, WIDTH - 80, y_value, color)
    bird.move_bird()

def change_score(amount):
    """Change the score based on bird color"""
    global score
    score += amount
    canvas.itemconfig(score_text, text=f"Score: {score}")


def on_key_press(event):
    if event.keysym in ("Up", "w", "W"):
        bar_obj.move_basket(1)
    elif event.keysym in ("Down", "s", "S"):
        bar_obj.move_basket(0)

def score_board(message="Game Over!"):
    from tkinter import Button, Label
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
    

# --- Start menu ---
def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    # Title text
    canvas.create_text(WIDTH // 2, 100, text=" Catch the Bird Game ",
                       font=("Comic Sans MS", 40, "bold"), fill="black")

    # Instructions
    canvas.create_text(WIDTH // 2, 220,
                       text="\nBlue bird = +1 point\n Red bird = -1 point and ends game\n\nUse UP/DOWN arrows or W/S to move the basket.\nCatch the blue birds, avoid the red ones!",
                       font=("Comic Sans MS", 18), fill="black", justify="center")

    # Speed slider label
    canvas.create_text(WIDTH // 2, 400, text="Select bird speed (0 - 6):",
                       font=("Comic Sans MS", 20), fill="black")

    # Speed slider widget
    speed_slider = Scale(canvas, from_=0, to=6, orient=HORIZONTAL, length=400, font=("Comic Sans MS", 16))
    speed_slider.set(3)
    speed_slider.place(x=200, y=440)
    menu_widgets.append(speed_slider)

    # Play button
    play_button = Button(canvas, text="PLAY", font=("Comic Sans MS", 24, "bold"),
                         bg="green", fg="white", command=lambda: start_game(speed_slider.get()))
    play_button.place(x=320, y=520)
    menu_widgets.append(play_button)


def start_game(selected_speed):
    global speed_value
    speed_value = selected_speed

    # Destroy all menu widgets
    for widget in menu_widgets:
        widget.destroy()
    menu_widgets.clear()

    main()

# --- Main game function ---
def main():
    global bar_obj, score, dist, score_text
    score = 0
    dist = 350

    canvas.delete("all")
    canvas.create_image(0,0,image=bg_photo,anchor="nw")

    # Scoreboard
    score_text = canvas.create_text(700, 30, text=f"Score: {score}",
                                    font=("Comic Sans MS", 20, "bold"), fill="black")

    # Basket
    global bar_obj
    bar_obj = Basket(canvas, 10, dist)

    # Controls
    root.bind("<Up>", on_key_press)
    root.bind("<Down>", on_key_press)
    root.bind("<w>", on_key_press)
    root.bind("<s>", on_key_press)

    # Spawn first bird
    bird_set()

# --- Run ---
start_menu()
root.mainloop()
