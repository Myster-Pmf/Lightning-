#!/usr/bin/env python3
"""
Simple test script for Lightning AI Studio file execution
"""

print("Hello from Lightning AI Studio!")
print("Python script is running successfully.")

import sys
print(f"Python version: {sys.version}")

import os
print(f"Current working directory: {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")

# Test some basic operations
numbers = [1, 2, 3, 4, 5]
result = sum(numbers)
print(f"Sum of {numbers} = {result}")

print("Script completed successfully!")