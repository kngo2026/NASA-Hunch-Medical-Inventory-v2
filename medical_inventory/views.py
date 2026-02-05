<<<<<<< HEAD
# views.py - Single capture facial recognition (no streaming)
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
=======
# views.py - Complete pill recognition implementation

from django.shortcuts import render, get_object_or_404
>>>>>>> 96694b898cbf97e57f11858eafeb0c016c7b690b
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from PIL import Image
import numpy as np
import cv2
import os
from .models import Medication

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
import pickle
<<<<<<< HEAD
import requests
import json
from datetime import timedelta
from .models import Astronaut, Medication, Prescription, MedicationCheckout, InventoryLog, SystemLog
from .forms import MedicationForm


# Configuration
ESP32_IP = ""
=======

>>>>>>> 96694b898cbf97e57f11858eafeb0c016c7b690b

# ============================================================================
# APPROACH 1: Deep Learning CNN Model (Most Accurate)
# ============================================================================

def load_pill_recognition_model():
    """Load the trained CNN model for pill recognition"""
    model_path = os.path.join('models', 'pill_recognition_model.h5')
    
    if os.path.exists(model_path) and TENSORFLOW_AVAILABLE:
        try:
            model = keras.models.load_model(model_path)
            return model
        except Exception as e:
            print(f"Error loading model: {e}")
            return None
    return None
def send_unlock_signal():
    """Send unlock signal to ESP32 via serial"""
    if esp32_serial:
        try:
            esp32_serial.write(b'unlock')  # unlock command
            response = esp32_serial.readline().decode().strip()
            return response == 'UNLOCKED'
        except Exception as e:
            print(f"Error sending unlock signal: {e}")
            return False
    return False 

# def send_lock_signal():
#     """Send lock signal to ESP32 via serial"""
#     if esp32_serial:
#         try:
#             esp32_serial.write(b'lock')  # unlock command
#             response = esp32_serial.readline().decode().strip()
#             return response == 'LOCKED'
#         except Exception as e:
#             print(f"Error sending unlock signal: {e}")
#             return False
#     return False

def home(request):
    """Home screen"""
    return render(request, 'home.html')


def preprocess_image_for_cnn(image_path, target_size=(224, 224)):
    """Preprocess image for CNN model"""
    img = Image.open(image_path)
    img = img.convert('RGB')
    img = img.resize(target_size)
    img_array = np.array(img)
    img_array = img_array / 255.0  # Normalize to 0-1
    img_array = np.expand_dims(img_array, axis=0)  # Add batch dimension
    return img_array

def recognize_pill_with_cnn(image_path):
    """
    Recognize pill using trained CNN model
    Returns: (medication_id, confidence, medication_name)
    """
    model = load_pill_recognition_model()
    
    if model is None:
        return None, 0.0, "Model not loaded"
    
    # Preprocess image
    processed_image = preprocess_image_for_cnn(image_path)
    
    # Make prediction
    predictions = model.predict(processed_image)
    predicted_class = np.argmax(predictions[0])
    confidence = float(predictions[0][predicted_class]) * 100
    
    # Load class labels (you need to create this file during training)
    labels_path = os.path.join('models', 'pill_labels.pkl')
    if os.path.exists(labels_path):
        with open(labels_path, 'rb') as f:
            class_labels = pickle.load(f)
        medication_name = class_labels[predicted_class]
    else:
        medication_name = f"Class_{predicted_class}"
    
    return predicted_class, confidence, medication_name


# ============================================================================
# APPROACH 2: Color and Shape Analysis (Fallback Method)
# ============================================================================

def extract_pill_features(image_path):
    """
    Extract color and shape features from pill image
    Returns: dict with color, shape, and size information
    """
    # Read image
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Convert to grayscale for shape detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Detect edges
    edges = cv2.Canny(blurred, 50, 150)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Get the largest contour (assumed to be the pill)
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Calculate shape features
    area = cv2.contourArea(largest_contour)
    perimeter = cv2.arcLength(largest_contour, True)
    circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
    
    # Approximate shape
    epsilon = 0.04 * perimeter
    approx = cv2.approxPolyDP(largest_contour, epsilon, True)
    num_sides = len(approx)
    
    # Determine shape
    if num_sides < 6 and circularity > 0.7:
        shape = "ROUND"
    elif num_sides == 4:
        shape = "SQUARE"
    elif 4 < num_sides < 8:
        shape = "OVAL"
    else:
        shape = "CAPSULE"
    
    # Extract dominant colors
    img_flat = img_rgb.reshape(-1, 3)
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    kmeans.fit(img_flat)
    dominant_colors = kmeans.cluster_centers_.astype(int)
    
    # Convert RGB to color names
    color_name = rgb_to_color_name(dominant_colors[0])
    
    # Get bounding rectangle for size
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    return {
        'shape': shape,
        'color': color_name,
        'circularity': round(circularity, 2),
        'width': w,
        'height': h,
        'area': int(area),
        'num_sides': num_sides,
        'dominant_colors': dominant_colors.tolist()
    }


def rgb_to_color_name(rgb):
    """Convert RGB values to common color names"""
    r, g, b = rgb
    
    # Define color thresholds
    if r > 200 and g > 200 and b > 200:
        return "WHITE"
    elif r < 50 and g < 50 and b < 50:
        return "BLACK"
    elif r > 180 and g < 100 and b < 100:
        return "RED"
    elif r < 100 and g > 180 and b < 100:
        return "GREEN"
    elif r < 100 and g < 100 and b > 180:
        return "BLUE"
    elif r > 180 and g > 180 and b < 100:
        return "YELLOW"
    elif r > 180 and g > 100 and b < 100:
        return "ORANGE"
    elif r > 150 and g < 100 and b > 150:
        return "PINK"
    elif r > 120 and g > 60 and b < 60:
        return "BROWN"
    else:
        return "MULTI-COLOR"


def match_pill_by_features(features):
    """
    Match pill to database by color and shape features
    Returns: list of potential matches with confidence scores
    """
    if not features:
        return []
    
    # Query medications from database
    medications = Medication.objects.filter(current_quantity__gt=0)
    
    matches = []
    for med in medications:
        score = 0
        
        # Compare shape (stored in medication description or custom field)
        # You would need to add these fields to your Medication model
        if hasattr(med, 'pill_shape') and med.pill_shape == features['shape']:
            score += 40
        
        # Compare color
        if hasattr(med, 'pill_color') and med.pill_color == features['color']:
            score += 40
        
        # Compare size (if you have this data)
        if hasattr(med, 'pill_size'):
            # Add size comparison logic
            pass
        
        if score > 30:  # Threshold for potential match
            matches.append({
                'medication': med,
                'confidence': score,
                'reason': f"Matched on shape: {features['shape']}, color: {features['color']}"
            })

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
                        
                        unlocked_sent = send_unlock_signal()
                        
                        SystemLog.objects.create(
                            event_type='AUTH_SUCCESS',
                            astronaut=astronaut,
                            description=f"Astronaut {astronaut.name} successfully authenticated",
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'astronaut_id': astronaut.id,
                            'astronaut_name': astronaut.name,
                            'door_unlocked': unlocked_sent,
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
    
    # Sort by confidence
    matches.sort(key=lambda x: x['confidence'], reverse=True)
    return matches[:5]  # Return top 5 matches


# ============================================================================
# APPROACH 3: Image Similarity Matching
# ============================================================================

def calculate_image_similarity(image1_path, image2_path):
    """
    Calculate similarity between two images using histogram comparison
    Returns: similarity score (0-100)
    """
    # Read images
    img1 = cv2.imread(image1_path)
    img2 = cv2.imread(image2_path)
    
    if img1 is None or img2 is None:
        return 0
    
    # Resize to same size
    img1 = cv2.resize(img1, (224, 224))
    img2 = cv2.resize(img2, (224, 224))
    
    # Convert to HSV for better color comparison
    img1_hsv = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
    img2_hsv = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
    
    # Calculate histograms
    hist1 = cv2.calcHist([img1_hsv], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    hist2 = cv2.calcHist([img2_hsv], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    
    # Normalize histograms
    hist1 = cv2.normalize(hist1, hist1).flatten()
    hist2 = cv2.normalize(hist2, hist2).flatten()
    
    # Compare histograms using correlation
    similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    
    return similarity * 100  # Convert to percentage


def match_pill_by_image(uploaded_image_path):
    """
    Match pill by comparing uploaded image to stored medication images
    Returns: list of matches with similarity scores
    """
    medications = Medication.objects.filter(
        current_quantity__gt=0,
        pill_image__isnull=False
    ).exclude(pill_image='')
    
    matches = []
    for med in medications:
        if med.pill_image:
            try:
                stored_image_path = med.pill_image.path
                similarity = calculate_image_similarity(uploaded_image_path, stored_image_path)
                
                if similarity > 60:  # Threshold for similarity
                    matches.append({
                        'medication': med,
                        'confidence': round(similarity, 2),
                        'reason': f"Visual similarity: {similarity:.1f}%"
                    })
            except Exception as e:
                print(f"Error comparing with {med.name}: {e}")
                continue
    
    matches.sort(key=lambda x: x['confidence'], reverse=True)
    return matches[:5]


# ============================================================================
# MAIN RECOGNITION FUNCTION
# ============================================================================

@csrf_exempt
def recognize_pill(request):
    """
    API endpoint for pill recognition using multiple approaches
    Tries: 1) CNN model, 2) Feature matching, 3) Image similarity
    """
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            
            # Save uploaded image temporarily
            image_path = default_storage.save(f'temp/{image_file.name}', image_file)
            full_path = default_storage.path(image_path)
            
            results = {
                'success': False,
                'method_used': None,
                'matches': [],
                'features': None
            }
            
            # APPROACH 1: Try CNN model first (most accurate)
            if TENSORFLOW_AVAILABLE:
                try:
                    med_id, confidence, med_name = recognize_pill_with_cnn(full_path)
                    
                    if med_id is not None and confidence > 70:  # Confidence threshold
                        # Try to find medication in database
                        try:
                            medication = Medication.objects.get(id=med_id)
                            results['success'] = True
                            results['method_used'] = 'CNN_MODEL'
                            results['matches'] = [{
                                'medication_id': medication.id,
                                'name': medication.name,
                                'generic_name': medication.generic_name,
                                'dosage': medication.dosage,
                                'confidence': round(confidence, 2),
                                'current_quantity': medication.current_quantity,
                                'image_url': medication.pill_image.url if medication.pill_image else None
                            }]
                            
                            # Clean up and return
                            default_storage.delete(image_path)
                            return JsonResponse(results)
                        except Medication.DoesNotExist:
                            pass
                except Exception as e:
                    print(f"CNN recognition failed: {e}")
            
            # APPROACH 2: Feature-based matching
            try:
                features = extract_pill_features(full_path)
                
                if features:
                    results['features'] = features
                    feature_matches = match_pill_by_features(features)
                    
                    if feature_matches:
                        results['success'] = True
                        results['method_used'] = 'FEATURE_MATCHING'
                        results['matches'] = [{
                            'medication_id': match['medication'].id,
                            'name': match['medication'].name,
                            'generic_name': match['medication'].generic_name,
                            'dosage': match['medication'].dosage,
                            'confidence': match['confidence'],
                            'reason': match['reason'],
                            'current_quantity': match['medication'].current_quantity,
                            'image_url': match['medication'].pill_image.url if match['medication'].pill_image else None
                        } for match in feature_matches]
                        
                        # Clean up and return
                        default_storage.delete(image_path)
                        return JsonResponse(results)
            except Exception as e:
                print(f"Feature matching failed: {e}")
            
            # APPROACH 3: Image similarity matching
            try:
                similarity_matches = match_pill_by_image(full_path)
                
                if similarity_matches:
                    results['success'] = True
                    results['method_used'] = 'IMAGE_SIMILARITY'
                    results['matches'] = [{
                        'medication_id': match['medication'].id,
                        'name': match['medication'].name,
                        'generic_name': match['medication'].generic_name,
                        'dosage': match['medication'].dosage,
                        'confidence': match['confidence'],
                        'reason': match['reason'],
                        'current_quantity': match['medication'].current_quantity,
                        'image_url': match['medication'].pill_image.url if match['medication'].pill_image else None
                    } for match in similarity_matches]
                    
                    # Clean up and return
                    default_storage.delete(image_path)
                    return JsonResponse(results)
            except Exception as e:
                print(f"Image similarity matching failed: {e}")
            
            # No matches found
            default_storage.delete(image_path)
            return JsonResponse({
                'success': False,
                'message': 'No matching medication found. Please try again with a clearer image or select manually.',
                'features': results.get('features'),
                'method_used': 'NONE'
            })
            
        except Exception as e:
            # Clean up on error
            if 'image_path' in locals():
                try:
                    default_storage.delete(image_path)
                except:
                    pass
            
            return JsonResponse({
                'success': False,
                'message': f'Error processing image: {str(e)}'
            })
    
<<<<<<< HEAD
    return JsonResponse({'error': 'No image provided'}, status=400)


# ===== ADMIN API ENDPOINTS =====

@csrf_exempt
def add_astronaut(request):
    """Add new astronaut with face photo"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            astronaut_id = request.POST.get('astronaut_id')
            password = request.POST.get('password', '')
            photo = request.FILES.get('photo')
            
            if not all([name, astronaut_id, photo]):
                return JsonResponse({
                    'success': False,
                    'message': 'Name, Astronaut ID, and photo are required'
                })
            
            # Create user account
            from django.contrib.auth.models import User
            username = astronaut_id.lower()
            user = User.objects.create_user(
                username=username,
                email=f"{username}@nasa.gov",  # Auto-generate email
                password=password if password else astronaut_id
            )
            
            # Create astronaut
            astronaut = Astronaut.objects.create(
                user=user,
                astronaut_id=astronaut_id,
                name=name
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
    """List all astronauts"""
    astronauts = Astronaut.objects.all()
    
    data = [{
        'id': a.id,
        'name': a.name,
        'astronaut_id': a.astronaut_id,
        'has_face_encoding': a.face_encoding is not None,
        'photo_url': None  # We don't store photos, just encodings
    } for a in astronauts]
    
    return JsonResponse({'astronauts': data})


@csrf_exempt
def update_astronaut_face(request):
    """Update astronaut face encoding"""
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
            
            # Process face encoding
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


@csrf_exempt
def add_medication(request):
    """Add new medication with image"""
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
def list_medications(request):
    """List all medications"""
    medications = Medication.objects.all()
    
    data = [{
        'id': m.id,
        'name': m.name,
        'generic_name': m.generic_name,
        'medication_type': m.get_medication_type_display(),
        'dosage': m.dosage,
        'current_quantity': m.current_quantity,
        'minimum_quantity': m.minimum_quantity,
        'container_location': m.container_location,
        'expiration_date': m.expiration_date.strftime('%Y-%m-%d') if m.expiration_date else None,
        'image_url': m.pill_image.url if m.pill_image else None
    } for m in medications]
    
    return JsonResponse({'medications': data})


@csrf_exempt
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


@csrf_exempt
def delete_medication(request, medication_id):
    """Delete medication"""
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


def manage_astronauts(request):
    """Astronaut management page"""
    return render(request, 'manage_astronauts.html')


def manage_medications(request):
    """Medication management page"""
    return render(request, 'manage_medications.html')

def inventory_dashboard(request):
    # Your existing view code
    medications = Medication.objects.all()
    total_medications = medications.count()
    low_stock_count = medications.filter(current_quantity__lte=10).count()
    # ... other context variables
    
    context = {
        'medications': medications,
        'total_medications': total_medications,
        'low_stock_count': low_stock_count,
        # ... other context
    }
    return render(request, 'inventory_dashboard.html', context)

def add_medication(request):
    if request.method == 'POST':
        form = MedicationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Medication added successfully!')
            return redirect('medical_inventory:inventory_dashboard')  # Adjust to your URL name
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = MedicationForm()
    
    return render(request, 'add_medication.html', {'form': form})
=======
    return JsonResponse({'error': 'No image provided'}, status=400)
>>>>>>> 96694b898cbf97e57f11858eafeb0c016c7b690b
