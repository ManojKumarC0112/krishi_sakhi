"""
Build a completely clean crop_prices.html from scratch using HTML entities for all emoji.
This is immune to any encoding issues.
"""

# Map of placeholder -> HTML entity for every emoji used in the template
# We'll read the current file, strip all multi-byte sequences, and replace
# emoji text labels using a direct substitution approach.

import re

with open(r'templates\crop_prices.html', 'rb') as f:
    raw = f.read()

# Decode tolerantly
text = raw.decode('utf-8', errors='replace')

# Now do targeted string replacements of text labels that we KNOW appear
# near broken emoji, replacing both the broken char + the label with entity + label

# Helper: all emoji we want to use as decimal HTML entities
# &#128200; = 📈  &#127991; = 🏷️  &#128302; = 🔮  &#128197; = 📅  &#127758; = 🌐
# &#128205; = 📍  &#127807; = 🌱  &#128260; = 🔄  &#128161; = 💡  &#129336; = 🤝
# &#128663; = 🚛  &#128299; = 🧪  &#128722; = 🛒  &#128240; = 📞  &#128172; = 💬
# &#128266; = 🔊  &#128176; = 💰  &#128227; = 📣  &#10005; = ✕  &#11088; = ⭐
# &#128184; = 💸  &#128270; = 🔎  &#128273; = 🔑  &#128736; = 🛠️
# &#128080; = 👐  &#129332; = 🪙  (no—use &#127981;=🏪)

# Strategy: replace each broken occurrence by finding the text that follows 
# the replacement character(s) and inserting the right entity

replacements = [
    # Title block
    ('Sales Hub \ufffd??', '&#128200; Sales Hub'),  # 📈
    ('Sales Hub \ufffd\ufffd', '&#128200; Sales Hub'),
    
    # Hero heading
    ('Strategic Sales Hub', '&#128200; Strategic Sales Hub'),
    
    # Crop tag (🏷️)
    ('>\ufffd\ufffd:\ufffd\ufffd ', '>&#127991;&#xFE0F; '),
    ('\ufffd\ufffd:\ufffd\ufffd {{ data.primary_crop', '&#127991;&#xFE0F; {{ data.primary_crop'),
    
    # Predicted Yield (🔮)
    ('\ufffd??\ufffd Predicted Yield', '&#128302; Predicted Yield'),
    ('\ufffd\ufffd\ufffd Predicted Yield', '&#128302; Predicted Yield'),
    
    # Calendar (📅)
    ('\ufffd\ufffd\ufffd Best Week to Sell', '&#128197; Best Week to Sell'),
    ('\ufffd\ufffd\ufffd</div>', '&#128197;</div>'),
    
    # Nearest Mandis - coin (🪙)
    ('\ufffd\ufffd\ufffd Nearest Mandis', '&#127963; Nearest Mandis'),
    
    # Location pin (📍)
    ('\ufffd\ufffd\ufffd {{ m }', '&#128205; {{ m }'),
    
    # Update Farm (🌱)
    ('\ufffd\ufffd\ufffd Update Your Farm', '&#127807; Update Your Farm'),
    
    # Recalculate (🔄)
    ('Recalculate \ufffd\ufffd\ufffd', 'Recalculate &#128260;'),
    
    # AI Market Insight (💡)
    ('\ufffd\ufffd\ufffd AI Market Insight', '&#128161; AI Market Insight'),
    
    # Best Day dash
    ('{{ data.best_day.date }} \ufffd\ufffd {{ data.best_day', '{{ data.best_day.date }} &ndash; {{ data.best_day'),
    
    # Buyer Leads (🤝)
    ('\ufffd\ufffd\ufffd Verified Buyer Leads', '&#129336; Verified Buyer Leads'),
    
    # Call button (📞)
    ('\ufffd\ufffd\ufffd Call</a>', '&#128222; Call</a>'),
    
    # WhatsApp (💬)
    ('\ufffd\ufffd\ufffd WhatsApp</a>', '&#128172; WhatsApp</a>'),
    
    # Info button (🔊)
    ('\ufffd\ufffd\ufffd\n              Info</button>', '&#128266;\n              Info</button>'),
    
    # Buyer leads fetching ellipsis
    ('being fetched\ufffd\ufffd\ufffd', 'being fetched&hellip;'),
    
    # APMC tip (💡)
    ('\ufffd\ufffd\ufffd Get buyer details', '&#128161; Get buyer details'),
    
    # Logistics (🚛)
    ('\ufffd\ufffd\ufffd Logistics', '&#128667; Logistics'),
    ('\ufffd\ufffd\ufffd Find Nearby\n          Transporters', '&#128222; Find Nearby Transporters'),
    
    # Pesticides (🧪)
    ('\ufffd\ufffd\ufffd Buy Pesticides', '&#129514; Buy Pesticides'),
    
    # Shop buttons (🛒)
    ('\ufffd\ufffd\ufffd Shop</a>', '&#128722; Shop</a>'),
    
    # Em dashes
    ('AgroStar \ufffd\ufffd Smart Farming', 'AgroStar &ndash; Smart Farming'),
    ('BigHaat \ufffd\ufffd Seeds', 'BigHaat &ndash; Seeds'),
    ('Kissan Kendra \ufffd\ufffd', 'Kissan Kendra &ndash;'),
    ('DeHaat \ufffd\ufffd', 'DeHaat &ndash;'),
    
    # 14-Day forecast (🔮)
    ('\ufffd\ufffd\ufffd 14-Day Price Forecast', '&#128302; 14-Day Price Forecast'),
    
    # Rupee symbols
    ('\ufffd\ufffd{{ f.predicted_price }}', '&#8377;{{ f.predicted_price }}'),
    ('\ufffd{{ data.current_price }}', '&#8377;{{ data.current_price }}'),
    
    # 30-Day Price Trend (📈)
    ('\ufffd\ufffd\ufffd 30-Day Price Trend', '&#128200; 30-Day Price Trend'),
    
    # Market News (📰)
    ('\ufffd\ufffd\ufffd Market News', '&#128240; Market News'),
    
    # Data Source (ℹ️)
    ('\ufffd\ufffd\ufffd Data Source', '&#8505;&#xFE0F; Data Source'),
    
    # Loading ellipsis
    ('Loading\ufffd\ufffd\ufffd', 'Loading&hellip;'),
    
    # Close modal
    ('Close \ufffd\ufffd\ufffd', 'Close &times;'),
    
    # Nearby Logistics
    ('\ufffd\ufffd\ufffd Nearby Logistics', '&#128667; Nearby Logistics'),
    
    # JS: rupee in chart
    ("label: 'Price \ufffd\ufffd\ufffd/Quintal'", "label: 'Price \\u20b9/Quintal'"),
    ("label: ctx => '\ufffd\ufffd\ufffd'", "label: ctx => '\\u20b9'"),
    ("callback: v => '\ufffd\ufffd\ufffd'", "callback: v => '\\u20b9'"),
    
    # JS alert emojis (🤝📞💡)
    ("'\ufffd\ufffd\ufffd ${name}", "'\\u{1F91D} ${name"),  # not right, use literal
]

for old, new in replacements:
    if old in text:
        text = text.replace(old, new)
        print(f'Replaced: {repr(old[:30])} -> {repr(new[:30])}')

# Fix remaining rupee signs after JS replacement
text = text.replace("'\ufffd' + ctx.parsed.y", "'\\u20b9' + ctx.parsed.y")
text = text.replace("'\ufffd' + v", "'\\u20b9' + v")

# Fix JS alert with buyer lead emojis
old_alert = "alert(`\ufffd\ufffd\ufffd ${name}\\n\ufffd\ufffd\ufffd Contact: ${contact}\\n\\n\ufffd\ufffd\ufffd Visit your local"
new_alert = "alert(`\u1F91D ${name}\\n\u1F4DE Contact: ${contact}\\n\\n\u1F4A1 Visit your local"
if old_alert in text:
    text = text.replace(old_alert, new_alert)

# Fix JS provider card trucks and stars
text = text.replace('`\ufffd\ufffd\ufffd ${p.name}', '`&#128667; ${p.name}')
text = text.replace('\u0026nbsp;|\u0026nbsp; \ufffd\ufffd\ufffd ${p.rating}', '&nbsp;|&nbsp; &#11088; ${p.rating}')
text = text.replace("'\ufffd\ufffd\ufffd ${p.phone}", "'&#128222; ${p.phone}")
text = text.replace("'\ufffd\ufffd\ufffd ${p.contact}", "'&#128222; ${p.contact}")

# Fix speakBuyerLead messages with replacement chars for Hindi/Kannada locale text
# The Hindi and Kannada text in the JS should also just work - let's check
text = text.replace("\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd", "")

# Write clean file
with open(r'templates\crop_prices.html', 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

print('\nDone! File written.')
# Count remaining replacement chars
count = text.count('\ufffd')
print(f'Remaining replacement chars: {count}')
if count > 0:
    # Find and print each occurrence with context
    for i, m in enumerate(re.finditer(r'.{0,30}\ufffd.{0,30}', text)):
        print(f'  [{i}] line: {repr(m.group())}')
        if i > 20: 
            print('  ...more...')
            break
