#!/bin/bash

# Debug: Show where we start
echo "=== DEBUG: Initial location ==="
pwd
ls -la

# Debug: Look for app.py in various locations
echo "=== DEBUG: Searching for app.py files ==="
find /opt/render/project -name "app.py" -type f 2>/dev/null || echo "No app.py found anywhere"

# Debug: Show full project structure
echo "=== DEBUG: Full project structure ==="
ls -la /opt/render/project/src/

# Debug: Look in webapp directory (if it exists)
if [ -d "/opt/render/project/src/webapp" ]; then
    echo "=== DEBUG: webapp directory contents ==="
    ls -la /opt/render/project/src/webapp/
else
    echo "=== DEBUG: webapp directory does not exist! ==="
fi

# Try to find the correct directory
echo "=== DEBUG: Looking for directories with app.py ==="
find /opt/render/project -name "*.py" -exec dirname {} \; | sort | uniq

# Change to webapp directory
cd webapp

# Debug: Show current directory and files
echo "=== DEBUG: Current directory after cd webapp ==="
pwd
echo "=== DEBUG: Files in current directory ==="
ls -la

# Debug: Check environment variables
echo "=== DEBUG: Environment variables ==="
echo "ALEGRA_USER: ${ALEGRA_USER:-'NOT SET'}"
echo "ALEGRA_TOKEN: ${ALEGRA_TOKEN:-'NOT SET'}" 
echo "AI_PROVIDER: ${AI_PROVIDER:-'NOT SET'}"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:-'NOT SET'}"
echo "GEMINI_API_KEY: ${GEMINI_API_KEY:-'NOT SET'}"

# Add current directory to Python path
export PYTHONPATH="$(pwd):${PYTHONPATH}"
echo "=== DEBUG: PYTHONPATH set to: $PYTHONPATH ==="

# Debug: Test if app can be imported now
echo "=== DEBUG: Testing app import with fixed path ==="
python3 -c "
import sys
print('Python path after fix:', sys.path)
try:
    import app
    print('✅ App imported successfully')
    print('Flask app object:', app.app)
except Exception as e:
    print('❌ App import still failed:', str(e))
    import traceback
    traceback.print_exc()
"

# Run gunicorn with current directory in Python path
echo "=== DEBUG: Starting gunicorn with fixed path ==="
exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 