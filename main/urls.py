# main/urls.py
from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # --- Auth ---
    path("signup/",  views.signup_view,  name="signup"),
    path("login/",   views.login_view,   name="login"),
    path("logout/",  views.logout_view,  name="logout"),

    # --- Main Pages ---
    path("",                              views.index_view,                  name="index"),
    path("predict/",                      views.predict_view,                name="predict"),
    path("live-vision/",                  views.live_vision_view,            name="live_vision"),
    path("history/",                      views.history_view,                name="history"),
    path("result/<int:prediction_id>/",   views.result_detail_view,          name="result_detail"),

    # --- Field Analysis ---
    path("analyze-field/",                views.analyze_field_dashboard_view, name="analyze_field_dashboard"),
    path("video-analysis/",               views.video_analysis_upload_view,  name="video_analysis_upload"),
    path("demo-analysis/",                views.demo_analysis_view,          name="demo_analysis"),
    path("video-result/<int:video_id>/",  views.video_result_detail_view,    name="video_result_detail"),

    # --- Utility Pages ---
    path("schemes/",      views.schemes_view,      name="schemes"),
    path("weather/",      views.weather_view,       name="weather"),
    path("chatbot/",      views.chatbot_view,       name="chatbot"),
    path("profile/",      views.profile_view,       name="profile"),
    path("personalize/",  views.personalize_view,   name="personalize"),
    path("market-prices/",views.crop_prices_view,   name="crop_prices"),
    path("direct-sell/",  views.direct_sell_view,   name="direct_sell"),

    # --- API Endpoints ---
    path("api/chatbot/",                         views.chatbot_api,          name="chatbot_api"),
    path("api/live-vision/",                     views.api_live_vision,      name="api_live_vision"),
    path("api/generate-report/",                 views.api_generate_report,  name="api_generate_report"),
    path("api/process-video/<int:video_id>/",    views.api_process_video,    name="api_process_video"),
    path("api/scan-crop/",                       views.api_scan_crop,        name="api_scan_crop"),
    path("api/detect-language/",                 views.api_detect_language,  name="api_detect_language"),
    path("api/demo-login/",                      views.api_demo_login,       name="api_demo_login"),
    path("api/call-logistics/",                  views.api_call_logistics,   name="api_call_logistics"),
    path("set-language/",                        views.set_language,         name="set_language"),

    # --- Marketplace ---
    path("marketplace/",              views.marketplace_view,       name="marketplace"),
    path("api/voice-list/",           views.api_voice_list_item,    name="api_voice_list_item"),
    path("api/confirm-listing/",      views.api_confirm_listing,    name="api_confirm_listing"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)