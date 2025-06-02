import os
import requests
import base64
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

alegra_user = os.environ.get('ALEGRA_USER')
alegra_token = os.environ.get('ALEGRA_TOKEN')

# Create auth header
credentials = f"{alegra_user}:{alegra_token}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()
headers = {
    'Authorization': f'Basic {encoded_credentials}',
    'Content-Type': 'application/json'
}

print("Testing Alegra API...")
print(f"User: {alegra_user}")

# Test 1: Get existing items first
print("\n1. Getting existing items:")
items_response = requests.get(
    'https://api.alegra.com/api/v1/items?limit=5',
    headers=headers
)
print(f"Items status: {items_response.status_code}")
existing_item_id = None
if items_response.status_code == 200:
    items = items_response.json()
    print(f"Found {len(items)} items")
    for item in items[:3]:
        print(f"- Item ID: {item.get('id')}, Name: {item.get('name')}")
        if existing_item_id is None:
            existing_item_id = item.get('id')

# Test 2: Try to create a bill with existing item ID
if existing_item_id:
    print(f"\n2. Testing bill creation with existing item ID {existing_item_id}:")
    bill_data = {
        "date": "2025-01-27",
        "dueDate": "2025-01-27", 
        "provider": 9,  # CLARO
        "items": [
            {
                "id": existing_item_id,  # Use existing item
                "price": 100,
                "quantity": 1
            }
        ]
    }
    
    response = requests.post(
        'https://api.alegra.com/api/v1/bills',
        json=bill_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")

# Test 3: Get categories to use the right structure
print("\n3. Getting expense categories:")
categories_response = requests.get(
    'https://api.alegra.com/api/v1/categories?type=expense&limit=10',
    headers=headers
)
print(f"Categories status: {categories_response.status_code}")
expense_category_id = None
if categories_response.status_code == 200:
    categories = categories_response.json()
    print(f"Found {len(categories)} categories")
    for cat in categories[:5]:
        if cat.get('type') == 'expense' and cat.get('id') != '5066':
            print(f"- Category ID: {cat.get('id')}, Name: {cat.get('name')}, Type: {cat.get('type')}")
            if expense_category_id is None:
                expense_category_id = cat.get('id')

# Test 4: Try with purchases.categories structure
if expense_category_id:
    print(f"\n4. Testing bill creation with purchases.categories structure using category {expense_category_id}:")
    bill_data = {
        "date": "2025-01-27",
        "dueDate": "2025-01-27", 
        "provider": 9,  # CLARO
        "purchases": {
            "categories": [
                {
                    "id": expense_category_id,
                    "price": 100,
                    "quantity": 1,
                    "tax": [{"id": 3}]  # IVA
                }
            ]
        }
    }
    
    response = requests.post(
        'https://api.alegra.com/api/v1/bills',
        json=bill_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 201:
        print("SUCCESS! Bill created with purchases.categories structure") 