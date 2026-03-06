# main/forms.py  –  PIN-based signup with name field
from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator


class PINSignupForm(forms.Form):
    """Simplified signup: Name + Phone Number + 4-digit PIN for rural accessibility."""

    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your full name',
            'autocomplete': 'name',
        })
    )

    phone = forms.CharField(
        max_length=10,
        min_length=10,
        validators=[RegexValidator(r'^\d{10}$', 'Enter a valid 10-digit phone number.')],
        widget=forms.TextInput(attrs={
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'placeholder': 'Enter 10-digit phone number',
            'autocomplete': 'tel',
        })
    )

    pin = forms.CharField(
        max_length=4,
        min_length=4,
        validators=[RegexValidator(r'^\d{4}$', 'PIN must be exactly 4 digits.')],
        widget=forms.PasswordInput(attrs={
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'placeholder': '4-digit PIN',
            'autocomplete': 'new-password',
        })
    )

    pin_confirm = forms.CharField(
        max_length=4,
        min_length=4,
        validators=[RegexValidator(r'^\d{4}$', 'PIN must be exactly 4 digits.')],
        widget=forms.PasswordInput(attrs={
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'placeholder': 'Confirm 4-digit PIN',
            'autocomplete': 'new-password',
        })
    )

    # Optional fields
    SOIL_CHOICES = [
        ('', 'Select Soil Type'),
        ('Alluvial', 'Alluvial Soil'),
        ('Black', 'Black Soil (Regur)'),
        ('Red', 'Red Soil'),
        ('Laterite', 'Laterite Soil'),
        ('Desert', 'Desert / Sandy Soil'),
        ('Mountain', 'Mountain / Forest Soil'),
        ('Saline', 'Saline / Alkaline Soil'),
        ('Peaty', 'Peaty / Marshy Soil'),
    ]

    main_crops = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Rice, Wheat, Tomato...'})
    )

    soil_type = forms.ChoiceField(
        choices=SOIL_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean(self):
        cleaned_data = super().clean()
        pin         = cleaned_data.get('pin')
        pin_confirm = cleaned_data.get('pin_confirm')

        if pin and pin_confirm and pin != pin_confirm:
            raise forms.ValidationError("PINs do not match.")

        phone = cleaned_data.get('phone')
        if phone and User.objects.filter(username=phone).exists():
            raise forms.ValidationError("This phone number is already registered. Please login instead.")

        return cleaned_data

    def save(self):
        phone = self.cleaned_data['phone']
        pin   = self.cleaned_data['pin']
        name  = self.cleaned_data.get('name', '').strip()
        user  = User.objects.create_user(username=phone, password=pin)
        if name:
            user.first_name = name
            user.save()
        return user