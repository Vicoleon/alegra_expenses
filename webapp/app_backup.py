from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import alegra
from werkzeug.utils import secure_filename
import PyPDF2
import re
from datetime import datetime
from dotenv import load_dotenv
import json
import requests
import xml.etree.ElementTree as ET

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'xml'}

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Configure APIs
alegra.user = os.environ.get('ALEGRA_USER', '')
alegra.token = os.environ.get('ALEGRA_TOKEN', '')

# AI Provider configuration
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai').lower()  # 'openai' or 'gemini'
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
        return text
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""

def extract_payment_info_with_ai(text):
    """Extract payment information using AI (OpenAI or Gemini)"""
    
    prompt = """
    Analiza el siguiente texto de una factura y extrae la siguiente información en formato JSON:
    {
        "amount": número (monto total en colones, sin símbolos de moneda),
        "description": "descripción breve del pago o número de factura",
        "client_name": "nombre del cliente que RECIBE el pago",
        "client_id": "cédula o identificación del cliente que RECIBE el pago",
        "vendor_name": "nombre del vendedor/proveedor que EMITE la factura",
        "vendor_id": "cédula o identificación del vendedor/proveedor que EMITE la factura",
        "date": "fecha en formato YYYY-MM-DD",
        "invoice_number": "número de factura si está disponible"
    }
    
    IMPORTANTE: 
    - El cliente es quien RECIBE el pago (aparece como "Cliente", "Facturado a", "Bill to")
    - El vendedor es quien EMITE la factura (aparece en el encabezado, logo, o como "Emisor")
    - Si no encuentras algún dato, déjalo como null
    - Busca específicamente montos en colones (₡) o CRC
    - Para las cédulas en Costa Rica, pueden tener formato X-XXXX-XXXX o similar
    
    Texto de la factura:
    """
    
    try:
        if AI_PROVIDER == 'openai':
            return extract_with_openai(prompt + text)
        elif AI_PROVIDER == 'gemini':
            return extract_with_gemini(prompt + text)
        else:
            # Fallback to regex-based extraction
            return extract_payment_info(text)
    except Exception as e:
        print(f"Error with AI extraction: {e}")
        # Fallback to regex-based extraction
        return extract_payment_info(text)

def extract_with_openai(prompt):
    """Extract information using OpenAI API"""
    if not OPENAI_API_KEY:
        raise ValueError("OpenAI API key not configured")
    
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': 'gpt-3.5-turbo',
        'messages': [
            {'role': 'system', 'content': 'Eres un asistente especializado en extraer información de facturas de Costa Rica. Siempre responde en formato JSON válido.'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.1,
        'max_tokens': 500
    }
    
    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content']
        # Extract JSON from the response
        try:
            # Try to find JSON in the response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = content[start:end]
                extracted_data = json.loads(json_str)
                return format_ai_response(extracted_data)
        except:
            pass
    
    raise Exception(f"OpenAI API error: {response.status_code}")

def extract_with_gemini(prompt):
    """Extract information using Google Gemini API"""
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API key not configured")
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        'contents': [{
            'parts': [{
                'text': prompt
            }]
        }],
        'generationConfig': {
            'temperature': 0.1,
            'maxOutputTokens': 500,
        }
    }
    
    response = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}',
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result['candidates'][0]['content']['parts'][0]['text']
        # Extract JSON from the response
        try:
            # Try to find JSON in the response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = content[start:end]
                extracted_data = json.loads(json_str)
                return format_ai_response(extracted_data)
        except:
            pass
    
    raise Exception(f"Gemini API error: {response.status_code}")

def format_ai_response(ai_data):
    """Format AI response to match our expected structure"""
    return {
        'amount': ai_data.get('amount'),
        'description': ai_data.get('description', '') or ai_data.get('invoice_number', ''),
        'client_name': ai_data.get('client_name', ''),
        'client_id': ai_data.get('client_id', ''),
        'vendor_name': ai_data.get('vendor_name', ''),
        'vendor_id': ai_data.get('vendor_id', ''),
        'date': ai_data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'auto_matched': False,
        'line_items': ai_data.get('line_items', [])
    }

def extract_data_from_xml(xml_path):
    """Extract structured data from Costa Rican electronic invoice XML"""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Define namespace
        ns = {'fe': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronica'}
        
        # Extract vendor info
        vendor_name = root.find('.//fe:Emisor/fe:Nombre', ns).text if root.find('.//fe:Emisor/fe:Nombre', ns) is not None else ''
        vendor_id = root.find('.//fe:Emisor/fe:Identificacion/fe:Numero', ns).text if root.find('.//fe:Emisor/fe:Identificacion/fe:Numero', ns) is not None else ''
        
        # Extract client info
        client_name = root.find('.//fe:Receptor/fe:Nombre', ns).text if root.find('.//fe:Receptor/fe:Nombre', ns) is not None else ''
        client_id = root.find('.//fe:Receptor/fe:Identificacion/fe:Numero', ns).text if root.find('.//fe:Receptor/fe:Identificacion/fe:Numero', ns) is not None else ''
        
        # Extract invoice details
        invoice_number = root.find('.//fe:NumeroConsecutivo', ns).text if root.find('.//fe:NumeroConsecutivo', ns) is not None else ''
        date_str = root.find('.//fe:FechaEmision', ns).text if root.find('.//fe:FechaEmision', ns) is not None else ''
        
        # Parse date
        date = datetime.now().strftime('%Y-%m-%d')
        if date_str:
            try:
                # Handle both 2025-05-24T03:31:13 and other formats
                if 'T' in date_str:
                    date_obj = datetime.fromisoformat(date_str.split('.')[0])
                else:
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date = date_obj.strftime('%Y-%m-%d')
            except:
                pass
        
        # Extract line items
        line_items = []
        for line in root.findall('.//fe:LineaDetalle', ns):
            item = {
                'line_number': line.find('fe:NumeroLinea', ns).text if line.find('fe:NumeroLinea', ns) is not None else '',
                'description': line.find('fe:Detalle', ns).text if line.find('fe:Detalle', ns) is not None else '',
                'quantity': float(line.find('fe:Cantidad', ns).text) if line.find('fe:Cantidad', ns) is not None else 1,
                'unit_price': float(line.find('fe:PrecioUnitario', ns).text) if line.find('fe:PrecioUnitario', ns) is not None else 0,
                'subtotal': float(line.find('fe:SubTotal', ns).text) if line.find('fe:SubTotal', ns) is not None else 0,
                'discount': float(line.find('.//fe:MontoDescuento', ns).text) if line.find('.//fe:MontoDescuento', ns) is not None else 0,
                'taxes': []
            }
            
            # Extract taxes for this line
            for tax in line.findall('.//fe:Impuesto', ns):
                tax_rate = float(tax.find('fe:Tarifa', ns).text) if tax.find('fe:Tarifa', ns) is not None else 0
                tax_amount = float(tax.find('fe:Monto', ns).text) if tax.find('fe:Monto', ns) is not None else 0
                item['taxes'].append({
                    'rate': tax_rate,
                    'amount': tax_amount
                })
            
            # Calculate final amount (subtotal - discount)
            item['amount'] = item['subtotal'] - item['discount']
            item['has_tax'] = len(item['taxes']) > 0
            item['tax_percentage'] = item['taxes'][0]['rate'] if item['taxes'] else 0
            
            line_items.append(item)
        
        # Extract totals
        total = 0
        total_node = root.find('.//fe:ResumenFactura/fe:TotalComprobante', ns)
        if total_node is not None:
            try:
                total = float(total_node.text)
            except:
                pass
        
        # If total is still 0, calculate from line items
        if total == 0 and line_items:
            subtotal = sum(item['amount'] for item in line_items)
            total_tax = sum(sum(tax['amount'] for tax in item['taxes']) for item in line_items)
            total = subtotal + total_tax
        
        return {
            'vendor_name': vendor_name,
            'vendor_id': vendor_id,
            'client_name': client_name,
            'client_id': client_id,
            'invoice_number': invoice_number,
            'date': date,
            'line_items': line_items,
            'total': total,
            'is_xml': True
        }
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return None

def extract_vendor_info(text):
    """Extract vendor information from invoice text"""
    vendor_info = {
        'name': '',
        'id': ''
    }
    
    # Look for vendor patterns in Costa Rica invoices
    # Common vendor name patterns
    vendor_patterns = [
        r'(?:Emisor|EMISOR|Proveedor|PROVEEDOR|Vendedor|VENDEDOR)[:\s]*([^\n]+)',
        r'(?:Razón Social|RAZÓN SOCIAL)[:\s]*([^\n]+)',
        r'(?:Nombre Comercial|NOMBRE COMERCIAL)[:\s]*([^\n]+)'
    ]
    
    for pattern in vendor_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor_info['name'] = match.group(1).strip()
            break
    
    # If no vendor name found with patterns, look for known vendors
    known_vendors = [
        'CLARO CR TELECOMUNICACIONES',
        'CORPORACION SUPERMERCADOS UNIDOS',
        'WAL MART',
        'WALMART'
    ]
    
    if not vendor_info['name']:
        text_upper = text.upper()
        for vendor in known_vendors:
            if vendor in text_upper:
                vendor_info['name'] = vendor
                break
    
    # Vendor ID patterns
    id_patterns = [
        r'(?:Cédula Jurídica|CÉDULA JURÍDICA|CED\. JURÍDICA)[:\s]*([\d-]+)',
        r'(?:Identificación del Emisor|IDENTIFICACIÓN DEL EMISOR)[:\s]*([\d-]+)',
        r'(?:RUC|NIT)[:\s]*([\d-]+)'
    ]
    
    for pattern in id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vendor_info['id'] = match.group(1).strip().replace('-', '')
            break
    
    return vendor_info

def extract_invoice_data(pdf_text):
    """Extract structured invoice data from PDF text using AI if available"""
    
    # Extract basic info using regex patterns
    vendor_info = extract_vendor_info(pdf_text)
    
    # Extract dates
    date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    dates = re.findall(date_pattern, pdf_text)
    invoice_date = dates[0] if dates else datetime.now().strftime('%Y-%m-%d')
    
    # Try to normalize date format
    if invoice_date and '/' in invoice_date:
        try:
            parts = invoice_date.split('/')
            if len(parts[2]) == 2:
                parts[2] = '20' + parts[2]
            invoice_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        except:
            invoice_date = datetime.now().strftime('%Y-%m-%d')
    
    # Extract invoice number
    invoice_pattern = r'(?:factura|invoice|n[úu]mero|no\.?)\s*[:#]?\s*(\d{5,})'
    invoice_match = re.search(invoice_pattern, pdf_text, re.IGNORECASE)
    invoice_number = invoice_match.group(1) if invoice_match else ''
    
    # Extract total amount
    total_pattern = r'(?:total|monto total|total a pagar)[:\s]*(?:₡|CRC)?\s*([\d,]+\.?\d*)'
    total_match = re.search(total_pattern, pdf_text, re.IGNORECASE)
    total = 0
    if total_match:
        total_str = total_match.group(1).replace(',', '')
        try:
            total = float(total_str)
        except:
            total = 0
    
    return {
        'vendor_name': vendor_info.get('name', ''),
        'vendor_id': vendor_info.get('id', ''),
        'client_name': '',  # Would need more sophisticated extraction
        'client_id': '',
        'invoice_number': invoice_number,
        'date': invoice_date,
        'total': total,
        'amount': total
    }

def analyze_invoice_items_with_ai(pdf_text, expense_accounts):
    """Use AI to analyze invoice and categorize line items"""
    
    # Create a comprehensive list of available expense categories for the AI
    if expense_accounts and len(expense_accounts) > 0:
        # Create a detailed list of ALL available categories
        accounts_list = []
        for acc in expense_accounts:
            if acc.get('id') not in ['5066', '5065']:  # Exclude parent categories
                accounts_list.append({
                    'id': acc['id'],
                    'name': acc['name'],
                    'code': acc.get('code', '')
                })
        
        # Sort by code for better organization
        accounts_list.sort(key=lambda x: x.get('code', ''))
        
        # Create a detailed account listing for AI
        accounts_detail = "
".join([
            f"- ID: {acc['id']} | Código: {acc.get('code', 'N/A')} | Nombre: {acc['name']}"
            for acc in accounts_list
        ])
        
        account_instruction = f"""
        CUENTAS CONTABLES DISPONIBLES EN EL SISTEMA:
        {accounts_detail}
        
        IMPORTANTE PARA CATEGORIZACIÓN:
        - Analiza cada línea de la factura y asigna la cuenta más apropiada según su descripción
        - Para productos de supermercado: busca cuentas como "Costo de ventas", "Inventario", "Mercadería"
        - Para servicios: busca cuentas de "Servicios", "Gastos administrativos", etc.
        - Para telecomunicaciones: busca cuentas específicas de "Telecomunicaciones", "Internet", etc.
        - Si no puedes determinar la cuenta apropiada, usa ID: 5077 (Gastos Generales)
        - NO uses cuentas de Salarios (5076) a menos que sea realmente nómina
        - Asigna un account_id específico a CADA línea de la factura
        """
    else:
        # If no accounts available, use default
        account_instruction = """
        No hay cuentas contables disponibles en el sistema.
        Usa account_id: 5077 (Gastos Generales) para todas las líneas.
        """
    
    prompt = f"""
    Analiza la siguiente factura y extrae CADA línea de producto/servicio por separado.
    
    {account_instruction}
    
    IMPORTANTE - Debes extraer:
    1. CADA producto/servicio como una línea separada
    2. NO agrupes múltiples productos en una sola línea
    3. Asigna el account_id más apropiado a cada línea según las cuentas disponibles
    
    Para cada línea determina:
    1. Descripción exacta del producto/servicio (tal como aparece en la factura)
    2. Cantidad (número de unidades)
    3. Precio unitario (sin impuestos)
    4. Monto total de la línea (precio unitario × cantidad, sin impuestos)
    5. account_id: El ID de la cuenta contable más apropiada (OBLIGATORIO - usa 5077 si no puedes determinar)
    6. Si aplica IVA/impuesto (true/false)
    7. Porcentaje de IVA (típicamente 13% en Costa Rica)
    
    Responde en formato JSON:
    {{
        "line_items": [
            {{
                "description": "descripción exacta del producto",
                "quantity": número de unidades,
                "unit_price": precio unitario sin impuestos,
                "amount": monto total sin impuestos,
                "account_id": "ID de la cuenta contable apropiada",
                "has_tax": true/false,
                "tax_percentage": número (13 para IVA normal, 0 si no aplica)
            }}
        ],
        "total_subtotal": suma de todos los amounts,
        "total_tax": suma de todos los impuestos,
        "total": total con impuestos
    }}
    
    Texto de la factura:
    {pdf_text}
    """

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test')
def test_page():
    return send_from_directory('.', 'test_debug.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    """Check API configuration status"""
    # Test API connection
    test_result = "Not tested"
    contact_count = 0
    
    if alegra.user and alegra.token:
        try:
            import base64
            credentials = f"{alegra.user}:{alegra.token}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                'https://api.alegra.com/api/v1/contacts?limit=5',
                headers=headers
            )
            
            if response.status_code == 200:
                contacts = response.json()
                contact_count = len(contacts) if isinstance(contacts, list) else 0
                test_result = f"Success - Found {contact_count} contacts"
            else:
                test_result = f"Error {response.status_code}: {response.text[:100]}"
        except Exception as e:
            test_result = f"Exception: {str(e)}"
    
    return jsonify({
        'alegra_configured': bool(alegra.user and alegra.token),
        'ai_configured': bool(
            (AI_PROVIDER == 'openai' and OPENAI_API_KEY) or 
            (AI_PROVIDER == 'gemini' and GEMINI_API_KEY)
        ),
        'ai_provider': AI_PROVIDER if (OPENAI_API_KEY or GEMINI_API_KEY) else None,
        'api_test': test_result,
        'contact_count': contact_count
    })

def find_contact_by_id(vendor_id):
    """Find a contact in Alegra by their identification number"""
    if not vendor_id:
        return None
    
    try:
        # Clean the vendor ID for search (remove dashes, spaces, etc.)
        clean_vendor_id = re.sub(r'[\s\-\.]+', '', str(vendor_id).strip())
        
        # Use direct API call
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Search through pages to find the contact
        all_contacts = []
        page = 1
        limit = 30
        max_pages = 10  # Search up to 10 pages (300 contacts)
        found = False
        
        print(f"Searching for contact with ID: {clean_vendor_id}")
        
        while page <= max_pages and not found:
            api_response = requests.get(
                f'https://api.alegra.com/api/v1/contacts?limit={limit}&start={(page-1)*limit}',
                headers=headers
            )
            
            if api_response.status_code == 200:
                contacts_page = api_response.json()
                if isinstance(contacts_page, list):
                    print(f"Page {page}: Checking {len(contacts_page)} contacts")
                    
                    for contact in contacts_page:
                        if isinstance(contact, dict):
                            # Handle both formats: string directly or object with 'number'
                            contact_id_info = contact.get('identification', '')
                            if isinstance(contact_id_info, dict):
                                contact_id = str(contact_id_info.get('number', ''))
                            else:
                                contact_id = str(contact_id_info)
                            clean_contact_id = re.sub(r'[\s\-\.]+', '', contact_id)
                            
                            if clean_contact_id == clean_vendor_id:
                                print(f"Found match on page {page}: {contact.get('name')}")
                                all_contacts = [contact]
                                found = True
                                break
                    
                    if not found:
                        all_contacts.extend(contacts_page)
                        
                    if len(contacts_page) < limit:
                        break  # No more pages
                    page += 1
                else:
                    break
            else:
                print(f"Error fetching page {page}: {api_response.status_code}")
                break
        
        data = all_contacts
        if not found:
            print(f"Contact with ID {clean_vendor_id} not found after searching {page} pages")
            
        # Handle the response
        contacts = []
        if isinstance(data, list):
            contacts = data
        elif isinstance(data, dict):
            # Check for error response
            if 'code' in data and 'message' in data:
                print(f"API Error: {data.get('code')} - {data.get('message')}")
                return None
            # Check for data wrapper
            elif 'data' in data:
                contacts = data['data']
            else:
                print(f"Unexpected response structure when listing contacts")
                return None
        
        # Search for contact with matching identification
        for contact in contacts:
            if isinstance(contact, dict):
                # Handle both formats: string directly or object with 'number'
                contact_id_info = contact.get('identification', '')
                if isinstance(contact_id_info, dict):
                    contact_id = str(contact_id_info.get('number', ''))
                else:
                    contact_id = str(contact_id_info)
                clean_contact_id = re.sub(r'[\s\-\.]+', '', contact_id)
                
                if clean_contact_id == clean_vendor_id:
                    print(f"Found matching contact: {contact.get('name')} with ID {contact_id}")
                    return {
                        'id': contact['id'],
                        'name': str(contact.get('name', '')),
                        'identification': contact_id,
                        'email': str(contact.get('email', ''))
                    }
        
        print(f"No contact found with identification: {vendor_id}")
        return None
    except Exception as e:
        print(f"Error searching for contact: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró el archivo'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    if file and file.filename.lower().endswith(tuple(app.config['ALLOWED_EXTENSIONS'])):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Check if it's XML or PDF
        is_xml = filename.lower().endswith('.xml')
        
        if is_xml:
            # Extract data from XML
            xml_data = extract_data_from_xml(filepath)
            if not xml_data:
                return jsonify({'error': 'Error al procesar el archivo XML'}), 500
            
            # Format the response similar to PDF extraction
            extracted_data = {
                'vendor_name': xml_data['vendor_name'],
                'vendor_id': xml_data['vendor_id'],
                'client_name': xml_data['client_name'],
                'client_id': xml_data['client_id'],
                'invoice_number': xml_data['invoice_number'],
                'date': xml_data['date'],
                'total': xml_data['total'],
                'line_items': xml_data['line_items'],
                'is_xml': True,
                'raw_text': f"Factura XML de {xml_data['vendor_name']}"
            }
        else:
            # Extract PDF text
            pdf_text = extract_text_from_pdf(filepath)
            if not pdf_text:
                return jsonify({'error': 'No se pudo extraer texto del PDF'}), 500
            
            # Extract structured data from PDF
            extracted_data = extract_invoice_data(pdf_text)
            extracted_data['raw_text'] = pdf_text
            extracted_data['is_xml'] = False
        
        # Clean up - remove the uploaded file
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'data': extracted_data
        })
    
    return jsonify({'error': 'Tipo de archivo no permitido. Solo se aceptan PDF y XML.'}), 400

@app.route('/api/contacts/search', methods=['GET'])
def search_contacts():
    try:
        query = request.args.get('q', '')
        
        # Clean the query for identification search
        clean_query = re.sub(r'[\s\-\.]+', '', query.strip())
        
        # Use direct API call to get contacts
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # If searching by ID, try to get all contacts (pagination)
        all_contacts = []
        if clean_query.isdigit() and len(clean_query) >= 9:
            page = 1
            limit = 30
            max_pages = 5  # Limit to prevent infinite loops
            
            while page <= max_pages:
                api_response = requests.get(
                    f'https://api.alegra.com/api/v1/contacts?limit={limit}&start={(page-1)*limit}',
                    headers=headers
                )
                
                if api_response.status_code == 200:
                    contacts_page = api_response.json()
                    if isinstance(contacts_page, list):
                        all_contacts.extend(contacts_page)
                        # Check if we found the contact we're looking for
                        for contact in contacts_page:
                            if isinstance(contact, dict):
                                # Handle both formats: string directly or object with 'number'
                                contact_id_info = contact.get('identification', '')
                                if isinstance(contact_id_info, dict):
                                    contact_id = str(contact_id_info.get('number', ''))
                                else:
                                    contact_id = str(contact_id_info)
                                
                                if re.sub(r'[\s\-\.]+', '', contact_id) == clean_query:
                                    print(f"Found contact on page {page}: {contact.get('name')}")
                                    all_contacts = [contact]  # Just return this one
                                    page = max_pages + 1  # Exit loop
                                    break
                        
                        if len(contacts_page) < limit or page >= max_pages:
                            break
                        page += 1
                    else:
                        break
                else:
                    break
            
            data = all_contacts
            print(f"Searched {page-1} pages, total contacts checked: {len(all_contacts)}")
        else:
            # For name searches, just get first page
            api_response = requests.get(
                'https://api.alegra.com/api/v1/contacts?limit=30',
                headers=headers
            )
            
            if api_response.status_code == 200:
                data = api_response.json()
            else:
                print(f"API Error Response: {api_response.text}")
                data = []
            
        # Handle the response
        contacts = []
        if isinstance(data, list):
            contacts = data
            print(f"Got {len(contacts)} contacts from API")
        elif isinstance(data, dict):
            # Check for error response
            if 'code' in data and 'message' in data:
                print(f"API Error: {data.get('code')} - {data.get('message')}")
                contacts = []
            # Check for data wrapper
            elif 'data' in data:
                contacts = data['data']
                print(f"Got {len(contacts)} contacts from API (wrapped in 'data')")
            else:
                print(f"Unexpected response structure: {list(data.keys())[:5]}")
                contacts = []
        
        # Filter contacts by name or identification
        filtered_contacts = []
        
        # Debug: Show first few contacts and their IDs
        if len(contacts) > 0:
            print(f"\nFirst 5 contacts for debugging:")
            for i, contact in enumerate(contacts[:5]):
                if isinstance(contact, dict):
                    print(f"Contact {i+1}: {contact.get('name', 'No name')} - ID info: {contact.get('identification', 'No ID')}")
        
        for contact in contacts:
            if isinstance(contact, dict):
                contact_name = str(contact.get('name', ''))
                # Handle both formats: string directly or object with 'number'
                contact_id_info = contact.get('identification', '')
                if isinstance(contact_id_info, dict):
                    contact_id = str(contact_id_info.get('number', ''))
                else:
                    contact_id = str(contact_id_info)
                
                # Clean contact ID for comparison
                clean_contact_id = re.sub(r'[\s\-\.]+', '', contact_id)
                
                # Check if query matches name or identification
                match_by_name = query.lower() in contact_name.lower()
                match_by_id = clean_query == clean_contact_id
                
                # Also check if it's Claro by name
                if query == "3101460479" and "claro" in contact_name.lower():
                    print(f"Found Claro contact: {contact_name} with ID: {contact_id}")
                
                if match_by_name or match_by_id:
                    filtered_contacts.append({
                        'id': contact['id'],
                        'name': contact_name,
                        'identification': contact_id,
                        'email': str(contact.get('email', ''))
                    })
        
        return jsonify({'contacts': filtered_contacts[:10]})  # Limit to 10 results
        
    except Exception as e:
        print(f"Error in search_contacts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error buscando contactos: {str(e)}'}), 500

@app.route('/api/contacts/create', methods=['POST'])
def create_contact():
    try:
        data = request.json
        
        # Create contact in Alegra
        response = alegra.Contact.create(
            name=data['name'],
            identification={
                "type": "CC",  # Cédula for Costa Rica
                "number": data['identification']
            },
            email=data.get('email', ''),
            type=["client"],
            address={
                "city": "San José, Costa Rica"  # Default city
            }
        )
        
        # Handle response
        if hasattr(response, 'json'):
            contact = response.json()
        elif hasattr(response, 'content'):
            contact = json.loads(response.content.decode('utf-8'))
        else:
            contact = response
            
        # Handle both formats for identification
        contact_id = ''
        if 'identification' in contact:
            if isinstance(contact['identification'], dict):
                contact_id = contact['identification'].get('number', '')
            else:
                contact_id = str(contact['identification'])
                
        return jsonify({
            'success': True,
            'contact': {
                'id': contact['id'],
                'name': contact['name'],
                'identification': contact_id
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Error creando contacto: {str(e)}'}), 500

@app.route('/api/payments/register', methods=['POST'])
def register_payment():
    try:
        data = request.json
        
        # First, get the accounting catalog and taxes
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Check if we have any items first
        items_response = requests.get(
            'https://api.alegra.com/api/v1/items?limit=30',
            headers=headers
        )
        
        default_item_id = None
        if items_response.status_code == 200:
            items = items_response.json()
            if isinstance(items, list) and len(items) > 0:
                # Use item ID 6 which works for purchases
                # Try to find it specifically, or use the highest ID as fallback
                purchase_item = None
                for item in items:
                    if str(item.get('id')) == '6':
                        purchase_item = item
                        break
                
                if purchase_item:
                    default_item_id = int(purchase_item.get('id'))
                    print(f"Using purchase item ID: {default_item_id} - {purchase_item.get('name')}")
                else:
                    # Fallback to highest ID
                    items_sorted = sorted(items, key=lambda x: int(x.get('id', 0)), reverse=True)
                    default_item_id = int(items_sorted[0].get('id'))
                    print(f"Using highest ID item: {default_item_id} - {items_sorted[0].get('name')}")
            else:
                print("No items found, will create one")
        
        # If no items exist, create a default one
        if not default_item_id:
            print("Creating default item...")
            new_item_data = {
                'name': 'Servicios y Compras Generales',
                'description': 'Item genérico para facturas de proveedores',
                'price': 0,  # Price will be set per invoice
                'reference': 'SERV-GENERAL',
                'type': 'service'  # Service type doesn't require inventory
            }
            
            create_item_response = requests.post(
                'https://api.alegra.com/api/v1/items',
                json=new_item_data,
                headers=headers
            )
            
            if create_item_response.status_code in [200, 201]:
                created_item = create_item_response.json()
                default_item_id = int(created_item.get('id'))  # Ensure it's an integer
                print(f"Created default item with ID: {default_item_id}")
            else:
                print(f"Failed to create item: {create_item_response.text}")
        
        # Initialize category IDs
        default_expense_id = None  # Don't default to parent Egresos
        grocery_expense_id = None
        generic_expense_id = None
        
        # Get expense accounts
        accounts_response = requests.get(
            'https://api.alegra.com/api/v1/categories?limit=200',
            headers=headers
        )
        expense_accounts = []
        all_expense_categories = {}
        
        if accounts_response.status_code == 200:
            accounts = accounts_response.json()
            if isinstance(accounts, list):
                # Filter for expense accounts
                for a in accounts:
                    # Check if it's an expense type and NOT a parent category
                    if (a.get('type') == 'expense' and 
                        a.get('id') not in ['5066', '5065'] and  # Exclude parent categories
                        a.get('name', '').lower() not in ['egresos', 'ingresos']):  # Exclude main parent names
                        
                        expense_accounts.append({
                            'id': a['id'], 
                            'code': a.get('code', ''), 
                            'name': a['name'], 
                            'description': a.get('description', '')
                        })
                        # Store for easy lookup
                        all_expense_categories[a['name'].lower()] = a['id']
                        
                print(f"Found {len(expense_accounts)} expense accounts")
                
                # Find specific categories for common expense types
                for acc in expense_accounts:
                    name_lower = acc['name'].lower()
                    
                    # Look for grocery/food related categories
                    if any(word in name_lower for word in ['compra', 'mercadería', 'inventario', 'costo de venta', 'producto', 'mercancía']):
                        if not grocery_expense_id:
                            grocery_expense_id = int(acc['id'])  # Ensure integer
                            print(f"Found grocery/inventory category: {acc['name']} (ID: {acc['id']})")
                    
                    # Look for general expense categories
                    elif any(word in name_lower for word in ['otros gastos', 'gastos varios', 'gastos generales', 'otros']):
                        if not generic_expense_id:
                            generic_expense_id = int(acc['id'])  # Ensure integer
                            print(f"Found generic expense category: {acc['name']} (ID: {acc['id']})")
                    
                    # Set a default if we haven't found one yet
                    elif not default_expense_id and 'salario' not in name_lower and 'nómina' not in name_lower:
                        default_expense_id = int(acc['id'])  # Ensure integer
                
                # If we didn't find specific categories, use any available expense account
                if not grocery_expense_id and expense_accounts:
                    # Try to find "Costo de ventas" or similar
                    for acc in expense_accounts:
                        if ('costo' in acc['name'].lower() or 'compra' in acc['name'].lower()) and acc['id'] != '5076':
                            grocery_expense_id = int(acc['id'])  # Ensure integer
                            print(f"Using cost/purchase category: {acc['name']} (ID: {acc['id']})")
                            break
                
                # Set default IDs with fallback chain
                if not default_expense_id:
                    if generic_expense_id:
                        default_expense_id = generic_expense_id
                    elif grocery_expense_id:
                        default_expense_id = grocery_expense_id
                    elif expense_accounts:
                        # Use first non-salary expense account
                        for acc in expense_accounts:
                            if acc['id'] != '5076' and 'salario' not in acc['name'].lower():
                                default_expense_id = int(acc['id'])  # Ensure integer
                                break
                        if not default_expense_id and expense_accounts:
                            default_expense_id = int(expense_accounts[0]['id'])  # Ensure integer
                
                # If still no expense categories, create one
                if not default_expense_id and len(expense_accounts) == 0:
                    print("No expense categories found, creating one...")
                    new_category_data = {
                        'name': 'Compras y Servicios',
                        'type': 'expense',
                        'parent': 5066,  # Parent is Egresos
                        'description': 'Gastos generales de compras y servicios'
                    }
                    
                    create_cat_response = requests.post(
                        'https://api.alegra.com/api/v1/categories',
                        json=new_category_data,
                        headers=headers
                    )
                    
                    if create_cat_response.status_code in [200, 201]:
                        created_cat = create_cat_response.json()
                        default_expense_id = int(created_cat.get('id'))  # Ensure integer
                        print(f"Created expense category with ID: {default_expense_id}")
                    else:
                        print(f"Failed to create category: {create_cat_response.text}")
                
                print(f"Default expense category ID: {default_expense_id}")
                print(f"Grocery category ID: {grocery_expense_id}")
                print(f"Generic expense category ID: {generic_expense_id}")
                
        else:
            print(f"Could not fetch expense categories: {accounts_response.status_code}")
        
        # Get taxes
        taxes_response = requests.get(
            'https://api.alegra.com/api/v1/taxes',
            headers=headers
        )
        available_taxes = []
        iva_tax_id = None
        if taxes_response.status_code == 200:
            taxes = taxes_response.json()
            for tax in taxes:
                if isinstance(tax, dict):
                    if 'IVA' in tax.get('name', '').upper() or tax.get('percentage') == 13:
                        iva_tax_id = int(tax['id'])
                        print(f"Found IVA tax with ID: {iva_tax_id}")
                        break
        
        # Process line items - either from XML or analyze with AI
        line_items_data = []
        
        if data.get('lineItems'):
            # If line items are already provided (from XML)
            print("Using pre-extracted line items from XML")
            line_items_data = data['lineItems']
        elif data.get('pdfText'):
            # Analyze PDF text with AI
            print("Analyzing PDF with AI to extract line items")
            line_items_data = analyze_invoice_items_with_ai(data['pdfText'], expense_accounts)
            
            # If AI returned a dict with line_items key, extract it
            if isinstance(line_items_data, dict) and 'line_items' in line_items_data:
                line_items_data = line_items_data['line_items']
        
        print(f"Found {len(line_items_data)} line items")
        
        # Create a purchase invoice (factura de proveedor)
        purchase_data = {
            'date': data['date'],
            'dueDate': data['date'],  # Same as invoice date for now
            'provider': int(data['contactId']),  # The vendor/provider
            'numberTemplate': {
                'number': data.get('invoiceNumber', '')  # Invoice number from PDF
            },
            'paymentMethod': data.get('paymentMethod', 'cash'),
            'observations': data.get('description', ''),
            'anotation': f"Factura registrada desde PDF: {data.get('description', '')}"
        }
        
        # Decide whether to use items or categories based on what's available
        # Force categories for purchase bills - items are for sales
        use_items = False  # Don't use items for purchases
        use_categories = True  # Always use categories for expenses
        
        # Use 5077 (Gastos Generales) as default if no expense categories found
        if not default_expense_id or default_expense_id in ['5066', '5065']:
            default_expense_id = 5077
            print(f"Using default expense category ID: {default_expense_id} (Gastos Generales)")
        
        print(f"Use items: {use_items} (item ID: {default_item_id})")
        print(f"Use categories: {use_categories} (category ID: {default_expense_id})")
        
        if use_items:
            # Use items approach - this is more reliable
            print("Using items approach for bill creation")
            
            # Calculate total amount from line items or use provided amount
            total_amount = float(data['amount'])
            if line_items_data:
                calculated_total = sum(
                    float(item.get('amount', 0)) if 'amount' in item 
                    else float(item.get('unit_price', 0)) * float(item.get('quantity', 1))
                    for item in line_items_data
                )
                if calculated_total > 0:
                    total_amount = calculated_total
            
            # Create items list for purchases.items structure
            items_list = []
            
            if line_items_data and len(line_items_data) > 0:
                # Create an item entry for each line item
                for idx, item in enumerate(line_items_data):
                    amount = float(item.get('amount', 0))
                    if 'unit_price' in item and 'quantity' in item:
                        amount = float(item['unit_price']) * float(item.get('quantity', 1))
                    
                    item_entry = {
                        'id': str(default_item_id),  # Ensure it's a string
                        'price': amount,
                        'quantity': float(item.get('quantity', 1))
                    }
                    
                    # Add tax if applicable
                    if item.get('has_tax') and iva_tax_id:
                        item_entry['tax'] = [{'id': iva_tax_id}]
                    
                    items_list.append(item_entry)
            else:
                # Single item for the entire invoice
                item_entry = {
                    'id': str(default_item_id),  # Ensure it's a string
                    'price': total_amount,
                    'quantity': 1
                }
                
                # Add tax
                if iva_tax_id:
                    item_entry['tax'] = [{'id': iva_tax_id}]
                    
                items_list.append(item_entry)
            
            # Use purchases.items structure for bills
            purchase_data['purchases'] = {
                'items': items_list
            }
            
            print(f"Using {len(items_list)} items in purchases.items structure")
            
        elif use_categories:
            # Use categories approach as fallback
            print("Using categories approach for bill creation")
            
            # Build categories from line items
            categories = []
            
            if line_items_data:
                # Process each line item
                for idx, item in enumerate(line_items_data):
                    # Find the account ID for this item
                    account_id = item.get('account_id')
                    
                    # If no account_id from AI or XML, use default
                    if not account_id:
                        account_id = 5077  # Gastos Generales
                        print(f"Line {idx+1}: No category determined by AI, using default ID: {account_id} (Gastos Generales)")
                    else:
                        # Ensure account_id is integer if provided
                        account_id = int(account_id)
                        print(f"Line {idx+1}: AI assigned category ID: {account_id}")
                    
                    # Calculate the amount (handle both unit_price * quantity and direct amount)
                    if 'unit_price' in item and 'quantity' in item:
                        amount = float(item['unit_price']) * float(item.get('quantity', 1))
                    else:
                        amount = float(item.get('amount', 0))
                    
                    # Build category entry
                    category_entry = {
                        'id': account_id,
                        'price': amount,
                        'quantity': float(item.get('quantity', 1)),
                        'observations': item.get('description', f'Línea {idx+1}')
                    }
                    
                    # Add tax if applicable
                    if item.get('has_tax') and iva_tax_id:
                        category_entry['tax'] = [{'id': iva_tax_id}]
                    
                    categories.append(category_entry)
            
            # If no categories yet, create a default one
            if not categories:
                print("No line items found, creating default category")
                categories.append({
                    'id': 5077,  # Gastos Generales as fallback
                    'price': float(data['amount']),
                    'quantity': 1,
                    'observations': data.get('description', 'Servicio'),
                    'tax': [{'id': iva_tax_id}] if iva_tax_id else []
                })
            
            purchase_data['purchases'] = {
                'categories': categories
            }
            print(f"Using {len(categories)} categories for bill")
        else:
            # Neither items nor valid categories available
            return jsonify({
                'error': 'No se encontraron items ni categorías contables válidas. Por favor configure al menos un item o categoría de gastos en Alegra.'
            }), 400
        
        print(f"Purchase data: {json.dumps(purchase_data, indent=2)}")
        
        # Create purchase invoice using direct API call
        response = requests.post(
            'https://api.alegra.com/api/v1/bills',
            json=purchase_data,
            headers=headers
        )
        
        if response.status_code == 201:
            bill = response.json()
            
            # Return line items info for UI display
            response_data = {
                'success': True,
                'bill': {
                    'id': bill['id'],
                    'number': bill.get('numberTemplate', {}).get('fullNumber', ''),
                    'amount': bill.get('total', 0)
                },
                'lineItems': []
            }
            
            # Add line items info for UI
            if 'purchases' in purchase_data and 'items' in purchase_data['purchases']:
                # If we used purchases.items structure
                for item in purchase_data['purchases']['items']:
                    response_data['lineItems'].append({
                        'description': data.get('description', 'Servicio'),
                        'amount': item.get('price', 0),
                        'hasTax': bool(item.get('tax'))
                    })
            elif 'purchases' in purchase_data and 'categories' in purchase_data['purchases']:
                # If we used purchases.categories structure
                for cat in purchase_data['purchases']['categories']:
                    response_data['lineItems'].append({
                        'description': cat.get('observations', cat.get('description', 'Servicio')),
                        'amount': cat.get('price', 0),
                        'hasTax': bool(cat.get('tax'))
                    })
            
            # If createPayment is true and paymentMethod is not 'credit', create a payment for this bill
            if data.get('createPayment', True) and data.get('paymentMethod', 'cash') != 'credit':
                payment_data = {
                    'date': data['date'],
                    'bankAccount': 1,  # Default bank account
                    'paymentMethod': data.get('paymentMethod', 'cash'),
                    'type': 'out',  # Outgoing payment (expense)
                    'bills': [{
                        'id': bill['id'],
                        'amount': float(data['amount'])
                    }],
                    'provider': int(data['contactId']),
                    'observations': f"Pago de factura {bill.get('numberTemplate', {}).get('fullNumber', '')}"
                }
                
                payment_response = requests.post(
                    'https://api.alegra.com/api/v1/payments',
                    json=payment_data,
                    headers=headers
                )
                
                if payment_response.status_code == 201:
                    payment = payment_response.json()
                    response_data['payment'] = {
                        'id': payment['id'],
                        'amount': payment['amount']
                    }
                else:
                    # Bill created but payment failed
                    response_data['warning'] = f'Factura creada pero el pago falló: {payment_response.text}'
            
            return jsonify(response_data)
        else:
            print(f"Error response from Alegra: {response.text}")
            return jsonify({
                'error': f'Error creando factura de compra: {response.text}'
            }), response.status_code
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error registrando factura: {str(e)}'}), 500

@app.route('/api/contacts/all', methods=['GET'])
def get_all_contacts():
    """Get all contacts with pagination"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        all_contacts = []
        page = 1
        limit = 30
        
        # Fetch all pages
        while True:
            print(f"Fetching page {page}...")
            response = requests.get(
                f'https://api.alegra.com/api/v1/contacts?limit={limit}&start={(page-1)*limit}',
                headers=headers
            )
            
            if response.status_code == 200:
                contacts = response.json()
                if isinstance(contacts, list):
                    all_contacts.extend(contacts)
                    if len(contacts) < limit:
                        break  # No more pages
                    page += 1
                else:
                    break
            else:
                print(f"Error on page {page}: {response.status_code}")
                break
        
        print(f"Total contacts fetched: {len(all_contacts)}")
        
        # Find CLARO specifically
        claro_contacts = []
        for contact in all_contacts:
            if isinstance(contact, dict):
                name = contact.get('name', '').lower()
                if 'claro' in name:
                    claro_contacts.append({
                        'id': contact.get('id'),
                        'name': contact.get('name', ''),
                        'identification': contact.get('identification', {}),
                        'email': contact.get('email', ''),
                        'type': contact.get('type', [])
                    })
        
        # Format first 50 contacts for display
        formatted_contacts = []
        for contact in all_contacts[:50]:
            if isinstance(contact, dict):
                formatted_contacts.append({
                    'id': contact.get('id'),
                    'name': contact.get('name', ''),
                    'identification': contact.get('identification', {}),
                    'email': contact.get('email', ''),
                    'type': contact.get('type', [])
                })
        
        return jsonify({
            'total': len(all_contacts),
            'showing': len(formatted_contacts),
            'claro_contacts': claro_contacts,
            'contacts': formatted_contacts
        })
        
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/accounts-catalog', methods=['GET'])
def get_accounts_catalog():
    """Get the accounting accounts catalog"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Get all accounting accounts
        all_accounts = []
        page = 1
        limit = 100
        
        while True:
            response = requests.get(
                f'https://api.alegra.com/api/v1/categories?limit={limit}&start={(page-1)*limit}',
                headers=headers
            )
            
            if response.status_code == 200:
                accounts = response.json()
                if isinstance(accounts, list):
                    all_accounts.extend(accounts)
                    if len(accounts) < limit:
                        break
                    page += 1
                else:
                    break
            else:
                break
        
        # Filter and organize accounts
        expense_accounts = []
        for account in all_accounts:
            if isinstance(account, dict):
                # Focus on expense accounts (typically 5xxx and 6xxx)
                account_code = str(account.get('code', ''))
                if account_code.startswith(('5', '6')) and account.get('type') != 'ingresos':
                    expense_accounts.append({
                        'id': account.get('id'),
                        'code': account_code,
                        'name': account.get('name', ''),
                        'type': account.get('type', ''),
                        'description': account.get('description', '')
                    })
        
        return jsonify({
            'total': len(all_accounts),
            'expense_accounts': sorted(expense_accounts, key=lambda x: x['code'])
        })
        
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/taxes', methods=['GET'])
def get_taxes():
    """Get available taxes"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://api.alegra.com/api/v1/taxes',
            headers=headers
        )
        
        if response.status_code == 200:
            taxes = response.json()
            # Focus on IVA/sales tax
            sales_taxes = []
            for tax in taxes:
                if isinstance(tax, dict) and 'IVA' in tax.get('name', '').upper():
                    sales_taxes.append({
                        'id': tax.get('id'),
                        'name': tax.get('name'),
                        'percentage': tax.get('percentage', 0)
                    })
            
            return jsonify({'taxes': sales_taxes})
        else:
            return jsonify({'error': 'Error getting taxes'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/bank-accounts', methods=['GET'])
def get_bank_accounts():
    try:
        # Get bank accounts using direct API call
        import requests
        import base64
        
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://api.alegra.com/api/v1/bank-accounts',
            headers=headers
        )
        
        if response.status_code == 200:
            accounts = response.json()
            return jsonify({'accounts': accounts})
        else:
            return jsonify({'error': 'Error obteniendo cuentas bancarias'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/debug/categories', methods=['GET'])
def debug_categories():
    """Debug endpoint to check categories structure"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://api.alegra.com/api/v1/categories?limit=200',
            headers=headers
        )
        
        if response.status_code == 200:
            categories = response.json()
            
            # Filter expense categories
            expense_categories = []
            parent_categories = []
            usable_categories = []
            
            for cat in categories:
                if isinstance(cat, dict) and cat.get('type') == 'expense':
                    cat_info = {
                        'id': cat.get('id'),
                        'code': cat.get('code'),
                        'name': cat.get('name'),
                        'type': cat.get('type'),
                        'status': cat.get('status', 'unknown')
                    }
                    
                    # Check if it's a parent category
                    if cat.get('id') in ['5066', '5065'] or cat.get('name', '').lower() in ['egresos', 'ingresos']:
                        parent_categories.append(cat_info)
                    else:
                        expense_categories.append(cat_info)
                        # Check if it's usable (not disabled)
                        if cat.get('status') != 'inactive' and 'salario' not in cat.get('name', '').lower():
                            usable_categories.append(cat_info)
            
            return jsonify({
                'total_categories': len(categories),
                'expense_categories': expense_categories[:20],
                'parent_categories': parent_categories,
                'usable_expense_categories': usable_categories[:20],
                'types_found': list(set(cat.get('type') for cat in categories if isinstance(cat, dict)))
            })
        else:
            return jsonify({'error': response.text}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/expense-categories', methods=['GET'])
def get_expense_categories():
    """Get expense subcategories"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Get the specific expense category (Egresos) which has id 5066
        response = requests.get(
            'https://api.alegra.com/api/v1/categories/5066',
            headers=headers
        )
        
        if response.status_code == 200:
            category = response.json()
            
            # Get children categories if they exist
            children = category.get('children', [])
            
            # If no children in the response, try to get all categories and filter
            if not children:
                all_response = requests.get(
                    'https://api.alegra.com/api/v1/categories?limit=200',
                    headers=headers
                )
                if all_response.status_code == 200:
                    all_categories = all_response.json()
                    # Find expense type categories that are not top-level
                    expense_categories = []
                    for cat in all_categories:
                        if isinstance(cat, dict):
                            # Check if it's an expense category and has a proper code
                            if (cat.get('type') == 'expense' and 
                                cat.get('id') != '5066' and  # Not the parent Egresos
                                cat.get('code') is not None):
                                expense_categories.append({
                                    'id': cat['id'],
                                    'code': cat.get('code', ''),
                                    'name': cat['name'],
                                    'description': cat.get('description', '')
                                })
                    
                    return jsonify({
                        'expense_categories': expense_categories,
                        'total': len(expense_categories)
                    })
            
            return jsonify({
                'parent': {
                    'id': category.get('id'),
                    'name': category.get('name'),
                    'type': category.get('type')
                },
                'children': children,
                'has_children': len(children) > 0
            })
        else:
            return jsonify({'error': response.text}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-bill', methods=['GET'])
def test_bill():
    """Test creating a simple bill"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # First get all items
        items_resp = requests.get(
            'https://api.alegra.com/api/v1/items?limit=30',
            headers=headers
        )
        
        items = []
        if items_resp.status_code == 200:
            items = items_resp.json()
        
        results = []
        
        # Try each item to see which ones work for bills
        for item in items[:10]:  # Test first 10 items
            test_data = {
                'date': '2025-01-27',
                'dueDate': '2025-01-27',
                'provider': 9,  # CLARO
                'purchases': {
                    'items': [{
                        'id': str(item['id']),  # Ensure string
                        'price': 100,
                        'quantity': 1
                    }]
                }
            }
            
            response = requests.post(
                'https://api.alegra.com/api/v1/bills',
                json=test_data,
                headers=headers
            )
            
            results.append({
                'item_id': item['id'],
                'item_name': item['name'],
                'item_type': item.get('type', 'N/A'),
                'category': item.get('category', {}).get('name', 'N/A') if item.get('category') else 'N/A',
                'status_code': response.status_code,
                'response': response.text[:100] if response.status_code != 201 else 'SUCCESS - Bill Created!',
            })
            
            # If one works, we found it!
            if response.status_code == 201:
                results.append({
                    'note': f'WORKING ITEM FOUND: ID {item["id"]} - {item["name"]}'
                })
                break
        
        return jsonify({
            'items_tested': len(results),
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-expense-category', methods=['POST'])
def create_expense_category():
    """Create a basic expense category for purchases"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Create a "Compras Generales" category under Egresos
        category_data = {
            'name': 'Compras Generales',
            'type': 'expense',
            'parent': 5066,  # Parent is Egresos
            'description': 'Gastos generales de compras y suministros'
        }
        
        response = requests.post(
            'https://api.alegra.com/api/v1/categories',
            json=category_data,
            headers=headers
        )
        
        if response.status_code in [200, 201]:
            return jsonify({
                'success': True,
                'category': response.json()
            })
        else:
            return jsonify({
                'error': response.text
            }), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/init', methods=['GET'])
def system_init():
    """Check and initialize system with default items/categories if needed"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Check items
        items_response = requests.get(
            'https://api.alegra.com/api/v1/items?limit=10',
            headers=headers
        )
        
        items_count = 0
        default_item = None
        if items_response.status_code == 200:
            items = items_response.json()
            if isinstance(items, list):
                items_count = len(items)
                for item in items:
                    if 'general' in item.get('name', '').lower() or 'servicio' in item.get('name', '').lower():
                        default_item = {
                            'id': item.get('id'),
                            'name': item.get('name'),
                            'reference': item.get('reference')
                        }
                        break
        
        # Check expense categories
        categories_response = requests.get(
            'https://api.alegra.com/api/v1/categories?limit=200',
            headers=headers
        )
        
        expense_categories = []
        if categories_response.status_code == 200:
            categories = categories_response.json()
            if isinstance(categories, list):
                for cat in categories:
                    if (cat.get('type') == 'expense' and 
                        cat.get('id') not in ['5066', '5065'] and
                        cat.get('name', '').lower() not in ['egresos', 'ingresos']):
                        expense_categories.append({
                            'id': cat.get('id'),
                            'code': cat.get('code'),
                            'name': cat.get('name')
                        })
        
        # Get taxes
        taxes_response = requests.get(
            'https://api.alegra.com/api/v1/taxes',
            headers=headers
        )
        
        iva_tax = None
        if taxes_response.status_code == 200:
            taxes = taxes_response.json()
            for tax in taxes:
                if isinstance(tax, dict) and ('IVA' in tax.get('name', '').upper() or tax.get('percentage') == 13):
                    iva_tax = {
                        'id': tax.get('id'),
                        'name': tax.get('name'),
                        'percentage': tax.get('percentage')
                    }
                    break
        
        return jsonify({
            'items': {
                'count': items_count,
                'default_item': default_item,
                'needs_creation': items_count == 0
            },
            'categories': {
                'expense_count': len(expense_categories),
                'expense_categories': expense_categories[:10],  # First 10
                'needs_creation': len(expense_categories) == 0
            },
            'taxes': {
                'iva_configured': iva_tax is not None,
                'iva_tax': iva_tax
            },
            'ready': (items_count > 0 or len(expense_categories) > 0) and iva_tax is not None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/system/setup', methods=['POST'])
def system_setup():
    """Setup default items for the system"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        created = {
            'items': [],
            'errors': []
        }
        
        # Check if we have any items
        items_response = requests.get(
            'https://api.alegra.com/api/v1/items?limit=10',
            headers=headers
        )
        
        existing_items = []
        if items_response.status_code == 200:
            existing_items = items_response.json()
            if not isinstance(existing_items, list):
                existing_items = []
        
        # Create default items if we don't have any
        if len(existing_items) == 0:
            print("No items found, creating default items...")
            
            default_items = [
                {
                    'name': 'Compras Generales',
                    'description': 'Compras y gastos generales',
                    'price': 0,
                    'reference': 'COMPRAS-001',
                    'type': 'service',
                    'category': None  # Don't assign to sales category
                },
                {
                    'name': 'Servicios Profesionales',
                    'description': 'Servicios profesionales y consultorías',
                    'price': 0,
                    'reference': 'SERVICIOS-001',
                    'type': 'service',
                    'category': None
                },
                {
                    'name': 'Gastos Operativos',
                    'description': 'Gastos operativos diversos',
                    'price': 0,
                    'reference': 'GASTOS-001',
                    'type': 'service',
                    'category': None
                }
            ]
            
            for item_data in default_items:
                create_response = requests.post(
                    'https://api.alegra.com/api/v1/items',
                    json=item_data,
                    headers=headers
                )
                
                if create_response.status_code in [200, 201]:
                    created_item = create_response.json()
                    created['items'].append(created_item)
                    print(f"Created item: {created_item.get('name')} (ID: {created_item.get('id')})")
                else:
                    error_msg = f"Error creating item {item_data['name']}: {create_response.text}"
                    created['errors'].append(error_msg)
                    print(error_msg)
        else:
            print(f"Found {len(existing_items)} existing items")
        
        return jsonify({
            'success': len(created['errors']) == 0,
            'created_items': created['items'],
            'existing_items': len(existing_items),
            'errors': created['errors'],
            'message': f"Sistema configurado con {len(created['items'])} items nuevos" if len(created['errors']) == 0 else 'Configuración con errores'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/items', methods=['GET'])
def get_items():
    """Get all items"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            'https://api.alegra.com/api/v1/items?limit=30',
            headers=headers
        )
        
        if response.status_code == 200:
            items = response.json()
            return jsonify({
                'items': items,
                'count': len(items) if isinstance(items, list) else 0
            })
        else:
            return jsonify({'error': response.text}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-purchase-item', methods=['POST'])
def create_purchase_item():
    """Create an item specifically for purchases/bills"""
    try:
        import base64
        credentials = f"{alegra.user}:{alegra.token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # Create an item without category (so it's not a sales item)
        item_data = {
            'name': 'Gastos y Compras Generales',
            'description': 'Item para registro de facturas de proveedores',
            'reference': 'GASTO-GENERAL',
            'type': 'service',
            'price': 0  # Price will be set per invoice
        }
        
        response = requests.post(
            'https://api.alegra.com/api/v1/items',
            json=item_data,
            headers=headers
        )
        
        if response.status_code in [200, 201]:
            item = response.json()
            return jsonify({
                'success': True,
                'item': item,
                'message': f'Item creado con ID: {item["id"]}'
            })
        else:
            return jsonify({
                'error': response.text
            }), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001) 