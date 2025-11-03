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
bird_image = Image.open("bird.png").resize((70, 50))
basket_image = Image.open("basket.png").resize((80, 100))

# --- Tkinter window ---
root = Tk()
root.title("Catch the Bird")
root.resizable(False, False)

bg_photo = ImageTk.PhotoImage(bg_image)
bird_photo = ImageTk.PhotoImage(bird_image)
basket_photo = ImageTk.PhotoImage(basket_image)

canvas = Canvas(root, width=WIDTH, height=HEIGHT)
canvas.pack()

# --- Classes ---
class Bird:
    def __init__(self, canvas, x, y):
        self.canvas = canvas
        self.bird = canvas.create_image(x, y, image=bird_photo, anchor="nw")

    def move_bird(self):
        global limit, score, dist
        offset = 15
        bird_coords = canvas.coords(self.bird)
        bird_x, bird_y = bird_coords[0], bird_coords[1]

        if bird_x <= 50:
            if dist - offset <= bird_y <= dist + 100 + offset:
                canvas.delete(self.bird)
                score_increment()
                bird_set()
            else:
                canvas.delete(self.bird)
                bar_obj.delete_basket()
                score_board()
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
def bird_set():
    global limit
    limit = 0
    y_value = randint(50, HEIGHT - 100)
    bird = Bird(canvas, WIDTH - 80, y_value)
    bird.move_bird()

def score_increment():
    global score
    score += 10
    canvas.itemconfig(score_text, text=f"Score: {score}")

def on_key_press(event):
    if event.keysym in ("Up", "w", "W"):
        bar_obj.move_basket(1)
    elif event.keysym in ("Down", "s", "S"):
        bar_obj.move_basket(0)

def score_board():
    from tkinter import Button, Label
    root2 = Tk()
    root2.title("Game Over")
    root2.resizable(False, False)
    canvas2 = Canvas(root2, width=400, height=300)
    canvas2.pack()

    Label(canvas2, text=f"The bird escaped!\n\nYour score: {score}\n\n",
          font=("Comic Sans MS", 17, "bold")).pack()

    Button(canvas2, text="PLAY AGAIN", bg="green", fg="white", font=("Arial",16,"bold"),
           command=lambda: [root2.destroy(), main()]).pack(pady=10)
    Button(canvas2, text="EXIT", bg="red", fg="white", font=("Arial",16,"bold"),
           command=lambda: [root2.destroy(), root.destroy()]).pack(pady=10)

# --- Start menu ---
def start_menu():
    canvas.delete("all")
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")

    # Title text - Positioned near the top
    canvas.create_text(WIDTH // 2, 80, text=" Catch the Bird Game ",
                       font=("Comic Sans MS", 30, "bold"), fill="black")

    # Instructions - Positioned below the title
    canvas.create_text(WIDTH // 2, 170, # Increased y-coordinate to prevent overlap
                       text="Use UP/DOWN arrows or W/S to move the basket.\nCatch the bird to score points!",
                       font=("Comic Sans MS", 20), fill="black", justify="center", width=WIDTH-50) # Reduced font size for better fit

    # Speed slider label - Positioned below instructions
    canvas.create_text(WIDTH // 2, 280, text="Select bird speed (0 - 6):",
                       font=("Comic Sans MS", 20), fill="black") # Reduced font size

    # Speed slider widget
    speed_slider = Scale(canvas, from_=0, to=6, orient=HORIZONTAL, length=300, 
                         font=("Comic Sans MS", 20), troughcolor="lightblue", highlightbackground="white")
    speed_slider.set(3)
    # Centering the slider: (WIDTH - length) / 2
    slider_x = (WIDTH - 300) // 2 
    speed_slider.place(x=slider_x, y=320) # Adjusted x and y
    menu_widgets.append(speed_slider)

    # Play button
    play_button = Button(canvas, text="PLAY", font=("Comic Sans MS", 40, "bold"),
                         bg="green", fg="white", activebackground="darkgreen", activeforeground="white",
                         command=lambda: start_game(speed_slider.get()))
    # Centering the button: (WIDTH - button_width) / 2. This is an estimate.
    play_button.place(x=WIDTH//2 - 100, y=430) # Adjusted x and y
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
