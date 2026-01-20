# views.py - Single capture facial recognition (no streaming)
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.core.files.storage import default_storage
import face_recognition
import pickle
import requests
import json
from datetime import timedelta
from .models import Astronaut, Medication, Prescription, MedicationCheckout, InventoryLog, SystemLog

# Configuration
ESP32_IP = "192.168.1.100"


def home(request):
    """Home screen"""
    return render(request, 'home.html')


def lockscreen(request):
    """Lockscreen with single-capture facial recognition"""
    return render(request, 'lockscreen.html')


@csrf_exempt
def authenticate_face(request):
    """Single image capture face authentication"""
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            
            # Load image with face_recognition
            image = face_recognition.load_image_file(image_file)
            
            # Find faces in the uploaded image
            face_locations = face_recognition.face_locations(image, model="hog")
            
            if not face_locations:
                SystemLog.objects.create(
                    event_type='AUTH_FAILURE',
                    description="No face detected in image",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                return JsonResponse({
                    'success': False,
                    'message': 'No face detected. Please ensure your face is clearly visible.'
                })
            
            # Get face encodings
            face_encodings = face_recognition.face_encodings(image, face_locations)
            
            if not face_encodings:
                return JsonResponse({
                    'success': False,
                    'message': 'Could not process face. Please try again.'
                })
            
            # Load known faces from database
            astronauts = Astronaut.objects.exclude(face_encoding__isnull=True)
            
            for face_encoding in face_encodings:
                for astronaut in astronauts:
                    known_encoding = pickle.loads(astronaut.face_encoding)
                    
                    # Compare faces
                    matches = face_recognition.compare_faces([known_encoding], face_encoding, tolerance=0.6)
                    
                    if matches[0]:
                        # Face recognized!
                        SystemLog.objects.create(
                            event_type='AUTH_SUCCESS',
                            astronaut=astronaut,
                            description=f"Astronaut {astronaut.name} successfully authenticated",
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'astronaut_id': astronaut.id,
                            'astronaut_name': astronaut.name
                        })
            
            # No match found
            SystemLog.objects.create(
                event_type='AUTH_FAILURE',
                description="Face not recognized - unknown individual",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({
                'success': False,
                'message': 'Face not recognized. Please ensure you are an authorized user.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Authentication error: {str(e)}'
            })
    
    return JsonResponse({'error': 'Invalid request - image required'}, status=400)



def medication_selection(request, astronaut_id):
    """Display medication selection page after authentication"""
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
    """Process medication checkout"""
    if request.method == 'POST':
        data = json.loads(request.body)
        astronaut_id = data.get('astronaut_id')
        medications = data.get('medications', [])
        
        astronaut = get_object_or_404(Astronaut, id=astronaut_id)
        checkouts = []
        
        for med_data in medications:
            medication = get_object_or_404(Medication, id=med_data['medication_id'])
            quantity = med_data.get('quantity', 1)
            
            checkout = MedicationCheckout.objects.create(
                astronaut=astronaut,
                medication=medication,
                quantity=quantity,
                is_prescription=med_data.get('is_prescription', False)
            )
            checkouts.append(checkout)
            
            InventoryLog.objects.create(
                medication=medication,
                log_type='CHECKOUT',
                quantity_change=-quantity,
                previous_quantity=medication.current_quantity + quantity,
                new_quantity=medication.current_quantity,
                performed_by=astronaut,
                notes=f"Checkout by {astronaut.name}"
            )
        
        unlock_success = unlock_container(astronaut)
        
        SystemLog.objects.create(
            event_type='CONTAINER_UNLOCK',
            astronaut=astronaut,
            description=f"Container unlocked for {astronaut.name}. Status: {'Success' if unlock_success else 'Failed'}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'checkouts': len(checkouts),
            'unlock_status': unlock_success
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)


def unlock_container(astronaut):
    """Send unlock signal to ESP32"""
    try:
        url = f"http://{ESP32_IP}/unlock"
        payload = {
            'astronaut_id': astronaut.astronaut_id,
            'timestamp': timezone.now().isoformat()
        }
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Error unlocking container: {e}")
        return False


def inventory_dashboard(request):
    """Display full inventory with statistics"""
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
    """Detailed view of a specific medication with usage statistics"""
    medication = get_object_or_404(Medication, id=medication_id)
    
    thirty_days_ago = timezone.now() - timedelta(days=30)
    checkouts = MedicationCheckout.objects.filter(
        medication=medication,
        checkout_time__gte=thirty_days_ago
    ).order_by('-checkout_time')
    
    daily_usage = MedicationCheckout.objects.filter(
        medication=medication,
        checkout_time__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('checkout_time')
    ).values('date').annotate(
        total_quantity=Sum('quantity'),
        checkout_count=Count('id')
    ).order_by('date')
    
    inventory_logs = InventoryLog.objects.filter(medication=medication)[:20]
    
    context = {
        'medication': medication,
        'checkouts': checkouts,
        'daily_usage': list(daily_usage),
        'inventory_logs': inventory_logs,
        'total_dispensed_30d': sum(item['total_quantity'] for item in daily_usage)
    }
    
    return render(request, 'medication_detail.html', context)


def pill_recognition(request):
    """Page for pill/medication recognition via camera"""
    return render(request, 'pill_recognition.html')


@csrf_exempt
def recognize_pill(request):
    """API endpoint for pill recognition using uploaded image"""
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            
            # Save uploaded image temporarily
            image_path = default_storage.save(f'temp/{image_file.name}', image_file)
            full_path = default_storage.path(image_path)
            
            # TODO: Load your trained pill recognition model here
            # For now, return placeholder response
            
            # Clean up temp file
            default_storage.delete(image_path)
            
            return JsonResponse({
                'success': False,
                'message': 'Pill recognition model not yet implemented. Upload your trained model to enable this feature.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error processing image: {str(e)}'
            })
    
    return JsonResponse({'error': 'No image provided'}, status=400)