# views.py - Updated with Authentication, Camera Capture, Transaction Log
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.core.files.storage import default_storage
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from PIL import Image
import PIL.Image
from difflib import SequenceMatcher
import re
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
import face_recognition
import pickle
import requests
import json
import numpy as np
import cv2
import csv
import hashlib
import io
import base64
import os
from datetime import timedelta
import serial
import serial.tools.list_ports

# Import for deep learning model (TensorFlow/Keras)
try:
    from tensorflow import keras
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("TensorFlow not available. Install with: pip install tensorflow")

# Import for color/shape analysis
from sklearn.cluster import KMeans
import pytesseract
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
from .models import Astronaut, Medication, Prescription, MedicationCheckout, InventoryLog, SystemLog
from .forms import MedicationForm
from sklearn.cluster import KMeans

ESP32_IP = getattr(settings, 'ESP32_IP_ADDRESS', '')
# ============================================================================
# LOGIN/LOGOUT VIEWS
# ============================================================================
def login_view(request):
    """Login page for staff/admin users"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            next_url = request.GET.get('next', 'medical_inventory:home')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions')
    
    return render(request, 'login.html')


def logout_view(request):
    """Logout view"""
    logout(request)
    return redirect('medical_inventory:home')


# ============================================================================
# HOME AND FACE AUTHENTICATION VIEWS
# ============================================================================

def home(request):
    """Home screen"""
    return render(request, 'home.html')


def lockscreen(request):
    """Lockscreen with facial recognition"""
    return render(request, 'lockscreen.html')


@csrf_exempt
def authenticate_face(request):
    """
    Face authentication using HOG (fast) + num_jitters=3 (accurate enough).
    Resizes image first for speed, strict threshold to avoid misidentification.
    """
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            image = face_recognition.load_image_file(image_file)
            pil_img = Image.fromarray(image)
            if pil_img.width > 640:
                scale = 640 / pil_img.width
                pil_img = pil_img.resize((640, int(pil_img.height * scale)))
                image = np.array(pil_img)
            face_locations = face_recognition.face_locations(image, model="hog")

            if not face_locations:
                SystemLog.objects.create(
                    event_type='AUTH_FAILURE',
                    description="No face detected in image",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                return JsonResponse({
                    'success': False,
                    'message': 'No face detected. Please ensure your face is clearly visible and well-lit.'
                })
            face_encodings = face_recognition.face_encodings(
                image, face_locations, num_jitters=2
            )

            if not face_encodings:
                return JsonResponse({
                    'success': False,
                    'message': 'Could not process face. Please try again.'
                })
            astronauts = list(Astronaut.objects.exclude(face_encoding__isnull=True))

            if not astronauts:
                return JsonResponse({
                    'success': False,
                    'message': 'No registered users found in the system.'
                })

            known_encodings = [pickle.loads(a.face_encoding) for a in astronauts]

            for face_encoding in face_encodings:
                distances = face_recognition.face_distance(known_encodings, face_encoding)

                best_index = int(distances.argmin())
                best_distance = distances[best_index]

                print(f"Best match: {astronauts[best_index].name}, distance: {best_distance:.4f}")
                print(f"All distances: {[(astronauts[i].name, round(d, 4)) for i, d in enumerate(distances)]}")
                THRESHOLD = 0.45

                if best_distance > THRESHOLD:
                    SystemLog.objects.create(
                        event_type='AUTH_FAILURE',
                        description=f"Face not recognized (best distance: {best_distance:.4f})",
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
                    return JsonResponse({
                        'success': False,
                        'message': 'Face not recognized. Please try again.'
                    })
                if len(distances) > 1:
                    sorted_distances = sorted(distances)
                    gap = sorted_distances[1] - sorted_distances[0]
                    if gap < 0.08:
                        print(f"Ambiguous match ΓÇö gap too small: {gap:.4f}")
                        SystemLog.objects.create(
                            event_type='AUTH_FAILURE',
                            description=f"Ambiguous face match (gap: {gap:.4f})",
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                        return JsonResponse({
                            'success': False,
                            'message': 'Could not confidently identify face. Please try again.'
                        })

                # Success
                astronaut = astronauts[best_index]
                confidence = round((1 - best_distance) * 100, 1)

                SystemLog.objects.create(
                    event_type='AUTH_SUCCESS',
                    astronaut=astronaut,
                    description=f"Face authenticated: {astronaut.name} (confidence: {confidence}%, distance: {best_distance:.4f})",
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                return JsonResponse({
                    'success': True,
                    'astronaut_id': astronaut.id,
                    'astronaut_name': astronaut.name,
                    'confidence': confidence,
                    'message': f'Welcome, {astronaut.name}!'
                })

            return JsonResponse({
                'success': False,
                'message': 'Face not recognized. Please try again.'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'error': 'Invalid request'}, status=400)


# ============================================================================
# MEDICATION SELECTION AND CHECKOUT
# ============================================================================

def medication_selection(request, astronaut_id):
    """Medication selection page"""
    astronaut = get_object_or_404(Astronaut, id=astronaut_id)
    prescriptions = Prescription.objects.filter(
        astronaut=astronaut,
        is_active=True
    ).select_related('medication')
    all_medications = Medication.objects.filter(current_quantity__gt=0)
    
    context = {
        'astronaut': astronaut,
        'prescriptions': prescriptions,
        'all_medications': all_medications
    }
    
    return render(request, 'medication_selection.html', context)


@csrf_exempt
def checkout_medication(request):
    """Process medication checkout with transaction logging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            astronaut_id = data.get('astronaut_id')
            medications = data.get('medications', [])
            
            astronaut = get_object_or_404(Astronaut, id=astronaut_id)
            
            # First: Validate all medications and check stock availability
            medication_list = []
            for med_data in medications:
                medication = get_object_or_404(Medication, id=med_data['medication_id'])
                quantity = med_data['quantity']
                
                # Check quantity available
                if quantity > medication.current_quantity:
                    return JsonResponse({
                        'success': False,
                        'message': f'Insufficient stock for {medication.name}'
                    }, status=400)
                
                medication_list.append({
                    'medication': medication,
                    'quantity': quantity,
                    'is_prescription': med_data.get('is_prescription', False),
                    'previous_quantity': medication.current_quantity
                })
            
            # Second: Try to unlock the container BEFORE making any database changes
            unlock_success = send_esp32_unlock(astronaut)
            
            if not unlock_success:
                return JsonResponse({
                    'success': False,
                    'message': 'Failed to unlock medication container. Please try again.'
                }, status=500)
            
            # Third: Only if unlock succeeds, create checkout records
            checkouts_created = 0
            for med_data in medication_list:
                medication = med_data['medication']
                quantity = med_data['quantity']
                previous_quantity = med_data['previous_quantity']
                
                # Create checkout
                MedicationCheckout.objects.create(
                    astronaut=astronaut,
                    medication=medication,
                    quantity=quantity,
                    is_prescription=med_data['is_prescription']
                )
                
                # Create inventory log
                InventoryLog.objects.create(
                    medication=medication,
                    log_type='CHECKOUT',
                    quantity_change=-quantity,
                    previous_quantity=previous_quantity,
                    new_quantity=medication.current_quantity,
                    performed_by=astronaut,
                    notes=f"Checkout by {astronaut.name}"
                )
                
                checkouts_created += 1
            
            SystemLog.objects.create(
                event_type='CONTAINER_UNLOCK',
                astronaut=astronaut,
                description=f"Checkout completed: {checkouts_created} medications dispensed",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': True,
                'checkouts': checkouts_created,
                'unlock_status': unlock_success
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'POST required'}, status=400)


def check_medication_threshold(astronaut, medication, quantity):
    """Check if medication withdrawal exceeds thresholds"""
    try:
        threshold = medication.threshold
    except:
        return False, None
    
    # warning_created = False
    max_severity = None
    
    # Check single dose limit
    # if quantity > threshold.single_dose_limit:
    #     severity = 'CRITICAL' if quantity > threshold.single_dose_limit * 1.5 else 'HIGH'
    #     WarningLog.objects.create(
    #         astronaut=astronaut,
    #         medication=medication,
    #         quantity_taken=quantity,
    #         warning_message=f"Single dose limit exceeded: {quantity} units (limit: {threshold.single_dose_limit})",
    #         severity=severity
    #     )
    #     warning_created = True
    #     max_severity = severity
    
    # Check daily limit
    # today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # today_total = MedicationCheckout.objects.filter(
    #     astronaut=astronaut,
    #     medication=medication,
    #     checkout_time__gte=today_start
    # ).aggregate(total=Sum('quantity'))['total'] or 0
    # today_total += quantity
    
    # if today_total > threshold.daily_limit:
    #     WarningLog.objects.create(
    #         astronaut=astronaut,
    #         medication=medication,
    #         quantity_taken=quantity,
    #         warning_message=f"Daily limit exceeded: {today_total} units today (limit: {threshold.daily_limit})",
    #         severity='CRITICAL'
    #     )
    #     warning_created = True
    #     max_severity = 'CRITICAL'
    
    # return warning_created, max_severity


# ============================================================================
# ESP32 COMMUNICATION - USB SERIAL & WIFI
# ============================================================================

def find_esp32_serial_port():
    """Auto-detect the ESP32 USB serial port"""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if any(keyword in port.description.upper() for keyword in
               ['CP210', 'CH340', 'UART', 'USB SERIAL', 'ESP']):
            return port.device
    ports = list(ports)
    if ports:
        return ports[0].device
    return None


def send_esp32_unlock_serial(username):
    """Send unlock command to ESP32 via USB Serial"""
    import time

    port = getattr(settings, 'ESP32_SERIAL_PORT', None) or find_esp32_serial_port()

    if not port:
        print("No serial port found for ESP32")
        return False

    try:
        command = json.dumps({
            "action": "unlock",
            "username": username,
            "source": "django"
        }) + "\n"

        with serial.Serial() as ser:
            ser.port = port
            ser.baudrate = getattr(settings, 'ESP32_BAUD_RATE', 115200)
            ser.timeout = 3
            ser.dtr = False  # Prevent ESP32 reset when port opens
            ser.rts = False
            ser.open()

            time.sleep(0.5)
            ser.reset_input_buffer()
            ser.write(command.encode('utf-8'))

            response = ser.readline().decode('utf-8', errors='ignore').strip()
            print(f"ESP32 Serial response: {response}")

            try:
                data = json.loads(response)
                return data.get('success', True)
            except json.JSONDecodeError:
                # Echo or garbled — command was still sent and lock unlocked
                return True

    except Exception as e:
        print(f"Serial error: {e}")
        return False


def _send_esp32_unlock(username, extra_payload=None):
    """
    Master unlock function used by ALL unlock paths.
    Tries WiFi first if IP is set, falls back to Serial.
    """
    esp32_ip = getattr(settings, 'ESP32_IP_ADDRESS', '')

    if esp32_ip:
        try:
            payload = {
                'username': username,
                'timestamp': timezone.now().isoformat(),
                'source': 'django'
            }
            if extra_payload:
                payload.update(extra_payload)

            response = requests.post(
                f'http://{esp32_ip}/unlock',
                json=payload,
                timeout=5
            )
            if response.status_code == 200:
                print(f"ESP32 unlocked via WiFi for: {username}")
                return True
        except requests.exceptions.RequestException as e:
            print(f"WiFi unlock failed: {e} — trying Serial...")

    return send_esp32_unlock_serial(username)


def send_esp32_unlock(astronaut):
    """Send unlock command to ESP32 - tries WiFi first, then falls back to USB Serial"""
    return _send_esp32_unlock(astronaut.name, {'user_id': str(astronaut.id)})


# ============================================================================
# INVENTORY VIEWS
# ============================================================================

def inventory_dashboard(request):
    """Inventory dashboard"""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return redirect('/?alert=login_required')
    
    medications = Medication.objects.all().order_by('name')
    total_medications = medications.count()
    low_stock_count = sum(1 for med in medications if med.is_low_stock)
    total_checkouts_today = MedicationCheckout.objects.filter(
        checkout_time__date=timezone.now().date()
    ).count()
    
    context = {
        'medications': medications,
        'total_medications': total_medications,
        'low_stock_count': low_stock_count,
        'total_checkouts_today': total_checkouts_today
    }
    
    return render(request, 'inventory_dashboard.html', context)


def medication_detail(request, medication_id):
    """Medication detail view with transaction log"""
    medication = get_object_or_404(Medication, id=medication_id)
    
    thirty_days_ago = timezone.now() - timedelta(days=30)
    checkouts = MedicationCheckout.objects.filter(
        medication=medication,
        checkout_time__gte=thirty_days_ago
    ).order_by('-checkout_time')
    
    # Get transaction log (inventory logs)
    inventory_logs = InventoryLog.objects.filter(
        medication=medication
    ).order_by('-timestamp')[:50]
    
    daily_usage = MedicationCheckout.objects.filter(
        medication=medication,
        checkout_time__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('checkout_time')
    ).values('date').annotate(
        total_quantity=Sum('quantity'),
        checkout_count=Count('id')
    ).order_by('date')
    
    total_dispensed_30d = sum(item['total_quantity'] for item in daily_usage)
    
    context = {
        'medication': medication,
        'checkouts': checkouts,
        'daily_usage': list(daily_usage),
        'inventory_logs': inventory_logs,
        'total_dispensed_30d': total_dispensed_30d
    }
    
    return render(request, 'medication_detail.html', context)


# ============================================================================
# ASTRONAUT MANAGEMENT (PROTECTED)
# ============================================================================

def manage_astronauts(request):
    """Astronaut management page"""
    return render(request, 'manage_astronauts.html')


@csrf_exempt
def add_astronaut(request):
    """Add new astronaut with face encoding"""
    if request.method == 'POST':
        try:
            astronaut_id = request.POST.get('astronaut_id')
            name = request.POST.get('name')
            photo = request.FILES.get('photo')
            password = request.POST.get('password', astronaut_id)
            
            if not all([astronaut_id, name, photo]):
                return JsonResponse({
                    'success': False,
                    'message': 'All fields are required'
                })
            
            # Create user account
            from django.contrib.auth.models import User
            user = User.objects.create_user(
                username=astronaut_id,
                password=password,
                first_name=name.split()[0] if name else '',
                last_name=' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
            )
            
            # Create astronaut with base64 encoded photo
            photo.seek(0)  # Reset file pointer
            photo_base64 = base64.b64encode(photo.read()).decode('utf-8')
            
            astronaut = Astronaut.objects.create(
                user=user,
                astronaut_id=astronaut_id,
                name=name,
                photo=photo_base64
            )
            
            # Process face encoding
            image = face_recognition.load_image_file(photo)
            face_encodings = face_recognition.face_encodings(image)
            
            if face_encodings:
                astronaut.face_encoding = pickle.dumps(face_encodings[0])
                astronaut.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Astronaut added successfully',
                    'astronaut_id': astronaut.id
                })
            else:
                astronaut.delete()
                user.delete()
                return JsonResponse({
                    'success': False,
                    'message': 'No face detected in photo. Please use a clear, front-facing photo.'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def list_astronauts(request):
    """List all astronauts with photo URLs"""
    astronauts = Astronaut.objects.all()
    
    data = [{
        'id': a.id,
        'name': a.name,
        'astronaut_id': a.astronaut_id,
        'has_face_encoding': a.face_encoding is not None,
        'photo_url': f'data:image/jpeg;base64,{a.photo}' if a.photo else None
    } for a in astronauts]
    
    return JsonResponse({'astronauts': data})


@csrf_exempt
def update_astronaut_face(request):
    """Update astronaut face encoding with camera capture option"""
    if request.method == 'POST':
        try:
            astronaut_id = request.POST.get('astronaut_id')
            photo = request.FILES.get('photo')
            
            if not all([astronaut_id, photo]):
                return JsonResponse({
                    'success': False,
                    'message': 'Astronaut ID and photo are required'
                })
            
            astronaut = get_object_or_404(Astronaut, id=astronaut_id)
            
            # Update photo as base64
            photo.seek(0)  # Reset file pointer
            photo_base64 = base64.b64encode(photo.read()).decode('utf-8')
            astronaut.photo = photo_base64
            
            # Process face encoding
            photo.seek(0)  # Reset file pointer again for face_recognition
            image = face_recognition.load_image_file(photo)
            face_encodings = face_recognition.face_encodings(image)
            
            if face_encodings:
                astronaut.face_encoding = pickle.dumps(face_encodings[0])
                astronaut.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Face encoding updated successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No face detected in photo'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def delete_astronaut(request, astronaut_id):
    """Delete astronaut"""
    if request.method == 'DELETE':
        try:
            astronaut = get_object_or_404(Astronaut, id=astronaut_id)
            user = astronaut.user
            astronaut.delete()
            user.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Astronaut deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


# ============================================================================
# MEDICATION MANAGEMENT (PROTECTED)
# ============================================================================

def manage_medications(request):
    """Medication management page"""
    return render(request, 'manage_medications.html')


@csrf_exempt
@login_required
def add_medication(request):
    """Add new medication"""
    if request.method == 'POST':
        try:
            medication = Medication.objects.create(
                name=request.POST.get('name'),
                generic_name=request.POST.get('generic_name', ''),
                medication_type=request.POST.get('medication_type'),
                dosage=request.POST.get('dosage'),
                description=request.POST.get('description', ''),
                current_quantity=int(request.POST.get('current_quantity', 0)),
                minimum_quantity=int(request.POST.get('minimum_quantity', 0)),
                container_location=request.POST.get('container_location'),
                expiration_date=request.POST.get('expiration_date') or None,
                pill_image=request.FILES.get('pill_image')
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Medication added successfully',
                'medication_id': medication.id
            })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def update_medication_quantity(request):
    """Update medication quantity (for authorized users)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            medication_id = data.get('medication_id')
            new_quantity = int(data.get('quantity'))
            reason = data.get('reason', 'Manual adjustment')
            
            medication = get_object_or_404(Medication, id=medication_id)
            previous_quantity = medication.current_quantity
            quantity_change = new_quantity - previous_quantity
            
            medication.current_quantity = new_quantity
            medication.save()
            
            # Log the change
            astronaut = request.user.astronaut if hasattr(request.user, 'astronaut') else None
            InventoryLog.objects.create(
                medication=medication,
                log_type='ADJUSTMENT',
                quantity_change=quantity_change,
                previous_quantity=previous_quantity,
                new_quantity=new_quantity,
                performed_by=astronaut,
                notes=reason
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Quantity updated successfully',
                'new_quantity': new_quantity
            })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def restock_medication(request):
    """Restock medication (add inventory)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            medication_id = data.get('medication_id')
            quantity = int(data.get('quantity', 0))
            expiration_date = data.get('expiration_date')
            notes = data.get('notes', 'Restock')
            
            medication = get_object_or_404(Medication, id=medication_id)
            previous_quantity = medication.current_quantity
            
            medication.current_quantity += quantity
            medication.save()
            
            # Log the change
            astronaut = request.user.astronaut if hasattr(request.user, 'astronaut') else None
            InventoryLog.objects.create(
                medication=medication,
                log_type='RESTOCK',
                quantity_change=quantity,
                previous_quantity=previous_quantity,
                new_quantity=medication.current_quantity,
                performed_by=astronaut,
                notes=notes
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Medication restocked successfully',
                'new_quantity': medication.current_quantity
            })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt  
def list_medications(request):
    """List all medications"""
    medications = Medication.objects.all()
    
    data = [{
        'id': m.id,
        'name': m.name,
        'generic_name': m.generic_name,
        'medication_type': m.medication_type,
        'medication_type_display': m.get_medication_type_display(),
        'dosage': m.dosage,
        'current_quantity': m.current_quantity,
        'minimum_quantity': m.minimum_quantity,
        'container_location': m.container_location,
        'status': m.status,
        'expiration_date': m.expiration_date.strftime('%Y-%m-%d') if m.expiration_date else None,
        'pill_image': m.pill_image.url if m.pill_image else None
    } for m in medications]
    
    return JsonResponse({'medications': data})


@csrf_exempt
@login_required
def update_medication_image(request):
    """Update medication image"""
    if request.method == 'POST':
        try:
            medication_id = request.POST.get('medication_id')
            image = request.FILES.get('image')
            
            if not all([medication_id, image]):
                return JsonResponse({
                    'success': False,
                    'message': 'Medication ID and image are required'
                })
            
            medication = get_object_or_404(Medication, id=medication_id)
            medication.pill_image = image
            medication.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Image updated successfully',
                'image_url': medication.pill_image.url
            })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# ============================================================================
# BOTTLE READING (OCR-based medication scanning)
# ============================================================================
class PillBottleReader:
    
    def __init__(self):
        self.dosage_pattern = re.compile(r'(\d+\.?\d*)\s*(mg|mcg|g|ml|units?)', re.IGNORECASE)
    
    def preprocess_image(self, image_path):
        """Enhanced preprocessing for maximum OCR accuracy"""
        img = cv2.imread(image_path)
        
        # Resize if too large
        height, width = img.shape[:2]
        if width > 1920 or height > 1080:
            scale = min(1920/width, 1080/height)
            img = cv2.resize(img, None, fx=scale, fy=scale)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Enhance contrast
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, h=15)
        
        # Sharpen
        kernel_sharpen = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(denoised, -1, kernel_sharpen)
        
        # Binary threshold
        _, binary = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Scale up 2x for better OCR
        scale_percent = 200
        width_scaled = int(cleaned.shape[1] * scale_percent / 100)
        height_scaled = int(cleaned.shape[0] * scale_percent / 100)
        scaled = cv2.resize(cleaned, (width_scaled, height_scaled), interpolation=cv2.INTER_CUBIC)
        
        return scaled
    
    def extract_text_from_bottle(self, image_path):
        """Extract text using multiple OCR methods"""
        try:
            processed_img = self.preprocess_image(image_path)
            pil_img = Image.fromarray(processed_img)
            
            # Try multiple configs
            configs = [
                '--oem 3 --psm 6',
                '--oem 3 --psm 11',
                '--oem 1 --psm 6',
            ]
            
            results = []
            for config in configs:
                try:
                    text = pytesseract.image_to_string(pil_img, config=config)
                    if text and len(text.strip()) > 0:
                        results.append(text.strip())
                except:
                    continue
            
            # Also try original image
            try:
                original = cv2.imread(image_path)
                gray_simple = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
                text_simple = pytesseract.image_to_string(gray_simple, config='--oem 3 --psm 6')
                if text_simple:
                    results.append(text_simple.strip())
            except:
                pass
            
            if not results:
                return ""
            
            # Combine all results into one big text block
            combined_text = '\n'.join(results)
            
            print("\n=== OCR EXTRACTED TEXT ===")
            print(combined_text[:500])  # Print first 500 chars
            print("=" * 50)
            
            return combined_text
            
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
    
    def search_for_medications_in_text(self, text):
        """Search OCR text for known medications from database"""
        from .models import Medication
        
        if not text:
            return []
        
        # Get ALL medications from database
        all_medications = Medication.objects.all()
        
        if not all_medications.exists():
            print("No medications in database to search for!")
            return []
        
        # Clean the OCR text
        text_clean = text.lower()
        
        # Remove extra whitespace
        text_clean = ' '.join(text_clean.split())
        
        matches = []
        
        print(f"\n🔍 Searching for {all_medications.count()} medications in OCR text...")
        
        for med in all_medications:
            # Search for medication name
            med_name = med.name.lower().strip()
            
            # Also search generic name if it exists
            generic_name = None
            if hasattr(med, 'generic_name') and med.generic_name:
                generic_name = med.generic_name.lower().strip()
            
            # Split into words for partial matching
            name_words = med_name.split()
            
            # Calculate match score
            score = 0
            match_method = None
            
            # Method 1: Exact match (best)
            if med_name in text_clean:
                score = 95
                match_method = "exact match"
            
            # Method 2: Generic name exact match
            elif generic_name and generic_name in text_clean:
                score = 90
                match_method = "generic name exact"
            
            # Method 3: All words present (good)
            elif len(name_words) > 1 and all(word in text_clean for word in name_words):
                score = 85
                match_method = "all words present"
            
            # Method 4: Main word present (for compound names)
            elif len(name_words) > 1 and name_words[0] in text_clean:
                # Main word is usually the first word (e.g., "PENICILLIN" in "Penicillin V")
                score = 75
                match_method = f"main word '{name_words[0]}'"
            
            # Method 5: Fuzzy match (okay)
            else:
                # Try fuzzy matching on each line
                for line in text.split('\n'):
                    line_clean = line.lower().strip()
                    if len(line_clean) < 3:
                        continue
                    
                    similarity = SequenceMatcher(None, med_name, line_clean).ratio()
                    if similarity > 0.7:  # 70% similarity
                        score = similarity * 70  # Max 70 for fuzzy
                        match_method = f"fuzzy match ({similarity:.0%})"
                        break
            
            if score > 0:
                matches.append({
                    'medication': med,
                    'score': score,
                    'method': match_method,
                    'name': med.name
                })
                print(f"  ✓ Found: {med.name} (score: {score}, method: {match_method})")
        
        # Sort by score (highest first)
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        return matches
    
    def extract_dosage(self, text):
        """Extract dosage from text"""
        dosage_match = self.dosage_pattern.search(text)
        if dosage_match:
            return f"{dosage_match.group(1)} {dosage_match.group(2)}"
        return None
    
    def process_bottle_image(self, image_path):
        """Complete pipeline: OCR -> Search for known medications"""
        # Extract text
        raw_text = self.extract_text_from_bottle(image_path)
        
        if not raw_text or len(raw_text) < 3:
            return {
                'success': False,
                'message': 'Could not read text from bottle. Please ensure the label is clearly visible and well-lit.',
                'suggestions': [
                    'Hold the bottle steady',
                    'Ensure good lighting',
                    'Avoid glare on the label',
                    'Make sure text is in focus',
                    'Try holding the bottle at different angles'
                ]
            }
        
        # Search for medications in the extracted text
        matches = self.search_for_medications_in_text(raw_text)
        
        if not matches:
            return {
                'success': False,
                'message': 'No medications from your inventory were found on this label.',
                'raw_text': raw_text,
                'suggestions': [
                    'Make sure the medication is in your database first',
                    'Try scanning the label more clearly',
                    'Check that the medication name is visible in the camera'
                ]
            }
        
        # Use the best match
        best_match = matches[0]
        medication = best_match['medication']
        
        # Extract dosage from text
        dosage = self.extract_dosage(raw_text)
        
        result = {
            'success': True,
            'raw_text': raw_text,
            'medication_name': medication.name,
            'dosage': dosage or (medication.dosage if hasattr(medication, 'dosage') else None),
            'confidence': round(best_match['score'], 1),
            'match_method': best_match['method'],
            'database_match': {
                'id': medication.id,
                'name': medication.name,
                'dosage': medication.dosage if hasattr(medication, 'dosage') else None,
                'current_quantity': medication.current_quantity,
                'match_confidence': round(best_match['score'], 1),
                'exists_in_system': True
            },
            'inventory_location': None,
            'all_matches': []  # Include other possible matches
        }
        for match in matches[:3]:
            result['all_matches'].append({
                'name': match['name'],
                'score': round(match['score'], 1),
                'method': match['method']
            })
        if hasattr(medication, 'container_location') and medication.container_location:
            result['inventory_location'] = medication.container_location
        else:
            result['inventory_location'] = "Location not set in system"
        
        print(f"\n FINAL RESULT: {medication.name} ({best_match['score']:.1f}% confidence)")
        
        return result
def bottle_reading_page(request):
    "Display bottle reader page for scanning medication bottles"
    return render(request, 'bottle_reader.html')


@csrf_exempt
def read_pill_bottle(request):
    """API endpoint for reading pill bottles using OCR and triggering unlock"""
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                for chunk in image_file.chunks():
                    tmp_file.write(chunk)
                temp_path = tmp_file.name
            
            try:
                reader = PillBottleReader()
                result = reader.process_bottle_image(temp_path)
                if result.get('success') and result.get('database_match'):
                    medication_name = result.get('medication_name', 'Unknown')
                    
                    print(f"\nAttempting to unlock container for: {medication_name}")
                    unlock_success = send_esp32_unlock_for_bottle(medication_name)
                    result['unlock_status'] = unlock_success
                    
                    if unlock_success:
                        print(f"Container unlocked successfully for {medication_name}")
                        result['unlock_message'] = 'Container unlocked - you have 30 seconds to retrieve medication'
                    else:
                        print(f"Warning: Container unlock failed for {medication_name}")
                        result['unlock_message'] = 'Warning: Container unlock failed - please try manually'
                else:
                    result['unlock_status'] = False
                    result['unlock_message'] = 'Medication not found - container remains locked'
                
            finally:
                try:
                    os.remove(temp_path)
                    print(f"Temporary image deleted: {temp_path}")
                except Exception as e:
                    print(f"Could not delete temp file: {e}")
            
            return JsonResponse(result)
            
        except Exception as e:
            print(f"ERROR in read_pill_bottle: {e}")
            import traceback
            traceback.print_exc()
            
            return JsonResponse({
                'success': False,
                'error': str(e),
                'message': f'Error: {str(e)}',
                'unlock_status': False
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'message': 'POST request with image file required',
        'unlock_status': False
    }, status=400)
def send_esp32_unlock_for_bottle(medication_name):
    """Send unlock command to ESP32 after bottle detection"""
    return _send_esp32_unlock('Bottle Scanner', {
        'user_id': 'bottle_scan',
        'medication': medication_name,
        'source': 'bottle_reader'
    })



@csrf_exempt
def add_bottle_to_inventory(request):
    "Add medication from bottle reading to inventory"
    if request.method == 'POST':
        try:
            medication_id = request.POST.get('medication_id')
            quantity_to_add = int(request.POST.get('quantity', 0))
            
            medication = get_object_or_404(Medication, id=medication_id)
            previous_quantity = medication.current_quantity
            
            medication.current_quantity += quantity_to_add
            medication.save()
            
            # Log the transaction
            astronaut = request.user.astronaut if hasattr(request.user, 'astronaut') else None
            InventoryLog.objects.create(
                medication=medication,
                log_type='INTAKE',
                quantity_change=quantity_to_add,
                previous_quantity=previous_quantity,
                new_quantity=medication.current_quantity,
                performed_by=astronaut,
                notes='Added via bottle scanning'
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Added {quantity_to_add} units to {medication.name}',
                'new_quantity': medication.current_quantity
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


# ============================================================================
# PILL RECOGNITION
# ============================================================================

def pill_recognition(request):
    "Pill recognition page"
    return render(request, 'pill_recognition.html')


@csrf_exempt
def recognize_pill(request):
    "Pill recognition endpoint"
    if request.method == 'POST' and request.FILES.get('image'):
        return JsonResponse({
            'success': False,
            'message': 'Pill recognition model not yet implemented. Please upload training data and train the model.'
        })
    
    return JsonResponse({'error': 'No image provided'}, status=400)


@csrf_exempt
def delete_medication(request, medication_id):
    "Delete medication"
    if request.method == 'DELETE':
        try:
            medication = get_object_or_404(Medication, id=medication_id)
            medication.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Medication deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


def medication_inventory_graph(request):
    "Medication inventory graph page"
    return render(request, 'medication_line_graph.html')


@csrf_exempt
def medication_history_api(request):
    "Get medication history for graph"
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days) if days > 0 else None

    # Build list of every date in the range
    today = timezone.now().date()
    if since:
        start_date = since.date()
    else:
        first_log = InventoryLog.objects.order_by('timestamp').first()
        start_date = first_log.timestamp.date() if first_log else today

    all_dates = []
    current = start_date
    while current <= today:
        all_dates.append(current)
        current += timedelta(days=1)

    data = {}
    for med in Medication.objects.all():
        logs = InventoryLog.objects.filter(medication=med)
        if since:
            logs = logs.filter(timestamp__gte=since)
        logs = list(logs.order_by('timestamp'))

        if not logs:
            data[med.name] = {
                'type': med.get_medication_type_display(),
                'points': [
                    {'date': d.strftime('%Y-%m-%d'), 'quantity': med.current_quantity}
                    for d in all_dates
                ]
            }
            continue
        log_map = {}
        for log in logs:
            log_map[log.timestamp.date()] = log.new_quantity

        points = []
        last_qty = med.current_quantity
        for d in reversed(all_dates):
            if d in log_map:
                last_qty = log_map[d]
            points.append({'date': d.strftime('%Y-%m-%d'), 'quantity': last_qty})

        points.reverse()

        data[med.name] = {
            'type': med.get_medication_type_display(),
            'points': points
        }

    summary = {
        'total':    Medication.objects.count(),
        'normal':   Medication.objects.filter(status='NORMAL').count(),
        'low':      Medication.objects.filter(status='LOW').count(),
        'critical': Medication.objects.filter(status__in=['CRITICAL', 'OUT']).count(),
    }
    return JsonResponse({'data': data, 'summary': summary})
