#!/bin/bash
cd webapp

# Debug: Show current directory and files
echo "=== DEBUG: Current directory ==="
pwd
echo "=== DEBUG: Files in directory ==="
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