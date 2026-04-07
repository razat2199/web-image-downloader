import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote

# =========================
# 1. MAIN GALLERY PAGE URL
# =========================
url = "https://arstechnica.com/security/2026/04/heres-why-its-prudent-for-openclaw-users-to-assume-compromise/"
# base_thread_url = ""
# base_folder_name = "pg"

# for page_num in range(5, 8):   # page2, page3, page4
#     url = f"{base_thread_url}/page{page_num}"
#     print("Processing:", url)

#     folder = f"{base_folder_name}{page_num}"
#     os.makedirs(folder, exist_ok=True)

#     print("Saving into folder:", folder)

# =========================
# 2. OUTPUT FOLDER
# =========================
folder = "high_res_images"
os.makedirs(folder, exist_ok=True)

# =========================
# 3. SESSION + HEADERS
# =========================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": url
})

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")


# -------------------------
# Helper: get extension from content-type
# -------------------------
def ext_from_content_type(content_type):
    content_type = content_type.lower()
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    elif "png" in content_type:
        return ".png"
    elif "webp" in content_type:
        return ".webp"
    elif "gif" in content_type:
        return ".gif"
    elif "bmp" in content_type:
        return ".bmp"
    elif "avif" in content_type:
        return ".avif"
    return ".img"


# -------------------------
# Helper: save real image response
# -------------------------
def save_response_as_image(resp, index):
    content_type = resp.headers.get("Content-Type", "").lower()
    if not content_type.startswith("image/"):
        return False

    ext = ext_from_content_type(content_type)

    parsed = urlparse(resp.url)
    filename = os.path.basename(parsed.path)
    filename = unquote(filename)

    if not filename or "." not in filename:
        filename = f"image_{index}{ext}"
    else:
        base = os.path.splitext(filename)[0]
        filename = base + ext

    file_path = os.path.join(folder, filename)

    base, extension = os.path.splitext(file_path)
    counter = 1
    while os.path.exists(file_path):
        file_path = f"{base}_{counter}{extension}"
        counter += 1

    with open(file_path, "wb") as f:
        f.write(resp.content)

    print(f"    Downloaded REAL image: {file_path}")
    return True


# -------------------------
# Helper: fetch URL and check if it is image
# -------------------------
def try_fetch_image(candidate_url, referer):
    try:
        headers = {"Referer": referer}
        resp = session.get(candidate_url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        print(f"    Trying candidate: {candidate_url}")
        print(f"    Final URL: {resp.url}")
        print(f"    Content-Type: {content_type}")

        if content_type.startswith("image/"):
            return resp

        return resp  # may be HTML, useful for deeper parsing

    except Exception as e:
        print(f"    Failed candidate: {candidate_url} -> {e}")
        return None


# -------------------------
# Extract image candidates from HTML
# -------------------------
def extract_candidates_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # 1) Meta tags
    for selector in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[property="og:image:url"]', "content"),
    ]:
        tag = soup.select_one(selector[0])
        if tag and tag.get(selector[1]):
            candidates.append(urljoin(base_url, tag.get(selector[1])))

    # 2) All img tags
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original", "srcset"]:
            val = img.get(attr)
            if not val:
                continue

            if attr == "srcset":
                parts = [x.strip().split(" ")[0] for x in val.split(",") if x.strip()]
                if parts:
                    # take largest
                    candidates.append(urljoin(base_url, parts[-1]))
            else:
                candidates.append(urljoin(base_url, val))

    # 3) Regex absolute URLs
    regex_urls = re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png|webp|gif|bmp|avif)(?:\?[^"\']*)?', html, re.I)
    candidates.extend(regex_urls)

    # 4) Regex relative URLs
    regex_rel = re.findall(r'["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif|bmp|avif)(?:\?[^"\']*)?)["\']', html, re.I)
    for rel in regex_rel:
        candidates.append(urljoin(base_url, rel))

    # dedupe
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique


# -------------------------
# Resolve detail page -> real image response
# -------------------------
def resolve_real_image(detail_url):
    try:
        print(f"  Opening detail page: {detail_url}")
        resp = session.get(detail_url, headers={"Referer": url}, timeout=20, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        print(f"  Detail page final URL: {resp.url}")
        print(f"  Detail page Content-Type: {content_type}")

        # Case 1: detail page itself is already image
        if content_type.startswith("image/"):
            return resp

        # Case 2: detail page is HTML -> extract candidates
        if "html" not in content_type and "text/" not in content_type:
            print("  Unexpected non-HTML and non-image response.")
            return None

        candidates = extract_candidates_from_html(resp.text, resp.url)
        print(f"  Found {len(candidates)} image candidates in detail page.")

        # Try each candidate
        for candidate in candidates:
            c_resp = try_fetch_image(candidate, resp.url)
            if not c_resp:
                continue

            ctype = c_resp.headers.get("Content-Type", "").lower()

            # If it's a real image, return it
            if ctype.startswith("image/"):
                return c_resp

            # If it's HTML again, maybe nested viewer page -> parse once more
            if "html" in ctype or "text/" in ctype:
                nested_candidates = extract_candidates_from_html(c_resp.text, c_resp.url)
                print(f"    Nested HTML found. {len(nested_candidates)} nested candidates.")

                for nested in nested_candidates:
                    n_resp = try_fetch_image(nested, c_resp.url)
                    if not n_resp:
                        continue
                    ntype = n_resp.headers.get("Content-Type", "").lower()
                    if ntype.startswith("image/"):
                        return n_resp

        print("  Could not resolve a real image.")
        return None

    except Exception as e:
        print(f"  Failed to resolve detail page: {e}")
        return None


# =========================
# 4. FETCH MAIN GALLERY PAGE
# =========================
print(f"Fetching gallery page: {url}")

try:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
except Exception as e:
    print(f"Failed to fetch gallery page: {e}")
    exit()

soup = BeautifulSoup(resp.text, "html.parser")

# =========================
# 5. COLLECT DETAIL PAGE LINKS
# =========================
detail_links = []

for a in soup.find_all("a", href=True):
    if a.find("img"):
        href = a.get("href")
        if href:
            full_url = urljoin(url, href)
            detail_links.append(full_url)

# dedupe
seen = set()
detail_links = [x for x in detail_links if not (x in seen or seen.add(x))]

print(f"Found {len(detail_links)} detail links.")

# =========================
# 6. VISIT EACH DETAIL PAGE -> RESOLVE REAL IMAGE -> SAVE
# =========================
downloaded = 0

for i, detail_url in enumerate(detail_links, start=1):
    print(f"\n[{i}/{len(detail_links)}] Processing:")
    real_img_resp = resolve_real_image(detail_url)

    if real_img_resp:
        ok = save_response_as_image(real_img_resp, i)
        if ok:
            downloaded += 1
    else:
        print("  Skipped: no real image found.")

print(f"\nDone! Downloaded {downloaded} REAL images into folder: {folder}")