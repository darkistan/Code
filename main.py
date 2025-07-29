import sqlite3
import csv
import os
import shutil
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from pydantic import BaseModel

# Создание директорий если их нет
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("static/documents", exist_ok=True)

app = FastAPI(title="Мобильная инвентаризация")

# Настройка шаблонов и статических файлов
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
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

def create_document(user_id: int, doc_type: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO documents (user_id, doc_type, status, created_at) VALUES (?, ?, 'active', ?)",
        (user_id, doc_type, datetime.now().isoformat())
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
        writer.writerow(['Пользователь', 'Дата', 'Тип документа', 'Штрихкод'])
        
        for barcode in barcodes:
            writer.writerow([
                document['user_name'],
                document['created_at'],
                document['doc_type'],
                barcode['barcode']
            ])
    
    return filename

# Маршруты
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    users = load_users_from_file()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "users": list(users.keys())
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
    
    # Проверяем активный документ
    active_doc = get_active_document(user_id)
    
    # Получаем все документы пользователя
    user_documents = get_user_documents(user_id)
    
    conn.close()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": dict(user),
        "active_doc": active_doc,
        "documents": user_documents
    })

@app.post("/create_document/{user_id}")
async def create_new_document(user_id: int, doc_type: str = Form(...)):
    if doc_type not in ['Инвентаризация', 'Приход']:
        raise HTTPException(status_code=400, detail="Неверный тип документа")
    
    # Закрываем активный документ если есть
    active_doc = get_active_document(user_id)
    if active_doc:
        close_document(active_doc['id'])
    
    # Создаем новый документ
    document_id = create_document(user_id, doc_type)
    
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
    
    # Получаем штрихкоды
    barcodes = get_document_barcodes(active_doc['id'])
    
    conn.close()
    
    return templates.TemplateResponse("scan.html", {
        "request": request,
        "user": dict(user),
        "document": active_doc,
        "barcodes": barcodes
    })

@app.post("/add_barcode/{user_id}")
async def add_new_barcode(user_id: int, barcode: str = Form(...)):
    if not barcode.strip():
        raise HTTPException(status_code=400, detail="Штрихкод не может быть пустым")
    
    active_doc = get_active_document(user_id)
    if not active_doc:
        raise HTTPException(status_code=400, detail="Нет активного документа")
    
    barcode_value = barcode.strip()
    
    # Проверяем, не был ли уже добавлен такой же штрихкод в последние 5 секунд
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM barcodes 
        WHERE document_id = ? AND barcode = ? 
        AND datetime(created_at) > datetime('now', '-5 seconds')
    """, (active_doc['id'], barcode_value))
    
    recent_count = cursor.fetchone()[0]
    conn.close()
    
    # Если такой штрихкод уже был добавлен недавно, игнорируем
    if recent_count > 0:
        return RedirectResponse(url=f"/scan/{user_id}", status_code=303)
    
    add_barcode(active_doc['id'], barcode_value)
    
    return RedirectResponse(url=f"/scan/{user_id}", status_code=303)

@app.post("/delete_barcode/{user_id}")
async def remove_barcode(user_id: int, barcode_id: int = Form(...)):
    delete_barcode(barcode_id)
    return RedirectResponse(url=f"/scan/{user_id}", status_code=303)

@app.post("/close_document/{user_id}")
async def close_active_document(user_id: int):
    active_doc = get_active_document(user_id)
    if not active_doc:
        raise HTTPException(status_code=400, detail="Нет активного документа")
    
    close_document(active_doc['id'])
    generate_csv(active_doc['id'])
    
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/regenerate_csv/{user_id}")
async def regenerate_document_csv(user_id: int, document_id: int = Form(...)):
    filename = generate_csv(document_id)
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

# Загрузка логотипа удалена - используется постоянный SVG

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("static", "documents", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    else:
        raise HTTPException(status_code=404, detail="Файл не найден")

@app.get("/static/icon-{size}.png")
async def get_icon(size: str):
    """Генерирует простую иконку для PWA"""
    from fastapi.responses import Response
    
    # Простая PNG иконка (1x1 пиксель синего цвета в base64)
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xddcc\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    
    return Response(content=png_data, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)