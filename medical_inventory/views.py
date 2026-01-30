# views.py - Complete pill recognition implementation

from django.shortcuts import render, get_object_or_404
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
    
    return JsonResponse({'error': 'No image provided'}, status=400)