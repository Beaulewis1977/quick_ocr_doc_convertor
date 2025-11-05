#!/usr/bin/env python3
"""
Legacy DLL Builder CLI - VB6/VFP9 Integration System
Separated from universal_document_converter.py for clean architecture

This CLI provides all DLL building, testing, and integration functionality
that was previously embedded in the main GUI application.

Usage:
    python cli.py build              # Build the DLL
    python cli.py status             # Check DLL status
    python cli.py test               # Run comprehensive tests
    python cli.py vb6 generate       # Generate VB6 integration module
    python cli.py vfp9 generate      # Generate VFP9 integration class
    python cli.py package            # Create distribution package
    python cli.py install           # Install DLL system-wide
"""

import argparse
import sys
import os
import logging
from pathlib import Path
from typing import Optional

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from commands.build import DLLBuilder
from commands.integration import VB6VFP9Integration
from commands.testing import DLLTester

class LegacyDLLBuilderCLI:
    """Main CLI for Legacy DLL Builder system"""
    
    def __init__(self, config=None):
        self.setup_logging()
        self.config = config or {}
        self.builder = DLLBuilder(self.logger, self.config)
        self.integration = VB6VFP9Integration(self.logger)
        self.tester = DLLTester(self.logger)
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def create_parser(self):
        """Create argument parser"""
        parser = argparse.ArgumentParser(
            description="Legacy DLL Builder CLI - VB6/VFP9 Integration System"
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Build commands
        build_parser = subparsers.add_parser('build', help='Build the DLL')
        build_parser.add_argument('--force', action='store_true', help='Force rebuild even if DLL exists')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Check DLL status')
        
        # Test commands
        test_parser = subparsers.add_parser('test', help='Test DLL functionality')
        test_subparsers = test_parser.add_subparsers(dest='test_command', help='Test commands')
        
        test_subparsers.add_parser('functions', help='Test DLL functions')
        test_subparsers.add_parser('all', help='Run comprehensive test suite')
        
        conv_parser = test_subparsers.add_parser('conversion', help='Test conversion with specific file')
        conv_parser.add_argument('--file', required=True, help='Test file path')
        
        perf_parser = test_subparsers.add_parser('performance', help='Performance test')
        perf_parser.add_argument('--file', required=True, help='Test file path')
        perf_parser.add_argument('--iterations', type=int, default=5, help='Number of test iterations')
        
        # VB6 commands
        vb6_parser = subparsers.add_parser('vb6', help='VB6 integration commands')
        vb6_subparsers = vb6_parser.add_subparsers(dest='vb6_command', help='VB6 commands')
        
        vb6_subparsers.add_parser('generate', help='Generate VB6 integration module')
        vb6_subparsers.add_parser('examples', help='Show VB6 integration examples')
        vb6_subparsers.add_parser('test', help='Show VB6 test code')
        
        # VFP9 commands
        vfp9_parser = subparsers.add_parser('vfp9', help='VFP9 integration commands')
        vfp9_subparsers = vfp9_parser.add_subparsers(dest='vfp9_command', help='VFP9 commands')
        
        vfp9_subparsers.add_parser('generate', help='Generate VFP9 integration class')
        vfp9_subparsers.add_parser('examples', help='Show VFP9 integration examples')
        vfp9_subparsers.add_parser('test', help='Show VFP9 test code')
        
        # Package and install commands
        subparsers.add_parser('package', help='Create distribution package')
        subparsers.add_parser('install', help='Install DLL system-wide')
        
        # Utility commands
        subparsers.add_parser('requirements', help='Show build requirements')
        subparsers.add_parser('open-source', help='Open DLL source directory')
        subparsers.add_parser('copy-files', help='Copy integration files to desktop')
        
        return parser
    
    def run(self):
        """Run the CLI"""
        parser = self.create_parser()
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return 1
        
        try:
            return self.handle_command(args)
        except KeyboardInterrupt:
            self.logger.info("Operation cancelled by user")
            return 1
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            return 1
    
    def handle_command(self, args):
        """Handle the parsed command"""
        if args.command == 'build':
            success = self.builder.build_dll()
            return 0 if success else 1
        
        elif args.command == 'status':
            status = self.builder.check_dll_status()
            if status['found']:
                self.logger.info("DLL Status: ✅ Built and ready")
            else:
                self.logger.info("DLL Status: ❌ Not built")
            return 0
        
        elif args.command == 'test':
            return self.handle_test_command(args)
        
        elif args.command == 'vb6':
            return self.handle_vb6_command(args)
        
        elif args.command == 'vfp9':
            return self.handle_vfp9_command(args)
        
        elif args.command == 'package':
            success = self.builder.create_dll_package()
            return 0 if success else 1
        
        elif args.command == 'install':
            success = self.builder.install_dll_system()
            return 0 if success else 1
        
        elif args.command == 'requirements':
            print(self.builder.show_build_requirements())
            return 0
        
        elif args.command == 'open-source':
            success = self.builder.open_dll_source()
            return 0 if success else 1
        
        elif args.command == 'copy-files':
            success = self.integration.copy_integration_files()
            return 0 if success else 1
        
        else:
            self.logger.error(f"Unknown command: {args.command}")
            return 1
    
    def handle_test_command(self, args):
        """Handle test subcommands"""
        if not args.test_command or args.test_command == 'all':
            success = self.tester.run_comprehensive_test()
            return 0 if success else 1
        
        elif args.test_command == 'functions':
            success = self.tester.test_dll_functions()
            return 0 if success else 1
        
        elif args.test_command == 'conversion':
            if hasattr(args, 'file') and args.file:
                if not self.tester.set_test_file(args.file):
                    return 1
            success = self.tester.test_dll_conversion()
            return 0 if success else 1
        
        elif args.test_command == 'performance':
            if hasattr(args, 'file') and args.file:
                if not self.tester.set_test_file(args.file):
                    return 1
            iterations = getattr(args, 'iterations', 5)
            success = self.tester.performance_test_dll(iterations)
            return 0 if success else 1
        
        else:
            self.logger.error(f"Unknown test command: {args.test_command}")
            return 1
    
    def handle_vb6_command(self, args):
        """Handle VB6 subcommands"""
        if args.vb6_command == 'generate':
            success = self.integration.generate_vb6_module()
            return 0 if success else 1
        
        elif args.vb6_command == 'examples':
            print(self.integration.show_vb6_examples())
            return 0
        
        elif args.vb6_command == 'test':
            test_code = self.integration.test_vb6_integration()
            return 0
        
        else:
            self.logger.error(f"Unknown VB6 command: {args.vb6_command}")
            return 1
    
    def handle_vfp9_command(self, args):
        """Handle VFP9 subcommands"""
        if args.vfp9_command == 'generate':
            success = self.integration.generate_vfp9_class()
            return 0 if success else 1
        
        elif args.vfp9_command == 'examples':
            print(self.integration.show_vfp9_examples())
            return 0
        
        elif args.vfp9_command == 'test':
            test_code = self.integration.test_vfp9_integration()
            return 0
        
        else:
            self.logger.error(f"Unknown VFP9 command: {args.vfp9_command}")
            return 1

def main():
    """Main entry point"""
    cli = LegacyDLLBuilderCLI()
    return cli.run()

if __name__ == "__main__":
    sys.exit(main())