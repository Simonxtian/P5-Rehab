# SOLUTION: Prevent Arduino Reset When Launching Games

## Problem
When games launched, they opened their own serial connection to the Arduino, causing it to reset and lose all configured parameters (mass, arm length, admittance settings).

## Root Cause
Arduino boards reset when a serial connection is established. Each game was:
1. Triggering GUI to disconnect
2. Opening its own serial connection
3. Causing Arduino to reset → **ALL PARAMETERS LOST**

## Solution Implemented

### 1. GUI Maintains Serial Connection
- GUI **no longer disconnects** when launching games
- GUI continuously reads Arduino data and writes to `live_angle_data.json`
- Arduino never resets, parameters are preserved ✓

### 2. Shared Data File Communication
- **File**: `WristRehab/live_angle_data.json`
- **Format**: `{"angle": 87.5, "button": 1.0, "timestamp": 1733430156.2}`
- **Update Rate**: Every time Arduino sends data (~50-100Hz)

### 3. Games Read From Shared File
- New module: `shared_serial_reader.py`
- Provides `SharedSerialReader` class
- Drop-in replacement for serial communication
- Games detect `--use-shared-data` command line flag

## Files Modified

### ✅ GUI (`user_interface.py`)
1. Added `SHARED_DATA_FILE = "live_angle_data.json"` constant
2. Modified `_handle_line()` to write angle data to shared file
3. Modified `launch_game()` to NOT disconnect and pass `--use-shared-data` flag
4. Removed reconnection in `_monitor_game()`

### ✅ Created Files
1. `shared_serial_reader.py` - Shared data reader module
2. `GAME_MODIFICATION_GUIDE.txt` - Instructions for modifying games

## Next Steps - MODIFY GAMES

Each game needs to be updated to support shared data mode:

### Game 1 - Flexion (`Game 1 - Flexion/flexion_game.py`)
### Game 2 - All (`Game 2 - All/Flex_and_ext_game.py`)  
### Game 3 - Extension (`Game 3 - Extension/extension.py`)

**Required changes per game:**
1. Import SharedSerialReader
2. Check for `--use-shared-data` flag
3. Use SharedSerialReader instead of serial connection
4. Read angle/button from shared file in game loop

See `GAME_MODIFICATION_GUIDE.txt` for detailed instructions.

## Benefits

✅ **Arduino never resets** - parameters preserved across games
✅ **No parameter loss** - mass, arm length, admittance stay configured
✅ **Backward compatible** - games can still run standalone with serial
✅ **Cleaner architecture** - GUI controls hardware, games handle gameplay
✅ **Real-time data** - games get same data rate as before

## Testing

1. Load patient and run MVC test
2. Set mass and arm length  
3. Launch calibration and then a game
4. **Verify**: Parameters should remain configured (no restart needed after game)

## Technical Details

**Data Flow:**
```
Arduino → GUI (serial) → live_angle_data.json → Game (file read)
```

**Update Rate:**
- GUI updates file: ~50-100 times/second
- Game reads file: Every frame (~60 times/second)
- Data freshness check: < 1 second considered valid
