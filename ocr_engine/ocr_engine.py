"""
OCR Engine for Quick Document Convertor

Provides comprehensive OCR functionality with support for multiple backends,
image preprocessing, and batch processing capabilities.

Author: Beau Lewis (blewisxx@gmail.com)
"""

import os
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
import json
import hashlib
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import numpy as np

try:
    import pytesseract
    import cv2
    from PIL import Image, ImageEnhance, ImageFilter
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    from .google_vision_backend import GoogleVisionBackend
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False

from .image_processor import ImageProcessor
from .format_detector import OCRFormatDetector

import tesseract_config  # Auto-configure Tesseract
class OCREngineError(Exception):
    """Base exception for OCR engine errors"""
    pass

class OCRBackendError(OCREngineError):
    """Raised when OCR backend is not available"""
    pass

class ImageProcessingError(OCREngineError):
    """Raised when image processing fails"""
    pass

class OCREngine:
    """
    Main OCR engine for image-to-text conversion
    
    Features:
    - Multiple OCR backend support (Tesseract, EasyOCR)
    - Image preprocessing and enhancement
    - Batch processing with progress tracking
    - Caching for improved performance
    - Configurable quality settings
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize OCR engine
        
        Args:
            config: Configuration dictionary for OCR settings
            logger: Optional logger instance
        """
        self.config = config or {}
        self.logger = logger or logging.getLogger("OCREngine")
        self.image_processor = ImageProcessor(self.logger)
        self.format_detector = OCRFormatDetector()
        
        # Cache directory for OCR results
        self.cache_dir = Path.home() / ".quick_document_convertor" / "ocr_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread-local storage for OCR readers
        self._thread_local = threading.local()
        
        # Initialize OCR backends (after locks are created)
        self._initialize_backends()
        
        # Configuration defaults
        self.default_config = {
            'backend': 'auto',
            'languages': ['en'],
            'use_cache': True,
            'cache_ttl': 86400,  # 24 hours
            'preprocessing': {
                'enhance_contrast': True,
                'denoise': True,
                'resize_max': 2048,
                'threshold_method': 'adaptive'
            },
            'tesseract_config': '--oem 3 --psm 6',
            'confidence_threshold': 30
        }
        
        # Merge user config with defaults
        self.config = {**self.default_config, **self.config}

    def _initialize_backends(self):
        """Initialize available OCR backends"""
        self.backends = {}
        
        # Tesseract OCR
        if TESSERACT_AVAILABLE:
            try:
                # Test if tesseract is available
                pytesseract.get_tesseract_version()
                self.backends['tesseract'] = {
                    'name': 'Tesseract OCR',
                    'priority': 1,
                    'available': True
                }
                self.logger.info("Tesseract OCR backend initialized")
            except Exception as e:
                self.logger.warning(f"Tesseract not available: {e}")
                self.backends['tesseract'] = {
                    'name': 'Tesseract OCR',
                    'priority': 1,
                    'available': False
                }
        
        # EasyOCR
        if EASYOCR_AVAILABLE:
            try:
                self.backends['easyocr'] = {
                    'name': 'EasyOCR',
                    'priority': 2,
                    'available': True,
                    'reader': None  # Lazy initialization
                }
                self.logger.info("EasyOCR backend available")
            except Exception as e:
                self.logger.warning(f"EasyOCR initialization failed: {e}")
                self.backends['easyocr'] = {
                    'name': 'EasyOCR',
                    'priority': 2,
                    'available': False
                }
        
        # Google Vision API
        if GOOGLE_VISION_AVAILABLE:
            try:
                # Initialize Google Vision backend with config
                google_config = self.config.get('google_vision', {})
                self.google_vision_backend = GoogleVisionBackend(google_config, self.logger)
                
                self.backends['google_vision'] = {
                    'name': 'Google Vision API',
                    'priority': 0,  # Highest priority when available
                    'available': self.google_vision_backend.is_available(),
                    'backend_instance': self.google_vision_backend
                }
                
                if self.google_vision_backend.is_available():
                    self.logger.info("Google Vision API backend initialized successfully")
                else:
                    self.logger.warning("Google Vision API backend not available (credentials missing)")
                    
            except Exception as e:
                self.logger.warning(f"Google Vision API initialization failed: {e}")
                self.backends['google_vision'] = {
                    'name': 'Google Vision API',
                    'priority': 0,
                    'available': False
                }

    def is_tesseract_available(self) -> bool:
        """Check if Tesseract OCR is available"""
        return 'tesseract' in self.backends and self.backends['tesseract']['available']

    def is_easyocr_available(self) -> bool:
        """Check if EasyOCR is available"""
        return 'easyocr' in self.backends and self.backends['easyocr']['available']
    
    def is_google_vision_available(self) -> bool:
        """Check if Google Vision API is available"""
        return 'google_vision' in self.backends and self.backends['google_vision']['available']

    def is_available(self) -> bool:
        """Check if any OCR backend is available"""
        return len(self.get_available_backends()) > 0

    def get_available_backends(self) -> List[str]:
        """Get list of available OCR backends"""
        return [name for name, info in self.backends.items() if info['available']]

    def get_preferred_backend(self) -> str:
        """Get the preferred OCR backend based on availability and priority"""
        available = [(name, info['priority']) for name, info in self.backends.items() 
                    if info['available']]
        if not available:
            raise OCRBackendError("No OCR backends available")
        
        # Sort by priority (lower is better)
        available.sort(key=lambda x: x[1])
        return available[0][0]
    
    def get_active_backend_info(self, backend: str = None) -> Dict[str, Any]:
        """Get information about the active OCR backend"""
        if backend is None:
            backend = self.get_preferred_backend()
        
        if backend not in self.backends:
            return {'name': 'Unknown', 'available': False, 'status': 'Not configured'}
        
        backend_info = self.backends[backend]
        status = 'Ready' if backend_info['available'] else 'Not Available'
        
        # Special handling for Google Vision
        if backend == 'google_vision' and hasattr(self, 'google_vision_backend'):
            if not self.google_vision_backend.is_available():
                status = 'API Key Required'
        
        return {
            'name': backend_info['name'],
            'backend_id': backend,
            'available': backend_info['available'],
            'status': status,
            'priority': backend_info['priority']
        }

    def _get_easyocr_reader(self, languages: List[str] = None):
        """Get thread-local EasyOCR reader"""
        if not hasattr(self._thread_local, 'easyocr_reader'):
            if languages is None:
                languages = self.config['languages']
            self._thread_local.easyocr_reader = easyocr.Reader(
                languages, 
                gpu=False,  # Disable GPU for compatibility
                verbose=False
            )
        return self._thread_local.easyocr_reader

    def _get_cache_key(self, image_path: Path, options: Dict[str, Any]) -> str:
        """Generate cache key for OCR result"""
        # Create hash from file content and options
        hasher = hashlib.md5()
        
        # Add file content hash
        if image_path.exists():
            with open(image_path, 'rb') as f:
                hasher.update(f.read(1024))  # First 1KB for speed
        
        # Add options hash
        options_str = json.dumps(options, sort_keys=True)
        hasher.update(options_str.encode())
        
        return hasher.hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[str]:
        """Load OCR result from cache"""
        cache_file = self.cache_dir / f"{cache_key}.txt"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.logger.warning(f"Failed to load from cache: {e}")
        return None

    def _save_to_cache(self, cache_key: str, text: str) -> None:
        """Save OCR result to cache"""
        cache_file = self.cache_dir / f"{cache_key}.txt"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            self.logger.warning(f"Failed to save to cache: {e}")

    def extract_text(self, image_path: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract text from an image using OCR
        
        Args:
            image_path: Path to the image file
            options: OCR options (backend, languages, etc.)
            
        Returns:
            Dictionary with extracted text and metadata
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        if not self.format_detector.is_ocr_supported(str(image_path)):
            raise ValueError(f"Unsupported image format: {image_path.suffix}")
        
        # Merge options with config
        ocr_options = {**self.config, **(options or {})}
        
        # Check cache first
        if ocr_options.get('use_cache', True):
            cache_key = self._get_cache_key(image_path, ocr_options)
            cached_text = self._load_from_cache(cache_key)
            if cached_text:
                return {
                    'text': cached_text,
                    'source': 'cache',
                    'confidence': None,
                    'word_count': len(cached_text.split()),
                    'character_count': len(cached_text)
                }
        
        # Select backend
        backend = ocr_options.get('backend', 'auto')
        if backend == 'auto':
            backend = self.get_preferred_backend()
        
        # Preprocess image
        try:
            processed_image = self.image_processor.preprocess_image(
                str(image_path), 
                ocr_options.get('preprocessing', {})
            )
        except Exception as e:
            raise ImageProcessingError(f"Image preprocessing failed: {e}")
        
        # Extract text based on backend with fallback support
        start_time = time.time()
        result = None
        
        if backend == 'google_vision' and self.is_google_vision_available():
            try:
                result = self._extract_with_google_vision(str(image_path), ocr_options)
            except Exception as e:
                self.logger.warning(f"Google Vision API failed: {e}")
                # Fallback to Tesseract if available
                if self.is_tesseract_available():
                    self.logger.info("Falling back to Tesseract OCR")
                    try:
                        result = self._extract_with_tesseract(processed_image, ocr_options)
                        result['fallback'] = True
                        result['fallback_reason'] = f"Google Vision failed: {str(e)}"
                    except Exception as fallback_error:
                        self.logger.error(f"Tesseract fallback also failed: {fallback_error}")
                        raise OCRBackendError(f"Both Google Vision and Tesseract failed. Google Vision: {e}, Tesseract: {fallback_error}")
                elif self.is_easyocr_available():
                    self.logger.info("Falling back to EasyOCR")
                    try:
                        result = self._extract_with_easyocr(processed_image, ocr_options)
                        result['fallback'] = True
                        result['fallback_reason'] = f"Google Vision failed: {str(e)}"
                    except Exception as fallback_error:
                        self.logger.error(f"EasyOCR fallback also failed: {fallback_error}")
                        raise OCRBackendError(f"Both Google Vision and EasyOCR failed. Google Vision: {e}, EasyOCR: {fallback_error}")
                else:
                    raise OCRBackendError(f"Google Vision failed and no fallback backends available: {e}")
        
        elif backend == 'tesseract' and self.is_tesseract_available():
            result = self._extract_with_tesseract(processed_image, ocr_options)
        elif backend == 'easyocr' and self.is_easyocr_available():
            result = self._extract_with_easyocr(processed_image, ocr_options)
        else:
            raise OCRBackendError(f"Selected backend '{backend}' is not available")
        
        if result is None:
            raise OCRBackendError("OCR extraction failed - no result generated")
        
        duration = time.time() - start_time
        
        # Add metadata
        result.update({
            'backend': backend,
            'duration': duration,
            'image_path': str(image_path),
            'word_count': len(result['text'].split()),
            'character_count': len(result['text'])
        })
        
        # Cache result
        if ocr_options.get('use_cache', True):
            cache_key = self._get_cache_key(image_path, ocr_options)
            self._save_to_cache(cache_key, result['text'])
        
        return result

    def _extract_with_tesseract(self, image: np.ndarray, options: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text using Tesseract OCR"""
        try:
            # Convert numpy array to PIL Image
            if len(image.shape) == 3:
                pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            else:
                pil_image = Image.fromarray(image)
            
            # Extract text
            text = pytesseract.image_to_string(
                pil_image,
                lang='+'.join(options.get('languages', ['en'])),
                config=options.get('tesseract_config', '--oem 3 --psm 6')
            )
            
            # Get confidence data
            try:
                data = pytesseract.image_to_data(
                    pil_image,
                    lang='+'.join(options.get('languages', ['en'])),
                    output_type=pytesseract.Output.DICT
                )
                confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            except:
                avg_confidence = None
            
            return {
                'text': text.strip(),
                'confidence': avg_confidence,
                'source': 'tesseract'
            }
            
        except Exception as e:
            raise OCRBackendError(f"Tesseract OCR failed: {e}")

    def _extract_with_easyocr(self, image: np.ndarray, options: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text using EasyOCR"""
        try:
            reader = self._get_easyocr_reader(options.get('languages', ['en']))
            
            # Convert BGR to RGB if needed
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            # Extract text
            results = reader.readtext(image_rgb)
            
            # Combine text and calculate confidence
            text_parts = []
            confidences = []
            
            for (bbox, text, confidence) in results:
                if confidence >= options.get('confidence_threshold', 30):
                    text_parts.append(text)
                    confidences.append(confidence)
            
            combined_text = ' '.join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                'text': combined_text.strip(),
                'confidence': avg_confidence,
                'source': 'easyocr'
            }
            
        except Exception as e:
            raise OCRBackendError(f"EasyOCR failed: {e}")

    def _extract_with_google_vision(self, image_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Extract text using Google Vision API"""
        try:
            if not hasattr(self, 'google_vision_backend'):
                raise OCRBackendError("Google Vision backend not initialized")
            
            # Use the Google Vision backend to extract text
            result = self.google_vision_backend.extract_text(image_path, options)
            return result
            
        except Exception as e:
            raise OCRBackendError(f"Google Vision API failed: {e}")

    def extract_text_from_multiple_images(
        self, 
        image_paths: List[str], 
        options: Optional[Dict[str, Any]] = None,
        max_workers: int = 2,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract text from multiple images using parallel processing
        
        Args:
            image_paths: List of image file paths
            options: OCR options
            max_workers: Maximum number of concurrent workers
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of extraction results
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self.extract_text, path, options): path
                for path in image_paths
            }
            
            # Process completed tasks
            for i, future in enumerate(as_completed(future_to_path)):
                path = future_to_path[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(i + 1, len(image_paths))
                        
                except Exception as e:
                    self.logger.error(f"Failed to process {path}: {e}")
                    results.append({
                        'image_path': path,
                        'text': '',
                        'error': str(e),
                        'success': False
                    })
        
        return results

    def get_image_info(self, image_path: str) -> Dict[str, Any]:
        """Get information about an image file"""
        try:
            return self.image_processor.get_image_info(image_path)
        except Exception as e:
            return {'error': str(e)}

    def clear_cache(self) -> bool:
        """Clear the OCR cache"""
        try:
            for cache_file in self.cache_dir.glob("*.txt"):
                cache_file.unlink()
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False

    def get_cache_size(self) -> int:
        """Get the total size of the cache in bytes"""
        try:
            return sum(f.stat().st_size for f in self.cache_dir.glob("*.txt") if f.is_file())
        except:
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            cache_files = list(self.cache_dir.glob("*.txt"))
            total_size = sum(f.stat().st_size for f in cache_files)
            
            return {
                'file_count': len(cache_files),
                'total_size': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            return {'error': str(e)}

    def save_result(self, result: Dict[str, Any], output_path: str, output_format: str = 'txt') -> bool:
        """
        Save OCR result to file
        
        Args:
            result: OCR result dictionary
            output_path: Output file path
            output_format: Output format (txt, json, markdown)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            text = result.get('text', '')
            
            if output_format.lower() == 'json':
                # Save as JSON with metadata
                output_data = {
                    'text': text,
                    'confidence': result.get('confidence'),
                    'backend': result.get('backend'),
                    'duration': result.get('duration'),
                    'word_count': result.get('word_count', 0),
                    'character_count': result.get('character_count', 0),
                    'image_path': result.get('image_path')
                }
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
                    
            elif output_format.lower() == 'markdown':
                # Save as markdown with metadata
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"# OCR Result\n\n")
                    f.write(f"**Source:** {result.get('image_path', 'Unknown')}\n\n")
                    if result.get('confidence'):
                        f.write(f"**Confidence:** {result.get('confidence'):.1f}%\n\n")
                    if result.get('backend'):
                        f.write(f"**Backend:** {result.get('backend')}\n\n")
                    f.write(f"**Word Count:** {result.get('word_count', 0)}\n\n")
                    f.write(f"**Character Count:** {result.get('character_count', 0)}\n\n")
                    f.write("---\n\n")
                    f.write(text)
                    
            else:  # txt
                # Save as plain text
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(text)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save result: {e}")
            return False

    def extract_text_from_pdf(self, pdf_path: str, language: str = 'eng') -> str:
        """
        Extract text from PDF using OCR
        
        Args:
            pdf_path: Path to PDF file
            language: Language for OCR (default: eng)
            
        Returns:
            Extracted text string
        """
        try:
            # Import PDF processing libraries
            try:
                import fitz  # PyMuPDF
            except ImportError:
                self.logger.error("PyMuPDF not available for PDF processing")
                return ""
            
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                self.logger.error(f"PDF file not found: {pdf_path}")
                return ""
            
            # Open PDF and extract text
            doc = fitz.open(str(pdf_path))
            text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                
                # If page has no text or very little text, use OCR
                if not page_text.strip() or len(page_text.strip()) < 50:
                    # Convert page to image and OCR
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    
                    # Save temporary image
                    temp_image = pdf_path.parent / f"temp_page_{page_num}.png"
                    with open(temp_image, 'wb') as f:
                        f.write(img_data)
                    
                    # OCR the image
                    ocr_result = self.extract_text(str(temp_image), {'language': language})
                    ocr_text = ocr_result.get('text', '')
                    text += f"\n--- Page {page_num + 1} ---\n{ocr_text}\n"
                    
                    # Clean up
                    temp_image.unlink(missing_ok=True)
                else:
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            
            doc.close()
            return text.strip()
            
        except Exception as e:
            self.logger.error(f"PDF OCR extraction failed: {e}")
            return ""