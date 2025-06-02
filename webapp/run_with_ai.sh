#!/bin/bash

echo "=== Iniciando aplicación con extracción inteligente ==="
echo ""
echo "Asegúrate de configurar las siguientes variables en tu .env:"
echo "- ALEGRA_USER y ALEGRA_TOKEN (requerido)"
echo "- AI_PROVIDER (openai o gemini)"
echo "- OPENAI_API_KEY o GEMINI_API_KEY según tu elección"
echo ""
echo "Iniciando servidor..."
python3 app.py 