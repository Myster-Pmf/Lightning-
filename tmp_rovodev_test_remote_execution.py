#!/usr/bin/env python3
"""
Test script to verify remote execution functionality
This script will test the upgraded file execution system
"""

import requests
import json
import time

# Test configuration
BASE_URL = "http://localhost:8080"  # Adjust if needed
TEST_FILE_CONTENT = '''#!/usr/bin/env python3
print("Hello from remote Lightning AI Studio!")
print("Current working directory:", __import__("os").getcwd())
print("Python version:", __import__("sys").version)
print("Available files in /tmp:", __import__("os").listdir("/tmp"))
'''

def test_remote_execution():
    """Test the remote execution functionality"""
    
    print("🧪 Testing Remote Execution Functionality")
    print("=" * 50)
    
    # Step 1: Create a test file locally
    test_file_path = "tmp_rovodev_test_script.py"
    with open(test_file_path, 'w') as f:
        f.write(TEST_FILE_CONTENT)
    print(f"✅ Created test file: {test_file_path}")
    
    # Step 2: Test file execution (should now run on remote studio)
    print("\n📤 Testing remote file execution...")
    
    execute_data = {
        "file_path": test_file_path,
        "interpreter": "python",
        "args": "",
        "timeout": 60
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/files/execute",
            json=execute_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Execution successful: {result.get('success')}")
            print(f"📍 Execution location: {result.get('execution_location', 'unknown')}")
            print(f"🔗 Remote path: {result.get('remote_path', 'N/A')}")
            print(f"⏱️  Execution time: {result.get('execution_time', 0):.2f}s")
            print(f"📤 Return code: {result.get('return_code', 'N/A')}")
            
            if result.get('stdout'):
                print("\n📋 STDOUT:")
                print(result['stdout'])
            
            if result.get('stderr'):
                print("\n❌ STDERR:")
                print(result['stderr'])
                
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing execution: {e}")
    
    # Step 3: Test remote command execution
    print("\n🖥️  Testing direct remote command...")
    
    command_data = {
        "command": "echo 'Direct command execution on remote studio' && pwd && whoami && python --version",
        "timeout": 30
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/files/run-remote-command",
            json=command_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Command successful: {result.get('success')}")
            print(f"⏱️  Execution time: {result.get('execution_time', 0):.2f}s")
            
            if result.get('stdout'):
                print("\n📋 Command output:")
                print(result['stdout'])
            
            if result.get('stderr'):
                print("\n❌ Command errors:")
                print(result['stderr'])
                
        else:
            print(f"❌ Command request failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing remote command: {e}")
    
    # Step 4: Test upload functionality
    print("\n📤 Testing file upload to remote...")
    
    upload_data = {
        "local_file_path": test_file_path,
        "remote_file_path": "/tmp/uploaded_test_script.py"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/files/upload-to-remote",
            json=upload_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful: {result.get('success')}")
            print(f"📁 Local path: {result.get('local_path', 'N/A')}")
            print(f"🔗 Remote path: {result.get('remote_path', 'N/A')}")
            print(f"💬 Message: {result.get('message', 'N/A')}")
        else:
            print(f"❌ Upload request failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing upload: {e}")
    
    # Clean up
    import os
    try:
        os.remove(test_file_path)
        print(f"\n🧹 Cleaned up test file: {test_file_path}")
    except:
        pass
    
    print("\n" + "=" * 50)
    print("🏁 Remote execution testing completed!")

if __name__ == "__main__":
    test_remote_execution()