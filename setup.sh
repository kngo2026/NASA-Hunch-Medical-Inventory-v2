#!/bin/bash

# NASA Medical Inventory System - Setup Script
# This script initializes the Django project from scratch

echo "=========================================="
echo "NASA Medical Inventory System Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install Django first
echo "📥 Installing Django..."
pip install Django==4.2.0

# Create Django project
echo "🏗️  Creating Django project 'nasa'..."
django-admin startproject nasa .

# Create medical_inventory app
echo "🏗️  Creating 'medical_inventory' app..."
python manage.py startapp medical_inventory

# Create directory structure
echo "📁 Creating directory structure..."

# Templates directory
mkdir -p medical_inventory/templates

# Static files directory
mkdir -p medical_inventory/static/css
mkdir -p medical_inventory/static/js
mkdir -p medical_inventory/static/images

# Media directory
mkdir -p media/pill_images

# Management commands
mkdir -p medical_inventory/management/commands
touch medical_inventory/management/__init__.py
touch medical_inventory/management/commands/__init__.py

# Hardware directory
mkdir -p hardware

# Create __init__.py files
touch medical_inventory/__init__.py

echo "✓ Directory structure created"
echo ""

# Install remaining dependencies
echo "📥 Installing project dependencies..."
cat > requirements.txt << 'EOF'
Django==4.2.0
Pillow==10.0.0
opencv-python==4.8.0
face-recognition==1.3.0
dlib==19.24.0
numpy==1.24.0
requests==2.31.0
psycopg2-binary==2.9.6
python-dotenv==1.0.0
gunicorn==21.2.0
EOF

pip install -r requirements.txt

echo "✓ Dependencies installed"
echo ""

# Create .env file
echo "📝 Creating .env file..."
cat > .env << 'EOF'
SECRET_KEY=django-insecure-change-this-in-production-$(openssl rand -base64 32)
DEBUG=True
ESP32_IP=192.168.1.100
CAMERA_INDEX=0
ALLOWED_HOSTS=localhost,127.0.0.1
EOF

echo "✓ .env file created"
echo ""

# Update settings.py
echo "⚙️  Updating Django settings..."
cat > nasa/settings.py << 'EOF'
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Security settings
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-temporary-key')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'medical_inventory',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nasa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'nasa.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ESP32 Configuration
ESP32_IP = os.getenv('ESP32_IP', '192.168.1.100')
CAMERA_INDEX = int(os.getenv('CAMERA_INDEX', '0'))
EOF

echo "✓ Settings updated"
echo ""

# Update main urls.py
echo "🔗 Updating URL configuration..."
cat > nasa/urls.py << 'EOF'
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('medical_inventory.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
EOF

echo "✓ URLs configured"
echo ""

# Create README.md
echo "📄 Creating README.md..."
cat > README.md << 'EOF'
# NASA Medical Inventory System

Advanced medication management system for space missions using facial recognition and automated inventory tracking.

## Features

- 🔐 Facial Recognition Authentication
- 💊 Automated Medication Dispensing
- 📊 Real-time Inventory Tracking
- 📈 Usage Analytics and Reporting
- 🤖 AI-Powered Pill Recognition
- 🔓 ESP32-Controlled Smart Lock

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/GStormcrow/medical-inventory-.git
cd medical-inventory-
```

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

3. Activate virtual environment:
```bash
source venv/bin/activate
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Run development server:
```bash
python manage.py runserver
```

Visit http://localhost:8000 to access the system.

## Project Structure

```
medical-inventory-/
├── manage.py
├── requirements.txt
├── nasa/                    # Main project
├── medical_inventory/       # Core app
├── hardware/               # ESP32 code
├── media/                  # Uploaded files
└── staticfiles/           # Static assets
```

## Documentation

For detailed setup instructions, see the installation guide in the docs.

## NASA HUNCH Program

This project is part of the NASA HUNCH (High School Students United with NASA to Create Hardware) program.

## License

MIT License - See LICENSE file for details
EOF

echo "✓ README created"
echo ""

# Initialize git (if not already initialized)
if [ ! -d .git ]; then
    echo "🔧 Initializing Git repository..."
    git init
    echo "✓ Git initialized"
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Run migrations: python manage.py migrate"
echo "3. Create superuser: python manage.py createsuperuser"
echo "4. Start server: python manage.py runserver"
echo ""
echo "📝 Don't forget to:"
echo "   - Update .env with your settings"
echo "   - Add your model files to medical_inventory/"
echo "   - Configure your ESP32 IP address"
echo ""
echo "Happy coding! 🚀"