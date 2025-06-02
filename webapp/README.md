# Aplicación Web de Registro de Pagos - Alegra

Esta aplicación web permite cargar facturas en PDF y registrar pagos automáticamente en Alegra, adaptada específicamente para Costa Rica.

## Características

- 📄 **Carga de PDF**: Arrastra y suelta o selecciona facturas en formato PDF
- 🔍 **Extracción Automática**: Extrae información del pago del PDF (monto, fecha, cliente)
- 🤖 **Extracción con IA**: Usa OpenAI o Google Gemini para extracción inteligente (opcional)
- 🎯 **Identificación Automática de Contactos**: Identifica automáticamente el cliente basado en la cédula del vendedor
- 👥 **Gestión de Clientes**: Busca clientes existentes o crea nuevos
- 💰 **Registro de Pagos**: Registra pagos directamente en Alegra
- 🇨🇷 **Adaptado para Costa Rica**: Soporta colones (₡) y cédulas costarricenses

## Requisitos Previos

- Python 3.8 o superior
- Cuenta en Alegra con acceso API
- Credenciales API de Alegra (usuario y token)

## Instalación

1. **Clona o descarga el proyecto**

2. **Instala las dependencias**:
   ```bash
   cd webapp
   pip install -r requirements.txt
   ```

3. **Instala la librería Alegra** (desde el directorio principal):
   ```bash
   cd ..
   pip install -e .
   ```

## Configuración

### Opción 1: Variables de Entorno

Crea un archivo `.env` en el directorio `webapp`:

```env
# Credenciales de Alegra (requerido)
ALEGRA_USER=tu_usuario_api
ALEGRA_TOKEN=tu_token_api

# Configuración de IA (opcional - para extracción inteligente)
AI_PROVIDER=openai  # o 'gemini'
OPENAI_API_KEY=tu_openai_key  # Si usas OpenAI
GEMINI_API_KEY=tu_gemini_key  # Si usas Gemini
```

### Opción 2: Exportar Variables

```bash
# Credenciales de Alegra
export ALEGRA_USER="tu_usuario_api"
export ALEGRA_TOKEN="tu_token_api"

# Para extracción con IA (opcional)
export AI_PROVIDER="openai"
export OPENAI_API_KEY="tu_openai_key"
```

### Obtener las Credenciales

- **Alegra**: https://app.alegra.com/configuration/api
- **OpenAI**: https://platform.openai.com/api-keys
- **Google Gemini**: https://makersuite.google.com/app/apikey

## Ejecución

1. **Inicia la aplicación**:
   ```bash
   cd webapp
   python app.py
   ```

2. **Abre tu navegador** en: http://localhost:5000

## Uso

1. **Carga un PDF**: Arrastra una factura PDF al área de carga
2. **Revisa la información**: La app extraerá automáticamente:
   - Monto (busca ₡ o CRC)
   - Fecha
   - Información del cliente
3. **Selecciona o crea un cliente**: 
   - Busca por nombre o cédula
   - O crea un nuevo cliente
4. **Confirma y registra**: Revisa los datos y registra el pago

## Métodos de Extracción

### Con IA (Recomendado)
Si configuras OpenAI o Gemini, la aplicación usará inteligencia artificial para extraer:
- Montos totales en cualquier formato
- Información del vendedor (quien emite la factura)
- Información del cliente (quien recibe el pago)
- Fechas en múltiples formatos
- Números de factura
- Descripciones relevantes

**Identificación Automática de Contactos:**
- La IA distingue entre el vendedor (emisor de la factura) y el cliente (receptor)
- Busca automáticamente en tus contactos de Alegra usando la cédula del vendedor
- Si encuentra una coincidencia exacta, selecciona el contacto automáticamente
- Muestra una notificación cuando identifica el contacto correctamente

La IA es especialmente útil para:
- PDFs con formatos complejos o no estándar
- Facturas escaneadas con OCR
- Documentos en múltiples idiomas
- Identificación precisa de vendedor vs cliente

### Sin IA (Regex)
Si no configuras IA, la aplicación busca patrones específicos:

**Montos:**
- Total: ₡ XXX,XXX.XX
- TOTAL A PAGAR: CRC XXX,XXX
- Monto Total: XXX,XXX.XX

**Cliente:**
- Cliente/Nombre/Razón Social: XXXX
- Cédula/Identificación: X-XXXX-XXXX

**Fecha:**
- Fecha: DD/MM/YYYY
- Fecha de Emisión: DD-MM-YYYY

## Solución de Problemas

### Error de autenticación
- Verifica que las credenciales de Alegra sean correctas
- Asegúrate de que tu cuenta tenga permisos API activos

### PDF no se procesa correctamente
- Verifica que el PDF no esté protegido o encriptado
- Asegúrate de que el PDF contenga texto seleccionable (no solo imágenes)

### No encuentra clientes
- Verifica que existan clientes en tu cuenta de Alegra
- Prueba buscar por cédula exacta

## Estructura del Proyecto

```
webapp/
├── app.py              # Aplicación Flask principal
├── templates/
│   └── index.html      # Interfaz web
├── uploads/            # Directorio temporal para PDFs (se crea automáticamente)
├── requirements.txt    # Dependencias Python
└── README.md          # Este archivo
```

## Seguridad

- Los PDFs se eliminan automáticamente después de procesarse
- Las credenciales API nunca se exponen en el frontend
- Límite de carga: 16MB por archivo

## Contribuciones

Si encuentras algún problema o tienes sugerencias, por favor abre un issue en el repositorio. 