import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote

# =========================
# 1. PUT WEBSITE URL HERE
# =========================
url = "https://arstechnica.com/security/2026/04/heres-why-its-prudent-for-openclaw-users-to-assume-compromise/"

# =========================
# 2. OUTPUT FOLDER
# =========================
folder = "downloaded_images_new"
os.makedirs(folder, exist_ok=True)

# =========================
# 3. HEADERS
# =========================
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": url
}

print(f"Fetching webpage: {url}")

try:
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
except Exception as e:
    print(f"Failed to fetch webpage: {e}")
    exit()

html = response.text
soup = BeautifulSoup(html, "html.parser")

img_urls = set()

for img in soup.find_all("img"):
    possible_attrs = ["src", "data-src", "data-lazy-src", "data-original", "srcset"]

    for attr in possible_attrs:
        val = img.get(attr)
        if not val:
            continue

        if attr == "srcset":
            first_url = val.split(",")[0].strip().split(" ")[0]
            full_url = urljoin(url, first_url)
            img_urls.add(full_url)
        else:
            full_url = urljoin(url, val)
            img_urls.add(full_url)

print(f"Found {len(img_urls)} image URLs.")

downloaded_count = 0

for i, img_url in enumerate(img_urls, start=1):
    try:
        print(f"Downloading {i}: {img_url}")

        img_response = requests.get(img_url, headers=headers, timeout=20)
        img_response.raise_for_status()

        parsed = urlparse(img_url)
        original_name = os.path.basename(parsed.path)
        original_name = unquote(original_name)

        if not original_name or "." not in original_name:
            original_name = f"image_{i}.jpg"

        filename = os.path.join(folder, original_name)

        # Avoid overwriting duplicate names
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filename):
            filename = f"{base}_{counter}{ext}"
            counter += 1

        with open(filename, "wb") as f:
            f.write(img_response.content)

        downloaded_count += 1

    except Exception as e:
        print(f"Failed to download {img_url}: {e}")

print(f"\nDone! Downloaded {downloaded_count} images into folder: {folder}")
