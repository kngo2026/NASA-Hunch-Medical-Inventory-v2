from django import forms
from django.contrib.auth.models import User
from .models import (
    Medication, Astronaut, Prescription, MedicationCheckout, 
    MedicationThreshold, InventoryLog
)


class MedicationForm(forms.ModelForm):
    """Form for adding and editing medications"""
    class Meta:
        model = Medication
        fields = [
            'name', 'generic_name', 'medication_type', 'dosage', 
            'description', 'current_quantity', 'minimum_quantity', 
            'container_location', 'expiration_date', 'pill_image',
            'pill_shape', 'pill_color', 'pill_imprint', 'pill_size'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., Ibuprofen'
            }),
            'generic_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., Acetaminophen'
            }),
            'medication_type': forms.Select(attrs={'class': 'form-control'}),
            'dosage': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., 200mg'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Medication description and usage notes'
            }),
            'current_quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '0'
            }),
            'minimum_quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': '0'
            }),
            'container_location': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., Cabinet A-1'
            }),
            'expiration_date': forms.DateInput(attrs={
                'class': 'form-control', 
                'type': 'date'
            }),
            'pill_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'pill_shape': forms.Select(attrs={'class': 'form-control'}),
            'pill_color': forms.Select(attrs={'class': 'form-control'}),
            'pill_imprint': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Text/numbers on pill'
            }),
            'pill_size': forms.Select(attrs={'class': 'form-control'}),
        }
        
    def clean_current_quantity(self):
        """Validate current quantity is not negative"""
        quantity = self.cleaned_data.get('current_quantity')
        if quantity is not None and quantity < 0:
            raise forms.ValidationError("Quantity cannot be negative")
        return quantity
    
    def clean_minimum_quantity(self):
        """Validate minimum quantity is not negative"""
        quantity = self.cleaned_data.get('minimum_quantity')
        if quantity is not None and quantity < 0:
            raise forms.ValidationError("Minimum quantity cannot be negative")
        return quantity


class AstronautForm(forms.ModelForm):
    """Form for adding and editing astronauts"""
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username for login'
        })
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Leave blank to auto-generate'
        })
    )
    
    class Meta:
        model = Astronaut
        fields = ['astronaut_id', 'name', 'photo']
        widgets = {
            'astronaut_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., NASA001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name'
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }
    
    def clean_photo(self):
        """Validate photo is an image"""
        photo = self.cleaned_data.get('photo')
        if photo:
            # Check file size (max 5MB)
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Photo size should not exceed 5MB")
            
            # Check file type
            if not photo.content_type.startswith('image/'):
                raise forms.ValidationError("File must be an image")
        
        return photo
    
    def save(self, commit=True):
        """Create user account when saving astronaut"""
        astronaut = super().save(commit=False)
        
        # Create or get user
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if not astronaut.user_id:  # New astronaut
            if not password:
                password = User.objects.make_random_password()
            
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=astronaut.name.split()[0] if astronaut.name else '',
                last_name=' '.join(astronaut.name.split()[1:]) if len(astronaut.name.split()) > 1 else ''
            )
            astronaut.user = user
        
        if commit:
            astronaut.save()
        
        return astronaut


class PrescriptionForm(forms.ModelForm):
    """Form for managing prescriptions"""
    class Meta:
        model = Prescription
        fields = [
            'astronaut', 'medication', 'prescribed_dosage', 
            'frequency', 'start_date', 'end_date', 'notes', 'is_active'
        ]
        widgets = {
            'astronaut': forms.Select(attrs={'class': 'form-control'}),
            'medication': forms.Select(attrs={'class': 'form-control'}),
            'prescribed_dosage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2 tablets'
            }),
            'frequency': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 2x daily, as needed'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes or instructions'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
    
    def clean(self):
        """Validate end date is after start date"""
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date must be after start date")
        
        return cleaned_data


class MedicationCheckoutForm(forms.ModelForm):
    """Form for medication checkout"""
    class Meta:
        model = MedicationCheckout
        fields = ['astronaut', 'medication', 'quantity', 'is_prescription', 'notes']
        widgets = {
            'astronaut': forms.Select(attrs={'class': 'form-control'}),
            'medication': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'is_prescription': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional notes'
            })
        }
    
    def clean_quantity(self):
        """Validate quantity does not exceed available stock"""
        quantity = self.cleaned_data.get('quantity')
        medication = self.cleaned_data.get('medication')
        
        if medication and quantity:
            if quantity > medication.current_quantity:
                raise forms.ValidationError(
                    f"Insufficient stock. Only {medication.current_quantity} units available."
                )
            if quantity < 1:
                raise forms.ValidationError("Quantity must be at least 1")
        
        return quantity


class MedicationThresholdForm(forms.ModelForm):
    """Form for setting medication thresholds"""
    class Meta:
        model = MedicationThreshold
        fields = ['medication', 'daily_limit', 'single_dose_limit', 'warning_percentage']
        widgets = {
            'medication': forms.Select(attrs={'class': 'form-control'}),
            'daily_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'single_dose_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'warning_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '100',
                'value': '80'
            })
        }
    
    def clean(self):
        """Validate limits make sense"""
        cleaned_data = super().clean()
        daily_limit = cleaned_data.get('daily_limit')
        single_dose_limit = cleaned_data.get('single_dose_limit')
        
        if daily_limit and single_dose_limit:
            if single_dose_limit > daily_limit:
                raise forms.ValidationError(
                    "Single dose limit cannot exceed daily limit"
                )
        
        return cleaned_data


class InventoryAdjustmentForm(forms.Form):
    """Form for manual inventory adjustments"""
    medication = forms.ModelChoiceField(
        queryset=Medication.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    adjustment_type = forms.ChoiceField(
        choices=[
            ('RESTOCK', 'Restock'),
            ('EXPIRED', 'Remove Expired'),
            ('ADJUSTMENT', 'Manual Adjustment')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    quantity_change = forms.IntegerField(
        help_text="Positive to add, negative to remove",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., +50 or -10'
        })
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for adjustment'
        })
    )
    
    def clean_quantity_change(self):
        """Validate quantity change doesn't result in negative stock"""
        quantity_change = self.cleaned_data.get('quantity_change')
        medication = self.cleaned_data.get('medication')
        
        if medication and quantity_change:
            new_quantity = medication.current_quantity + quantity_change
            if new_quantity < 0:
                raise forms.ValidationError(
                    f"Cannot remove more than available stock ({medication.current_quantity} units)"
                )
        
        return quantity_change


class RestockForm(forms.Form):
    """Simple form for restocking medications"""
    medication = forms.ModelChoiceField(
        queryset=Medication.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Medication"
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Quantity to add'
        }),
        label="Quantity to Add"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes (e.g., supplier, batch number)'
        }),
        label="Notes"
    )


class SearchForm(forms.Form):
    """Form for searching medications"""
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search medications...'
        })
    )
    medication_type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Types')] + Medication.MEDICATION_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Stock Levels'),
            ('NORMAL', 'In Stock'),
            ('LOW', 'Low Stock'),
            ('CRITICAL', 'Critical'),
            ('OUT', 'Out of Stock')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class LoginForm(forms.Form):
    """Custom login form"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class UserRegistrationForm(forms.ModelForm):
    """Form for creating new user accounts"""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
    
    def clean_password2(self):
        """Validate passwords match"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        
        return password2
    
    def save(self, commit=True):
        """Create user with hashed password"""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()
        
        return user


class PhotoCaptureForm(forms.Form):
    """Form for capturing photos via camera"""
    photo_data = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
        help_text="Base64 encoded photo data"
    )
    astronaut_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    def clean_photo_data(self):
        """Validate photo data is valid base64"""
        photo_data = self.cleaned_data.get('photo_data')
        
        if not photo_data or not photo_data.startswith('data:image/'):
            raise forms.ValidationError("Invalid photo data")
        
        return photo_data