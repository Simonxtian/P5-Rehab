# Quick Start Guide - Wrist Rehab Games

## Installation

No installation needed! Just ensure you have Python and required packages:

```bash
pip install pillow pyserial tkinter
```

## Launch the System

```bash
python game_launcher.py
```

## First Time Setup

### Step 1: ROM Calibration
1. Connect your Arduino wrist controller via USB
2. Click **"Connect to Device"**
3. Move your wrist through its FULL range - slowly up and down
4. Watch the values update:
   - **Current Angle** (in blue)
   - **Minimum** (in red)
   - **Maximum** (in green)
   - **Range** (in purple)
5. When satisfied with the range, click **"Save Calibration & Continue"**

**Tip**: Make sure the range is at least 30-40 degrees for best game experience!

### Step 2: Choose a Game
You'll see three games:

- **Game 1: Gold Miner** - Practice flexion movements
- **Game 2: Bird Catcher** - Use full range of motion
- **Game 3: Rocket Launch** - Practice extension movements

Click the **"Play"** button for any game.

### Step 3: Play!
- The game will open in a new window
- Your calibrated ROM is automatically applied
- To return to the game menu, click **"← Back to Launcher"** (top-left or bottom of screen depending on game)

## Re-Calibration

If you need to recalibrate (e.g., patient's ROM improved):

1. From the Game Selection page, click **"Re-Calibrate ROM"**
2. Follow the same calibration steps
3. New calibration is saved automatically
4. All future game sessions will use the new calibration

## Tips for Best Results

### Calibration
- Move slowly and deliberately
- Cover the ENTIRE comfortable range
- Don't rush - take 10-15 seconds
- The system tracks min/max automatically

### Gameplay
- Start with lower difficulty/speed settings
- Focus on smooth, controlled movements
- Take breaks between games
- Gradually increase difficulty as ROM improves

## Troubleshooting

### "No Arduino found"
- Check USB connection
- Verify Arduino is powered on
- Try a different USB port
- Restart the launcher

### "Calibration range too small"
- Move through a wider range
- Minimum requirement: 10 degrees
- Ideal range: 30-60 degrees or more

### Game controls not responding
- Check Arduino connection
- Verify calibration was saved
- Try re-calibrating
- Restart the game

### Back button not showing
- Back button only appears when launched from game_launcher.py
- If running games directly, no back button will show

## File Structure

```
ROB5/P5-Rehab/
├── game_launcher.py          ← START HERE
├── rom_calibration.json       (created automatically)
├── Game 1 - Flexion/
│   ├── flexion_game.py
│   └── highscore_flex.json
├── Game 2 - All/
│   ├── gam_potentiometer.py
│   └── highscore_all.json
└── Game 3 - Extension/
    ├── extension.py
    └── highscore_extension.json
```

## Support

For issues or questions:
1. Check GAMES_README.md for detailed documentation
2. Verify all game files are in correct folders
3. Ensure Arduino drivers are installed
4. Check Python version (3.7+ recommended)

## Enjoy!

Have fun with your wrist rehabilitation games! Remember to:
- ✓ Calibrate before first use
- ✓ Re-calibrate if ROM changes
- ✓ Take breaks
- ✓ Track your progress via highscores
