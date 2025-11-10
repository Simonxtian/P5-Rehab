import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW, Toplevel
from PIL import Image, ImageTk, ImageDraw
import math

# --- CONFIG ---
# Invertido a vertical
HEIGHT, WIDTH = 800, 600
STAR_Y = 50 # Posición Y del objetivo
PLATFORM_COUNT = 12 # Más plataformas
PLATFORM_WIDTH, PLATFORM_HEIGHT = 180, 30 # Plataformas más grandes
PLATFORM_MIN_SPEED, PLATFORM_MAX_SPEED = 1.5, 4.0 # Plataformas MÓVILES horizontalmente
JUMP_HEIGHT = (HEIGHT - STAR_Y) / (PLATFORM_COUNT + 1) # Distancia a saltar
JUMP_SPEED = 40 # Velocidad del ascenso por tick (pixels/update)
UPDATE_MS = 25
ANGLE_MIN, ANGLE_MAX = 40.0, 150.0
ARDUINO_BAUD = 9600
ROCKET_SIZE = (50, 70)

# --- IMAGE LOADER (Mantenido) ---
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

# --- SERIAL UTILS (Mantenido) ---
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
        
        # Load assets
        self.bg_img = load_image(r"Game 3 - Extension\space.png", (WIDTH, HEIGHT))
        self.rocket_img = load_image(r"Game 3 - Extension\rocket.png", ROCKET_SIZE)
        self.star_img = load_image(r"Game 3 - Extension\star.png", (50, 50))
        self.platform_img = load_image(r"Game 3 - Extension\platform.png", (PLATFORM_WIDTH, PLATFORM_HEIGHT))

        self.canvas.create_image(0, 0, image=self.bg_img, anchor=NW)
        
        # Rocket initialization (bottom center)
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.rocket_y = HEIGHT - ROCKET_SIZE[1] - 10
        self.rocket_item = self.canvas.create_image(self.rocket_x, self.rocket_y, image=self.rocket_img, anchor=NW)
        
        # Star initialization (top center)
        self.star_item = self.canvas.create_image(WIDTH // 2 - 25, STAR_Y - 25, image=self.star_img, anchor=NW)

        # Score/Level display
        self.score_text = self.canvas.create_text(50, 24, text="Plataforma: 0/12", font=("Arial", 16), fill="white")
        self.level_text = self.canvas.create_text(WIDTH - 50, 24, text=f"Level: 1", font=("Arial", 16), fill="white")

        # Buttons
        self.jump_btn = Button(root, text="JUMP (Extensión)", command=self.attempt_jump)
        self.jump_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET", command=self.reset_game)
        self.reset_btn.pack(side="left", padx=10)

        # Controls
        root.bind("<space>", lambda e: self.attempt_jump())
        root.bind("<Left>", self.keyboard_move)
        root.bind("<Right>", self.keyboard_move)
        
        # Game variables
        self.current_platform_index = -1 # -1: Suelo, 0: Plataforma 1, etc.
        self.level = 1
        self.game_over = False
        self.arduino = connect_arduino()
        self.platforms = []
        self.rocket_w, self.rocket_h = ROCKET_SIZE
        self.vertical_offset = 0 
        self.is_jumping = False
        self.jump_end_offset = 0
        self.pot_normalized = 1.0 
        
        self.spawn_platforms()
        
        self.root.after(UPDATE_MS, self.update)
        
        if self.arduino:
            self.root.after(50, self.update_from_arduino)
        
        self.start_time = time.time()


    # --- PLATFORMS ---
    def spawn_platforms(self):
        for p in self.platforms:
            self.canvas.delete(p["id"])
            self.canvas.delete(p["id_img"])
        self.platforms.clear()
        
        y_step = JUMP_HEIGHT
        
        for i in range(PLATFORM_COUNT):
            y = self.rocket_y - ROCKET_SIZE[1] - (i + 1) * y_step
            x = randint(0, WIDTH - PLATFORM_WIDTH)
            
            # Plataformas móviles
            speed = PLATFORM_MIN_SPEED + (self.level - 1) * 0.5 + randint(0, 10) / 10 * (PLATFORM_MAX_SPEED - PLATFORM_MIN_SPEED)
            direction = choice([-1, 1])

            pid_rect = self.canvas.create_rectangle(x, y, x + PLATFORM_WIDTH, y + PLATFORM_HEIGHT, fill="", outline="")
            pid_img = self.canvas.create_image(x, y, image=self.platform_img, anchor=NW)
            
            self.platforms.append(dict(
                id=pid_rect, 
                id_img=pid_img,
                x=x, y=y, 
                w=PLATFORM_WIDTH, 
                h=PLATFORM_HEIGHT,
                speed=speed,
                dir=direction
            ))
        
        self.platforms.sort(key=lambda p: p['y'], reverse=True)


    def update_platforms(self):
        for p in self.platforms:
            # Movimiento horizontal de la plataforma
            p["x"] += p["dir"] * p["speed"]
            
            # Rebotar en los bordes
            if p["x"] < 0:
                p["x"] = 0
                p["dir"] = 1
            elif p["x"] > WIDTH - p["w"]:
                p["x"] = WIDTH - p["w"]
                p["dir"] = -1
                
            # Ajustar la posición vertical de la imagen y el rectángulo por el offset
            y_adjusted = p["y"] - self.vertical_offset
            self.canvas.coords(p["id_img"], p["x"], y_adjusted)
            self.canvas.coords(p["id"], p["x"], y_adjusted, p["x"] + p["w"], y_adjusted + p["h"])


    # --- CONTROLS ---
    def keyboard_move(self, event):
        if self.game_over or self.is_jumping: return
        step = 10
        if event.keysym == 'Left':
            self.rocket_x = max(0, self.rocket_x - step)
        elif event.keysym == 'Right':
            self.rocket_x = min(WIDTH - self.rocket_w, self.rocket_x + step)
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
        
    def check_platform_alignment(self, platform):
        # Comprueba si el cohete está horizontalmente sobre la plataforma
        rocket_left = self.rocket_x
        rocket_right = self.rocket_x + self.rocket_w
        platform_left = platform["x"]
        platform_right = platform["x"] + platform["w"]
        
        # El cohete debe superponerse completamente a la plataforma
        return (rocket_right > platform_left and rocket_left < platform_right)

    def attempt_jump(self):
        if self.game_over or self.is_jumping: return
        
        # 1. Condición de Extensión: Solo permite saltar si el potenciómetro está en Extensión (ángulo bajo)
        if self.arduino and self.pot_normalized > 0.2:
            print(f"Jump failed: Requires Extension (angle < {ANGLE_MIN + (ANGLE_MAX - ANGLE_MIN)*0.2:.1f}°)")
            return
        
        # 2. Identificar la siguiente plataforma objetivo
        next_index = self.current_platform_index + 1
        
        if next_index >= PLATFORM_COUNT:
             # Salto final a la estrella
             self.jump_end_offset = HEIGHT - STAR_Y - ROCKET_SIZE[1] # Distancia a la estrella
             self.is_jumping = True
             self.current_platform_index = next_index
             return
        
        next_platform = self.platforms[next_index]
        
        # 3. Condición de Alineación Horizontal
        if not self.check_platform_alignment(next_platform):
            print("Jump failed: Rocket is not aligned with the platform.")
            return

        # 4. Iniciar el ascenso
        self.current_platform_index = next_index
        
        # La distancia vertical es fija, hasta la base de la plataforma
        self.jump_end_offset = self.vertical_offset + JUMP_HEIGHT 
        self.is_jumping = True
        
        self.canvas.itemconfig(self.score_text, text=f"Plataforma: {self.current_platform_index}/{PLATFORM_COUNT}")

    
    def ascend(self):
        # Mover el fondo verticalmente
        if not self.is_jumping: return
        
        # Calcular el destino vertical basado en el offset del suelo
        target_offset = self.vertical_offset + JUMP_HEIGHT
        
        # Si es el último salto (a la estrella)
        if self.current_platform_index > PLATFORM_COUNT:
             target_offset = self.jump_end_offset

        remaining_vertical_jump = target_offset - self.vertical_offset
        
        # 1. Movimiento Vertical (Fondo)
        if remaining_vertical_jump <= JUMP_SPEED:
            move_y = remaining_vertical_jump
            self.is_jumping = False # Finalizar el salto
        else:
            move_y = JUMP_SPEED

        self.vertical_offset += move_y
            
        # Mover la estrella y las plataformas para simular el ascenso del cohete
        self.canvas.move(self.star_item, 0, move_y)
        for p in self.platforms:
            self.canvas.move(p["id_img"], 0, move_y)
            self.canvas.move(p["id"], 0, move_y)
            
        # 2. Comprobación Final (si ya no está saltando)
        if not self.is_jumping:
            # Si hemos llegado al final (la estrella)
            if self.current_platform_index > PLATFORM_COUNT:
                self.game_over = True
                self.root.after(500, self.show_end_menu)
            else:
                 # El cohete aterriza en la posición horizontal donde estaba
                 pass


    # --- ARDUINO POLLING ---
    def update_from_arduino(self):
        if self.arduino:
            latest = None
            try:
                while True:
                    raw = self.arduino.readline()
                    if not raw: break
                    s = raw.decode('utf-8', errors='ignore').strip()
                    if not s: continue
                    try:
                        angle = float(s)
                        latest = angle
                    except ValueError: continue 

                if latest is not None:
                    angle = max(ANGLE_MIN, min(ANGLE_MAX, latest))
                    self.pot_normalized = (angle - ANGLE_MIN) / (ANGLE_MAX - ANGLE_MIN)
                    
                    # Mover el cohete horizontalmente con el potenciómetro
                    max_x = WIDTH - self.rocket_w
                    target_x_by_pot = max_x * self.pot_normalized
                    self.rocket_x = int(max(0, min(max_x, target_x_by_pot)))
                    
                    self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
                    
            except Exception as e:
                pass

        self.root.after(50, self.update_from_arduino)


    # --- UPDATE LOOP ---
    def update(self):
        self.root.after(UPDATE_MS, self.update)
        if self.game_over: return
        
        # 1. Mover plataformas horizontalmente
        self.update_platforms()

        # 2. Ascenso/Salto
        if self.is_jumping:
            self.ascend()
        
        # 3. Comprobar si ha llegado a la estrella
        if self.vertical_offset >= HEIGHT - STAR_Y - ROCKET_SIZE[1]:
            self.game_over = True
            self.root.after(500, self.show_end_menu)
        
        
    def reset_game(self):
        self.current_platform_index = -1
        self.level = 1
        self.vertical_offset = 0
        self.is_jumping = False
        self.jump_end_offset = 0
        self.game_over = False
        self.start_time = time.time()

        # Reiniciar cohete
        self.rocket_x = WIDTH // 2 - ROCKET_SIZE[0] // 2
        self.canvas.coords(self.rocket_item, self.rocket_x, self.rocket_y)
        
        # Reiniciar estrella (moverla a su posición original)
        self.canvas.coords(self.star_item, WIDTH // 2 - 25, STAR_Y - 25)
        
        # Regenerar plataformas
        self.spawn_platforms()
        
        self.canvas.itemconfig(self.score_text, text=f"Plataforma: 0/{PLATFORM_COUNT}")
        self.canvas.itemconfig(self.level_text, text=f"Level: {self.level}")


    # --- END MENU ---
    def show_end_menu(self):
        self.game_over = True
        total_time = round(time.time() - self.start_time, 1)
        win = Toplevel(self.root)
        win.title("Game Over")
        win.resizable(False, False)
        c = Canvas(win, width=400, height=300)
        c.pack()
        
        if self.vertical_offset >= HEIGHT - STAR_Y - ROCKET_SIZE[1]:
            msg = f"🌟 ¡Misión Cumplida! 🌟\n\n Tiempo total: {total_time} segundos"
            
            def _play_again():
                win.destroy()
                self.level += 1
                self.reset_game()
            
            play_btn_text = "SIGUIENTE NIVEL"
            play_btn_command = _play_again
            
        else:
            msg = f"🚀 Juego Terminado\n\nTiempo transcurrido: {total_time} segundos"
            
            def _play_again():
                win.destroy()
                self.reset_game()
                
            play_btn_text = "REINTENTAR"
            play_btn_command = _play_again
            
        c.create_text(200, 100, text=msg, font=("Comic Sans MS", 18, "bold"), fill="black")

        Button(win, text=play_btn_text, bg="green", fg="white",
            font=("Arial", 14, "bold"), command=play_btn_command).place(x=120, y=180)
        Button(win, text="SALIR", bg="red", fg="white", font=("Arial", 14, "bold"),
            command=self.root.destroy).place(x=250, y=180)

# --- START MENU ---
def start_menu(root):
    canvas = Canvas(root, width=WIDTH, height=HEIGHT)
    canvas.pack()
    canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#2c3e50", outline="")
    canvas.create_text(WIDTH//2, 150, text="🚀 Rocket Extensión Game 🌟",
                       font=("Comic Sans MS", 30, "bold"), fill="white")
    canvas.create_text(WIDTH//2, 300,
                       text=("Mueve el cohete horizontalmente con la muñeca para alinearte.\n"
                             "Para **SALTAR** (ascenso vertical) a la siguiente plataforma, debes:\n"
                             "1. Estar **alineado horizontalmente** sobre la plataforma móvil.\n"
                             "2. Ejecutar la **EXTENSIÓN** de muñeca (ángulo bajo).\n"
                             "Las plataformas se mueven continuamente de izquierda a derecha.\n"
                             "**EXTENSIÓN ({:.1f}°):** Permite saltar. **FLEXIÓN ({:.1f}°):** No permite saltar.".format(ANGLE_MIN, ANGLE_MAX)),
                       font=("Comic Sans MS", 16), fill="white", justify="center")
    Button(root, text="JUGAR", bg="green", fg="white", font=("Comic Sans MS", 24, "bold"),
           command=lambda: (canvas.destroy(), RocketGame(root))).place(x=WIDTH//2 - 60, y=500)

# --- MAIN ---
if __name__ == "__main__":
    root = Tk()
    root.title("Rocket Extension Game")
    start_menu(root)
    root.mainloop()