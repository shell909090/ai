#!/usr/bin/env python3
"""
Test script for device table functionality
"""

import sys
import importlib.util

# Load libs.constants first
constants_spec = importlib.util.spec_from_file_location("libs.constants", "libs/constants.py")
constants_module = importlib.util.module_from_spec(constants_spec)
sys.modules["libs.constants"] = constants_module
constants_spec.loader.exec_module(constants_module)

# Load libs.device directly to avoid triggering libs/__init__.py
device_spec = importlib.util.spec_from_file_location("libs.device", "libs/device.py")
device_module = importlib.util.module_from_spec(device_spec)
sys.modules["libs.device"] = device_module
device_spec.loader.exec_module(device_module)

from libs.device import get_devices_with_upscale_info, print_devices_table

# Test with test_pixels.csv
print("Testing with test_pixels.csv in auto mode:")
devices = get_devices_with_upscale_info("test_pixels.csv", "auto")
print_devices_table(devices)

print("\n" + "="*80)
print("\nTesting with test_pixels.csv in upscale mode:")
devices = get_devices_with_upscale_info("test_pixels.csv", "upscale")
print_devices_table(devices)

print("\n" + "="*80)
print("\nTesting with test_pixels.csv in usdu mode:")
devices = get_devices_with_upscale_info("test_pixels.csv", "usdu")
print_devices_table(devices)
