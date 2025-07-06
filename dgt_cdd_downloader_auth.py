"""
DGT CDD Downloader - QGIS Processing Tool with Cookie-based Authentication
Ferramenta para download de dados geoespaciais da DGT através do QGIS com autenticação por cookies
"""

import math
import requests
import os
import json
import time
import urllib.parse
from typing import Dict, List, Tuple, Any, Optional
from html.parser import HTMLParser

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterExtent,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsMessageLog,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsWkbTypes,
    QgsFields,
    QgsField,
    QgsProcessingParameterVectorDestination,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsVectorFileWriter
)
from qgis.PyQt.QtWidgets import QMessageBox


class AuthenticationError(Exception):
    """Custom exception for authentication errors."""
    pass


class KeycloakFormParser(HTMLParser):
    """HTML parser to extract form data from Keycloak login page"""
    
    def __init__(self):
        super().__init__()
        self.form_action = None
        self.form_data = {}
        self.in_form = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'form' and attrs_dict.get('id') == 'kc-form-login':
            self.in_form = True
            self.form_action = attrs_dict.get('action')
            
        elif tag == 'input' and self.in_form:
            input_name = attrs_dict.get('name')
            input_value = attrs_dict.get('value', '')
            input_type = attrs_dict.get('type', 'text')
            
            if input_name and input_type == 'hidden':
                self.form_data[input_name] = input_value
                
    def handle_endtag(self, tag):
        if tag == 'form' and self.in_form:
            self.in_form = False


class DgtCddDownloaderAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm for downloading DGT CDD data with cookie-based authentication
    """
    
    # Constants
    INPUT_EXTENT = 'INPUT_EXTENT'
    USERNAME = 'USERNAME'
    PASSWORD = 'PASSWORD'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    DELAY = 'DELAY'
    COLLECTIONS = 'COLLECTIONS'
    MAX_AREA = 'MAX_AREA'
    CREATE_BOUNDARY_LAYER = 'CREATE_BOUNDARY_LAYER'
    BOUNDARY_OUTPUT = 'BOUNDARY_OUTPUT'
    
    def __init__(self):
        super().__init__()
        self.stac_url = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
        self.auth_base_url = "https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/protocol/openid-connect"
        self.redirect_uri = "https://cdd.dgterritorio.gov.pt/auth/callback"
        self.client_id = "aai-oidc-dgt"
        self.main_site = "https://cdd.dgterritorio.gov.pt"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin"
        }
        
        self.available_collections = []
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)
    
    def createInstance(self):
        return DgtCddDownloaderAlgorithm()
    
    def name(self):
        return 'dgt_cdd_downloader_auth'
    
    def displayName(self):
        return self.tr('DGT CDD Downloader')
    
    def group(self):
        return self.tr('DGT CDD Portal')
    
    def groupId(self):
        return 'dgt_cdd_portal'
    
    def shortHelpString(self):
        return self.tr("""
        Download geospatial data from DGT (Direção-Geral do Território) CDD Portal.
        
        This tool allows you to:
        - Login with your DGT credentials (username and password)
        - Select an area of interest using QGIS extent selector
        - Download various geospatial LiDAR datasets from DGT CDD Portal
        (LAZ, MDS-50cm, MDS-2m, MDT-50cm, MDT-2m)
        - Automatically organize files by collection
        - Create boundary layers showing download areas
        
        Requirements:
        - Valid DGT CDD portal credentials
        (https://cdd.dgterritorio.gov.pt)
        - Internet connection
        
        The tool will automatically handle the authentication process using session cookies
        and divide large areas into smaller chunks to avoid server overload.
        
        -------------------------------------------------
        
        Serviço de descarregamento de dados geográficos da DGT (Direção-Geral do Território) - Centro de Dados.
        
        Esta ferramenta permite:
        - Fazer login no Centro de dados da DGT com as suas credenciais (username e password)
        - Selecionar uma área de interesse utilizando as ferramentas do QGIS
        - Descarregar as várias coleções de dados LiDAR disponíveis no Centro de Dados da DGT
        (LAZ, MDS-50cm, MDS-2m, MDT-50cm, MDT-2m)
        - Organizar os ficheiros descarregados por coleção
        - Criar uma layer com a extensão das áreas de download
        
        Requisitos:
        - Credenciais válidas do Centro de Dados da DGT
        (https://cdd.dgterritorio.gov.pt)
        - Ligação à Internet
        
        Esta ferramenta vai gerir automaticamente o processo de autenticação usando cookies de sessão
        e dividir áreas grandes em partes mais pequenas, respeitando os limites impostos pelo ervidor.
        
        """)
    
    def initAlgorithm(self, config=None):
        # Input extent (can be selected from canvas)
        self.addParameter(
            QgsProcessingParameterExtent(
                self.INPUT_EXTENT,
                self.tr('Area of Interest'),
                defaultValue=None
            )
        )
        
        # Authentication parameters
        self.addParameter(
            QgsProcessingParameterString(
                self.USERNAME,
                self.tr('Username'),
                multiLine=False,
                defaultValue='',
                optional=False
            )
        )
        
        # Password parameter (Note: QGIS Processing doesn't support native password fields)
        # The password will be visible while typing - use with caution in shared environments
        self.addParameter(
            QgsProcessingParameterString(
                self.PASSWORD,
                self.tr('Password'),
                multiLine=False,
                defaultValue='',
                optional=False
            )
        )
        
        # Output folder
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output Folder')
            )
        )
        
        # Optional parameters
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DELAY,
                self.tr('Delay between requests (seconds)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=5.0,
                minValue=1.0,
                maxValue=60.0
            )
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_AREA,
                self.tr('Maximum area per request (km²)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=200.0,
                minValue=50.0,
                maxValue=200.0
            )
        )
        
        # Collections (predefined options)
        self.addParameter(
            QgsProcessingParameterEnum(
                self.COLLECTIONS,
                self.tr('Collections to download'),
                options=['LAZ', 'MDS-2m', 'MDS-50cm', 'MDT-2m', 'MDT-50cm'],
                allowMultiple=True,
                optional=True
            )
        )
        
        # Create boundary layer
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_BOUNDARY_LAYER,
                self.tr('Create boundary layer showing download areas'),
                defaultValue=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.BOUNDARY_OUTPUT,
                self.tr('Boundary Layer'),
                type=QgsProcessing.TypeVectorPolygon,
                optional=True
            )
        )
    
    def authenticate(self, username: str, password: str, feedback: QgsProcessingFeedback) -> bool:
        """Authenticate with DGT using username and password, extracting session cookies"""
        try:
            feedback.pushInfo("Starting authentication process...")
            
            # Create a fresh session
            self.session = requests.Session()
            self.session.headers.update(self.headers)
            
            # Step 1: Visit main site to get initial session
            feedback.pushInfo("Visiting main site...")
            response = self.session.get(self.main_site, timeout=30)
            response.raise_for_status()
            
            # Step 2: Look for login link or go directly to auth
            auth_url = f"{self.auth_base_url}/auth"
            auth_params = {
                'client_id': self.client_id,
                'response_type': 'code',
                'redirect_uri': self.redirect_uri,
                'scope': 'openid profile email'
            }
            
            full_auth_url = f"{auth_url}?" + urllib.parse.urlencode(auth_params)
            feedback.pushInfo("Getting authentication page...")
            
            # Step 3: Get the login form
            response = self.session.get(full_auth_url, timeout=30)
            response.raise_for_status()
            
            feedback.pushInfo(f"Got login page (status: {response.status_code})")
            
            # Step 4: Parse the login form
            parser = KeycloakFormParser()
            parser.feed(response.text)
            
            if not parser.form_action:
                raise AuthenticationError("Could not find login form")
            
            feedback.pushInfo("Found login form, submitting credentials...")
            
            # Step 5: Submit login form
            login_data = parser.form_data.copy()
            login_data.update({
                'username': username,
                'password': password
            })
            
            # Build absolute URL for form action
            if parser.form_action.startswith('/'):
                login_url = f"https://auth.cdd.dgterritorio.gov.pt{parser.form_action}"
            else:
                login_url = parser.form_action
            
            login_headers = self.headers.copy()
            login_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://auth.cdd.dgterritorio.gov.pt',
                'Referer': response.url
            })
            
            response = self.session.post(
                login_url,
                data=login_data,
                headers=login_headers,
                allow_redirects=True,  # Allow redirects
                timeout=30
            )
            
            feedback.pushInfo(f"Login response: {response.status_code}")
            
            # Step 6: Check if we're back at the main site (successful auth)
            if response.url.startswith(self.main_site):
                feedback.pushInfo("Successfully redirected to main site")
                
                # Extract important cookies
                cookies = self.session.cookies
                important_cookies = []
                
                for cookie in cookies:
                    if cookie.name in ['auth_session', 'connect.sid', 'JSESSIONID', 'KC_RESTART']:
                        important_cookies.append(f"{cookie.name}={cookie.value}")
                
                if important_cookies:
                    feedback.pushInfo(f"Found authentication cookies: {', '.join([c.split('=')[0] for c in important_cookies])}")
                else:
                    feedback.pushInfo("No specific authentication cookies found, but session should be valid")
                
                # Test the session by making a request to the STAC API
                test_bbox = [-9.0, 38.0, -8.0, 39.0]  # Small test area
                test_payload = {
                    "bbox": test_bbox,
                    "limit": 1
                }
                
                feedback.pushInfo("Testing authentication with STAC API...")
                test_response = self.session.post(
                    self.stac_url,
                    json=test_payload,
                    timeout=30
                )
                
                if test_response.status_code == 200:
                    feedback.pushInfo("Authentication successful! Session is valid.")
                    return True
                else:
                    feedback.reportError(f"Authentication test failed: {test_response.status_code}")
                    return False
            
            # Step 7: Check for authentication errors
            if "error" in response.url.lower() or response.status_code >= 400:
                feedback.reportError("Authentication failed - check credentials")
                return False
            
            # If we get here, something unexpected happened
            feedback.reportError(f"Unexpected response: {response.status_code}, URL: {response.url}")
            return False
            
        except requests.RequestException as e:
            feedback.reportError(f"Network error during authentication: {e}")
            return False
        except Exception as e:
            feedback.reportError(f"Authentication error: {e}")
            return False
    
    def get_file_extension(self, mime_type: str) -> str:
        """Get file extension based on MIME type"""
        mime_to_extension = {
            "image/tiff; application=geotiff": ".tif",
            "image/tiff": ".tif",
            "application/vnd.laszip": ".laz",
            "application/octet-stream": ".bin",
            "application/json": ".json",
            "text/xml": ".xml"
        }
        return mime_to_extension.get(mime_type, ".bin")
    
    def divide_bbox(self, bbox: List[float], max_area_km2: float) -> List[List[float]]:
        """Divide large bounding box into smaller chunks"""
        min_lon, min_lat, max_lon, max_lat = bbox
        deg_to_km = 111
        
        # Calculate dimensions
        width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
        height_km = (max_lat - min_lat) * deg_to_km
        total_area_km2 = width_km * height_km
        
        if total_area_km2 <= max_area_km2:
            return [bbox]
        
        # Calculate splits
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
    
    def search_stac_api(self, bbox: List[float], collections: List[str] = None, 
                       delay: float = 0.2) -> Dict:
        """Search STAC API for items in bounding box"""
        payload = {
            "bbox": bbox,
            "limit": 1000
        }
        if collections:
            payload["collections"] = collections
        
        time.sleep(delay)
        
        try:
            response = self.session.post(
                self.stac_url, 
                json=payload, 
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            QgsMessageLog.logMessage(
                f"STAC API error for bbox {bbox}: {e}",
                "DGT Downloader",
                Qgis.Warning
            )
            return {"features": []}
    
    def collect_urls_per_collection(self, stac_response: Dict) -> Dict[str, List[Tuple[str, str, str]]]:
        """Collect download URLs organized by collection"""
        urls_per_collection = {}
        seen_urls = set()
        
        for item in stac_response.get("features", []):
            collection = item.get("collection", "unknown")
            
            # Get item ID
            item_id = None
            for link in item.get("links", []):
                if link.get("rel") == "self":
                    item_id = link.get("href", "").split("/")[-1]
                    break
            
            if not item_id:
                item_id = item.get("id", "unknown")
            
            # Process assets
            assets = item.get("assets", {})
            for asset_key, asset in assets.items():
                url = asset.get("href")
                mime_type = asset.get("type", "")
                extension = self.get_file_extension(mime_type)
                
                if url and url not in seen_urls:
                    if collection not in urls_per_collection:
                        urls_per_collection[collection] = []
                    urls_per_collection[collection].append((url, item_id, extension))
                    seen_urls.add(url)
        
        return urls_per_collection
    
    def download_file(self, url: str, item_id: str, extension: str, 
                     output_dir: str, delay: float,
                     feedback: QgsProcessingFeedback) -> bool:
        """Download a single file"""
        filename = f"{item_id}{extension}"
        file_path = os.path.join(output_dir, filename)
        
        # Skip if file exists
        if os.path.exists(file_path):
            feedback.pushInfo(f"Skipping {filename}: file already exists")
            return False
        
        feedback.pushInfo(f"Downloading {filename}...")
        time.sleep(delay)
        
        try:
            response = self.session.get(
                url, 
                stream=True,
                timeout=60
            )
            
            # Check for authentication errors
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type.startswith("text/html"):
                # Might be an auth error page
                if "login" in response.text.lower() or "auth" in response.text.lower():
                    raise AuthenticationError(f"Authentication error for {url}")
            
            response.raise_for_status()
            
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # Download with progress
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if feedback.isCanceled():
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = int(100 * downloaded / total_size)
                            feedback.setProgress(progress)
            
            feedback.pushInfo(f"Downloaded {filename} successfully")
            return True
            
        except Exception as e:
            feedback.reportError(f"Error downloading {url}: {e}")
            return False
    
    def create_boundary_layer(self, bboxes: List[List[float]], output_path: str, 
                            context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> str:
        """Create a vector layer showing download boundaries"""
        try:
            # Create memory layer first
            crs = QgsCoordinateReferenceSystem('EPSG:4326')
            layer = QgsVectorLayer(
                f"Polygon?crs=EPSG:4326",
                "DGT Download Boundaries",
                "memory"
            )
            
            # Create fields with proper constructor
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int, "Integer"))
            fields.append(QgsField("min_lon", QVariant.Double, "Real"))
            fields.append(QgsField("min_lat", QVariant.Double, "Real"))
            fields.append(QgsField("max_lon", QVariant.Double, "Real"))
            fields.append(QgsField("max_lat", QVariant.Double, "Real"))
            fields.append(QgsField("area_km2", QVariant.Double, "Real"))
            
            # Add fields to layer
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            
            # Create features
            features = []
            for i, bbox in enumerate(bboxes):
                min_lon, min_lat, max_lon, max_lat = bbox
                
                # Create polygon geometry
                points = [
                    QgsPointXY(min_lon, min_lat),
                    QgsPointXY(max_lon, min_lat),
                    QgsPointXY(max_lon, max_lat),
                    QgsPointXY(min_lon, max_lat),
                    QgsPointXY(min_lon, min_lat)
                ]
                
                geometry = QgsGeometry.fromPolygonXY([points])
                
                # Calculate area
                deg_to_km = 111
                width_km = (max_lon - min_lon) * deg_to_km * math.cos(math.radians((min_lat + max_lat) / 2))
                height_km = (max_lat - min_lat) * deg_to_km
                area_km2 = width_km * height_km
                
                # Create feature
                feature = QgsFeature()
                feature.setGeometry(geometry)
                feature.setAttributes([i + 1, min_lon, min_lat, max_lon, max_lat, area_km2])
                features.append(feature)
            
            # Add features to layer
            layer.dataProvider().addFeatures(features)
            layer.updateExtents()
            
            # Write layer to file
            transform_context = context.transformContext()
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.fileEncoding = "UTF-8"
            
            error = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer,
                output_path,
                transform_context,
                save_options
            )
            
            if error[0] == QgsVectorFileWriter.NoError:
                feedback.pushInfo(f"Boundary layer created successfully: {output_path}")
                return output_path
            else:
                feedback.reportError(f"Error creating boundary layer: {error[1]}")
                return None
                
        except Exception as e:
            feedback.reportError(f"Error creating boundary layer: {str(e)}")
            return None
    
    def processAlgorithm(self, parameters, context, feedback):
        """Main processing algorithm"""
        try:
            # Get parameters
            extent = self.parameterAsExtent(parameters, self.INPUT_EXTENT, context)
            username = self.parameterAsString(parameters, self.USERNAME, context)
            password = self.parameterAsString(parameters, self.PASSWORD, context)
            output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
            delay = self.parameterAsDouble(parameters, self.DELAY, context)
            max_area = self.parameterAsDouble(parameters, self.MAX_AREA, context)
            create_boundary = self.parameterAsBool(parameters, self.CREATE_BOUNDARY_LAYER, context)
            boundary_output = self.parameterAsOutputLayer(parameters, self.BOUNDARY_OUTPUT, context)
            
            # Validate credentials
            if not username or not password:
                raise QgsProcessingException("Username and password are required")
            
            # Authenticate
            if not self.authenticate(username, password, feedback):
                raise QgsProcessingException("Authentication failed")
            
            # Convert extent to WGS84 if needed
            extent_crs = self.parameterAsExtentCrs(parameters, self.INPUT_EXTENT, context)
            if extent_crs != QgsCoordinateReferenceSystem('EPSG:4326'):
                transform = QgsCoordinateTransform(
                    extent_crs,
                    QgsCoordinateReferenceSystem('EPSG:4326'),
                    context.project()
                )
                extent = transform.transformBoundingBox(extent)
            
            # Convert to bbox list
            bbox = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
            
            feedback.pushInfo(f"Processing area: {bbox}")
            
            # Get selected collections
            collection_indices = self.parameterAsEnums(parameters, self.COLLECTIONS, context)
            available_collections = ['LAZ', 'MDS-2m', 'MDS-50cm', 'MDT-2m', 'MDT-50cm']
            
            if collection_indices:
                selected_collections = [available_collections[i] for i in collection_indices]
                feedback.pushInfo(f"Selected collections: {', '.join(selected_collections)}")
            else:
                # If no collections selected, download all
                selected_collections = available_collections
                feedback.pushInfo(f"No collections selected, downloading all: {', '.join(available_collections)}")
            
            # Divide bounding box
            small_bboxes = self.divide_bbox(bbox, max_area)
            feedback.pushInfo(f"Divided area into {len(small_bboxes)} smaller areas")
            
            # Create boundary layer if requested
            if create_boundary and boundary_output:
                boundary_result = self.create_boundary_layer(small_bboxes, boundary_output, context, feedback)
                if boundary_result:
                    feedback.pushInfo("Created boundary layer successfully")
                else:
                    feedback.reportError("Failed to create boundary layer")
            
            # Search and download
            all_urls_per_collection = {}
            total_steps = len(small_bboxes)
            
            for i, small_bbox in enumerate(small_bboxes):
                if feedback.isCanceled():
                    break
                
                feedback.setProgress(int(50 * i / total_steps))
                feedback.pushInfo(f"Searching area {i+1}/{total_steps}: {small_bbox}")
                
                # Search STAC API
                stac_response = self.search_stac_api(
                    small_bbox, 
                    collections=selected_collections,
                    delay=delay
                )
                
                # Collect URLs
                urls_per_collection = self.collect_urls_per_collection(stac_response)
                
                # Merge results
                for collection, url_list in urls_per_collection.items():
                    if collection not in all_urls_per_collection:
                        all_urls_per_collection[collection] = []
                    all_urls_per_collection[collection].extend(url_list)
                
                feedback.pushInfo(f"Found {sum(len(urls) for urls in urls_per_collection.values())} items")
            
            # Download files
            total_files = sum(len(urls) for urls in all_urls_per_collection.values())
            feedback.pushInfo(f"Total files to download: {total_files}")
            
            downloaded = 0
            skipped = 0
            
            for collection, url_list in all_urls_per_collection.items():
                if feedback.isCanceled():
                    break
                
                feedback.pushInfo(f"Downloading collection: {collection}")
                collection_dir = os.path.join(output_folder, collection)
                
                for url, item_id, extension in url_list:
                    if feedback.isCanceled():
                        break
                    
                    if self.download_file(url, item_id, extension, collection_dir, delay, feedback):
                        downloaded += 1
                    else:
                        skipped += 1
                    
                    # Update progress
                    progress = 50 + int(50 * (downloaded + skipped) / total_files)
                    feedback.setProgress(progress)
            
            feedback.pushInfo(f"Download complete: {downloaded} files downloaded, {skipped} files skipped")
            
            results = {
                self.OUTPUT_FOLDER: output_folder
            }
            
            if create_boundary and boundary_output:
                results[self.BOUNDARY_OUTPUT] = boundary_output
            
            return results
            
        except Exception as e:
            raise QgsProcessingException(f"Error in processing: {str(e)}")


# Provider class for the algorithm
class DgtCddProvider:
    def __init__(self):
        self.algorithms = [DgtCddDownloaderAlgorithm]
    
    def load(self):
        return True
    
    def unload(self):
        return True
    
    def loadAlgorithms(self):
        return self.algorithms