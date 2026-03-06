from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import json # Ensure json is imported for default value

# This model will store the prediction history for each user (Image Prediction)
class Prediction(models.Model):
    # Link this prediction to a specific user
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Store the image they uploaded
    image = models.ImageField(upload_to='predictions/')
    
    crop_type = models.CharField(max_length=100)
    symptoms = models.TextField(blank=True, null=True) # Contains JSON details from AI
    
    # The result from your ML model
    disease = models.CharField(max_length=200)
    severity = models.CharField(max_length=50, default='Unknown') # Added severity field
    
    # The date of the prediction
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.crop_type} ({self.disease})"

# --------------------------------------------------
# --- ✅ NEW: VIDEO ANALYSIS MODEL (AI Crop Guardian) ---
# --------------------------------------------------

class VideoAnalysis(models.Model):
    """Stores information about a field video upload and its AI analysis result."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Store the 30-second video file
    video_file = models.FileField(upload_to='field_videos/')
    
    # Status tracking (helpful for long-running AI tasks)
    status = models.CharField(
        max_length=50, 
        default='PENDING', 
        choices=[
            ('PENDING', 'Pending Analysis'),
            ('ANALYZING', 'Analyzing Video'),
            ('COMPLETED', 'Analysis Completed'),
            ('FAILED', 'Analysis Failed')
        ]
    )
    
    # Date of analysis initiation
    date = models.DateTimeField(auto_now_add=True)
    
    # Store the comprehensive AI output as a JSON string
    # Default is an empty JSON object string to avoid database errors
    analysis_result = models.JSONField(default=dict)

    def __str__(self):
        return f"Video {self.id} - {self.user.username} - {self.status}"
    
    def get_analysis_data(self):
        """Helper to get Python dictionary from JSONField."""
        return self.analysis_result

# --------------------------------------------------
# --- USER PROFILE MODEL (Unchanged) ---
# --------------------------------------------------

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Fields required by your views
    language = models.CharField(max_length=20, default="en")  
    location = models.CharField(max_length=100, blank=True, null=True)
    main_crops = models.TextField(blank=True, null=True)
    soil_type = models.CharField(max_length=100, blank=True, null=True)


    def __str__(self):
        return f"{self.user.username}'s Profile"

# --- These functions automatically create/save a UserProfile (Unchanged)
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()


# --------------------------------------------------
# --- CHAT MESSAGE MODEL (Context-Aware Chatbot) ---
# --------------------------------------------------
class ChatMessage(models.Model):
    """Stores individual chat messages for context-aware conversation history."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    role = models.CharField(max_length=10, choices=[('user', 'User'), ('model', 'Model')])
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user.username} [{self.role}]: {self.message[:50]}"


# --------------------------------------------------
# --- CIRCLE-OF-TRUST MARKETPLACE MODEL ---
# --------------------------------------------------
class MarketplaceListing(models.Model):
    """Hyper-local marketplace listing — visible only to users in the same location."""
    CATEGORIES = [
        ('SEEDS', 'Seeds / Heritage Seeds'),
        ('FERT',  'Organic Fertilizer'),
        ('CROP',  'Surplus Harvest'),
        ('OTHER', 'Other'),
    ]
    seller        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    category      = models.CharField(max_length=10, choices=CATEGORIES, default='CROP')
    item_name     = models.CharField(max_length=200)
    description   = models.TextField(blank=True)
    quantity_str  = models.CharField(max_length=100, default='')   # e.g. "3 kg"
    price         = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_exchange   = models.BooleanField(default=False)             # True for seed-swap (price=0)
    location_tag  = models.CharField(max_length=150, db_index=True) # from UserProfile.location
    is_available  = models.BooleanField(default=True)
    seed_guardian = models.BooleanField(default=False)             # earned on seed swaps
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item_name} by {self.seller.username} @ {self.location_tag}"