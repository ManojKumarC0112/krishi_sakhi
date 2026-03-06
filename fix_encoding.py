"""Comprehensive fix for crop_prices.html - fixes line endings and remaining garbled chars."""

with open(r'templates\crop_prices.html', 'rb') as f:
    raw = f.read()

# Strip BOM
if raw.startswith(b'\xef\xbb\xbf'):
    raw = raw[3:]

# First fix double CRLF -> LF
text = raw.replace(b'\r\r\n', b'\n').replace(b'\r\n', b'\n').replace(b'\r', b'\n')
text = text.decode('utf-8', errors='replace')

# Replace remaining replacement chars that came from failed decode
# The tour step emojis: the original file likely had these emoji in garbled form
# We need to manually fix the broken tour step strings
replacements = [
    # Page Tour steps with garbled emojis
    ("'🌾 Sales Hub'", "'🌾 Sales Hub'"),
    ("title: '🌾 Sales Hub'", "title: '🌾 Sales Hub'"),
    ("'🌾 बिक्री हब'", "'🌾 बिक्री हब'"),
    ("'🌾 ಮಾರಾಟ ಹಬ್'", "'🌾 ಮಾರಾಟ ಹಬ್'"),
    ("'📅 Best Week to Sell'", "'📅 Best Week to Sell'"),
    ("'📅 बेचने का सही समय'", "'📅 बेचने का सही समय'"),
    ("'📅 ಮಾರಾಟಕ್ಕೆ ಉತ್ತಮ ಸಮಯ'", "'📅 ಮಾರಾಟಕ್ಕೆ ಉತ್ತಮ ಸಮಯ'"),
    ("'🤝 Buyer Leads'", "'🤝 Buyer Leads'"),
    ("'🤝 खरीदार'", "'🤝 खरीदार'"),
    ("'🤝 ಖರೀದಿದಾರರು'", "'🤝 ಖರೀದಿದಾರರು'"),
    ("'🚛 Call Transporter'", "'🚛 Call Transporter'"),
    ("'🚛 ट्रान्सपोर्टर'", "'🚛 ट्रान्सपोर्टर'"),
    ("'🚛 ಸಾರಿಗೆ'", "'🚛 ಸಾರಿಗೆ'"),
    ("'🧪 Buy Pesticides'", "'🧪 Buy Pesticides'"),
    ("'🧪 कीटनाशक खरीदें'", "'🧪 कीटनाशक खरीदें'"),
    ("'🧪 ಕೀಟನಾಶಕ ಖರೀದಿ'", "'🧪 ಕೀಟನಾಶಕ ಖರೀದಿ'"),
]

# Fix replacement character sequences in tour steps
import re

# Fix tour title_hi descriptions - replace all replacement chars sequences
def fix_tour_steps(text):
    # Replace entire pageTourSteps block with clean version
    new_steps = """  window.pageTourSteps = [
    {
      target: 'hero-sales-hub', title: '🌾 Sales Hub', desc: 'See today\\'s mandi price and AI predicted yield for your land.',
      title_hi: '🌾 बिक्री हब', desc_hi: 'आज का मंडी भाव और अपनी जमीन की AI पैदावार यहाँ देखें।',
      title_kn: '🌾 ಮಾರಾಟ ಹಬ್', desc_kn: 'ಇಂದಿನ ಮಂಡಿ ಬೆಲೆ ಮತ್ತು AI ಇಳುವರಿ ಇಲ್ಲಿ ನೋಡಿ.'
    },
    {
      target: 'best-week-banner', title: '📅 Best Week to Sell', desc: 'AI recommends the best week based on market trends.',
      title_hi: '📅 बेचने का सही समय', desc_hi: 'AI बाज़ार के रुझान से सही समय बताता है।',
      title_kn: '📅 ಮಾರಾಟಕ್ಕೆ ಉತ್ತಮ ಸಮಯ', desc_kn: 'AI ಮಾರುಕಟ್ಟೆ ಪ್ರವೃತ್ತಿ ಆಧಾರದಲ್ಲಿ ಸರಿಯಾದ ಸಮಯ ತಿಳಿಸುತ್ತದೆ.'
    },
    {
      target: 'buyer-leads', title: '🤝 Buyer Leads', desc: 'Click Call or WhatsApp to contact buyers directly.',
      title_hi: '🤝 खरीदार', desc_hi: 'सीधे कॉल या व्हाट्सएप से खरीदारों से जुड़ें।',
      title_kn: '🤝 ಖರೀದಿದಾರರು', desc_kn: 'ನೇರ ಕಾಲ್ ಅಥವಾ ವಾಟ್ಸಾಪ್ ಮೂಲಕ ಖರೀದಿದಾರರನ್ನು ಸಂಪರ್ಕಿಸಿ.'
    },
    {
      target: 'transporter-btn', title: '🚛 Call Transporter', desc: 'Tap to find local logistics to take your harvest to the mandi.',
      title_hi: '🚛 ट्रान्सपोर्टर', desc_hi: 'मंडी तक फसल भेजने के लिए नजदीकी ट्रान्सपोर्टर खोजें।',
      title_kn: '🚛 ಸಾರಿಗೆ', desc_kn: 'ಮಂಡಿಗೆ ಕೊಯ್ಲು ತಲುಪಿಸಲು ಸ್ಥಳೀಯ ಸಾರಿಗೆ ಹುಡುಕಿ.'
    },
    {
      target: 'pesticide-section', title: '🧪 Buy Pesticides', desc: 'Tap Shop to buy pesticides, seeds and fertilisers online.',
      title_hi: '🧪 कीटनाशक खरीदें', desc_hi: 'कीटनाशक, बीज और खाद ऑनलाइन खरीदें।',
      title_kn: '🧪 ಕೀಟನಾಶಕ ಖರೀದಿ', desc_kn: 'ಕೀಟನಾಶಕ, ಬೀಜ ಮತ್ತು ಗೊಬ್ಬರ ಆನ್‌ಲೈನ್‌ನಲ್ಲಿ ಖರೀದಿಸಿ.'
    },
  ];"""
    # Replace the pageTourSteps block
    pattern = r'window\.pageTourSteps\s*=\s*\[.*?\];'
    result = re.sub(pattern, new_steps.strip(), text, flags=re.DOTALL)
    return result

# Fix welcome messages
def fix_welcome_msgs(text):
    new_msgs = """    const msgs = {
        'hi-IN': "बाज़ार हब में आपका स्वागत है।",
        'kn-IN': "ಮಾರುಕಟ್ಟೆ ಹಬ್‌ಗೆ ಸ್ವಾಗತ.",
        'ta-IN': "சந்தை மையத்திற்கு வரவேற்கிறோம்.",
        'te-IN': "మార్కెట్ హబ్‌కు స్వాగతం.",
        'en-US': "Welcome to the Sales Hub.",
      };"""
    pattern = r"const msgs\s*=\s*\{[^}]+\};"
    result = re.sub(pattern, new_msgs.strip(), text, flags=re.DOTALL)
    return result

text = fix_tour_steps(text)
text = fix_welcome_msgs(text)

with open(r'templates\crop_prices.html', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('DONE: Full fix applied to crop_prices.html')
# Verify
with open(r'templates\crop_prices.html', 'r', encoding='utf-8') as f:
    sample = f.read()[200:500]
print('SAMPLE:', sample[:300])
