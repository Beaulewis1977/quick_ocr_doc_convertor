#!/usr/bin/env python3
"""
Command Line Interface for Universal Document Converter
Designed and built by Beau Lewis (blewisxx@gmail.com)
"""

import argparse
import sys
import os
from pathlib import Path
import json
import time
import logging
from typing import List, Optional

# Import the converter classes (conditional import)
CONVERTER_AVAILABLE = False
try:
    from universal_document_converter import (
        UniversalConverter, FormatDetector, ConverterLogger, ConfigManager,
        DocumentConverterError, UnsupportedFormatError, FileProcessingError
    )
    CONVERTER_AVAILABLE = True
except ImportError:
    # Defer error until actual conversion is attempted
    UniversalConverter = None
    FormatDetector = None
    ConverterLogger = None
    ConfigManager = None
    DocumentConverterError = Exception
    UnsupportedFormatError = Exception
    FileProcessingError = Exception

# Import OCR functionality
try:
    from ocr_engine.ocr_integration import OCRIntegration
    from ocr_engine.format_detector import OCRFormatDetector
    from ocr_engine.config_manager import ConfigManager as OCRConfigManager
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    OCRIntegration = None
    OCRFormatDetector = None
    OCRConfigManager = None


class DocumentConverterCLI:
    """Command Line Interface for the Universal Document Converter"""

    def __init__(self, config_file: Optional[str] = None):
        # Initialize configuration manager
        self.config_manager = ConfigManager(config_file)

        # Initialize converter with config
        self.converter = UniversalConverter("CLI", config_manager=self.config_manager)

        # Initialize logger with config
        log_level = self.config_manager.get('logging', 'log_level', 'INFO')
        self.logger_instance = ConverterLogger("CLI", log_level)
        self.logger = self.logger_instance.get_logger()
        
        # Initialize OCR integration if available
        if OCR_AVAILABLE:
            try:
                self.ocr_config_manager = OCRConfigManager()
                self.ocr_integration = OCRIntegration(logger=self.logger, config_manager=self.ocr_config_manager)
                self.format_detector = OCRFormatDetector()
                self.logger.info("OCR functionality initialized")
            except Exception as e:
                self.logger.warning(f"OCR initialization failed: {e}")
                self.ocr_integration = None
                self.format_detector = None
        else:
            self.ocr_integration = None
            self.format_detector = None
        
    def create_parser(self) -> argparse.ArgumentParser:
        """Create and configure the argument parser"""
        parser = argparse.ArgumentParser(
            description="Quick Document Convertor - Convert documents between multiple formats",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s file.docx -o output.md                    # Convert single file
  %(prog)s *.txt -o output_dir/ -f markdown          # Convert multiple files
  %(prog)s input_dir/ -o output_dir/ --recursive     # Convert directory recursively
  %(prog)s file.pdf -f auto -t html --workers 8      # Auto-detect input, use 8 threads
  %(prog)s image.jpg --ocr -o output.txt             # OCR image to text
  %(prog)s scan.pdf --ocr --ocr-backend tesseract    # OCR PDF with Tesseract
  %(prog)s *.png --ocr --ocr-language fra -o text/   # OCR images in French
  %(prog)s --list-formats                            # Show supported formats
  %(prog)s --batch config.json                       # Batch conversion from config file

Supported Input Formats:  DOCX, PDF, TXT, HTML, RTF, Images (with --ocr)
Supported Output Formats: Markdown, TXT, HTML, RTF
            """
        )
        
        # Input/Output arguments
        parser.add_argument('input', nargs='*', 
                          help='Input file(s) or directory to convert')
        parser.add_argument('-o', '--output', required=False,
                          help='Output file or directory')
        
        # Format arguments
        parser.add_argument('-f', '--from-format', default='auto',
                          choices=['auto'] + list(FormatDetector.SUPPORTED_INPUT_FORMATS.keys()),
                          help='Input format (default: auto-detect)')
        parser.add_argument('-t', '--to-format', default='markdown',
                          choices=list(FormatDetector.SUPPORTED_OUTPUT_FORMATS.keys()),
                          help='Output format (default: markdown)')
        
        # Processing options
        parser.add_argument('--recursive', '-r', action='store_true',
                          help='Process directories recursively')
        parser.add_argument('--preserve-structure', action='store_true', default=True,
                          help='Preserve directory structure in output (default: True)')
        parser.add_argument('--overwrite', action='store_true',
                          help='Overwrite existing output files')
        parser.add_argument('--workers', type=int, default=None,
                          help='Number of worker threads (default: auto)')
        
        # OCR options
        parser.add_argument('--ocr', action='store_true',
                          help='Enable OCR processing for image files and PDFs')
        parser.add_argument('--ocr-backend', choices=['auto', 'tesseract', 'easyocr', 'google_vision'],
                          default='auto', help='OCR backend to use (default: auto)')
        parser.add_argument('--ocr-language', default='eng',
                          help='OCR language code (default: eng)')
        parser.add_argument('--ocr-preprocess', action='store_true', default=True,
                          help='Enable OCR preprocessing (default: True)')
        
        # Caching and performance
        parser.add_argument('--no-cache', action='store_true',
                          help='Disable caching for this conversion')
        parser.add_argument('--clear-cache', action='store_true',
                          help='Clear the conversion cache and exit')
        
        # Batch processing
        parser.add_argument('--batch', metavar='CONFIG_FILE',
                          help='Batch conversion using JSON configuration file')
        
        # Information commands
        parser.add_argument('--list-formats', action='store_true',
                          help='List all supported input and output formats')
        parser.add_argument('--version', action='version', version='Quick Document Convertor 3.1.0')
        
        # Logging and output
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Enable verbose logging')
        parser.add_argument('--quiet', '-q', action='store_true',
                          help='Suppress all output except errors')
        parser.add_argument('--log-file', metavar='FILE',
                          help='Write logs to specified file')

        # Configuration management
        parser.add_argument('--config', metavar='CONFIG_FILE',
                          help='Use specified configuration file')
        parser.add_argument('--save-config', metavar='CONFIG_FILE',
                          help='Save current settings to configuration file')
        parser.add_argument('--show-config', action='store_true',
                          help='Show current configuration and exit')
        parser.add_argument('--reset-config', action='store_true',
                          help='Reset configuration to defaults')

        # Profile management
        parser.add_argument('--profile', metavar='PROFILE_NAME',
                          help='Use named configuration profile')
        parser.add_argument('--list-profiles', action='store_true',
                          help='List available configuration profiles')

        return parser
    
    def list_formats(self):
        """Display supported formats"""
        print("Quick Document Convertor - Supported Formats\n")
        
        print("INPUT FORMATS:")
        for key, info in FormatDetector.SUPPORTED_INPUT_FORMATS.items():
            extensions = ', '.join(info['extensions'])
            print(f"  {key.upper():8} - {info['name']} ({extensions})")
        
        print("\nOUTPUT FORMATS:")
        for key, info in FormatDetector.SUPPORTED_OUTPUT_FORMATS.items():
            extension = info['extension']
            print(f"  {key.upper():8} - {info['name']} ({extension})")
        
        print("\nUse 'auto' for automatic input format detection")

    def show_config(self):
        """Display current configuration"""
        print("Quick Document Convertor - Current Configuration\n")

        # General settings
        print("GENERAL SETTINGS:")
        general = self.config_manager.get_section('general')
        for key, value in general.items():
            print(f"  {key}: {value}")

        # Performance settings
        print("\nPERFORMANCE SETTINGS:")
        performance = self.config_manager.get_section('performance')
        for key, value in performance.items():
            print(f"  {key}: {value}")

        # Logging settings
        print("\nLOGGING SETTINGS:")
        logging_config = self.config_manager.get_section('logging')
        for key, value in logging_config.items():
            print(f"  {key}: {value}")

        print(f"\nConfiguration file: {self.config_manager.config_file}")

    def save_config(self, config_file: str):
        """Save current configuration to file"""
        try:
            if self.config_manager.export_config(config_file):
                print(f"Configuration saved to: {config_file}")
                return True
            else:
                print(f"Error: Failed to save configuration to {config_file}")
                return False
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

    def reset_config(self):
        """Reset configuration to defaults"""
        try:
            self.config_manager.reset_to_defaults()
            self.config_manager.save_config()
            print("Configuration reset to defaults")
            return True
        except Exception as e:
            print(f"Error resetting configuration: {e}")
            return False

    def list_profiles(self):
        """List available configuration profiles"""
        config_dir = self.config_manager.config_dir
        profiles = []

        if config_dir.exists():
            for file in config_dir.glob("*.json"):
                if file.name != "config.json":  # Skip default config
                    profile_name = file.stem
                    profiles.append(profile_name)

        if profiles:
            print("Available configuration profiles:")
            for profile in sorted(profiles):
                print(f"  {profile}")
        else:
            print("No configuration profiles found")

        print(f"\nProfiles directory: {config_dir}")
        print("Create profiles by saving configurations with --save-config")

    def load_profile(self, profile_name: str):
        """Load a configuration profile"""
        profile_file = self.config_manager.config_dir / f"{profile_name}.json"

        if not profile_file.exists():
            print(f"Error: Profile '{profile_name}' not found")
            print(f"Expected file: {profile_file}")
            return False

        try:
            if self.config_manager.import_config(str(profile_file)):
                print(f"Loaded profile: {profile_name}")
                return True
            else:
                print(f"Error: Failed to load profile '{profile_name}'")
                return False
        except Exception as e:
            print(f"Error loading profile: {e}")
            return False

    def validate_args(self, args) -> bool:
        """Validate command line arguments"""
        # Check for information commands first
        if args.list_formats or args.clear_cache or args.show_config or args.list_profiles or args.reset_config:
            return True

        # Check for configuration commands
        if args.save_config:
            return True

        # Check for batch mode
        if args.batch:
            if not Path(args.batch).exists():
                print(f"Error: Batch configuration file not found: {args.batch}")
                return False
            return True
        
        # Regular mode validation
        if not args.input:
            print("Error: No input files specified")
            return False
        
        if not args.output:
            print("Error: Output path required (use -o/--output)")
            return False
        
        # Validate input files exist
        for input_path in args.input:
            path = Path(input_path)
            if not path.exists():
                print(f"Error: Input path does not exist: {input_path}")
                return False
        
        return True
    
    def setup_logging(self, args):
        """Configure logging based on arguments"""
        # Determine log level
        if args.quiet:
            log_level = 'ERROR'
        elif args.verbose:
            log_level = 'DEBUG'
        else:
            log_level = self.config_manager.get('logging', 'log_level', 'INFO')

        # Update logger level
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(numeric_level)

        # Update all handlers
        for handler in self.logger.handlers:
            handler.setLevel(numeric_level)
    
    def convert_single_file(self, input_path: Path, output_path: Path, 
                          from_format: str, to_format: str, enable_ocr: bool = False,
                          ocr_backend: str = 'auto', ocr_language: str = 'eng') -> bool:
        """Convert a single file with optional OCR support"""
        try:
            # Check if OCR should be used for this file
            if enable_ocr and self.ocr_integration and self.format_detector:
                file_extension = input_path.suffix.lower()
                image_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif', '.webp']
                
                if file_extension in image_extensions or file_extension == '.pdf':
                    self.logger.info(f"Processing {input_path} with OCR")
                    
                    # Configure OCR settings
                    if ocr_backend != 'auto':
                        self.ocr_config_manager.set_default_backend(ocr_backend)
                    if ocr_language != 'eng':
                        self.ocr_config_manager.set_language(ocr_language)
                    
                    try:
                        # Perform OCR
                        ocr_result = self.ocr_integration.process_file(str(input_path))
                        
                        if ocr_result and 'text' in ocr_result:
                            # Write OCR result to output file
                            with open(output_path, 'w', encoding='utf-8') as f:
                                f.write(ocr_result['text'])
                            self.logger.info(f"OCR completed for {input_path}")
                            return True
                        else:
                            self.logger.warning(f"OCR failed for {input_path}, falling back to standard conversion")
                    except Exception as e:
                        self.logger.warning(f"OCR error for {input_path}: {e}, falling back to standard conversion")
            
            # Standard conversion (fallback or non-OCR files)
            self.converter.convert_file(input_path, output_path, from_format, to_format)
            return True
        except (UnsupportedFormatError, FileProcessingError, DocumentConverterError) as e:
            self.logger.error(f"Failed to convert {input_path}: {e}")
            return False
    
    def get_output_path(self, input_path: Path, output_base: Path, 
                       to_format: str, preserve_structure: bool, 
                       base_input_dir: Optional[Path] = None) -> Path:
        """Generate output path for a given input file"""
        output_ext = FormatDetector.SUPPORTED_OUTPUT_FORMATS[to_format]['extension']
        
        if output_base.is_file() or (not output_base.exists() and not output_base.suffix):
            # Output is a specific file or directory
            if preserve_structure and base_input_dir and input_path != base_input_dir:
                # Preserve directory structure
                rel_path = input_path.relative_to(base_input_dir)
                return output_base / rel_path.with_suffix(output_ext)
            else:
                # Single file or flat structure
                if output_base.suffix:
                    return output_base  # Specific output file
                else:
                    return output_base / f"{input_path.stem}{output_ext}"
        else:
            # Output directory
            return output_base / f"{input_path.stem}{output_ext}"
    
    def collect_input_files(self, input_paths: List[str], recursive: bool) -> List[Path]:
        """Collect all input files to process"""
        files = []
        
        for input_path in input_paths:
            path = Path(input_path)
            
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                if recursive:
                    # Find all supported files recursively
                    for fmt_info in FormatDetector.SUPPORTED_INPUT_FORMATS.values():
                        for ext in fmt_info['extensions']:
                            files.extend(path.rglob(f"*{ext}"))
                else:
                    # Find supported files in directory only
                    for fmt_info in FormatDetector.SUPPORTED_INPUT_FORMATS.values():
                        for ext in fmt_info['extensions']:
                            files.extend(path.glob(f"*{ext}"))
            else:
                # Handle glob patterns
                from glob import glob
                matched_files = glob(str(path))
                files.extend([Path(f) for f in matched_files if Path(f).is_file()])
        
        # Remove duplicates and filter out temporary files
        unique_files = list(set(files))
        return [f for f in unique_files if not f.name.startswith('~$')]
    
    def run(self, args=None) -> int:
        """Main CLI execution method"""
        parser = self.create_parser()
        args = parser.parse_args(args)
        
        # Validate arguments
        if not self.validate_args(args):
            return 1
        
        # Setup logging
        self.setup_logging(args)
        
        # Handle information commands
        if args.list_formats:
            self.list_formats()
            return 0

        if args.clear_cache:
            # Clear cache (implementation would go here)
            print("Cache cleared successfully")
            return 0

        # Handle configuration commands
        if args.show_config:
            self.show_config()
            return 0

        if args.list_profiles:
            self.list_profiles()
            return 0

        if args.reset_config:
            return 0 if self.reset_config() else 1

        if args.save_config:
            return 0 if self.save_config(args.save_config) else 1

        # Handle profile loading
        if args.profile:
            if not self.load_profile(args.profile):
                return 1

        # Handle batch mode
        if args.batch:
            return self.run_batch_conversion(args.batch)
        
        # Regular conversion mode
        return self.run_conversion(args)

    def run_conversion(self, args) -> int:
        """Run regular file conversion"""
        try:
            # Collect input files
            input_files = self.collect_input_files(args.input, args.recursive)

            if not input_files:
                print("No supported input files found")
                return 1

            output_path = Path(args.output)

            # Determine base input directory for structure preservation
            base_input_dir = None
            if args.preserve_structure and len(input_files) > 1:
                try:
                    base_input_dir = Path(os.path.commonpath([str(f.parent) for f in input_files]))
                except ValueError:
                    base_input_dir = None

            print(f"Converting {len(input_files)} files...")
            print(f"From: {args.from_format} -> To: {args.to_format}")

            # Progress tracking
            successful = 0
            failed = 0
            start_time = time.time()

            # Use batch conversion for multiple files
            if len(input_files) > 1:
                def progress_callback(completed, total, result):
                    nonlocal successful, failed
                    if result['status'] == 'success':
                        successful += 1
                        if not args.quiet:
                            print(f"SUCCESS: {result['file']} -> {result['output']}")
                    elif result['status'] == 'error':
                        failed += 1
                        print(f"ERROR: {result['file']}: {result['error']}")
                    elif result['status'] == 'skipped':
                        if not args.quiet:
                            print(f"SKIPPED (exists): {result['file']}")

                # Create output directory
                if not output_path.exists():
                    output_path.mkdir(parents=True, exist_ok=True)

                # Run batch conversion
                results = self.converter.convert_batch(
                    file_list=input_files,
                    output_dir=output_path,
                    input_format=args.from_format,
                    output_format=args.to_format,
                    max_workers=args.workers,
                    progress_callback=progress_callback,
                    preserve_structure=args.preserve_structure,
                    overwrite_existing=args.overwrite,
                    base_dir=base_input_dir
                )

                successful = results['successful']
                failed = results['failed']

            else:
                # Single file conversion
                input_file = input_files[0]
                output_file = self.get_output_path(
                    input_file, output_path, args.to_format,
                    args.preserve_structure, base_input_dir
                )

                # Create output directory
                output_file.parent.mkdir(parents=True, exist_ok=True)

                if self.convert_single_file(input_file, output_file, args.from_format, args.to_format,
                                           enable_ocr=args.ocr, ocr_backend=args.ocr_backend, 
                                           ocr_language=args.ocr_language):
                    successful = 1
                    if not args.quiet:
                        print(f"SUCCESS: {input_file.name} -> {output_file.name}")
                else:
                    failed = 1

            # Final results
            duration = time.time() - start_time

            if not args.quiet:
                print(f"\nConversion complete in {duration:.2f} seconds!")
                print(f"Successful: {successful}")
                if failed > 0:
                    print(f"Failed: {failed}")
                print(f"Output saved to: {output_path}")

            return 0 if failed == 0 else 1

        except Exception as e:
            self.logger.error(f"Conversion failed: {e}")
            return 1

    def run_batch_conversion(self, config_file: str) -> int:
        """Run batch conversion from configuration file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            # Validate configuration
            if 'conversions' not in config:
                print("Error: Configuration file must contain 'conversions' array")
                return 1

            total_successful = 0
            total_failed = 0

            for i, conversion in enumerate(config['conversions']):
                print(f"\n📋 Running conversion {i+1}/{len(config['conversions'])}")

                # Create args object from configuration
                class Args:
                    pass

                args = Args()
                args.input = conversion.get('input', [])
                args.output = conversion.get('output')
                args.from_format = conversion.get('from_format', 'auto')
                args.to_format = conversion.get('to_format', 'markdown')
                args.recursive = conversion.get('recursive', False)
                args.preserve_structure = conversion.get('preserve_structure', True)
                args.overwrite = conversion.get('overwrite', False)
                args.workers = conversion.get('workers')
                args.quiet = False

                # Validate conversion config
                if not args.input or not args.output:
                    print(f"ERROR: Conversion {i+1}: Missing input or output")
                    total_failed += 1
                    continue

                # Run conversion
                result = self.run_conversion(args)
                if result == 0:
                    total_successful += 1
                else:
                    total_failed += 1

            print(f"\nBatch conversion complete!")
            print(f"Successful conversions: {total_successful}")
            if total_failed > 0:
                print(f"Failed conversions: {total_failed}")

            return 0 if total_failed == 0 else 1

        except Exception as e:
            print(f"Error running batch conversion: {e}")
            return 1


def main():
    """Entry point for CLI"""
    # Parse args to check for --config first
    import argparse
    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument('--config', metavar='CONFIG_FILE')
    temp_args, _ = temp_parser.parse_known_args()

    # Initialize CLI with config file if specified
    cli = DocumentConverterCLI(temp_args.config)
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())
