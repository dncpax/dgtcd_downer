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
    mime_to_extension = {
        "image/tiff; application=geotiff": ".tif",
        "image/tiff": ".tif",
        "application/vnd.laszip": ".laz",
    }
    return mime_to_extension.get(mime_type, ".bin")

def divide_bbox(bbox, max_area_km2=200):
    min_lon, min_lat, max_lon, max_lat = bbox
    deg_to_km = 111
    width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
    height_km = (max_lat - min_lat) * deg_to_km
    total_area_km2 = width_km * height_km

    if total_area_km2 <= max_area_km2:
        return [bbox]

    splits_x = math.ceil(width_km / math.sqrt(max_area_km2))
    splits_y = math.ceil(height_km / math.sqrt(max_area_km2))

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
    payload = {
        "bbox": bbox,
        "limit": 1000
    }
    if collections:
        payload["collections"] = collections

    print(f"A esperar {delay}s antes de procurar...")
    time.sleep(delay)
    
    try:
        response = requests.post(stac_url, json=payload, timeout=30)
        # Check Content-Type for text-based responses
        content_type = response.headers.get("Content-Type", "").lower()
        if content_type.startswith("text/") or content_type == "application/json":
            error_message = f"Authentication error detected for {url}: Content-Type is {content_type}"
            try:
                error_message += f"\nResponse content: {response.text[:1000]}"  # Limit for brevity
            except UnicodeDecodeError:
                error_message += "\nResponse content: (non-text response, unable to decode)"
            raise AuthenticationError(error_message)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Erro na query da API STAC para a bbox {bbox}: {e}")
        return {"features": []}

def collect_urls_per_collection(stac_response):
    urls_per_collection = {}
    seen_urls = set()

    for item in stac_response.get("features", []):
        collection = item.get("collection", "unknown")
        item_id = None
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
                urls_per_collection[collection].append((url, item_id, extension))
                seen_urls.add(url)
    
    return urls_per_collection

def download_file(url, item_id, extension, output_dir, headers, cookies, delay=5.0):
    import sys

    filename = f"{item_id}{extension}" if item_id else f"{url.split('/')[-1]}{extension}"
    file_path = os.path.join(output_dir, filename)

    if os.path.exists(file_path):
        print(f"Ignorar {filename}: ficheiro já existe")
        return False

    print(f"A esperar {delay}s antes do download do {filename}...")
    time.sleep(delay)

    try:
        response = requests.get(url, headers=headers, cookies=cookies, stream=True, timeout=30)
        response.raise_for_status()

        total = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        chunk_size = 8192
        bar_length = 30

        os.makedirs(output_dir, exist_ok=True)
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        done = int(bar_length * downloaded / total)
                        percent = int(100 * downloaded / total)
                        bar = f"[{'#' * done}{'-' * (bar_length - done)}] {percent}%"
                        sys.stdout.write(f"\rDownloading {filename} {bar}")
                        sys.stdout.flush()
            if total > 0:
                sys.stdout.write("\n")
            else:
                print(f"Download do {filename} realizado! (unknown size)")
        return True

    except requests.RequestException as e:
        print(f"\nErro no download {url}: {e}")
        return False


def get_available_collections_fallback(stac_url, headers=None, cookies=None):
    """Fallback: get unique collections from a broad STAC search."""
    print("A obter as coleções via a API do STAC...")
    payload = {
        "bbox": [-9.5, 36.5, -6.0, 42.5],  # Portugal mainland
        "limit": 1000
    }
    try:
        response = requests.post(stac_url, json=payload, headers=headers or {}, cookies=cookies or {}, timeout=30)
        response.raise_for_status()
        data = response.json()
        collections = set()
        for feature in data.get("features", []):
            c = feature.get("collection")
            if c:
                collections.add(c)
        return sorted(collections)
    except Exception as e:
        print(f"Erro a obter as coleções: {e}")
        return []

def main(bbox, stac_url, headers, cookies, output_dir, delay, collections=None):
    small_bboxes = divide_bbox(bbox)
    print(f"Bbox dividida em {len(small_bboxes)} pequenas bboxes")

    all_urls_per_collection = {}
    for i, small_bbox in enumerate(small_bboxes, 1):
        print(f"A processar bbox {i}/{len(small_bboxes)}: {small_bbox}")
        stac_response = search_stac_api(stac_url, small_bbox, collections=collections)
        urls_per_collection = collect_urls_per_collection(stac_response)
        
        for collection, url_id_ext_pairs in urls_per_collection.items():
            if collection not in all_urls_per_collection:
                all_urls_per_collection[collection] = []
            all_urls_per_collection[collection].extend(url_id_ext_pairs)
        
        print(f"Encontrados {sum(len(urls) for urls in urls_per_collection.values())} items na bbox {i}")

    total_urls = sum(len(urls) for urls in all_urls_per_collection.values())
    print(f"Total de URLs únicos para download: {total_urls}")
    downloaded = 0
    skipped = 0

    for collection, url_id_ext_pairs in all_urls_per_collection.items():
        print(f"\nDownloading da coleção: {collection}")
        for j, (url, item_id, extension) in enumerate(url_id_ext_pairs, 1):
            print(f"A processar o URL {j}/{len(url_id_ext_pairs)} : {url}")
            if download_file(url, item_id, extension, output_dir, headers, cookies, delay):
                downloaded += 1
            else:
                skipped += 1
    
    print(f"\nResumo: Download de {downloaded} ficheiros, ignorados {skipped} ficheiros")

if __name__ == "__main__":
    print("\n--- DGT CDD Downloader ---")

    try:
        # Bounding box
        bbox_input = input("Define a bounding box separada por virgulas, como (min_lon,min_lat,max_lon,max_lat):\n> ")
        input_bbox = [float(x.strip()) for x in bbox_input.split(",")]

        # Cookies
        auth_session = input("Valor do 'auth_session' cookie obtido no dev console do browser:\n> ").strip()
        connect_sid = input("Valor do 'connect.sid' cookie obtido no dev console do browser:\n> ").strip()

        # Output directory
        output_dir = input("Diretoria de outputr (default: ./downloaded_files):\n> ").strip()
        if not output_dir:
            output_dir = "./downloaded_files"

        # Delay
        delay_input = input("Tempo de espera em segundos entre cada request/download (default: 5.0):\n> ").strip()
        try:
            download_delay = float(delay_input) if delay_input else 5.0
        except ValueError:
            print("Tempo de espera inválido. Assumido o tempo de espera padrão: 5.0 segundos.")
            download_delay = 5.0

        # Static config
        STAC_SEARCH_URL = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
        HEADERS = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*"
        }
        COOKIES = {
            "ACCEPTED_TERMS": "true",
            "auth_session": auth_session,
            "connect.sid": connect_sid
        }

        # Get collections via fallback
        available = get_available_collections_fallback(STAC_SEARCH_URL, headers=HEADERS, cookies=COOKIES)
        if not available:
            print("AVISO: Não foi possível obter as coleções. A processar sem esse filtro.")
            selected_collections = None
        else:
            print("\nColeções disponíveis:")
            for i, name in enumerate(available, 1):
                print(f"  {i}. {name}")
            selected_input = input("Seleciona o número da coleção pretendida. Para mais que uma coleção usar os números separados por vírgula ou Enter para obter todas as coleções na bounding box:\n> ").strip()
            if selected_input:
                try:
                    indices = [int(i) - 1 for i in selected_input.split(",")]
                    selected_collections = [available[i] for i in indices if 0 <= i < len(available)]
                except Exception as e:
                    print(f"Input inválido: {e}. A processar sem esse filtro.")
                    selected_collections = None
            else:
                selected_collections = None

        print("\nInício do processo de download...\n")
        main(input_bbox, STAC_SEARCH_URL, HEADERS, COOKIES, output_dir, download_delay, collections=selected_collections)

    except Exception as e:
        print(f"Erro: {e}")
        sys.exit(1)
