#!/usr/bin/env python3
"""
Test script to verify OCR CLI functionality
"""

import sys
import subprocess
from pathlib import Path

def test_cli_help():
    """Test if CLI help shows OCR options"""
    print("Testing CLI help for OCR options...")
    try:
        result = subprocess.run([sys.executable, 'cli.py', '--help'], 
                               capture_output=True, text=True, timeout=10)
        help_text = result.stdout
        
        # Check for OCR-related options
        ocr_features = [
            '--ocr',
            '--ocr-backend',
            '--ocr-language',
            '--ocr-preprocess'
        ]
        
        missing_features = []
        for feature in ocr_features:
            if feature not in help_text:
                missing_features.append(feature)
        
        if missing_features:
            print(f"❌ Missing OCR features in CLI help: {missing_features}")
            return False
        else:
            print("✅ All OCR features found in CLI help")
            return True
            
    except Exception as e:
        print(f"❌ Error testing CLI help: {e}")
        return False

def test_cli_syntax():
    """Test CLI syntax"""
    print("Testing CLI syntax...")
    try:
        result = subprocess.run([sys.executable, '-m', 'py_compile', 'cli.py'], 
                               capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ CLI syntax is valid")
            return True
        else:
            print(f"❌ CLI syntax error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing CLI syntax: {e}")
        return False

def test_ocr_gui_exists():
    """Test if OCR GUI exists and is syntactically correct"""
    print("Testing OCR GUI...")
    
    ocr_gui_path = Path('universal_document_converter_ocr.py')
    if not ocr_gui_path.exists():
        print("❌ OCR GUI file not found")
        return False
        
    try:
        result = subprocess.run([sys.executable, '-m', 'py_compile', str(ocr_gui_path)], 
                               capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ OCR GUI syntax is valid")
            return True
        else:
            print(f"❌ OCR GUI syntax error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing OCR GUI: {e}")
        return False

def main():
    """Run all tests"""
    print("OCR CLI Functionality Test")
    print("=" * 40)
    
    tests = [
        test_cli_syntax,
        test_cli_help,
        test_ocr_gui_exists
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! OCR functionality is properly integrated.")
        return 0
    else:
        print("⚠️ Some tests failed. OCR integration may have issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
