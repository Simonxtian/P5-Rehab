# Unified Wrist Rehab System - Quick Start

## Overview
The complete wrist rehabilitation system is now integrated into a single GUI application that combines:
- Patient Management
- ROM (Range of Motion) Calibration using real potentiometer data
- MVC Testing & Admittance Control
- Rehabilitation Games

## Quick Start

### 1. Launch the System
```bash
cd WristRehab
python gui.py
```

### 2. Workflow

**Step 1: Patient Selection**
- Register a new patient (name, weight, difficulty)
- OR select an existing patient from the database
- Click "Load Patient" or "Register & Continue"

**Step 2: ROM Calibration** (automatic if not done)
- System displays real-time potentiometer readings in radians
- Move your wrist through FULL comfortable range
- System tracks minimum and maximum angles automatically
- Click "Save Calibration & Continue" when done
- **Note**: Uses actual `theta_pot` data from WristRehab controller

**Step 3: Connect Device** (on Therapy page)
- Select serial port
- Click "Connect"
- System automatically disables admittance on connection

**Step 4: Set Patient Mass**
- Click "Send Mass to Device"
- Sends calculated mass for gravity compensation

**Step 5: Run MVC Test**
- Click "Run MVC Test (5 s)"
- Apply maximum extension torque
- System calculates J, B, K parameters
- Admittance control activates automatically

**Step 6: Therapy Session**
- Patient performs rehabilitation exercises
- Live telemetry shows force, velocity, PWM
- Click "Stop Session" when done

**Step 7: Play Games** (optional)
- Click "🎮 Games" button in therapy page
- Choose from 3 games:
  - Game 1: Gold Miner (Flexion focus)
  - Game 2: Bird Catcher (Full range)
  - Game 3: Rocket Launch (Extension focus)
- Games use your calibrated ROM automatically
- Click "← Back to Launcher" in game to return

## Key Features

### Unified Navigation
```
Patient Selection
    ↓
ROM Calibration (uses real potentiometer data)
    ↓
Therapy Page (Connection + MVC + Control)
    ↓
Games Page
```

### ROM Calibration
- **Input**: `theta_pot` from WristRehab controller telemetry (in radians)
- **Display**: Shows current angle, min, max, and range
- **Storage**: Saved to `rom_calibration.json`
- **Format**: Both radians and degrees
- **Usage**: Automatically passed to games as degrees

### Data Files
- `patients_db.json` - Patient records & sessions
- `rom_calibration.json` - ROM calibration data
- `session_YYYYMMDD_HHMMSS.csv` - Telemetry logs

### Telemetry Columns
```
timestamp, theta_pot, theta_enc, w_user, w_meas, u_pwm, force_filt, tau_ext, w_adm
```

## Page Navigation

### Patient Page
- View all patients
- Register new patient
- Load patient → goes to ROM calibration if needed

### ROM Calibration Page
- Real-time potentiometer display
- Min/Max tracking
- Reset button
- Save & continue to therapy
- ← Back to patient selection

### Therapy Page
- 🎮 Games button → games page
- Stop Session button (enabled during therapy)
- ← Change Patient button
- Connection controls
- Patient parameters (editable)
- MVC test controls
- Live telemetry displays
- System log

### Games Page
- Shows ROM calibration status
- Re-Calibrate ROM button
- 3 game selection cards
- ← Back to Therapy button

## Important Notes

1. **ROM Calibration uses actual sensor data**
   - Reads `theta_pot` from CSV telemetry
   - Values are in radians from the controller
   - Converted to degrees when launching games

2. **Device must be connected for ROM calibration**
   - Need live telemetry data
   - Cannot calibrate offline

3. **Games launch externally**
   - GUI minimizes during game
   - Game window opens separately
   - Click back button in game to return
   - GUI reappears after game closes

4. **Session Management**
   - Each MVC test starts a new session
   - Session must be stopped before starting new MVC
   - All session data saved to patient record

## Troubleshooting

### ROM Calibration not updating
- Ensure device is connected
- Check telemetry is streaming
- Verify theta_pot values in log

### Games not launching
- Check game files exist in parent folder structure:
  ```
  ROB5/P5-Rehab/
  ├── WristRehab/gui.py  ← you are here
  ├── Game 1 - Flexion/flexion_game.py
  ├── Game 2 - All/gam_potentiometer.py
  └── Game 3 - Extension/extension.py
  ```

### ROM calibration range too small
- Move wrist through wider range
- Minimum: 0.17 radians (~10 degrees)
- Ideal: 0.5-1.0 radians (30-60 degrees)

### Connection issues
- Check USB cable
- Verify correct port selected
- Try disconnecting and reconnecting
- Restart application if needed

## System Requirements
- Python 3.7+
- Libraries: tkinter, pyserial, PIL (pillow)
- WristRehab Arduino controller
- USB connection

## Installation
```bash
pip install pyserial pillow
```

That's it! No additional setup needed.
