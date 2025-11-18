# Wrist Rehab Games System

## Overview
The Wrist Rehab Games system now features a centralized launcher with ROM (Range of Motion) calibration and game selection.

## How to Use

### 1. Launch the Game Launcher
```bash
python game_launcher.py
```

### 2. ROM Calibration (First Time)
The first time you run the launcher, you'll see the ROM Calibration page:

1. **Connect Device**: Click "Connect to Device" to connect to your Arduino
2. **Move Wrist**: Move your wrist through its FULL range of motion (up and down)
3. **Monitor Values**: Watch as the system tracks:
   - Current angle in real-time
   - Minimum angle reached
   - Maximum angle reached  
   - Total range calculated
4. **Save**: Click "Save Calibration & Continue" when you've covered the full range
   - Minimum range required: 10 degrees
   - Calibration is saved to `rom_calibration.json`

### 3. Game Selection Page
After calibration, you'll see three games to choose from:

#### Game 1: Gold Miner (Flexion Focus)
- **Description**: Catch gold and fish while avoiding trash
- **Movement**: Focuses on FLEXION movements
- **How to Play**: Control the fishing rod with wrist flexion

#### Game 2: Bird Catcher (Full Range)
- **Description**: Catch blue birds, avoid bombs
- **Movement**: Uses FULL range of motion
- **How to Play**: Move basket up and down to catch birds

#### Game 3: Rocket Launch (Extension Focus)
- **Description**: Launch a rocket by landing on platforms
- **Movement**: Focuses on EXTENSION movements
- **How to Play**: Control rocket height with wrist extension

### 4. Re-Calibration
You can re-calibrate ROM at any time:
- Click "Re-Calibrate ROM" button on the Game Selection page
- This will take you back to the calibration page
- Follow the same calibration steps
- Your new calibration will be saved and applied to all games

### 5. Playing Games
1. Select a game from the Game Selection page
2. The game will launch in a new window
3. **Back to Launcher**: Click the "← Back to Launcher" button in the top-left of the game menu
4. The launcher will reappear after you exit the game

## Files Created

- `game_launcher.py` - Main launcher application
- `rom_calibration.json` - Stores your ROM calibration data
  ```json
  {
    "min_angle": 45.2,
    "max_angle": 135.8,
    "is_calibrated": true
  }
  ```

## Technical Details

### ROM Calibration
- Calibration data is automatically passed to games via command-line arguments
- Games use this data to map sensor input to game controls
- Calibration persists between sessions

### Game Integration
- Games check if launched from launcher (command-line args present)
- If yes: Use provided calibration, show "Back to Launcher" button
- If no: Run standalone calibration, no back button

### Navigation Flow
```
Start
  ↓
ROM Calibration Page
  ↓
[Save Calibration]
  ↓
Game Selection Page ←→ [Re-Calibrate ROM]
  ↓
[Choose Game]
  ↓
Game Runs
  ↓
[Back to Launcher] or [Exit]
  ↓
Game Selection Page
```

## Benefits

1. **One-Time Setup**: Calibrate once, play all games
2. **Consistent Experience**: Same ROM calibration across all games
3. **Easy Updates**: Re-calibrate anytime if needed
4. **Better Organization**: All games accessible from one place
5. **Patient-Friendly**: Simple, clear interface with visual feedback

## Troubleshooting

### Arduino Not Found
- Ensure Arduino is connected via USB
- Check if correct drivers are installed
- Try disconnecting and reconnecting
- Use the "Refresh" button after reconnecting

### Calibration Range Too Small
- Make sure you're moving through the FULL range of motion
- The system requires at least 10 degrees of movement
- Try moving slower and more deliberately

### Game Won't Launch
- Verify game files exist in correct folders:
  - `Game 1 - Flexion/flexion_game.py`
  - `Game 2 - All/gam_potentiometer.py`
  - `Game 3 - Extension/extension.py`
- Check that Python can access these files

## Future Enhancements

Potential additions:
- Patient profiles integration
- Calibration history tracking
- Progress reports
- Difficulty settings per game
- Session time tracking
