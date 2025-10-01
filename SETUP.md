# 🔒 SECURITY SETUP GUIDE

**⚠️ IMPORTANT: This repository requires proper security setup before use.**

This guide will help you configure the system securely for production use.

## 🚨 Security Notice

This project has been designed with security in mind:
- **No sensitive data** is stored in the repository
- **Configuration files** must be created manually
- **AI model weights** must be downloaded separately
- **Camera access** requires explicit permission setup

## 📋 Prerequisites

- Python 3.11+
- Virtual environment
- Camera/webcam access permissions
- Internet connection (for model downloads)

## 🔧 Step-by-Step Security Setup

### 1. Clone and Navigate
```bash
git clone <repository-url>
cd retrux-shelf-eye
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate    # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create Required Directories
```bash
# Create directory structure
mkdir -p retruxosaproject/app_root/active_state/devices
mkdir -p retruxosaproject/app_root/active_state/product_visual
mkdir -p retruxosaproject/app_root/last_state
mkdir -p retruxosaproject/app_root/product_information
mkdir -p retruxosaproject/app_root/product_state
mkdir -p product_scan/oliwo_weights
mkdir -p logs
```

### 5. Model Weight Setup
```bash
# AI models will be automatically downloaded on first run
# Ensure you have internet connection for:
# - YOLO models (auto-download)
# - HuggingFace DETR models (auto-download)

# For manual setup, place model files in:
# product_scan/oliwo_weights/
```

### 6. Camera Permissions

#### Linux:
```bash
# Add user to video group
sudo usermod -a -G video $USER
# Logout and login again

# Check camera access
ls /dev/video*
```

#### macOS:
```bash
# Grant camera permissions in System Preferences > Security & Privacy > Camera
# Add Terminal and Python to allowed applications
```

#### Windows:
```bash
# Go to Settings > Privacy > Camera
# Enable "Allow apps to access your camera"
# Enable for Python and terminal applications
```

### 7. Test Installation
```bash
# Test basic functionality
python -c "import cv2, torch, transformers, ultralytics; print('All dependencies OK')"

# Test camera access
python -c "import cv2; cap = cv2.VideoCapture(0); print('Camera:', cap.isOpened()); cap.release()"
```

## 🛡️ Security Best Practices

### For Development:
```bash
# Never commit these files:
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore
echo "credentials.json" >> .gitignore
echo "config.json" >> .gitignore
```

### For Production:
```bash
# Set proper file permissions
chmod 700 retruxosaproject/
chmod 600 retruxosaproject/app_root/product_information/
chmod 644 requirements.txt
```

### Environment Variables:
```bash
# Create .env file for sensitive settings (never commit)
cat > .env << EOF
# Camera Settings
CAMERA_INDEX=0
CAMERA_RESOLUTION=640x480

# AI Model Settings
CONFIDENCE_THRESHOLD=0.7
DEVICE=cpu

# Paths
DATA_PATH=./retruxosaproject/app_root/
LOG_PATH=./logs/

# Security
DEBUG_MODE=false
ALLOW_EXTERNAL_ACCESS=false
EOF
```

## 📁 Directory Structure After Setup

```
retrux-shelf-eye/
├── .env                    # Your environment variables (not in git)
├── .gitignore             # Comprehensive exclusion rules
├── logs/                  # Application logs (not in git)
├── retruxosaproject/      # Data storage (not in git)
│   └── app_root/
│       ├── active_state/
│       │   ├── devices/           # Your camera images
│       │   └── product_visual/    # AI detection output
│       ├── last_state/            # Reference images
│       ├── product_information/   # Detection results
│       └── product_state/         # Inventory tracking
├── product_scan/
│   └── oliwo_weights/     # AI model weights (auto-downloaded)
└── people_counter/        # Your video files for analysis
```

## 🚀 First Run

After completing setup:

```bash
# Start the main application
python main_launcher.py

# Follow the workflow:
# 1. Click "🔄 Refresh Status"
# 2. Add sample images to devices/ folder
# 3. Click "⚙️ Run Setup" 
# 4. Click "🚀 Start All"
```

## ❗ Troubleshooting

### Permission Errors:
```bash
# Fix directory permissions
find retruxosaproject/ -type d -exec chmod 755 {} \;
find retruxosaproject/ -type f -exec chmod 644 {} \;
```

### Model Download Issues:
```bash
# Manual YOLO download
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"

# Check HuggingFace cache
ls ~/.cache/huggingface/transformers/
```

### Camera Access Issues:
```bash
# List available cameras
python -c "import cv2; [print(f'Camera {i}: {cv2.VideoCapture(i).isOpened()}') for i in range(5)]"
```

## 🔐 Security Checklist

- [ ] Virtual environment activated
- [ ] All dependencies installed
- [ ] Camera permissions granted
- [ ] Required directories created
- [ ] .env file configured (if needed)
- [ ] Model weights downloaded
- [ ] File permissions set correctly
- [ ] Test run completed successfully

## 📞 Support

If you encounter issues during setup:
1. Check the troubleshooting section above
2. Verify all prerequisites are met
3. Check file permissions and directory structure
4. Review logs in the `logs/` directory
5. Open an issue with your setup details

---

**⚠️ Security Reminder**: Never commit sensitive files like camera images, model weights, or configuration files containing credentials to version control.
