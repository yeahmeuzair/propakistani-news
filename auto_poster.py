import os
import json
import base64
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai
from google.genai import types

# Configurations
FEED_URL = "https://propakistani.pk/category/others/education/feed/"
HISTORY_FILE = "posted_links.json"

# Environment Variables (Set in GitHub Secrets)
WP_URL = os.environ.get("WP_URL")
WP_USERNAME = os.environ.get("WP_USERNAME")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")

# Replace with your actual Educational News category ID in WordPress
CATEGORY_ID = 15 

client = genai.Client(api_key=GEMINI_API_KEY)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def send_email_alert(title, edit_url):
    if not EMAIL_USER or not EMAIL_APP_PASSWORD:
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER
    msg['Subject'] = f"WP Draft Ready: {title}"

    body = f"A new automated post draft is ready for your review.\n\nTitle: {title}\n\nClick below to open the editor and publish:\n{edit_url}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email alert: {e}")

def process_with_ai(title, summary):
    prompt = f"""
    You are an expert SEO content writer for an educational website (BISE Pakistan).
    Rewrite the following news item into a professional, humanized, factual, and 100% SEO-optimized article.

    Original Title: {title}
    Original Context: {summary}

    Requirements:
    1. Structure the content using pure clean HTML (use <h2> for subheadings, <p> for paragraphs, and <ul>/<li> for bullet points). Do not wrap the output in markdown codeblocks.
    2. Tone must be informative, authentic, clear, and natural (avoid generic AI fluff).
    3. Include high-traffic keywords naturally (e.g., Punjab education, board news, school updates).
    4. Provide the output strictly in this JSON format:
    {{
        "title": "A catchy, SEO-friendly headline",
        "slug": "seo-friendly-short-slug",
        "excerpt": "A clean 1-2 sentence meta description without quotes",
        "content": "<p>First paragraph...</p><h2>Subheading</h2><p>Second paragraph...</p>"
    }}
    """
    
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
    )
    return json.loads(response.text)

def post_to_wordpress(article):
    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "title": article["title"],
        "slug": article["slug"],
        "excerpt": article["excerpt"],
        "content": article["content"],
        "status": "draft",
        "categories": [CATEGORY_ID]
    }
    
    res = requests.post(endpoint, json=payload, headers=headers)
    if res.status_code in [200, 201]:
        post_data = res.json()
        post_id = post_data.get("id")
        edit_url = f"{WP_URL.rstrip('/')}/wp-admin/post.php?post={post_id}&action=edit"
        send_email_alert(article["title"], edit_url)
        return True
    return False

def main():
    feed = feedparser.parse(FEED_URL)
    history = load_history()
    
    count = 0
    for entry in feed.entries:
        if entry.link not in history:
            print(f"Processing: {entry.title}")
            try:
                ai_data = process_with_ai(entry.title, entry.summary)
                success = post_to_wordpress(ai_data)
                
                if success:
                    print(f"Draft created successfully: {ai_data['title']}")
                    history.append(entry.link)
                    count += 1
                else:
                    print("Failed to save draft to WordPress.")
            except Exception as e:
                print(f"Error processing entry: {e}")
                
            if count >= 2: # Processes a maximum of 2 new articles per run to prevent API/WP overload
                break
                
    save_history(history)

if __name__ == "__main__":
    main()
