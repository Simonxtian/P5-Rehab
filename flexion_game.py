import os, sys, time, glob, serial
from random import randint, choice
from tkinter import Tk, Canvas, Button, NW
from PIL import Image, ImageTk

# --- CONFIG ---
WIDTH, HEIGHT = 800, 600
ROD_Y = 20
ROD_SWEEP_SPEED = 4
ROPE_MAX_LEN = HEIGHT - 60
UPDATE_MS = 25
ANGLE_MIN, ANGLE_MAX = 40.0, 150.0
ARDUINO_BAUD = 9600

OBJECT_TYPES = [
    ("gold", "gold.png", +5),
    ("fish", "fish.png", +2),
    ("trash", "trash.png", -3)
]
NUM_OBJECTS = 20 # INCREASED OBJECT COUNT

# --- IMAGE LOADER ---
def load_image(path, size=None):
    try:
        img = Image.open(path).convert("RGBA")
        # Ensure Image.ANTIALIAS is used for compatibility if PIL is older
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image.Resampling, 'LANCZOS') else Image.ANTIALIAS
        if size: img = img.resize(size, resample_filter)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        from PIL import ImageDraw
        w, h = size if size else (60,60)
        img = Image.new("RGBA", (w,h), (200,200,200,255))
        d = ImageDraw.Draw(img)
        d.rectangle((0,0,w-1,h-1), outline=(0,0,0))
        d.text((10,h//2-8), "missing", fill=(0,0,0))
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
        print("No Arduino found (test mode only).")
        return None
    try:
        s = serial.Serial(port, ARDUINO_BAUD, timeout=0)
        time.sleep(2)
        try: s.reset_input_buffer()
        except: pass
        print("Connected to Arduino:", port)
        return s
    except Exception as e:
        print("Serial error:", e)
        return None

# --- GAME CLASS ---
class FishingGame:
    def __init__(self, root):
        self.root = root
        self.canvas = Canvas(root, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        self.bg_img = load_image("sea.png", (WIDTH, HEIGHT))
        self.rod_img = load_image("fishing_rod.png", (90, 90)) # NEW SIZE
        self.obj_imgs = {
            "gold": load_image("gold.png", (60,60)),
            "fish": load_image("fish.png", (60,60)),
            "trash": load_image("trash.png", (60,60)),
        }

        self.rod_x = 100
        self.rod_dir = 1
        self.rope_len = 0
        self.sweeping = True
        self.rope_extending = False
        self.stopped = False
        self.score = 0
        self.arduino = connect_arduino()
        self.objects = []

        self.canvas.create_image(0,0, image=self.bg_img, anchor=NW)
        self.rod_item = self.canvas.create_image(self.rod_x, ROD_Y, image=self.rod_img, anchor=NW)
        self.rope_item = self.canvas.create_line(0,0,0,0, width=3, fill="white")
        self.score_text = self.canvas.create_text(80, 24, text=f"Score: {self.score}", font=("Arial",16), fill="black")

        # Buttons updated to use the new toggle function
        self.stop_btn = Button(root, text="STOP/RESUME", command=self.toggle_sweep)
        self.stop_btn.pack(side="left", padx=10)
        self.reset_btn = Button(root, text="RESET", command=self.reset_round)
        self.reset_btn.pack(side="left", padx=10)
        # self.sim_btn is removed

        # New Keyboard Bindings
        root.bind("<space>", lambda e: self.toggle_sweep())
        root.bind("<w>", self.adjust_rope)
        root.bind("<s>", self.adjust_rope)
        root.bind("<Up>", self.adjust_rope)
        root.bind("<Down>", self.adjust_rope)
        
        # Remove old 'f' binding
        # root.bind("f", lambda e: self.simulate_flex())

        self.spawn_objects()
        self.root.after(UPDATE_MS, self.update)

    def spawn_objects(self):
        # Clear existing objects on canvas before clearing list
        for obj in self.objects:
            self.canvas.delete(obj["id"])
        self.objects.clear()
        
        margin = 40
        # Calculate a reasonable spacing (though we are using random X/Y now)
        spacing = (WIDTH - 2*margin)//NUM_OBJECTS
        
        for i in range(NUM_OBJECTS):
            typ, imgname, pts = choice(OBJECT_TYPES)
            img = self.obj_imgs[typ]
            w,h = img.width(), img.height()
            
            # Use random placement within bounds
            x = randint(margin, WIDTH - margin - w)
            # FLOATING LOGIC: Spawn objects randomly between Y=300 and Y=550
            y = randint(300, 550)
            
            oid = self.canvas.create_image(x,y,image=img,anchor=NW)
            self.objects.append(dict(id=oid,type=typ,x=x,y=y,w=w,h=h,pts=pts))

    def toggle_sweep(self):
        """Toggles the rod's left-right sweeping motion (Spacebar/Button)."""
        # If currently sweeping, STOP it.
        if self.sweeping:
            self.sweeping = False
            self.stopped = True
        # If currently stopped, RESUME it (unless rope is actively extending/retrieving).
        elif self.stopped and not self.rope_extending:
            self.sweeping = True
            self.stopped = False

    # Renamed/Replaced the original stop_rod() function
    # def stop_rod(self):
    #     if self.sweeping:
    #         self.sweeping = False
    #         self.stopped = True

    def reset_round(self):
        self.sweeping = True
        self.stopped = False
        self.rope_len = 0
        self.spawn_objects()
        self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")

    def adjust_rope(self, event):
            """Manually controls rope length if Arduino is not connected and rod is stopped."""
            if self.arduino is not None or not self.stopped:
                return

            step = 15 # Rope adjustment speed

            if event.keysym in ('w', 'Up'):
                self.rope_len = max(0, self.rope_len - step)
            elif event.keysym in ('s', 'Down'):
                self.rope_len = min(ROPE_MAX_LEN, self.rope_len + step)

            # Check for hit immediately
            if self.check_hit():
                # If hit, stop manual movement and initiate resume sequence
                self.stopped = False
                # Call new method to retract rope and resume sweep after a short delay
                self.root.after(700, self.finish_catch_and_resume) 
                
            self.update_rope()
        
    def simulate_flex(self):
        # Kept for compatibility if you want to use the button, but removed binding
        if self.sweeping: return
        self.rope_extending = True
        self._sim_step()

    def _sim_step(self):
        if not self.rope_extending: return
        self.rope_len += 12
        self.update_rope()
        if self.check_hit(): self.rope_extending=False; return
        if self.rope_len >= ROPE_MAX_LEN: self.rope_extending=False; return
        self.root.after(30, self._sim_step)

    def read_angle(self):
        if not self.arduino: return None
        latest = None
        try:
            while True:
                if hasattr(self.arduino,"in_waiting") and self.arduino.in_waiting==0:
                    break
                raw = self.arduino.readline()
                if not raw: break
                try:
                    latest = float(raw.decode().strip())
                except: pass
        except: return None
        return latest

    def angle_to_len(self, a):
        a = max(ANGLE_MIN,min(ANGLE_MAX,a))
        norm = (a - ANGLE_MIN)/(ANGLE_MAX-ANGLE_MIN)
        return int(norm * ROPE_MAX_LEN)

    def rod_tip(self):
        """Approximate hook position relative to image"""
        bx,by,_,_ = self.canvas.bbox(self.rod_item)
        w,h = self.rod_img.width(), self.rod_img.height()
        # NEW OFFSETS for 90x90 image
        tip_x = bx + w - 10
        tip_y = by + h - 15
        return tip_x, tip_y

    def update_rope(self):
        tip_x, tip_y = self.rod_tip()
        end_x, end_y = tip_x, tip_y + self.rope_len
        self.canvas.coords(self.rope_item, tip_x, tip_y, end_x, end_y)

    def check_hit(self):
        tip_x, tip_y = self.rod_tip()
        end_y = tip_y + self.rope_len
        for obj in list(self.objects):
            ox1,oy1,ox2,oy2 = obj["x"],obj["y"],obj["x"]+obj["w"],obj["y"]+obj["h"]
            if ox1 <= tip_x <= ox2 and end_y >= oy1:
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
                self.score += obj["pts"]
                self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")
                self.canvas.create_text((ox1+ox2)//2, oy1-20,
                                        text=f"{obj['pts']:+}", font=("Arial",14,"bold"), fill="black")
                return True
        return False
    def finish_catch_and_resume(self):
            """Resets the rope and restarts the rod sweeping motion."""
            self.set_rope(0)
            self.sweeping = True
            self.stopped = False

    def update(self):
        if self.sweeping:
            self.rod_x += self.rod_dir * ROD_SWEEP_SPEED
            if self.rod_x < 0: self.rod_x=0; self.rod_dir=1
            if self.rod_x > WIDTH - self.rod_img.width():
                self.rod_x = WIDTH - self.rod_img.width(); self.rod_dir=-1
            self.canvas.coords(self.rod_item, self.rod_x, ROD_Y)

        if self.stopped and self.arduino is not None:
            # Only read Arduino angle if connected
            a = self.read_angle()
            if a is not None:
                target = self.angle_to_len(a)
                if target > self.rope_len: self.rope_len = min(target, self.rope_len + 15)
                else: self.rope_len = max(target, self.rope_len - 15)
                
                self.update_rope()
                
                # Check for hit when using Arduino
                if self.check_hit():
                    self.stopped = False
                    # Call new method to retract rope and resume sweep after a short delay
                    self.root.after(700, self.finish_catch_and_resume) 
        
        self.update_rope()
        self.root.after(UPDATE_MS, self.update)

    def set_rope(self, L):
        self.rope_len = L
        self.update_rope()

if __name__ == "__main__":
    root = Tk()
    root.title("Fishing Flexion Game")
    FishingGame(root)
    root.mainloop()