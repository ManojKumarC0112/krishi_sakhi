"""Fix base.html: improve chatbot UI and inject quickReply function."""
import re

with open(r'templates\base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the chatbot window HTML (from sakhi-window div to its closing tag)
old_window_pattern = r'<div class="sakhi-window" id="sakhi-window">.*?</div>\s*\n\s*<!-- GLOBAL SPOTLIGHT'

new_window = '''    <div class="sakhi-window" id="sakhi-window">
        <div class="sakhi-header">
            <span class="sakhi-header-title">
                <span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#69f0ae;margin-right:5px;box-shadow:0 0 5px #69f0ae;"></span>
                Sakhi
            </span>
            <div class="sakhi-header-controls">
                <select id="lang-select">
                    <option value="en-US">English</option>
                    <option value="hi-IN">Hindi</option>
                    <option value="te-IN">Telugu</option>
                    <option value="ta-IN">Tamil</option>
                    <option value="kn-IN">Kannada</option>
                    <option value="mr-IN">Marathi</option>
                </select>
                <button id="stop-speech-btn" title="Stop Speaking">&#x1F507;</button>
                <button onclick="toggleChat()" title="Close Chat"
                    style="font-weight:bold; background:none; font-size:1.1rem; padding:0 4px;">&#x2715;</button>
            </div>
        </div>

        <div class="sakhi-messages" id="sakhi-messages">
            <div class="s-msg-bot">
                <div class="s-bot-avatar">&#x1F33E;</div>
                <div>
                    <span>Namaste! I&#x27;m <strong>Sakhi</strong> &#x1F331; &mdash; your AI farming assistant. Ask me about crop diseases, weather, or market prices!</span>
                    <span class="s-msg-time">Just now</span>
                </div>
            </div>
        </div>

        <!-- Quick-reply suggestion chips -->
        <div id="sakhi-chips" style="padding:8px 10px 4px;display:flex;gap:6px;flex-wrap:wrap;background:#fff;border-top:1px solid rgba(0,0,0,.05);">
            <button onclick="quickReply(&#x27;&#x1F33E; My crop has yellow leaves&#x27;)" style="padding:5px 11px;border-radius:16px;border:1.5px solid #c8e6c9;background:#f1f8e9;color:#2e7d32;font-size:0.75rem;cursor:pointer;font-weight:600;">&#x1F33E; Yellow leaves</button>
            <button onclick="quickReply(&#x27;&#x1F4B0; What is the market price today?&#x27;)" style="padding:5px 11px;border-radius:16px;border:1.5px solid #c8e6c9;background:#f1f8e9;color:#2e7d32;font-size:0.75rem;cursor:pointer;font-weight:600;">&#x1F4B0; Market price</button>
            <button onclick="quickReply(&#x27;&#x1F327;&#xFE0F; Will it rain this week?&#x27;)" style="padding:5px 11px;border-radius:16px;border:1.5px solid #c8e6c9;background:#f1f8e9;color:#2e7d32;font-size:0.75rem;cursor:pointer;font-weight:600;">&#x1F327;&#xFE0F; Rain forecast</button>
            <button onclick="quickReply(&#x27;&#x1F41B; How to treat pest infestation?&#x27;)" style="padding:5px 11px;border-radius:16px;border:1.5px solid #c8e6c9;background:#f1f8e9;color:#2e7d32;font-size:0.75rem;cursor:pointer;font-weight:600;">&#x1F41B; Pest control</button>
        </div>

        <div class="sakhi-input-area">
            <div class="sakhi-text-row">
                <input type="text" id="sakhi-text-input" placeholder="Ask Sakhi anything&#x2026;">
                <button id="sakhi-send-btn" title="Send">&#x27A4;</button>
            </div>
            <div class="sakhi-mic-row">
                <button class="sakhi-mic" id="sakhi-mic" title="Tap to speak">&#x1F3A4;</button>
            </div>
            <div class="sakhi-status" id="sakhi-status">Tap &#x1F3A4; to speak</div>
        </div>
    </div>

    <!-- GLOBAL SPOTLIGHT'''

content = re.sub(old_window_pattern, new_window, content, flags=re.DOTALL)

# 2. Add quickReply function after the sendBtn click listener
old_send_listener = "sendBtn.addEventListener('click', () => sendMessage(textInput.value.trim()));"
new_send_and_quick = """sendBtn.addEventListener('click', () => sendMessage(textInput.value.trim()));

        function quickReply(text) {
            // Hide chips after first use
            const chips = document.getElementById('sakhi-chips');
            if (chips) chips.style.display = 'none';
            sendMessage(text);
        }"""

content = content.replace(old_send_listener, new_send_and_quick)

with open(r'templates\base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('base.html chatbot UI updated successfully')
# Verify the change
if 'sakhi-chips' in content and 'quickReply' in content:
    print('Verification: chips and quickReply function found!')
else:
    print('WARNING: something may not have been replaced correctly')
