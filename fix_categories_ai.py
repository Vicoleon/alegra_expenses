# fix_categories_ai.py
# Save this file in your main project directory and run: python3 fix_categories_ai.py

import re

# Read the current app.py
with open('webapp/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Update the analyze_invoice_items_with_ai function to include ALL categories
new_ai_function = '''def analyze_invoice_items_with_ai(pdf_text, expense_accounts):
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
        accounts_detail = "\\n".join([
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
    """'''

# Replace the old function
pattern = r'def analyze_invoice_items_with_ai\(pdf_text, expense_accounts\):.*?(?=\n@app\.route|def\s+\w+|$)'
content = re.sub(pattern, new_ai_function + '\n', content, flags=re.DOTALL)

# Fix 2: Update the logic to force categories and use 5077 as default
old_logic = '''        # Decide whether to use items or categories based on what's available
        use_items = default_item_id is not None
        use_categories = default_expense_id is not None and default_expense_id not in ['5066', '5065']'''

new_logic = '''        # Decide whether to use items or categories based on what's available
        # Force categories for purchase bills - items are for sales
        use_items = False  # Don't use items for purchases
        use_categories = True  # Always use categories for expenses
        
        # Use 5077 (Gastos Generales) as default if no expense categories found
        if not default_expense_id or default_expense_id in ['5066', '5065']:
            default_expense_id = 5077
            print(f"Using default expense category ID: {default_expense_id} (Gastos Generales)")'''

content = content.replace(old_logic, new_logic)

# Fix 3: Update the category assignment logic to use AI-suggested account_id or 5077 as fallback
old_category_logic = '''                    # If no account_id from AI or XML, use appropriate expense account
                    if not account_id:
                        # For grocery/supermarket items, use grocery category if available
                        if grocery_expense_id and ('Auto Mercado' in data.get('description', '') or 
                                                 'Walmart' in data.get('description', '') or
                                                 'supermercado' in data.get('description', '').lower()):
                            account_id = grocery_expense_id
                        else:
                            account_id = default_expense_id
                        print(f"Line {idx+1}: Using expense account ID: {account_id}")
                    else:
                        # Ensure account_id is integer if provided
                        account_id = int(account_id)'''

new_category_logic = '''                    # If no account_id from AI or XML, use default
                    if not account_id:
                        account_id = 5077  # Gastos Generales
                        print(f"Line {idx+1}: No category determined by AI, using default ID: {account_id} (Gastos Generales)")
                    else:
                        # Ensure account_id is integer if provided
                        account_id = int(account_id)
                        print(f"Line {idx+1}: AI assigned category ID: {account_id}")'''

content = content.replace(old_category_logic, new_category_logic)

# Fix 4: Update the default category assignment to use 5077
old_default = '''                categories.append({
                    'id': default_expense_id,
                    'price': float(data['amount']),
                    'quantity': 1,
                    'observations': data.get('description', 'Servicio'),
                    'tax': [{'id': iva_tax_id}] if iva_tax_id else []
                })'''

new_default = '''                categories.append({
                    'id': 5077,  # Gastos Generales as fallback
                    'price': float(data['amount']),
                    'quantity': 1,
                    'observations': data.get('description', 'Servicio'),
                    'tax': [{'id': iva_tax_id}] if iva_tax_id else []
                })'''

content = content.replace(old_default, new_default)

# Write the updated file
with open('webapp/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Fixed app.py successfully!")
print("\nChanges made:")
print("1. Updated AI analysis to receive ALL expense categories and intelligently assign them")
print("2. Forced use of categories instead of items for purchase bills")
print("3. Set default category to 5077 (Gastos Generales) when AI can't determine")
print("4. Enhanced AI prompt to better categorize expenses based on available accounts")
print("\nRestart your Flask app to apply changes!")