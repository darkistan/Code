import sqlite3
import csv
import os
import shutil
from datetime import datetime
from typing import Optional, List
import json
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from pydantic import BaseModel

# Создание директорий если их нет
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("static/documents", exist_ok=True)

app = FastAPI(title="Мобильная инвентаризация")

# Настройка шаблонов и статических файлов
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Функции локализации
def load_locale(lang: str = 'ru') -> dict:
    """Загружает локализацию для указанного языка"""
    try:
        with open(f'static/locales/{lang}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Если файл не найден, возвращаем русскую локализацию по умолчанию
        with open('static/locales/ru.json', 'r', encoding='utf-8') as f:
            return json.load(f)

def get_user_language(request: Request) -> str:
    """Получает язык пользователя из cookies или заголовков"""
    # Сначала проверяем cookie
    lang = request.cookies.get('language', None)
    if lang in ['ru', 'uk']:
        return lang
    
    # Если cookie нет, проверяем заголовок Accept-Language
    accept_language = request.headers.get('accept-language', '')
    if 'uk' in accept_language.lower():
        return 'uk'
    
    return 'ru'  # По умолчанию русский

# Модели данных
class User(BaseModel):
    id: int
    name: str
    created_at: str

class Document(BaseModel):
    id: int
    user_id: int
    doc_type: str
    status: str
    created_at: str
    closed_at: Optional[str] = None

class Barcode(BaseModel):
    id: int
    document_id: int
    barcode: str
    created_at: str

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Таблица документов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doc_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            closed_at TEXT,
            comment TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Добавляем колонку comment если её нет (для существующих БД)
    cursor.execute("PRAGMA table_info(documents)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'comment' not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN comment TEXT DEFAULT ''")
        conn.commit()
    
    # Таблица штрихкодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS barcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            barcode TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    conn.commit()
    
    # Создаем администратора если его нет
    cursor.execute("SELECT id FROM users WHERE name = ?", ("Администратор",))
    if not cursor.fetchone():
        # Проверяем, что администратор есть в файле users.txt
        try:
            with open('users.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('Администратор:'):
                        cursor.execute(
                            "INSERT INTO users (name, created_at) VALUES (?, ?)",
                            ("Администратор", datetime.now().isoformat())
                        )
                        conn.commit()
                        print("Пользователь 'Администратор' автоматически создан в БД")
                        break
        except FileNotFoundError:
            pass
    
    conn.close()

# Инициализация БД при запуске
init_db()

# Вспомогательные функции для работы с БД
def get_db_connection():
    conn = sqlite3.connect('db.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# Логотип теперь постоянный SVG файл

def load_users_from_file():
    """Загружает пользователей из файла users.txt"""
    users = {}
    try:
        with open('users.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    name, pin = line.split(':', 1)
                    users[name.strip()] = pin.strip()
    except FileNotFoundError:
        print("Файл users.txt не найден. Создайте файл с пользователями в формате: Имя:ПИН")
    return users

def authenticate_user(name: str, pin: str) -> bool:
    """Проверяет пользователя и пин-код"""
    users = load_users_from_file()
    return name in users and users[name] == pin

def is_admin(user_name: str) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_name == "admin"

def get_all_documents() -> List[dict]:
    """Получает все документы всех пользователей (для админа)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT d.*, u.name as user_name 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        ORDER BY d.created_at DESC
    """)
    documents = cursor.fetchall()
    conn.close()
    
    return [dict(doc) for doc in documents]

def get_all_users():
    """Получить всех пользователей из базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users ORDER BY name")
    users = cursor.fetchall()
    conn.close()
    
    return [dict(user) for user in users]

def add_user_to_system(name: str, pin: str):
    """Добавить пользователя в систему (в users.txt и в базу данных)"""
    # Добавляем в users.txt
    with open('users.txt', 'a', encoding='utf-8') as f:
        f.write(f'\n{name}:{pin}')
    
    # Добавляем в базу данных
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO users (name, created_at) VALUES (?, ?)",
        (name, datetime.now().isoformat())
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return user_id

def delete_user_from_system(user_id: int):
    """Удалить пользователя из системы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем имя пользователя
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False
    
    user_name = user['name']
    
    # Удаляем из базы данных (каскадно удалятся документы и штрихкоды)
    cursor.execute("DELETE FROM barcodes WHERE document_id IN (SELECT id FROM documents WHERE user_id = ?)", (user_id,))
    cursor.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    
    conn.commit()
    conn.close()
    
    # Удаляем из users.txt
    try:
        with open('users.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open('users.txt', 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip() and not line.strip().startswith(f'{user_name}:'):
                    f.write(line)
    except Exception as e:
        print(f"Ошибка при удалении пользователя из users.txt: {e}")
    
    return True

def admin_delete_document(document_id: int) -> bool:
    """Удаляет документ (админская функция)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о документе для удаления CSV файла
    cursor.execute("""
        SELECT d.*, u.name as user_name 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        WHERE d.id = ?
    """, (document_id,))
    document = cursor.fetchone()
    
    if not document:
        conn.close()
        return False
    
    # Удаляем CSV файл если он существует
    if document['status'] == 'closed':
        try:
            doc_date = datetime.fromisoformat(document['created_at']).strftime('%Y%m%d_%H%M%S')
            csv_filename = f"{document['doc_type']}_{document['user_name']}_{doc_date}.csv"
            csv_filepath = os.path.join("static", "documents", csv_filename)
            
            if os.path.exists(csv_filepath):
                os.remove(csv_filepath)
                print(f"Админ удалил CSV файл: {csv_filename}")
        except Exception as e:
            print(f"Ошибка при удалении CSV файла: {e}")
    
    # Удаляем штрихкоды документа
    cursor.execute("DELETE FROM barcodes WHERE document_id = ?", (document_id,))
    
    # Удаляем сам документ
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    
    conn.commit()
    conn.close()
    return True

def get_or_create_user(name: str) -> int:
    """Получает пользователя из БД или создает его если он есть в файле"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, существует ли пользователь в БД
    cursor.execute("SELECT id FROM users WHERE name = ?", (name,))
    user = cursor.fetchone()
    
    if user:
        user_id = user['id']
    else:
        # Создаем пользователя в БД только если он есть в файле
        users_file = load_users_from_file()
        if name in users_file:
            cursor.execute(
                "INSERT INTO users (name, created_at) VALUES (?, ?)",
                (name, datetime.now().isoformat())
            )
            user_id = cursor.lastrowid
            conn.commit()
        else:
            conn.close()
            return None
    
    conn.close()
    return user_id

def create_document(user_id: int, doc_type: str, comment: str = '') -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO documents (user_id, doc_type, status, created_at, comment) VALUES (?, ?, 'active', ?, ?)",
        (user_id, doc_type, datetime.now().isoformat(), comment)
    )
    document_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return document_id

def get_active_document(user_id: int) -> Optional[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM documents WHERE user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    doc = cursor.fetchone()
    conn.close()
    
    return dict(doc) if doc else None

def get_document_barcodes(document_id: int) -> List[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM barcodes WHERE document_id = ? ORDER BY created_at DESC",
        (document_id,)
    )
    barcodes = cursor.fetchall()
    conn.close()
    
    return [dict(barcode) for barcode in barcodes]

def get_document_barcodes_sorted(document_id: int) -> List[dict]:
    """Получает штрихкоды документа, отсортированные по значению для группировки одинаковых рядом"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем все штрихкоды, отсортированные по значению, затем по времени
    cursor.execute("""
        SELECT id, barcode, created_at
        FROM barcodes 
        WHERE document_id = ? 
        ORDER BY barcode, created_at DESC
    """, (document_id,))
    
    all_barcodes = cursor.fetchall()
    
    # Подсчитываем количество каждого штрихкода
    cursor.execute("""
        SELECT barcode, COUNT(*) as count
        FROM barcodes 
        WHERE document_id = ? 
        GROUP BY barcode
    """, (document_id,))
    
    barcode_counts = dict(cursor.fetchall())
    conn.close()
    
    result = []
    barcode_sequence = {}  # Для подсчета номера среди одинаковых
    barcode_color_index = {}  # Для определения цвета для каждого штрихкода
    
    for row in all_barcodes:
        barcode_value = row[1]
        
        # Увеличиваем счетчик для этого штрихкода
        if barcode_value not in barcode_sequence:
            barcode_sequence[barcode_value] = 0
            barcode_color_index[barcode_value] = 0
        barcode_sequence[barcode_value] += 1
        
        # Определяем цветовой индекс для парных штрихкодов
        color_index = 0
        if barcode_counts[barcode_value] > 1:
            # Для парных штрихкодов используем чередующиеся цвета
            color_index = (barcode_sequence[barcode_value] - 1) % 4  # 4 цвета: 0, 1, 2, 3
        
        result.append({
            'id': row[0],
            'barcode': barcode_value,
            'created_at': row[2],
            'is_duplicate': barcode_counts[barcode_value] > 1,
            'total_count': barcode_counts[barcode_value],
            'sequence_number': barcode_sequence[barcode_value],
            'color_index': color_index
        })
    
    return result

def add_barcode(document_id: int, barcode: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO barcodes (document_id, barcode, created_at) VALUES (?, ?, ?)",
        (document_id, barcode, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def delete_barcode(barcode_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM barcodes WHERE id = ?", (barcode_id,))
    conn.commit()
    conn.close()

def close_document(document_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE documents SET status = 'closed', closed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), document_id)
    )
    conn.commit()
    conn.close()

def get_user_documents(user_id: int) -> List[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    documents = cursor.fetchall()
    conn.close()
    
    return [dict(doc) for doc in documents]

def delete_document(document_id: int, user_id: int) -> bool:
    """Удаляет документ, все связанные штрихкоды и CSV файл"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о документе для удаления CSV файла
    cursor.execute("""
        SELECT d.*, u.name as user_name 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        WHERE d.id = ? AND d.user_id = ?
    """, (document_id, user_id))
    document = cursor.fetchone()
    
    if not document:
        conn.close()
        return False
    
    # Удаляем CSV файл если он существует
    if document['status'] == 'closed':
        try:
            doc_date = datetime.fromisoformat(document['created_at']).strftime('%Y%m%d_%H%M%S')
            csv_filename = f"{document['doc_type']}_{document['user_name']}_{doc_date}.csv"
            csv_filepath = os.path.join("static", "documents", csv_filename)
            
            if os.path.exists(csv_filepath):
                os.remove(csv_filepath)
                print(f"Удален CSV файл: {csv_filename}")
        except Exception as e:
            print(f"Ошибка при удалении CSV файла: {e}")
    
    # Удаляем штрихкоды документа
    cursor.execute("DELETE FROM barcodes WHERE document_id = ?", (document_id,))
    
    # Удаляем сам документ
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    
    conn.commit()
    conn.close()
    return True

def update_document_comment(document_id: int, user_id: int, comment: str) -> bool:
    """Обновляет комментарий к документу"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, что документ принадлежит пользователю
    cursor.execute(
        "UPDATE documents SET comment = ? WHERE id = ? AND user_id = ?",
        (comment, document_id, user_id)
    )
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def admin_update_document_comment(document_id: int, comment: str) -> bool:
    """Обновляет комментарий к документу (админская функция)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Админ может редактировать любой документ
    cursor.execute(
        "UPDATE documents SET comment = ? WHERE id = ?",
        (comment, document_id)
    )
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def generate_csv(document_id: int) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о документе
    cursor.execute("""
        SELECT d.*, u.name as user_name 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        WHERE d.id = ?
    """, (document_id,))
    document = cursor.fetchone()
    
    if not document:
        conn.close()
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    # Получаем штрихкоды
    cursor.execute(
        "SELECT barcode, created_at FROM barcodes WHERE document_id = ? ORDER BY created_at",
        (document_id,)
    )
    barcodes = cursor.fetchall()
    conn.close()
    
    # Формируем имя файла
    doc_date = datetime.fromisoformat(document['created_at']).strftime('%Y%m%d_%H%M%S')
    filename = f"{document['doc_type']}_{document['user_name']}_{doc_date}.csv"
    filepath = os.path.join("static", "documents", filename)
    
    # Создаем CSV файл
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Пользователь', 'Дата', 'Тип документа', 'Комментарий', 'Штрихкод'])
        
        for barcode in barcodes:
            writer.writerow([
                document['user_name'],
                document['created_at'],
                document['doc_type'],
                document['comment'],
                barcode['barcode']
            ])
    
    return filename

# Маршруты
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    users = load_users_from_file()
    current_lang = get_user_language(request)
    locale = load_locale(current_lang)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "users": list(users.keys()),
        "locale": locale,
        "current_lang": current_lang
    })

@app.post("/login")
async def login(request: Request, name: str = Form(...), pin: str = Form(...)):
    
    if not name.strip():
        users = load_users_from_file()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "users": list(users.keys()),
            "error": "Имя не может быть пустым"
        })
    
    if not pin.strip():
        users = load_users_from_file()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "users": list(users.keys()),
            "error": "ПИН-код не может быть пустым"
        })
    
    # Проверяем авторизацию
    if not authenticate_user(name.strip(), pin.strip()):
        users = load_users_from_file()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "users": list(users.keys()),
            "error": "Неверное имя пользователя или ПИН-код"
        })
    
    user_id = get_or_create_user(name.strip())
    if user_id is None:
        users = load_users_from_file()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "users": list(users.keys()),
            "error": "Пользователь не найден в системе"
        })
    
    response = RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)
    return response

@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о пользователе
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    user_dict = dict(user)
    
    # Если это администратор, перенаправляем на админ-панель
    if is_admin(user_dict['name']):
        conn.close()
        return RedirectResponse(url=f"/admin/{user_id}", status_code=303)
    
    # Проверяем активный документ
    active_doc = get_active_document(user_id)
    
    # Получаем все документы пользователя
    user_documents = get_user_documents(user_id)
    
    conn.close()
    
    current_lang = get_user_language(request)
    locale = load_locale(current_lang)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user_dict,
        "active_doc": active_doc,
        "documents": user_documents,
        "locale": locale,
        "current_lang": current_lang
    })

@app.post("/create_document/{user_id}")
async def create_new_document(user_id: int, doc_type: str = Form(...), comment: str = Form(default="")):
    # Преобразуем латинские типы в кириллические
    doc_type_map = {
        'inventory': 'Инвентаризация',
        'receipt': 'Приход',
        'expense': 'Расход'
    }
    
    if doc_type in doc_type_map:
        doc_type = doc_type_map[doc_type]
    else:
        # Если пришел кириллический тип, исправляем кодировку
        try:
            if isinstance(doc_type, str):
                doc_type_bytes = doc_type.encode('latin-1')
                doc_type = doc_type_bytes.decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    
    # Исправляем кодировку комментария
    try:
        if isinstance(comment, str):
            comment_bytes = comment.encode('latin-1')
            comment = comment_bytes.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    if doc_type not in ['Инвентаризация', 'Приход', 'Расход']:
        raise HTTPException(status_code=400, detail="Неверный тип документа")
    
    # Проверяем, есть ли уже активный документ
    active_doc = get_active_document(user_id)
    if active_doc:
        # Если активный документ того же типа, предотвращаем дублирование
        if active_doc['doc_type'] == doc_type:
            return RedirectResponse(url=f"/scan/{user_id}", status_code=303)
        
        # Проверяем, есть ли штрихкоды в активном документе
        barcodes = get_document_barcodes(active_doc['id'])
        if not barcodes:
            # Если документ пустой, удаляем его вместо закрытия
            delete_document(active_doc['id'], user_id)
        else:
            # Если есть штрихкоды, закрываем документ
            close_document(active_doc['id'])
            generate_csv(active_doc['id'])
    
    # Создаем новый документ с комментарием
    document_id = create_document(user_id, doc_type, comment.strip())
    
    return RedirectResponse(url=f"/scan/{user_id}", status_code=303)

@app.get("/scan/{user_id}", response_class=HTMLResponse)
async def scan_page(request: Request, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем пользователя
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем активный документ
    active_doc = get_active_document(user_id)
    
    if not active_doc:
        conn.close()
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)
    
    # Получаем штрихкоды (отсортированные для группировки рядом)
    barcodes = get_document_barcodes_sorted(active_doc['id'])
    
    conn.close()
    
    current_lang = get_user_language(request)
    locale = load_locale(current_lang)
    
    return templates.TemplateResponse("scan.html", {
        "request": request,
        "user": dict(user),
        "document": active_doc,
        "barcodes": barcodes,
        "locale": locale,
        "current_lang": current_lang
    })

@app.post("/add_barcode/{user_id}")
async def add_new_barcode(user_id: int, barcode: str = Form(...)):
    if not barcode.strip():
        raise HTTPException(status_code=400, detail="Штрихкод не может быть пустым")
    
    active_doc = get_active_document(user_id)
    if not active_doc:
        raise HTTPException(status_code=400, detail="Нет активного документа")
    
    barcode_value = barcode.strip()
    
    # Добавляем штрихкод без проверки на дубликаты
    add_barcode(active_doc['id'], barcode_value)
    
    return RedirectResponse(url=f"/scan/{user_id}?new_scan=true", status_code=303)

@app.post("/delete_barcode/{user_id}")
async def remove_barcode(user_id: int, barcode_id: int = Form(...)):
    # Удаляем только конкретный штрихкод по ID
    delete_barcode(barcode_id)
    return RedirectResponse(url=f"/scan/{user_id}", status_code=303)

@app.post("/close_document/{user_id}")
async def close_active_document(user_id: int):
    active_doc = get_active_document(user_id)
    if not active_doc:
        raise HTTPException(status_code=400, detail="Нет активного документа")
    
    # Проверяем, есть ли штрихкоды в документе
    barcodes = get_document_barcodes(active_doc['id'])
    if not barcodes:
        raise HTTPException(status_code=400, detail="Нельзя закрыть пустой документ. Добавьте хотя бы один штрихкод.")
    
    close_document(active_doc['id'])
    generate_csv(active_doc['id'])
    
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/regenerate_csv/{user_id}")
async def regenerate_document_csv(user_id: int, document_id: int = Form(...)):
    filename = generate_csv(document_id)
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/delete_document/{user_id}")
async def delete_user_document(user_id: int, document_id: int = Form(...)):
    success = delete_document(document_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден или нет прав доступа")
    
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/update_comment/{user_id}")
async def update_comment(user_id: int, document_id: int = Form(...), comment: str = Form(...)):
    # Проверяем, является ли пользователь администратором
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user and is_admin(user['name']):
        # Для админа - обновляем без проверки прав доступа
        success = admin_update_document_comment(document_id, comment.strip())
        redirect_url = f"/admin/{user_id}"
    else:
        # Для обычного пользователя - обычная проверка
        success = update_document_comment(document_id, user_id, comment.strip())
        redirect_url = f"/dashboard/{user_id}"
    
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден или нет прав доступа")
    
    return RedirectResponse(url=redirect_url, status_code=303)

# Админ-панель
@app.get("/admin/{user_id}", response_class=HTMLResponse)
async def admin_panel(request: Request, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о пользователе
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not is_admin(dict(user)['name']):
        conn.close()
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Получаем все документы всех пользователей
    all_documents = get_all_documents()
    
    # Получаем всех пользователей
    all_users = get_all_users()
    
    # Получаем статистику
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM documents")
    total_documents = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM documents WHERE status = 'active'")
    active_documents = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM barcodes")
    total_barcodes = cursor.fetchone()[0]
    
    conn.close()
    
    current_lang = get_user_language(request)
    locale = load_locale(current_lang)
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": dict(user),
        "documents": all_documents,
        "users": all_users,
        "stats": {
            "total_users": total_users,
            "total_documents": total_documents,
            "active_documents": active_documents,
            "total_barcodes": total_barcodes
        },
        "locale": locale,
        "current_lang": current_lang
    })

@app.post("/admin/delete_document/{user_id}")
async def admin_delete_doc(user_id: int, document_id: int = Form(...)):
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not is_admin(user['name']):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    success = admin_delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    return RedirectResponse(url=f"/admin/{user_id}", status_code=303)

@app.post("/admin/regenerate_csv/{user_id}")
async def admin_regenerate_csv(user_id: int, document_id: int = Form(...)):
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not is_admin(user['name']):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    filename = generate_csv(document_id)
    return RedirectResponse(url=f"/admin/{user_id}", status_code=303)

@app.get("/admin/document/{user_id}/{document_id}", response_class=HTMLResponse)
async def admin_view_document(request: Request, user_id: int, document_id: int):
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not is_admin(user['name']):
        conn.close()
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Получаем документ с информацией о пользователе
    cursor.execute("""
        SELECT d.*, u.name as user_name 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        WHERE d.id = ?
    """, (document_id,))
    document = cursor.fetchone()
    
    if not document:
        conn.close()
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    # Получаем штрихкоды документа (отсортированные для группировки рядом)
    barcodes = get_document_barcodes_sorted(document_id)
    
    conn.close()
    
    current_lang = get_user_language(request)
    locale = load_locale(current_lang)
    
    return templates.TemplateResponse("admin_document.html", {
        "request": request,
        "user": dict(user),
        "document": dict(document),
        "barcodes": barcodes,
        "locale": locale,
        "current_lang": current_lang
    })

# Загрузка логотипа
@app.post("/admin/upload_logo/{user_id}")
async def upload_logo(user_id: int, logo: UploadFile = File(...)):
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not is_admin(user['name']):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Проверяем тип файла
    if not logo.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    # Создаем папку для логотипов если её нет
    os.makedirs("static/logo", exist_ok=True)
    
    # Определяем расширение файла
    file_extension = logo.filename.split('.')[-1].lower()
    if file_extension not in ['jpg', 'jpeg', 'png', 'svg']:
        raise HTTPException(status_code=400, detail="Поддерживаются только JPG, PNG, SVG файлы")
    
    # Сохраняем файл как company_logo
    logo_filename = f"company_logo.{file_extension}"
    logo_path = os.path.join("static", "logo", logo_filename)
    
    # Удаляем старые логотипы
    for ext in ['jpg', 'jpeg', 'png', 'svg']:
        old_logo = os.path.join("static", "logo", f"company_logo.{ext}")
        if os.path.exists(old_logo):
            os.remove(old_logo)
    
    # Сохраняем новый логотип
    content = await logo.read()
    with open(logo_path, "wb") as f:
        f.write(content)
    
    return RedirectResponse(url=f"/admin/{user_id}", status_code=303)

@app.post("/admin/add_user/{user_id}")
async def admin_add_user(user_id: int, name: str = Form(...), pin: str = Form(...)):
    """Добавить нового пользователя"""
    # Исправляем кодировку для кириллических символов
    try:
        if isinstance(name, str):
            name_bytes = name.encode('latin-1')
            name = name_bytes.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    try:
        if isinstance(pin, str):
            pin_bytes = pin.encode('latin-1')
            pin = pin_bytes.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not is_admin(dict(user)['name']):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Проверяем, что пользователь с таким именем не существует
    users_data = load_users_from_file()
    if name in users_data:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    
    try:
        add_user_to_system(name, pin)
        return RedirectResponse(url=f"/admin/{user_id}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении пользователя: {str(e)}")

@app.post("/admin/delete_user/{user_id}")
async def admin_delete_user(user_id: int, delete_user_id: int = Form(...)):
    """Удалить пользователя"""
    # Проверяем права администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not is_admin(dict(user)['name']):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Нельзя удалить самого себя
    if user_id == delete_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    
    # Нельзя удалить администратора
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (delete_user_id,))
    delete_user = cursor.fetchone()
    conn.close()
    
    if delete_user and is_admin(dict(delete_user)['name']):
        raise HTTPException(status_code=400, detail="Нельзя удалить администратора")
    
    try:
        success = delete_user_from_system(delete_user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return RedirectResponse(url=f"/admin/{user_id}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении пользователя: {str(e)}")

@app.get("/logo")
async def get_logo():
    """Возвращает логотип компании или стандартный SVG"""
    # Ищем загруженный логотип
    for ext in ['png', 'jpg', 'jpeg', 'svg']:
        logo_path = os.path.join("static", "logo", f"company_logo.{ext}")
        if os.path.exists(logo_path):
            return FileResponse(logo_path)
    
    # Если логотип не найден, возвращаем стандартный SVG
    svg_content = '''<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="48" height="48" rx="8" fill="currentColor" fill-opacity="0.1"/>
        <rect x="8" y="12" width="32" height="24" rx="2" stroke="currentColor" stroke-width="2" fill="none"/>
        <rect x="10" y="14" width="28" height="20" rx="1" fill="currentColor" fill-opacity="0.2"/>
        <g transform="translate(12, 18)">
            <rect x="0" y="0" width="1" height="8" fill="currentColor"/>
            <rect x="2" y="0" width="2" height="8" fill="currentColor"/>
            <rect x="5" y="0" width="1" height="8" fill="currentColor"/>
            <rect x="7" y="0" width="3" height="8" fill="currentColor"/>
            <rect x="11" y="0" width="1" height="8" fill="currentColor"/>
            <rect x="13" y="0" width="2" height="8" fill="currentColor"/>
            <rect x="16" y="0" width="1" height="8" fill="currentColor"/>
            <rect x="18" y="0" width="2" height="8" fill="currentColor"/>
            <rect x="21" y="0" width="1" height="8" fill="currentColor"/>
            <rect x="23" y="0" width="1" height="8" fill="currentColor"/>
        </g>
        <path d="M16 30L20 34L32 22" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </svg>'''
    return Response(content=svg_content, media_type="image/svg+xml")

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("static", "documents", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    else:
        raise HTTPException(status_code=404, detail="Файл не найден")

@app.get("/pwa-icon")
async def get_pwa_icon(size: int = 144):
    """Генерирует простую иконку для PWA"""
    # Создаем простую SVG иконку с логотипом компании
    svg_icon = f'''<svg width="{size}" height="{size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="48" height="48" rx="8" fill="#0d6efd"/>
        <rect x="8" y="12" width="32" height="24" rx="2" stroke="white" stroke-width="2" fill="none"/>
        <rect x="10" y="14" width="28" height="20" rx="1" fill="white" fill-opacity="0.2"/>
        <g transform="translate(12, 18)">
            <rect x="0" y="0" width="1" height="8" fill="white"/>
            <rect x="2" y="0" width="2" height="8" fill="white"/>
            <rect x="5" y="0" width="1" height="8" fill="white"/>
            <rect x="7" y="0" width="3" height="8" fill="white"/>
            <rect x="11" y="0" width="1" height="8" fill="white"/>
            <rect x="13" y="0" width="2" height="8" fill="white"/>
            <rect x="16" y="0" width="1" height="8" fill="white"/>
            <rect x="18" y="0" width="2" height="8" fill="white"/>
            <rect x="21" y="0" width="1" height="8" fill="white"/>
            <rect x="23" y="0" width="1" height="8" fill="white"/>
        </g>
        <path d="M16 30L20 34L32 22" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </svg>'''
    
    return Response(content=svg_icon, media_type="image/svg+xml")

@app.post("/set_language")
async def set_language(request: Request, language: str = Form(...)):
    """Устанавливает язык пользователя"""
    if language not in ['ru', 'uk']:
        language = 'ru'
    
    # Получаем URL для редиректа из referer или переходим на главную
    referer = request.headers.get('referer', '/')
    
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie(key="language", value=language, max_age=365*24*60*60)  # 1 год
    return response

@app.get("/favicon.ico")
async def get_favicon():
    """Возвращает favicon для браузера"""
    # Используем ту же иконку, что и для PWA, но в размере 32x32
    svg_icon = '''<svg width="32" height="32" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="48" height="48" rx="8" fill="#0d6efd"/>
        <rect x="8" y="12" width="32" height="24" rx="2" stroke="white" stroke-width="2" fill="none"/>
        <rect x="10" y="14" width="28" height="20" rx="1" fill="white" fill-opacity="0.2"/>
        <g transform="translate(12, 18)">
            <rect x="0" y="0" width="1" height="8" fill="white"/>
            <rect x="2" y="0" width="2" height="8" fill="white"/>
            <rect x="5" y="0" width="1" height="8" fill="white"/>
            <rect x="7" y="0" width="3" height="8" fill="white"/>
            <rect x="11" y="0" width="1" height="8" fill="white"/>
            <rect x="13" y="0" width="2" height="8" fill="white"/>
            <rect x="16" y="0" width="1" height="8" fill="white"/>
            <rect x="18" y="0" width="2" height="8" fill="white"/>
            <rect x="21" y="0" width="1" height="8" fill="white"/>
            <rect x="23" y="0" width="1" height="8" fill="white"/>
        </g>
        <path d="M16 30L20 34L32 22" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </svg>'''
    
    return Response(content=svg_icon, media_type="image/svg+xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)