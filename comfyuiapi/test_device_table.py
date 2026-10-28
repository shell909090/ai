#!/usr/bin/env python3
"""Check the supported device-table upscale modes using local fixtures."""

from libs.device import get_devices_with_upscale_info, print_devices_table

for mode in ("auto", "upscale2x", "upscale4x", "usdu", "aurasr"):
    print(f"Testing test_pixels.csv in {mode} mode:")
    devices = get_devices_with_upscale_info("test_pixels.csv", mode)
    assert len(devices) == 4
    assert all(device["width"] > 0 and device["height"] > 0 for device in devices)
    print_devices_table(devices)
