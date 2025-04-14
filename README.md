# License Plate Detection and Speed Estimation

A comprehensive system for license plate detection, recognition, and vehicle speed estimation from video feeds using YOLOv8, OpenCV, and SQLite.

## Features

- 🚗 Real-time license plate detection using YOLOv8
- 📝 License plate text recognition with OCR (optional)
- 🔍 Plate image quality analysis and filtering
- 🔄 Multi-angle detection for tilted or rotated plates
- 💾 SQLite database storage for all detected plates
- ⚡ Vehicle speed estimation
- 📊 Detection statistics and reporting
- 🖼️ Support for both video files and live camera feeds

## Requirements

- Python 3.8+
- PyTorch
- OpenCV
- Ultralytics YOLO
- SQLite3
- Pillow
- NumPy
- (Optional) Pytesseract for OCR

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/your-username/license-plate-detection.git
   cd license-plate-detection
   ```

2. Install the required packages:
   ```
   pip install torch opencv-python ultralytics pillow numpy
   ```

3. For OCR functionality (optional):
   ```
   pip install pytesseract
   ```
   Note: You'll also need to install Tesseract OCR on your system.

4. Download a pre-trained YOLOv8 model for license plate detection or train your own.

## Usage

### Basic Usage

```bash
python plate_detector.py --video path/to/video.mp4 --model path/to/model.pt --display
```

### Command Line Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--model` | Path to YOLOv8 model file | `best.pt` |
| `--video` | Path to video file or camera index (0, 1, etc.) | Required |
| `--conf` | Detection confidence threshold | 0.5 |
| `--display` | Enable video display | False |
| `--rotate` | Enable multi-angle detection | False |
| `--save-dir` | Directory to save results | `plate_results` |
| `--debug` | Run in debug mode | False |
| `--db-name` | Database file name | `plates.db` |
| `--db-only` | Save to database only, no image files | False |
| `--use-ocr` | Use OCR for plate text recognition | False |
| `--measure-speed` | Enable speed measurement | False |
| `--distance` | Measurement distance in meters | 15.0 |

### Examples

#### Basic detection from video file:
```
python plate_detector.py --video traffic.mp4 --model best.pt --display
```

#### Enable rotation detection for tilted plates:
```
python plate_detector.py --video highway.mp4 --model best.pt --display --rotate
```

#### Measure vehicle speed:
```
python plate_detector.py --video highway.mp4 --model best.pt --display --measure-speed --distance 20.0
```

#### Use OCR to read plate text:
```
python plate_detector.py --video traffic.mp4 --model best.pt --display --use-ocr
```

#### Run in debug mode with all features:
```
python plate_detector.py --video traffic.mp4 --model best.pt --display --rotate --use-ocr --measure-speed --debug
```

## How It Works

### Speed Detection

The system calculates vehicle speed by measuring the time it takes for a license plate to travel between detection points. Configuration options allow you to specify the distance in meters to match your camera setup.

### Database Storage

All detected plates are stored in an SQLite database with the following information:
- Plate image
- OCR-detected text (if enabled)
- Image clarity score
- Detection confidence
- Rotation angle
- Capture timestamp
- Vehicle speed (if enabled)

### Image Quality Analysis

The system uses Laplacian variance to measure image clarity, ensuring that only the highest quality images are saved for each detected plate.


## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- This project uses the [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) for object detection
- OCR functionality powered by [Tesseract](https://github.com/tesseract-ocr/tesseract)
