# main/views.py  ─ Krishi Sakhi  (clean, single-file – no duplicate sections)
import os
import io
import json
import base64
import datetime
import time
from functools import wraps

import numpy as np
import cv2

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.contrib import messages
from django.views.decorators.http import require_POST

from dotenv import load_dotenv
from PIL import Image
from pathlib import Path
import google.generativeai as genai
from google.generativeai import GenerationConfig

import requests
from bs4 import BeautifulSoup

from .models import Prediction, UserProfile, VideoAnalysis, ChatMessage, MarketplaceListing
from .forms import PINSignupForm

# ─────────────────────────────────────────────────────────────
#  ML MODEL LOADING
# ─────────────────────────────────────────────────────────────
ML_DIR = os.path.join(settings.BASE_DIR, 'main', 'ml_models')

# --- 1. DISEASE MODEL (TF / Keras, used for offline crop-disease scan) ---
local_model = None
local_classes = None
try:
    from tensorflow.keras.models import load_model as tf_load_model
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input as mobilenet_preprocess

    _disease_path_h5   = os.path.join(ML_DIR, 'plant_disease_model.h5')
    _disease_path_h5_b = os.path.join(ML_DIR, 'model.h5')
    _disease_path_k    = os.path.join(ML_DIR, 'model.keras')
    _classes_path      = os.path.join(ML_DIR, 'classes.json')

    _disease_model_path = None
    for p in [_disease_path_h5, _disease_path_h5_b, _disease_path_k]:
        if os.path.exists(p):
            _disease_model_path = p
            break

    if _disease_model_path and os.path.exists(_classes_path):
        local_model = tf_load_model(_disease_model_path)
        with open(_classes_path) as f:
            local_classes = json.load(f)
        print(f"✅ Disease model loaded: {_disease_model_path}  ({len(local_classes)} classes)")
    else:
        print("⚠️  Disease model (.h5/.keras) not found – offline fallback disabled.")
except Exception as _e:
    print(f"⚠️  TF import/load failed: {_e}")

# --- 2. YIELD MODEL (sklearn RandomForest + one-hot encoders) ---
yield_model = None
yield_model_features = None   # list of 96 feature names
crop_yield_classes   = None   # dict built from encoder
season_yield_classes = None
state_yield_classes  = None

try:
    import pickle, warnings
    warnings.filterwarnings('ignore', category=UserWarning)

    _ym_path  = os.path.join(ML_DIR, 'yield_model (2).pkl')
    _ce_path  = os.path.join(ML_DIR, 'crop_encoder.pkl')
    _se_path  = os.path.join(ML_DIR, 'season_encoder.pkl')
    _ste_path = os.path.join(ML_DIR, 'state_encoder.pkl')

    if all(os.path.exists(p) for p in [_ym_path, _ce_path, _se_path, _ste_path]):
        with open(_ym_path,  'rb') as f: yield_model          = pickle.load(f)
        with open(_ce_path,  'rb') as f: _crop_encoder        = pickle.load(f)
        with open(_se_path,  'rb') as f: _season_encoder      = pickle.load(f)
        with open(_ste_path, 'rb') as f: _state_encoder       = pickle.load(f)

        crop_yield_classes   = list(_crop_encoder.classes_)
        season_yield_classes = list(_season_encoder.classes_)
        state_yield_classes  = list(_state_encoder.classes_)
        yield_model_features = list(yield_model.feature_names_in_)
        print(f"✅ Yield model loaded – {len(crop_yield_classes)} crops / {len(state_yield_classes)} states")
    else:
        print("⚠️  yield_model (2).pkl or encoders not found – yield estimation will use formula fallback.")
except Exception as _ye:
    print(f"⚠️  Yield model load failed: {_ye}")


def predict_yield(crop_name: str, state: str, area_ha: float,
                  season: str = "Kharif",
                  annual_rainfall: float = 900.0,
                  fertilizer: float = 100.0,
                  pesticide: float = 10.0) -> float:
    """
    Returns estimated yield in QUINTALS for `area_ha` hectares.
    Uses yield_model if available; falls back to a conservative formula.
    """
    if yield_model is None or yield_model_features is None:
        # Fallback: crop-based rough kg/hectare averages
        _defaults = {
            'tomato': 20000, 'potato': 18000, 'onion': 15000,
            'wheat': 3000, 'rice': 3500, 'maize': 4000,
            'sugarcane': 60000, 'cotton': 600, 'groundnut': 1500,
        }
        kg_per_ha = _defaults.get(crop_name.lower().strip(), 2000)
        return round((kg_per_ha * area_ha) / 100, 2)  # kg → quintals

    # Build the 96-dim one-hot feature vector
    # Numeric: Crop_Year, Area, Annual_Rainfall, Fertilizer, Pesticide
    # Then one-hot for Crop_, Season_, State_

    # Fuzzy-match crop
    crop_key = f'Crop_{crop_name}'
    matched_crop = None
    for c in crop_yield_classes:
        if c.strip().lower() == crop_name.strip().lower():
            matched_crop = f'Crop_{c}'
            break
    if not matched_crop:
        # try partial
        for c in crop_yield_classes:
            if crop_name.strip().lower() in c.strip().lower():
                matched_crop = f'Crop_{c}'
                break
    if not matched_crop:
        matched_crop = f'Crop_{crop_yield_classes[0]}'  # fallback to first

    # Fuzzy-match season
    matched_season = None
    for s in season_yield_classes:
        if s.strip().lower().startswith(season.strip().lower()):
            matched_season = f'Season_{s}'
            break
    if not matched_season:
        matched_season = f'Season_{season_yield_classes[0]}'

    # Fuzzy-match state
    matched_state = None
    for st in state_yield_classes:
        if st.strip().lower() == state.strip().lower():
            matched_state = f'State_{st}'
            break
    if not matched_state:
        for st in state_yield_classes:
            if state.strip().lower() in st.strip().lower():
                matched_state = f'State_{st}'
                break
    if not matched_state:
        matched_state = f'State_{state_yield_classes[0]}'

    row = {feat: 0.0 for feat in yield_model_features}
    row['Crop_Year']        = datetime.date.today().year
    row['Area']             = area_ha
    row['Annual_Rainfall']  = annual_rainfall
    row['Fertilizer']       = fertilizer
    row['Pesticide']        = pesticide
    if matched_crop   in row: row[matched_crop]   = 1.0
    if matched_season in row: row[matched_season] = 1.0
    if matched_state  in row: row[matched_state]  = 1.0

    X = np.array([[row[f] for f in yield_model_features]])
    try:
        kg = yield_model.predict(X)[0]
        return round(kg / 100, 2)           # kg → quintals
    except Exception as _pe:
        print(f"⚠️  yield_model.predict failed: {_pe}")
        return round((2000 * area_ha) / 100, 2)


# ─────────────────────────────────────────────────────────────
#  CONFIG & GEMINI
# ─────────────────────────────────────────────────────────────
load_dotenv()
GOOGLE_API_KEY        = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_CHAT     = os.environ.get("GEMINI_MODEL_CHAT",     "models/gemini-2.5-flash")
GEMINI_MODEL_VISION   = os.environ.get("GEMINI_MODEL_VISION",   "models/gemini-2.5-flash")
GEMINI_MODEL_VISION_PRO = os.environ.get("GEMINI_MODEL_VISION_PRO", "models/gemini-2.5-flash")
GEMINI_MODEL_FORECAST = os.environ.get("GEMINI_MODEL_FORECAST", GEMINI_MODEL_CHAT)

system_instruction = """
You are 'Sakhi', an expert agronomist and smart farming assistant for farmers in India.
Be concise and practical. Answer in the user's preferred language. When asked for structured JSON,
respond strictly with the JSON object/array only (no extra text).
"""

chat_model  = None

if not GOOGLE_API_KEY:
    print("❌ GOOGLE_API_KEY not found – Gemini features disabled.")
else:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        chat_model = genai.GenerativeModel(GEMINI_MODEL_CHAT, system_instruction=system_instruction)
        print(f"✅ Gemini configured ({GEMINI_MODEL_CHAT})")
    except Exception as _ge:
        print("❌ Gemini init error:", _ge)

# ─────────────────────────────────────────────────────────────
#  HELPER UTILITIES
# ─────────────────────────────────────────────────────────────
def ensure_gemini(func):
    @wraps(func)
    def inner(request, *args, **kwargs):
        if not chat_model:
            return JsonResponse({"error": "AI not configured. Check GOOGLE_API_KEY."}, status=500)
        return func(request, *args, **kwargs)
    return inner


def clean_ai_json_string(text):
    if not text:
        return "{}"
    s = text.strip()
    start = next((i for i, c in enumerate(s) if c in ('{', '[')), None)
    if start is None:
        return "{}"
    end = next((i for i in range(len(s)-1, -1, -1) if s[i] in ('}', ']')), None)
    if end is None or end < start:
        return "{}"
    return s[start:end+1]


def extract_text_from_genai_response(obj):
    try:
        if hasattr(obj, "text") and isinstance(obj.text, str):
            return obj.text
        if isinstance(obj, dict):
            if 'candidates' in obj and obj['candidates']:
                cand = obj['candidates'][0]
                if isinstance(cand, dict) and 'content' in cand:
                    cont = cand['content']
                    if isinstance(cont, list):
                        return "\n".join(p.get('text', '') for p in cont if isinstance(p, dict))
                    return cont if isinstance(cont, str) else ""
        return str(obj)
    except Exception:
        return str(obj)


def get_user_lang(request, full=False):
    """
    Returns the user's preferred language code.
    full=True → BCP-47 like 'kn-IN'; False → 'kn'
    Falls back to profile, then session, then 'hi'.
    """
    lang = 'hi'
    try:
        profile = request.user.userprofile
        if profile and profile.language:
            lang = profile.language
    except Exception:
        pass

    if not full:
        return lang

    _bcp = {
        'hi': 'hi-IN', 'kn': 'kn-IN', 'ta': 'ta-IN',
        'te': 'te-IN', 'mr': 'mr-IN', 'en': 'en-US',
    }
    return _bcp.get(lang, 'hi-IN')


AGRI_FACTS = [
    "India is the world's largest producer of milk, pulses, and jute.",
    "The monsoon is often called the 'true finance minister of India'.",
    "India's agriculture sector employs nearly half of the country's workforce.",
    "The Green Revolution in India started in the 1960s.",
    "Black soil (Regur soil) is ideal for growing cotton and sugarcane.",
]

# ─────────────────────────────────────────────────────────────
#  LANGUAGE DETECTION
# ─────────────────────────────────────────────────────────────
def api_detect_language(request):
    try:
        ip = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', '')
        )
        if ip in ('127.0.0.1', '::1', ''):
            return JsonResponse({'lang': 'kn', 'debug': 'local_dev_override'})

        geo_url = f'https://get.geojs.io/v1/ip/geo/{ip}.json'
        resp = requests.get(geo_url, timeout=3)
        data = resp.json()

        lang = 'hi'
        if data.get('country') == 'India' or data.get('country_code') == 'IN':
            region = (data.get('region') or '').lower()
            city   = (data.get('city') or '').lower()
            if 'tamil' in region:                                      lang = 'ta'
            elif 'telangana' in region or 'andhra' in region:         lang = 'te'
            elif 'karnataka' in region or 'bengaluru' in city:        lang = 'kn'
            elif 'maharashtra' in region or 'mumbai' in city:         lang = 'mr'
        else:
            lang = 'en'

        return JsonResponse({'lang': lang})
    except Exception as e:
        print("❌ detect_language:", e)
        return JsonResponse({'lang': 'hi'})


def set_language(request):
    lang_code = request.GET.get('lang', 'en')
    request.session['cur_lang'] = lang_code
    return redirect(request.META.get('HTTP_REFERER', 'index'))


# ─────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────
def index_view(request):
    lang = request.GET.get('lang', 'en')
    try:
        profile_lang = request.user.userprofile.language if request.user.is_authenticated else 'en'
        if profile_lang and profile_lang != 'en':
            lang = profile_lang
    except Exception:
        pass

    translations = {
        'hi': {'morning': 'सुप्रभात', 'afternoon': 'शुभ दोपहर', 'evening': 'शुभ संध्या', 'welcome': 'स्वागत है'},
        'ta': {'morning': 'காலை வணக்கம்', 'afternoon': 'மதிய வணக்கம்', 'evening': 'மாலை வணக்கம்', 'welcome': 'நல்வரவு'},
        'te': {'morning': 'శుభోదయం', 'afternoon': 'శుభ మధ్యాహ్నం', 'evening': 'శుభ సాయంత్రం', 'welcome': 'స్వాగతం'},
        'kn': {'morning': 'ಶುಭೋದಯ', 'afternoon': 'ಶುಭ ಮಧ್ಯಾಹ್ನ', 'evening': 'ಶುಭ ಸಂಜೆ', 'welcome': 'ಸ್ವಾಗತ'},
    }
    greeting = "Welcome"
    if request.user.is_authenticated:
        hour = datetime.datetime.now().hour
        time_key = 'morning' if hour < 12 else ('afternoon' if hour < 17 else 'evening')
        if lang in translations:
            greeting = translations[lang].get(time_key, "Welcome")
        else:
            greeting = {'morning': 'Good morning', 'afternoon': 'Good afternoon', 'evening': 'Good evening'}[time_key]
    else:
        if lang in translations:
            greeting = translations[lang].get('welcome', "Welcome")

    # Get display name: first_name > username (but don't show phone number)
    display_name = ""
    if request.user.is_authenticated:
        fn = request.user.first_name.strip()
        display_name = fn if fn else "Farmer"

    return render(request, "index.html", {
        "timeGreeting": greeting,
        "display_name": display_name,
    })


def signup_view(request):
    if request.method == "POST":
        form = PINSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            try:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.main_crops = form.cleaned_data.get('main_crops') or profile.main_crops
                profile.soil_type  = form.cleaned_data.get('soil_type')  or profile.soil_type
                profile.save()
            except Exception as e:
                print("⚠️ UserProfile save:", e)
            login(request, user)
            return redirect('index')
        else:
            return render(request, "signup.html", {"form": form})
    return render(request, "signup.html", {"form": PINSignupForm()})


def login_view(request):
    if request.method == "POST":
        phone = request.POST.get("username")
        pin   = request.POST.get("password")
        user  = authenticate(request, username=phone, password=pin)
        if user:
            login(request, user)
            return redirect('index')
        return render(request, "login.html", {"error": "Invalid phone number or PIN!"})
    return render(request, "login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect('index')


def api_demo_login(request):
    """
    One-click demo login: creates (or retrieves) demo account phone=9999999999 PIN=1234.
    Returns a redirect to index. Demo user displays as 'Demo Farmer' on home screen.
    """
    User = get_user_model()
    DEMO_PHONE = '9999999999'
    DEMO_PIN   = '1234'
    DEMO_NAME  = 'Demo Farmer'

    try:
        user, created = User.objects.get_or_create(username=DEMO_PHONE)
        # Always (re)set password and name to keep demo account fresh
        user.set_password(DEMO_PIN)
        user.first_name = DEMO_NAME
        user.save()

        try:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.main_crops:
                profile.main_crops = 'Wheat, Rice, Maize'
            if not profile.soil_type:
                profile.soil_type = 'Alluvial'
            if not profile.location:
                profile.location = 'Karnataka'
            profile.language = 'kn'
            profile.save()
        except Exception as pe:
            print('⚠️ Demo profile:', pe)

        # Use the Django authenticate + login flow for proper session setup
        auth_user = authenticate(request, username=DEMO_PHONE, password=DEMO_PIN)
        if auth_user:
            login(request, auth_user)
        else:
            # Fallback: direct login (bypasses authenticate)
            from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
    except Exception as e:
        print("❌ Demo login error:", e)

    return redirect('index')


# ─────────────────────────────────────────────────────────────
#  PREDICT (Disease scan – Gemini Vision + .h5 fallback)
# ─────────────────────────────────────────────────────────────
@login_required
def predict_view(request):
    if request.method == "POST":
        crop_type  = request.POST.get("crop-type", "").strip()
        symptoms   = request.POST.get("symptoms", "").strip()
        image_file = request.FILES.get("image")

        if not image_file:
            return render(request, "predict.html", {"error": "Please upload an image."})
        if not chat_model:
            return render(request, "predict.html", {"error": "AI model not configured."})

        user_lang = get_user_lang(request)
        lang_name = {'hi': 'Hindi', 'ta': 'Tamil', 'te': 'Telugu', 'kn': 'Kannada', 'mr': 'Marathi'}.get(user_lang, 'English')

        try:
            prompt = f"""
You are an expert plant pathologist 'Sakhi'.
A farmer uploaded an image of '{crop_type}'. Reported symptoms: "{symptoms}".
Respond in {lang_name}.
Return ONLY a JSON object with keys:
- disease_name, severity (Low|Medium|High), cause, solution (array of {{step, details}}).
"""
            vision  = genai.GenerativeModel(GEMINI_MODEL_VISION_PRO)
            gen_conf = GenerationConfig(response_mime_type="application/json")
            img      = Image.open(image_file)
            response = vision.generate_content([prompt, img], generation_config=gen_conf)
            details  = json.loads(clean_ai_json_string(extract_text_from_genai_response(response)))

            pred = Prediction.objects.create(
                user=request.user, image=image_file, crop_type=crop_type,
                symptoms=json.dumps(details),
                disease=details.get('disease_name', ''),
                severity=details.get('severity', '')
            )
            return redirect('result_detail', prediction_id=pred.id)

        except Exception as e:
            print("❌ predict_view:", e)
            err = {"disease_name": "Analysis Failed", "severity": "Unknown",
                   "cause": str(e), "solution": [{"step": "Retry", "details": "Upload a clearer image."}]}
            pred = Prediction.objects.create(
                user=request.user, image=image_file, crop_type=crop_type,
                symptoms=json.dumps(err), disease=err['disease_name'], severity=err['severity']
            )
            return redirect('result_detail', prediction_id=pred.id)

    return render(request, "predict.html")


@require_POST
@login_required
def api_scan_crop(request):
    """
    POST FormData 'image'.
    1. Try Gemini Vision for full analysis.
    2. Offline fallback: plant_disease_model.h5 (MobileNetV2).
    Voice-output language follows user profile.
    """
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'No image uploaded.'}, status=400)

    user_lang = get_user_lang(request)
    lang_name = {'hi': 'Hindi', 'ta': 'Tamil', 'te': 'Telugu', 'kn': 'Kannada', 'mr': 'Marathi'}.get(user_lang, 'English')

    # ── Gemini path ──
    if chat_model:
        try:
            prompt = f"""
You are an expert plant pathologist 'Sakhi'. Respond in {lang_name}.
Return ONLY JSON:
{{"crop_name":"...","disease_name":"...","severity":"Low|Medium|High","cause":"...","cure":"...","home_remedies":"...","solution":[{{"step":"...","details":"..."}}]}}
"""
            vision   = genai.GenerativeModel(GEMINI_MODEL_VISION)
            gen_conf = GenerationConfig(response_mime_type="application/json")
            img      = Image.open(image_file)
            response = vision.generate_content([prompt, img], generation_config=gen_conf)
            details  = json.loads(clean_ai_json_string(extract_text_from_genai_response(response)))

            image_file.seek(0)
            pred = Prediction.objects.create(
                user=request.user, image=image_file,
                crop_type=details.get('crop_name', 'Unknown'),
                symptoms=json.dumps(details),
                disease=details.get('disease_name', ''),
                severity=details.get('severity', '')
            )
            details['prediction_id'] = pred.id
            details['voice_lang']    = get_user_lang(request, full=True)
            return JsonResponse(details)
        except Exception as e:
            print("⚠️ Gemini scan_crop failed, trying local model:", e)

    # ── Offline: plant_disease_model.h5 ──
    if local_model and local_classes:
        try:
            image_file.seek(0)
            file_bytes = np.frombuffer(image_file.read(), dtype=np.uint8)
            img_cv  = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            img_cv  = cv2.resize(img_cv, (224, 224))
            img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
            img_arr = mobilenet_preprocess(np.expand_dims(img_rgb.astype(np.float32), 0))

            preds     = local_model.predict(img_arr)
            class_idx = int(np.argmax(preds[0]))
            predicted_class = local_classes[class_idx]

            parts      = predicted_class.replace('___', '_').split('_', 1)
            crop_name  = parts[0]
            disease    = parts[1].replace('_', ' ') if len(parts) > 1 else predicted_class
            is_healthy = 'healthy' in disease.lower()

            details = {
                'crop_name':     crop_name,
                'disease_name':  disease,
                'severity':      'Low' if is_healthy else 'Medium (Offline)',
                'cause':         'None (Healthy)' if is_healthy else 'Detected by offline model.',
                'cure':          'None needed.' if is_healthy else 'Consult an agronomist.',
                'home_remedies': 'Maintain good farming practices.' if is_healthy else 'Neem oil spray may help.',
                'solution':      [{'step': 'Offline Result', 'details': 'AI offline. Visit the nearest KVK (Krishi Vigyan Kendra) for advice.'}],
                'offline': True,
                'voice_lang': get_user_lang(request, full=True),
            }
            image_file.seek(0)
            pred = Prediction.objects.create(
                user=request.user, image=image_file,
                crop_type=crop_name, symptoms=json.dumps(details),
                disease=disease, severity=details['severity']
            )
            details['prediction_id'] = pred.id
            return JsonResponse(details)
        except Exception as le:
            print("❌ Local model fallback failed:", le)

    return JsonResponse({
        'crop_name': 'Unknown', 'disease_name': 'Analysis Failed',
        'severity': 'Unknown', 'cause': 'No AI or local model available.',
        'solution': [{'step': 'Retry', 'details': 'Ensure internet or local model is loaded.'}]
    }, status=500)


# ─────────────────────────────────────────────────────────────
#  RESULT DETAIL + HISTORY
# ─────────────────────────────────────────────────────────────
@login_required
def result_detail_view(request, prediction_id):
    try:
        pred = get_object_or_404(Prediction, id=prediction_id, user=request.user)
    except Exception:
        return redirect('history')

    try:
        details = json.loads(clean_ai_json_string(pred.symptoms or "{}"))
    except Exception:
        details = {"disease_name": pred.disease or "Unknown", "severity": pred.severity, "cause": "No data", "solution": []}

    user_lang = get_user_lang(request)
    req_lang  = request.GET.get('lang')

    if req_lang and req_lang != 'en' and chat_model:
        try:
            lang_name = {'hi': 'Hindi', 'ta': 'Tamil', 'te': 'Telugu', 'kn': 'Kannada', 'mr': 'Marathi'}.get(req_lang, 'English')
            resp = chat_model.generate_content(
                f"Translate the *values* (not keys) in this JSON to {lang_name}:\n{json.dumps(details)}\nRespond with ONLY the JSON.",
                generation_config=GenerationConfig(response_mime_type="application/json")
            )
            details = json.loads(clean_ai_json_string(extract_text_from_genai_response(resp)))
        except Exception as e:
            print("❌ Translation:", e)

    return render(request, "result_detail.html", {
        "prediction": pred, "details": details,
        "current_lang": req_lang or user_lang,
        "voice_lang": get_user_lang(request, full=True),
    })


@login_required
def history_view(request):
    image_history = Prediction.objects.filter(user=request.user).order_by('-date')[:50]
    video_history = VideoAnalysis.objects.filter(user=request.user).order_by('-date')[:50]
    combined = sorted(list(image_history) + list(video_history), key=lambda x: x.date, reverse=True)[:100]
    return render(request, "history.html", {"prediction_history": combined})


# ─────────────────────────────────────────────────────────────
#  VIDEO ANALYSIS (AI Crop Guardian)
# ─────────────────────────────────────────────────────────────
@login_required
def analyze_field_dashboard_view(request):
    return render(request, "analyze_field_dashboard.html")


@login_required
def video_analysis_upload_view(request):
    if request.method == "POST":
        video_file = request.FILES.get("video")
        if not video_file:
            messages.error(request, "Please upload a valid video file.")
            return render(request, "video_analysis.html")
        try:
            rec = VideoAnalysis.objects.create(
                user=request.user, video_file=video_file,
                status='PENDING', analysis_result={"error": "Analysis not started."}
            )
            return redirect('video_result_detail', video_id=rec.id)
        except Exception as e:
            messages.error(request, f"Upload failed: {e}")
    return render(request, "video_analysis.html")


@login_required
@ensure_gemini
@require_POST
def api_process_video(request, video_id):
    video_record = get_object_or_404(VideoAnalysis, id=video_id, user=request.user)
    if video_record.status != 'PENDING':
        return JsonResponse({"status": video_record.status}, status=200)

    try:
        video_record.status = 'ANALYZING'
        video_record.save()

        video_path = str(Path(settings.MEDIA_ROOT) / video_record.video_file.name)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception(f"Cannot open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames < 3:
            raise Exception("Video too short.")

        pil_images = []
        for pos in [int(total_frames * p) for p in (0.10, 0.50, 0.90)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue
            frame_rgb = cv2.cvtColor(cv2.resize(frame, (512, 512)), cv2.COLOR_BGR2RGB)
            pil_images.append(Image.fromarray(frame_rgb))
        cap.release()

        if not pil_images:
            raise Exception("Could not extract any frames.")

        prompt = """
You are 'Sakhi', an expert agronomist analysing a farmer's field video.
I provide 3 frames (10%, 50%, 90%).
Return ONLY JSON:
{"crop_health":<0-100>,"growth_percentage":<int>,"uniformity":"Excellent|Good|Fair|Poor",
"problem_zones":[...],"alerts":[{"type":"Weed|Disease|Dryness|Pest","summary":"...","severity":"High|Medium|Low"}],
"action_plan":["..."]}
"""
        vision   = genai.GenerativeModel(GEMINI_MODEL_VISION)
        gen_conf = GenerationConfig(response_mime_type="application/json")
        response = vision.generate_content([prompt] + pil_images, generation_config=gen_conf)
        details  = json.loads(clean_ai_json_string(extract_text_from_genai_response(response)))

        video_record.analysis_result = details
        video_record.status = 'COMPLETED'
        video_record.save()
        return JsonResponse({"status": "COMPLETED", "redirect": f"/video-result/{video_record.id}/"})

    except Exception as e:
        video_record.status = 'FAILED'
        video_record.analysis_result = {"error": str(e)}
        video_record.save()
        return JsonResponse({"status": "FAILED", "error": str(e)}, status=500)


@login_required
def video_result_detail_view(request, video_id):
    rec     = get_object_or_404(VideoAnalysis, id=video_id, user=request.user)
    details = rec.get_analysis_data() or {}
    if rec.status == 'FAILED' and 'error' in details:
        messages.error(request, f"Analysis Failed: {details.get('error')}")
        details = {}
    return render(request, "video_result_detail.html", {
        "video_record": rec, "details": details, "status": rec.status,
    })


@login_required
def demo_analysis_view(request):
    class MockFile:
        url = "#"
    class MockRecord:
        id = 999
        date = datetime.datetime.now()
        video_file = MockFile()
        status = 'COMPLETED'

    details = {
        "crop_health": 92, "growth_percentage": 11, "uniformity": "Excellent",
        "problem_zones": ["North-East Corner", "Center Patch"],
        "alerts": [
            {"type": "Weed",    "summary": "Low-level broadleaf weed infiltration.", "severity": "Medium"},
            {"type": "Dryness", "summary": "Soil moisture low in North-East.",        "severity": "Low"},
        ],
        "action_plan": [
            "Apply broadleaf selective herbicide to the North-East zone within 48 hours.",
            "Increase irrigation drip frequency to the North-East quadrant by 10%.",
            "Monitor Center Patch weekly for weed spread.",
        ],
    }
    return render(request, "video_result_detail.html", {
        "video_record": MockRecord(), "details": details, "status": "COMPLETED",
    })


# ─────────────────────────────────────────────────────────────
#  CHATBOT (voice-first, language-aware)
# ─────────────────────────────────────────────────────────────
@login_required
def chatbot_view(request):
    return redirect('index')


@require_POST
@login_required
@ensure_gemini
def chatbot_api(request):
    try:
        body         = json.loads(request.body.decode('utf-8'))
        message      = body.get('message', '').strip()
        full_lang    = body.get('lang') or get_user_lang(request, full=True)

        if not message:
            return JsonResponse({"error": "Empty message"}, status=400)

        ChatMessage.objects.create(user=request.user, role='user', message=message)

        lang_short  = full_lang.split('-')[0]
        lang_name   = {'hi': 'Hindi', 'en': 'English', 'ta': 'Tamil',
                       'te': 'Telugu', 'kn': 'Kannada', 'mr': 'Marathi'}.get(lang_short, 'Hindi')

        recent = list(reversed(
            ChatMessage.objects.filter(user=request.user).order_by('-timestamp')[:6]
        ))
        history = [{'role': m.role, 'parts': [m.message]} for m in recent[:-1]]
        chat_session = chat_model.start_chat(history=history)

        prompt = f"Please respond in {lang_name}. Be concise and actionable.\n\nUser: {message}"

        # Check if user is asking about market – if so, flag redirect
        market_redirect = any(kw in message.lower() for kw in
                               ['market', 'price', 'sell', 'bazar', 'bhav', 'mandi', 'बाजार', 'मंडी', 'ಮಾರುಕಟ್ಟೆ'])

        def stream_response():
            full_reply = ""
            try:
                response = chat_session.send_message(prompt, stream=True)
                for chunk in response:
                    try:
                        txt = chunk.text
                        full_reply += txt
                        yield txt
                    except Exception:
                        pass
                ChatMessage.objects.create(user=request.user, role='model', message=full_reply)
                if market_redirect:
                    yield "\n\n__REDIRECT__:/market-prices/"
            except Exception as e:
                print("Streaming error:", e)
                yield "⚠️ Network error while generating response."

        resp = StreamingHttpResponse(stream_response(), content_type='text/plain')
        resp['X-Voice-Lang'] = full_lang
        return resp

    except Exception as e:
        print("❌ Chatbot API:", e)
        return JsonResponse({"error": "AI error"}, status=500)


# ─────────────────────────────────────────────────────────────
#  LIVE VISION (camera)
# ─────────────────────────────────────────────────────────────
@login_required
@ensure_gemini
@require_POST
def api_live_vision(request):
    try:
        body           = json.loads(request.body.decode('utf-8'))
        user_question  = body.get('text', '').strip() or "What do you see?"
        image_data_url = body.get('image_data')
        lang           = body.get('lang') or get_user_lang(request, full=True)

        if not image_data_url:
            return JsonResponse({"error": "No image data."}, status=400)

        _, b64   = image_data_url.split(';base64,')
        img_bytes = base64.b64decode(b64)
        img       = Image.open(io.BytesIO(img_bytes))

        lang_short = lang.split('-')[0]
        lang_name  = {'hi': 'Hindi', 'en': 'English', 'ta': 'Tamil',
                      'te': 'Telugu', 'kn': 'Kannada', 'mr': 'Marathi'}.get(lang_short, 'English')

        prompt = f"""
You are 'Sakhi', an expert agronomist. Respond in {lang_name}.
Farmer asked: "{user_question}"
Analyze the image. Reply concisely with bullet points (each starting with '*').
If a disease is found: name, severity, 2 short steps.
"""
        vision  = genai.GenerativeModel(GEMINI_MODEL_VISION)
        response = vision.generate_content([prompt, img])
        reply    = extract_text_from_genai_response(response)

        return JsonResponse({"reply": reply, "voice_lang": lang})
    except Exception as e:
        print("❌ Live Vision:", e)
        return JsonResponse({"error": "AI error."}, status=500)


# ─────────────────────────────────────────────────────────────
#  WEATHER  (Precision Agri-Planner)
# ─────────────────────────────────────────────────────────────
def get_weather_data(city, soil_type='Alluvial', crop='Rice', lang='en'):
    if not chat_model:
        raise Exception("AI not configured. Check GOOGLE_API_KEY.")
    cache_key = f"weather_{city.lower()}_{soil_type.lower()}_{lang}_v8"
    cached = cache.get(cache_key)
    if cached:
        return cached

    today = datetime.date.today()
    days_list = [(today + datetime.timedelta(days=i)).strftime('%d %b') for i in range(15)]

    lang_name = {
        'hi': 'Hindi', 'kn': 'Kannada', 'ta': 'Tamil',
        'te': 'Telugu', 'mr': 'Marathi', 'en': 'English'
    }.get(lang, 'English')

    prompt = f"""
You are Sakhi, an expert Agrometeorologist and Farm Advisor for {city}, India.
Soil type: {soil_type}. Main crop: {crop}.
Today's date: {today.isoformat()}

IMPORTANT: Write ALL text values (task, ai_advice, soil_advice, ai_report, condition, reason, etc.) in {lang_name} ONLY. Do NOT mix languages.

Return ONLY a JSON object with EXACTLY these keys:
{{
  "city": "{city}",
  "temperature": "28°C",
  "condition": "Partly Cloudy",
  "humidity": "72%",
  "wind": "12 km/h",
  "spray_window": {{
    "safe": "6 AM – 9 AM",
    "unsafe": "11 AM – 5 PM",
    "reason": "High wind / low humidity in afternoon",
    "safe_today": true
  }},
  "irrigation_status": {{
    "water_today": true,
    "reason": "Soil moisture low, no rain expected today",
    "next_watering": "In 2 days"
  }},
  "irrigation_plan": ["Drip irrigate morning before 8 AM", "Check soil at 6 cm depth", "Skip if rain > 5mm"],
  "soil_advice": "Specific advice for {soil_type} soil this week.",
  "ai_advice": "One-line urgent farming tip for today.",
  "calendar": [
    {{"date": "{days_list[0]}", "day": "Today", "condition": "Sunny", "temp": "30°C", "task": "Irrigate early morning, apply nitrogen fertilizer", "spray_ok": true, "water": true, "emoji": "☀️"}},
    {{"date": "{days_list[1]}", "day": "Tomorrow", "condition": "Partly Cloudy", "temp": "28°C", "task": "Monitor for pests, no action needed", "spray_ok": true, "water": false, "emoji": "⛅"}},
    ... (generate all 30 days from {today.isoformat()} with realistic seasonal variations)
  ],
  "ai_report": "A detailed 3-4 paragraph farm advisory report covering: (1) overall weather pattern for the next 30 days, (2) key risks (drought/flood/pest outbreak), (3) best days to spray pesticide, (4) irrigation schedule recommendation, (5) what to plant or harvest this month. Write as if speaking to a farmer in simple language."
}}

RULES:
- calendar MUST have EXACTLY 15 entries, one per day starting {today.isoformat()}
- dates format: "DD Mon" e.g. "05 Mar"
- task: 5-10 word actionable farm task for that specific day
- spray_ok: boolean - true if wind < 15 km/h and no rain that day
- water: boolean - true if irrigation needed that day
- emoji: weather emoji for that day
- ai_report: 150-200 words, practical and farmer-friendly
- Respond with VALID JSON only. No markdown.
"""
    gen_conf = GenerationConfig(response_mime_type="application/json")
    response = chat_model.generate_content(prompt, generation_config=gen_conf)
    data     = json.loads(clean_ai_json_string(extract_text_from_genai_response(response)))

    # Ensure defaults
    data.setdefault('ai_advice', "Monitor weather closely.")
    data.setdefault('irrigation_plan', ["Check soil moisture before watering."])
    data.setdefault('spray_window', {"safe": "Early morning", "unsafe": "Afternoon", "reason": "Wind speed", "safe_today": True})
    data.setdefault('irrigation_status', {"water_today": True, "reason": "Standard watering schedule.", "next_watering": "In 2 days"})
    data.setdefault('soil_advice', "Maintain good drainage and balanced fertilisation.")
    data.setdefault('calendar', [])
    data.setdefault('ai_report', "No report available. Please try again.")

    cache.set(cache_key, data, 3600)  # 1 hour cache
    return data


@login_required
def weather_view(request):
    city = request.GET.get('city', None)
    soil_type = 'Alluvial'
    crop = 'Rice'
    user_lang = get_user_lang(request)  # e.g. 'kn', 'hi', 'en'
    try:
        profile = request.user.userprofile
        if profile.location and not city:
            city = profile.location
        if profile.soil_type:
            soil_type = profile.soil_type
        if profile.main_crops:
            crop = profile.main_crops.split(',')[0].strip()
    except Exception:
        pass
    city = city or "Bengaluru"

    try:
        data = get_weather_data(city, soil_type, crop, lang=user_lang)
        return render(request, "weather.html", {"data": data, "error": None,
                                                "voice_lang": get_user_lang(request, full=True)})
    except Exception as e:
        print("❌ Weather:", e)
        fallback = {
            "city": city, "temperature": "—", "condition": "Unavailable",
            "humidity": "—", "wind": "—",
            "ai_advice": "Weather service unavailable. Check local forecast.",
            "irrigation_plan": ["Check local forecast manually."],
            "spray_window": {"safe": "Early morning", "unsafe": "Afternoon", "reason": "N/A", "safe_today": True},
            "irrigation_status": {"water_today": True, "reason": "Data unavailable.", "next_watering": "Unknown"},
            "soil_advice": "No data available.", "calendar": [], "ai_report": "AI report unavailable. Please refresh.",
        }
        return render(request, "weather.html", {"data": fallback, "error": str(e),
                                                "voice_lang": get_user_lang(request, full=True)})


# ─────────────────────────────────────────────────────────────
#  MARKET PRICES  (Strategic Sales Hub)
# ─────────────────────────────────────────────────────────────
def fetch_agmarknet_price(crop_name):
    try:
        search_url = "https://agmarknet.gov.in/SearchCmmMkt.aspx"
        params = {"Tx_Commodity": crop_name, "Tx_State": "", "Tx_District": "", "Tx_Market": ""}
        try:
            r = requests.get(search_url, params=params, timeout=10)
        except requests.exceptions.Timeout:
            return None
        if not r.ok:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n")
        import re
        for ln in text.splitlines():
            if "Quintal" in ln or "qtl" in ln.lower():
                nums = re.findall(r"[\d,]+(?:\.\d+)?", ln)
                if nums:
                    price_val = float(nums[0].replace(",", ""))
                    return {"current_price": price_val, "unit": "Quintal",
                            "source": "Agmarknet", "date": datetime.date.today().isoformat()}
        return None
    except Exception as e:
        print("❌ Agmarknet:", e)
        return None


@ensure_gemini
def crop_prices_view(request):
    # Get primary crop from profile or query
    primary_crop = request.GET.get("crop")
    area_ha      = float(request.GET.get("area", 1.0))
    state        = "Karnataka"
    user_lang    = get_user_lang(request)  # 'kn', 'hi', 'en', etc.
    lang_name    = {
        'hi': 'Hindi', 'kn': 'Kannada', 'ta': 'Tamil',
        'te': 'Telugu', 'mr': 'Marathi', 'en': 'English'
    }.get(user_lang, 'English')

    try:
        profile = request.user.userprofile
        if not primary_crop and profile.main_crops:
            primary_crop = profile.main_crops.split(',')[0].strip()
        if profile.location:
            state = profile.location
    except Exception:
        pass

    primary_crop = primary_crop or "Wheat"

    # Yield estimate using the ML model
    yield_estimate = None
    try:
        yield_estimate = predict_yield(primary_crop, state, area_ha)
    except Exception as ye:
        print("⚠️ yield estimate:", ye)

    cache_key = f"market_hub_v4_{primary_crop}_{user_lang}"
    cached    = cache.get(cache_key)
    if cached:
        cached['yield_estimate_quintals'] = yield_estimate
        return render(request, "crop_prices.html", {"data": cached, "error": None,
                                                     "voice_lang": get_user_lang(request, full=True)})

    today_str = datetime.date.today().isoformat()

    prompt = f"""
You are an Indian agricultural market analyst. Use Google Search for real data.
Crop: "{primary_crop}", Today: {today_str}

IMPORTANT: Write ALL text values (best_week_to_sell, advice, highlight, buyer notes, news titles) in {lang_name} ONLY.

Return ONLY JSON:
{{
  "current_price": <number>,
  "unit": "Quintal",
  "source": "Google Search",
  "date": "{today_str}",
  "history": [{{"date":"YYYY-MM-DD","price":<number>}}],
  "forecast": [{{"date":"YYYY-MM-DD","predicted_price":<number>}}],
  "best_day": {{"date":"YYYY-MM-DD","predicted_price":<number>}},
  "best_week_to_sell": "One sentence describing the best week to sell and why (price trend reason).",
  "expected_increase_percent": <number>,
  "advice": "One sentence selling advice.",
  "highlight": "One sentence market trend summary.",
  "news": [{{"title":"...","source":"...","url":"..."}}],
  "buyer_leads": [
    {{"name":"Ram Agro Traders","phone":"9876543210","contact":"Call for direct purchase","interest":"{primary_crop}","notes":"Large wholesale buyer, {state}"}},
    {{"name":"FarmerConnect Co-op","phone":"8765432109","contact":"Local APMC Market","interest":"{primary_crop}","notes":"Fair trade co-operative, prompt payment"}},
    {{"name":"Namma Upajna Bazar","phone":"9988776655","contact":"Call or visit","interest":"{primary_crop}","notes":"Digital farmer-buyer platform, better prices"}}
  ],
  "mandis": ["Bengaluru APMC", "Hubballi Mandi", "Mysuru Mandi", "Tumkur Mandi", "Davangere Mandi"]
}}

Rules:
- history: 30 days ending {today_str}
- forecast: 14 days starting tomorrow
- best_day = highest forecast price day
- Use real current mandi prices from Google Search
- Respond with STRICT JSON only
"""
    try:
        gen_conf = GenerationConfig(response_mime_type="application/json")
        response = chat_model.generate_content(prompt, generation_config=gen_conf)
        obj      = json.loads(clean_ai_json_string(extract_text_from_genai_response(response)))

        final = {
            "source":                   obj.get("source", "AI Market Data"),
            "date":                     obj.get("date", today_str),
            "current_price":            obj.get("current_price"),
            "unit":                     obj.get("unit", "Quintal"),
            "history":                  obj.get("history", []),
            "forecast":                 obj.get("forecast", []),
            "best_day":                 obj.get("best_day", {}),
            "best_week_to_sell":        obj.get("best_week_to_sell", ""),
            "expected_increase_percent": obj.get("expected_increase_percent", 0.0),
            "advice":                   obj.get("advice", ""),
            "highlight":                obj.get("highlight", ""),
            "news":                     obj.get("news", []),
            "buyer_leads":              obj.get("buyer_leads", []),
            "mandis":                   obj.get("mandis", []),
            "primary_crop":             primary_crop,
            "yield_estimate_quintals":  yield_estimate,
            "area_ha":                  area_ha,
        }
        cache.set(cache_key, final, 3600)
        final['voice_lang'] = get_user_lang(request, full=True)
        return render(request, "crop_prices.html", {"data": final, "error": None,
                                                     "voice_lang": get_user_lang(request, full=True)})
    except Exception as e:
        print("❌ Market:", e)
        fallback = {
            "source": "N/A", "date": today_str, "current_price": None,
            "unit": "Quintal", "history": [], "forecast": [],
            "best_day": {}, "best_week_to_sell": "", "expected_increase_percent": 0,
            "advice": "Service unavailable.", "highlight": "", "news": [],
            "buyer_leads": [], "mandis": [], "primary_crop": primary_crop,
            "yield_estimate_quintals": yield_estimate, "area_ha": area_ha,
        }
        return render(request, "crop_prices.html", {"data": fallback, "error": str(e),
                                                     "voice_lang": get_user_lang(request, full=True)})


@login_required
@ensure_gemini
def api_call_logistics(request):
    """
    Returns nearby transporter/logistics leads for the farmer based on profile location.
    """
    location = "Karnataka"
    crop     = "your produce"
    try:
        profile  = request.user.userprofile
        location = profile.location or location
        crop     = (profile.main_crops or "").split(',')[0].strip() or crop
    except Exception:
        pass

    prompt = f"""
You are a logistics assistant for Indian farmers in {location}.
List 3 realistic logistics / transport providers for agricultural produce ({crop}).
Return ONLY JSON array:
[{{"name":"...","contact":"...","type":"Truck|Tempo|Tractor","notes":"...","rating":"4.2/5"}}]
"""
    try:
        gen_conf = GenerationConfig(response_mime_type="application/json")
        resp     = chat_model.generate_content(prompt, generation_config=gen_conf)
        leads    = json.loads(clean_ai_json_string(extract_text_from_genai_response(resp)))
        return JsonResponse({"providers": leads, "location": location})
    except Exception as e:
        print("❌ Logistics:", e)
        # Static fallback
        return JsonResponse({"providers": [
            {"name": "APMC Transport", "contact": "Visit local APMC mandi", "type": "Truck", "notes": "Government facilitated", "rating": "4.0/5"},
            {"name": "Kisan Vehicle", "contact": "Call local KVK", "type": "Tempo", "notes": "Affordable, local service", "rating": "4.3/5"},
            {"name": "eNAM Logistics", "contact": "enam.gov.in", "type": "Truck", "notes": "Pan-India network", "rating": "4.5/5"},
        ], "location": location})


# ─────────────────────────────────────────────────────────────
#  DIRECT SELL (legacy – kept for backward compat)
# ─────────────────────────────────────────────────────────────
@ensure_gemini
@login_required
def direct_sell_view(request):
    prompt_buyers = f"""
Find 3 potential buyers for farm produce in {getattr(request.user.userprofile, 'location', 'India')}.
Return JSON array: [{{"name":"...","contact":"...","interest":"...","notes":"..."}}]
"""
    gen_conf = GenerationConfig(response_mime_type="application/json")
    try:
        resp   = chat_model.generate_content(prompt_buyers, generation_config=gen_conf)
        buyers = json.loads(clean_ai_json_string(extract_text_from_genai_response(resp)))
    except Exception:
        buyers = []

    prompt_wa = f"Compose a short WhatsApp message for a farmer to sell {getattr(request.user.userprofile,'main_crops','produce')}. Include price placeholder."
    try:
        resp_msg    = chat_model.generate_content(prompt_wa)
        message_txt = extract_text_from_genai_response(resp_msg)
    except Exception:
        message_txt = f"Hi, I have fresh produce for sale. Contact: [phone]"

    if request.GET.get('format') == 'json':
        return JsonResponse({"buyers": buyers, "whatsapp_message": message_txt})
    return render(request, "direct_sell.html", {"buyers": buyers, "whatsapp_message": message_txt})


# ─────────────────────────────────────────────────────────────
#  PERSONALIZED REPORT
# ─────────────────────────────────────────────────────────────
@ensure_gemini
@login_required
@require_POST
def api_generate_report(request):
    try:
        profile = request.user.userprofile
    except Exception:
        return JsonResponse({"error": "Profile not found."}, status=400)

    crop_ctx     = profile.main_crops or "Not specified"
    soil_ctx     = profile.soil_type  or "Not specified"
    location_ctx = profile.location   or "Bengaluru"

    try:
        weather      = get_weather_data(location_ctx)
        weather_ctx  = f"{weather.get('condition','N/A')}, {weather.get('temperature','N/A')}°C"
    except Exception:
        weather_ctx  = "Weather unavailable"

    prompt = f"""
Produce a 3-key JSON report for a farmer:
- crops: {crop_ctx}, soil: {soil_ctx}, location: {location_ctx}, weather: {weather_ctx}
Return ONLY JSON: {{"market_opportunity":"...","pest_alert":"...","soil_health":"..."}}
Each value: 1-2 sentences, actionable.
"""
    try:
        gen_conf = GenerationConfig(response_mime_type="application/json")
        resp     = chat_model.generate_content(prompt, generation_config=gen_conf)
        report   = json.loads(clean_ai_json_string(extract_text_from_genai_response(resp)))
        return JsonResponse(report)
    except Exception as e:
        print("❌ generate_report:", e)
        return JsonResponse({"error": "AI failed."}, status=500)


# ─────────────────────────────────────────────────────────────
#  PROFILE & PERSONALIZE
# ─────────────────────────────────────────────────────────────
@login_required
def profile_view(request):
    try:
        profile = request.user.userprofile
    except Exception:
        profile = None

    predictions_count = Prediction.objects.filter(user=request.user).count()
    video_count = VideoAnalysis.objects.filter(user=request.user).count()
    recent_predictions = Prediction.objects.filter(user=request.user).order_by('-date')[:5]
    join_date = request.user.date_joined
    days_active = (datetime.datetime.now(datetime.timezone.utc) - join_date).days

    # Crops list from profile
    crops_list = []
    if profile and profile.main_crops:
        crops_list = [c.strip() for c in profile.main_crops.split(',') if c.strip()]

    return render(request, "profile.html", {
        "profile": profile,
        "predictions_count": predictions_count,
        "video_count": video_count,
        "recent_predictions": recent_predictions,
        "join_date": join_date,
        "days_active": days_active,
        "crops_list": crops_list,
    })


@login_required
def personalize_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.language   = request.POST.get('language', profile.language)
        profile.soil_type  = request.POST.get('soil-type', profile.soil_type)
        profile.main_crops = request.POST.get('main-crops', profile.main_crops)
        if hasattr(profile, 'location'):
            profile.location = request.POST.get('location', profile.location)
        profile.save()
        messages.success(request, "Preferences saved.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'language' in request.POST:
            return JsonResponse({"status": "ok"})
        return redirect('profile')
    return render(request, "personalize.html", {"profile": profile})


# ─────────────────────────────────────────────────────────────
#  GOVERNMENT SCHEMES
# ─────────────────────────────────────────────────────────────
def schemes_view(request):
    cached = cache.get("govt_schemes_v2")
    if cached:
        return render(request, "schemes.html", {"schemes": cached, "error": None})

    prompt = """
List the most recent active government schemes for farmers in India.
Return ONLY JSON array: [{"name":"...","description":"...","url":"..."}]
Include: PM Kisan, PMFBY, KCC, Soil Health Card, eNAM, and recent state schemes.
"""
    try:
        gen_conf = GenerationConfig(response_mime_type="application/json")
        resp     = chat_model.generate_content(prompt, generation_config=gen_conf)
        schemes  = json.loads(clean_ai_json_string(extract_text_from_genai_response(resp)))
        cache.set("govt_schemes_v2", schemes, 1800)
        return render(request, "schemes.html", {"schemes": schemes, "error": None})
    except Exception as e:
        print("❌ Schemes:", e)
        fallback = [
            {"name": "PM-KISAN", "description": "₹6,000/year in 3 installments.", "url": "https://pmkisan.gov.in/"},
            {"name": "PMFBY",    "description": "Crop insurance against yield losses.", "url": "https://pmfby.gov.in/"},
            {"name": "KCC",      "description": "Kisan Credit Card for timely credit.", "url": "https://sbi.co.in/web/agri-rural/agriculture-banking/crop-loan/kisan-credit-card"},
            {"name": "Soil Health Card", "description": "Soil nutrient status & fertiliser advice.", "url": "https://soilhealth.dac.gov.in/"},
            {"name": "e-NAM",    "description": "Pan-India electronic trading portal.",  "url": "https://enam.gov.in/"},
        ]
        return render(request, "schemes.html", {"schemes": fallback, "error": str(e)})


# ─────────────────────────────────────────────────────────────
#  LIVE VISION PAGE
# ─────────────────────────────────────────────────────────────
@login_required
def live_vision_view(request):
    return render(request, "live_vision.html",
                  {"voice_lang": get_user_lang(request, full=True)})


# ─────────────────────────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────────────────────────
def health_check(request):
    return JsonResponse({"status": "ok", "time": datetime.datetime.now().isoformat()})


# ─────────────────────────────────────────────────────────────
#  CIRCLE-OF-TRUST MARKETPLACE
# ─────────────────────────────────────────────────────────────
@login_required
def marketplace_view(request):
    """Show hyper-local listings filtered by the user's location."""
    profile = getattr(request.user, 'userprofile', None)
    user_location = (profile.location or '').strip() if profile else ''

    # Normal listings (not seed swaps)
    listings = MarketplaceListing.objects.filter(
        is_available=True,
        is_exchange=False,
    ).select_related('seller', 'seller__userprofile')

    # Heritage / seed-swap listings
    seed_swaps = MarketplaceListing.objects.filter(
        is_available=True,
        is_exchange=True,
    ).select_related('seller', 'seller__userprofile')

    # Filter by location if user has one set
    if user_location:
        listings   = listings.filter(location_tag__iexact=user_location)
        seed_swaps = seed_swaps.filter(location_tag__iexact=user_location)

    return render(request, 'marketplace.html', {
        'listings':      listings[:40],
        'seed_swaps':    seed_swaps[:20],
        'user_location': user_location,
        'has_location':  bool(user_location),
    })


@login_required
@require_POST
def api_voice_list_item(request):
    """Receive a voice transcript, extract listing details with Gemini, return for confirmation."""
    try:
        data = json.loads(request.body)
        transcript = data.get('transcript', '').strip()
        if not transcript:
            return JsonResponse({'error': 'Empty transcript'}, status=400)

        if not chat_model:
            return JsonResponse({'error': 'AI not available'}, status=503)

        prompt = f"""Extract item details from this Indian farmer voice note for a village marketplace listing.
Voice note: "{transcript}"

Return ONLY a JSON object with these exact keys:
{{"item_name": "string", "quantity": "string like 3 kg", "price": number_in_rupees_or_0, "is_exchange": true_or_false, "category": "SEEDS or FERT or CROP or OTHER", "description": "one short sentence"}}

Set is_exchange=true and price=0 if they say swap, exchange, free, or similar.
Return ONLY the JSON, no other text."""

        # Reuse the app-wide model instance (uses GEMINI_MODEL_CHAT env var)
        extraction_model = genai.GenerativeModel(GEMINI_MODEL_CHAT)
        resp = extraction_model.generate_content(prompt)

        # Parse JSON from the response text — strip code fences if present
        raw = resp.text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
        raw = raw.strip()

        extracted = json.loads(raw)
        return JsonResponse({'ok': True, 'data': extracted, 'transcript': transcript})

    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Could not parse AI response: {e}'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_confirm_listing(request):
    """Save the confirmed listing to the database."""
    try:
        data = json.loads(request.body)
        profile     = getattr(request.user, 'userprofile', None)
        loc         = (profile.location or 'Unknown').strip() if profile else 'Unknown'
        is_exchange = bool(data.get('is_exchange', False))
        price       = 0.00 if is_exchange else float(data.get('price', 0))

        listing = MarketplaceListing.objects.create(
            seller       = request.user,
            item_name    = data.get('item_name', 'Item')[:200],
            description  = data.get('description', ''),
            quantity_str = data.get('quantity', ''),
            price        = price,
            is_exchange  = is_exchange,
            category     = data.get('category', 'OTHER'),
            location_tag = loc,
            is_available = True,
            seed_guardian = is_exchange and data.get('category') == 'SEEDS',
        )
        return JsonResponse({'ok': True, 'id': listing.id, 'location': loc})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
