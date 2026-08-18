#!/usr/bin/env python3

from bottle import route, run, template, abort, request, debug, HTTPResponse 
from datetime import date
import os
import sqlite3
import umsgpack
import json

database = "data/db"

increase_sql = 'UPDATE products_control SET quantity = quantity + 1 WHERE pID = ?'
decrease_sql = 'UPDATE products_control SET quantity = quantity - 1, last_update = CURRENT_DATE WHERE pID = ?'
delete_sql = 'DELETE FROM product WHERE uID = ?'

@route('/save/<pID:int>/<uID>', method='POST')
def save(pID, uID):
    if pID != 0 and uID is not None: 
        try: 
            if not isProduct(uID) and isUID_valid(uID):
                color = give_color(uID)
                insert_row_to_product_table(pID, uID, color)

            if not isProduct_control(pID):
                color = give_color(uID)
                insert_row_to_products_control_table(pId, uID, color)

            return bottle.HTTPResponse(status = 200, headers = {'status': '200', 'CPEE-CALLBACK' : 'true'})

        #{"status": "success", 
        #            "uID": uID
        #            }

        except sqlite3.OperationalError as e: 
            print(e)
            abort(502, "Database error")
    else:
        abort(400, "Incorrect parametersi sended")
        
@route('/sync', method='POST')
def sync_inventory():

    raw_body_str = request.forms.get('qr_data') or request.forms.get('body')
    
    if not raw_body_str:
        raw_bytes = request.body.read()
        if raw_bytes:
            raw_body_str = raw_bytes.decode('utf-8')
            
    print(raw_body_str)

    if not raw_body_str:
        abort(400, "Empty payload received.")

    try:
        # 1. Convertir el texto JSON entrante y extraer 'qr_data'
        parsed_data = json.loads(raw_body_str)
        
        if isinstance(parsed_data, dict):
            string_list = parsed_data.get('qr_data')
        else:
            string_list = parsed_data
            
        if not isinstance(string_list, list):
            abort(400, "Invalid payload. Expected a JSON array in 'qr_data'.")

        scan_data = []

        import msgpack

        # 2. Recuperar los bytes de cada string y desempaquetar el MessagePack
        for item_str in string_list:
            # Intentamos deshacer el "mojibake" por doble encoding (utf-8 sobre latin-1)
            try:
                raw_bytes = item_str.encode('latin-1').decode('utf-8').encode('latin-1')
            except UnicodeError:
                # Si falla, usamos conversión directa asumiendo que no tiene mojibake
                raw_bytes = item_str.encode('latin-1')
            
            # Desempaquetar los bytes reales
            unpacker = msgpack.Unpacker()
            unpacker.feed(raw_bytes)
            objs = list(unpacker)
            
            # Formatear la secuencia de (clave, valor) a diccionario si es necesario
            if len(objs) > 1 and len(objs) % 2 == 0 and not isinstance(objs[0], dict):
                decoded_item = {}
                for i in range(0, len(objs), 2):
                    key = objs[i]
                    val = objs[i+1]
                    if isinstance(key, bytes):
                        key = key.decode('utf-8', errors='ignore')
                    if isinstance(val, bytes):
                        val = val.decode('utf-8', errors='ignore')
                    decoded_item[key] = val
            elif len(objs) == 1:
                decoded_item = objs[0]
                if isinstance(decoded_item, dict):
                    new_item = {}
                    for k, v in decoded_item.items():
                        if isinstance(k, bytes): k = k.decode('utf-8', errors='ignore')
                        if isinstance(v, bytes): v = v.decode('utf-8', errors='ignore')
                        new_item[k] = v
                    decoded_item = new_item
            else:
                decoded_item = objs
                
            scan_data.append(decoded_item)

        print(f"Decoded Payload: {scan_data}")

    except json.JSONDecodeError:
        abort(400, "Invalid JSON format in 'body'.")
    except Exception as e:
        print(f"MessagePack decoding error: {e}")
        abort(400, "Invalid MessagePack payload.")


    scanned_groups = {}
    uID_colors = {}

    for item in scan_data:
        pID = item.get('pID')
        uID = item.get('uID')
        color = item.get('color')

        if not pID or not isUID_valid(uID):
            continue

        if pID not in scanned_groups:
            scanned_groups[pID] = set()

        scanned_groups[pID].add(uID)
        uID_colors[uID] = color

    try:
        for pID, scanned_uids in scanned_groups.items():
            
            # Ensure the control group exists
            if not isProduct_control(pID):
                sample_color = uID_colors[list(scanned_uids)[0]]
                insert_row_to_products_control_table(pID, sample_color)

            database_uids = get_uids_for_pid(pID)

            items_to_add = scanned_uids - database_uids
            items_to_remove = database_uids - scanned_uids

            # Process Additions
            for uID in items_to_add:
                insert_row_to_product_table(pID, uID, uID_colors[uID])
                increaseProduct(pID)

            for uID in items_to_remove:
                deleteProduct(uID)
                decreaseProduct(pID)

        return HTTPResponse(status = 200, headers = {'status': '200', 'CPEE-CALLBACK' : 'true'}) # TODO think what the server should return to the cpee, what info is relevant for this case


    #    {
    #        "status": "success", 
    #        "message": "Inventory synchronized successfully."
    #    }

    except Exception as e:
        print(f"Sync error: {e}")
        abort(502, "Database error during synchronization")


## Database methods

def increaseProduct(pID):
    try: 
        with sqlite3.connect(database) as conn: 
            cursor = conn.cursor()
            cursor.execute(increase_sql,(pID,))
            conn.commit()
    except sqlite3.OperationalError as e:
        print(e)

def decreaseProduct(pID):
    try:
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()
            cursor.execute(decrease_sql, (pID,))
            conn.commit()
    except sqlite3.OperationalError as e:
        print(e)

def deleteProduct(uID):
    try:
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()
            cursor.execute(delete_sql, (uID,))
            conn.commit()
    except sqlite3.OperationalError as e:
        print(e)

def insert_row_to_products_control_table(pID, color):
    sql = ''' INSERT INTO products_control(pID, color, quantity, last_update)
              values(?,?,?,?)'''

    try: 
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()

            current_date = date.today().isoformat()

            cursor.execute(sql, (pID, color, 0, current_date))
            conn.commit()
    except sqlite3.OperationalError as e: 
        print(e)

def isProduct_control(pID):
    sql = ''' SELECT exists(SELECT 1 FROM products_control WHERE pID = ?) AS product_exists'''

    try:  
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, [pID])
            result = cursor.fetchone()
            return bool(result[0])
    except sqlite3.OperationalError as e:
        print(e)
        return False


def insert_row_to_product_table(pID, uID, color):
    sql = '''INSERT INTO product(pID, uID, color, created_at)
            values(?,?,?, CURRENT_DATE)'''
    try:
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()
            cursor.execute(sql,(pID, uID, color))
            conn.commit()
    except sqlite3.OperationalError as e: 
            print(e)

def isProduct(uID): # Check if a product exists in product table with the unique ID 
    sql = ''' SELECT exists(SELECT 1 FROM product WHERE uID = ?) AS product_exists'''

    try: 
        with sqlite3.connect(database) as conn: 
            cursor = conn.cursor()
            cursor.execute(sql, [uID])
            result = cursor.fetchone()
            return bool(result[0])
    except sqlite3.OperationalError as e:
        print(e)
        return False

def isUID_valid(uID):
    if not uID:
        return False

    valid_pref = ['A', 'R', 'Am', 'C']

    parts = uID.split('_')

    if len(parts) != 2: 
        return False

    prefix, number = parts

    if prefix in valid_pref and number.isdigit():
        return True

    return False

def give_color(uID):
    if not isUID_valid(uID):
        return None
    
    colors_dict = {'A':"azul", 'R': 'rojo', 'Am': 'amarillo', 'C': 'cafe'}

    parts = uID.split('_')

    prefix, _ = parts

    return colors_dict[prefix]

def get_uids_for_pid(pID):
    sql = '''SELECT uID FROM product WHERE pID = ?'''
    uids = set()
    try:
        with sqlite3.connect(database) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (pID,))
            rows = cursor.fetchall()
            
            # Extract the uID string from the tuple and add to the set
            for row in rows:
                uids.add(row[0])
                
        return uids
    except sqlite3.OperationalError as e:
        print(e)
        return set() 

if  __name__ == '__main__':
    debug(True)
    #run(host='::0', port=40201)
    run(host='localhost', port=8080)
#   print(isProduct_control(123))
#    print(isUID_valid('A_34'))
#    print(isUID_valid('Z_2'))

