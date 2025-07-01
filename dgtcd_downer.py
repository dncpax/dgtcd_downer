import math
import requests
import os
import json
import time
import sys

class AuthenticationError(Exception):
    """Custom exception for authentication errors."""
    pass

def get_file_extension(mime_type):
    """Map MIME type to file extension."""
    mime_to_extension = {
        "image/tiff; application=geotiff": ".tif",
        "image/tiff": ".tif",
        "application/x-las": ".laz",
        # Add more MIME types as needed
    }
    return mime_to_extension.get(mime_type, ".bin")  # Fallback to .bin for unknown types

def divide_bbox(bbox, max_area_km2=200):
    """Divide a large bbox into smaller bboxes with area <= max_area_km2."""
    min_lon, min_lat, max_lon, max_lat = bbox
    # Approximate conversion: 1 degree ~ 111 km
    deg_to_km = 111
    # Calculate approximate width and height in km
    width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
    height_km = (max_lat - min_lat) * deg_to_km
    total_area_km2 = width_km * height_km

    if total_area_km2 <= max_area_km2:
        return [bbox]

    # Calculate number of splits needed
    splits_x = math.ceil(width_km / math.sqrt(max_area_km2))
    splits_y = math.ceil(height_km / math.sqrt(max_area_km2))

    # Calculate size of each small bbox in degrees
    delta_lon = (max_lon - min_lon) / splits_x
    delta_lat = (max_lat - min_lat) / splits_y

    small_bboxes = []
    for i in range(splits_x):
        for j in range(splits_y):
            small_min_lon = min_lon + i * delta_lon
            small_max_lon = min(small_min_lon + delta_lon, max_lon)
            small_min_lat = min_lat + j * delta_lat
            small_max_lat = min(small_min_lat + delta_lat, max_lat)
            small_bboxes.append([small_min_lon, small_min_lat, small_max_lon, small_max_lat])
    
    return small_bboxes

def search_stac_api(stac_url, bbox, collections=None, delay=0.2):
    """Query STAC search API for items within a bbox."""
    payload = {
        "bbox": bbox,
        "limit": 1000  # Adjust as needed
    }
    if collections:
        payload["collections"] = collections

    # Add delay before download
    print(f"Waiting {delay}s before searching...")
    time.sleep(delay)
    
    try:
        response = requests.post(stac_url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error querying STAC API for bbox {bbox}: {e}")
        return {"features": []}

def collect_urls_per_collection(stac_response):
    """Extract unique URLs, item IDs, and extensions per collection from STAC response."""
    urls_per_collection = {}
    seen_urls = set()

    for item in stac_response.get("features", []):
        collection = item.get("collection", "unknown")
        item_id = None
        # Find the self link to get the item ID
        for link in item.get("links", []):
            if link.get("rel") == "self":
                item_id = link.get("href").split("/")[-1]
                break
        assets = item.get("assets", {})
        for asset_key, asset in assets.items():
            url = asset.get("href")
            mime_type = asset.get("type")
            extension = get_file_extension(mime_type)
            if url and url not in seen_urls:
                if collection not in urls_per_collection:
                    urls_per_collection[collection] = []
                # Store tuple of (url, item_id, extension)
                urls_per_collection[collection].append((url, item_id, extension))
                seen_urls.add(url)
    
    return urls_per_collection

def download_file(url, item_id, extension, output_dir, headers, cookies, delay=5.0):
    """Download a file from a URL if it doesn't already exist, using item_id and extension for filename."""
    # Use item_id with dynamic extension for filename
    filename = f"{item_id}{extension}" if item_id else f"{url.split('/')[-1]}{extension}"
    file_path = os.path.join(output_dir, filename)

    if os.path.exists(file_path):
        print(f"Skipping {filename}: file already exists")
        return False
    
    # Add delay before download
    print(f"Waiting 5s before downloading...")
    time.sleep(delay)

    try:
        response = requests.get(url, headers=headers, cookies=cookies, stream=True, timeout=30)
        # Check Content-Type for text-based responses
        content_type = response.headers.get("Content-Type", "").lower()
        #if content_type.startswith("text/") or content_type == "application/json":
        #    error_message = f"Authentication error detected for {url}: Content-Type is {content_type}"
        #    try:
        #        error_message += f"\nResponse content: {response.text[:1000]}"  # Limit for brevity
        #    except UnicodeDecodeError:
        #        error_message += "\nResponse content: (non-text response, unable to decode)"
        #    raise AuthenticationError(error_message)
        
        response.raise_for_status()
        os.makedirs(output_dir, exist_ok=True)
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"Downloaded {filename}")
        return True
    except requests.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False

def main(bbox, stac_url, headers, cookies, output_dir):
    """Main function to process bboxes, query STAC, and download files."""
    small_bboxes = divide_bbox(bbox)
    print(f"Divided bbox into {len(small_bboxes)} smaller bboxes")

    all_urls_per_collection = {}
    for i, small_bbox in enumerate(small_bboxes, 1):
        print(f"Processing bbox {i}/{len(small_bboxes)}: {small_bbox}")
        stac_response = search_stac_api(stac_url, small_bbox)
        urls_per_collection = collect_urls_per_collection(stac_response)
        
        for collection, url_id_ext_pairs in urls_per_collection.items():
            if collection not in all_urls_per_collection:
                all_urls_per_collection[collection] = []
            all_urls_per_collection[collection].extend(url_id_ext_pairs)
        
        print(f"Found {sum(len(urls) for urls in urls_per_collection.values())} items in bbox {i}")

    total_urls = sum(len(urls) for urls in all_urls_per_collection.values())
    print(f"Total unique URLs to download: {total_urls}")
    downloaded = 0
    skipped = 0

    for collection, url_id_ext_pairs in all_urls_per_collection.items():
        print(f"\nDownloading from collection: {collection}")
        for j, (url, item_id, extension) in enumerate(url_id_ext_pairs, 1):
            print(f"Processing URL {j}/{len(url_id_ext_pairs)} : {url}")
            if download_file(url, item_id, extension, output_dir, headers, cookies):
                downloaded += 1
            else:
                skipped += 1
    
    print(f"\nSummary: Downloaded {downloaded} files, skipped {skipped} files")

if __name__ == "__main__":
    # 
    input_bbox = [-7.9563, 37.9499, -7.7684, 38.1136]  # replace with your AIO 
    STAC_SEARCH_URL = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"  # Replace with actual STAC search URL
    DOWNLOAD_API_URL = "https://example.com/download"    # Replace with actual download URL - not relevant, urls are obtainted from search api results
    # REPLACE WITH "ACTIVE" HEADERS AND COOKIES AFTER LOGGING IN INTO THE PLATFORM, COPY FROM BROWSER DEV CONSOLE
    HEADERS = {
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
  "Accept-Language": "pt-PT,pt;q=0.7",
  "Cache-Control": "no-cache",
  "Connection": "keep-alive",
  "Pragma": "no-cache",
  "Sec-Fetch-Dest": "document",
  "Sec-Fetch-Mode": "navigate",
  "Sec-Fetch-Site": "same-site",
  "Sec-Fetch-User": "?1",
  "Sec-GPC": "1",
  "Upgrade-Insecure-Requests": "1",
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Brave\";v=\"138\"",
  "sec-ch-ua-mobile": "?0",
  "sec-ch-ua-platform": "\"Windows\""
}
    COOKIES = {
  "ACCEPTED_TERMS": "true",
  "auth_session": "04JevdgHMCuPvTlD_-6bkIRm7IDrbf8S",
  "connect.sid": "s:04JevdgHMCuPvTlD_-6bkIRm7IDrbf8S.nPr726tG2tNzafdoV9GNCeg19yOy7TonDFHlPmv1xOE"
}
    OUTPUT_DIR = "./downloaded_files"                   # Directory to save files

    main(input_bbox, STAC_SEARCH_URL, HEADERS, COOKIES, OUTPUT_DIR)
    
    
