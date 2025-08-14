#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для просмотра и анализа логов документов
"""

import os
import sys
from datetime import datetime
import argparse
from collections import Counter

def read_logs(log_file="logs/documents.log"):
    """Читает файл логов"""
    if not os.path.exists(log_file):
        print(f"Файл логов не найден: {log_file}")
        return []
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        print(f"Ошибка при чтении файла логов: {e}")
        return []

def filter_logs(logs, user=None, action=None, date=None):
    """Фильтрует логи по параметрам"""
    filtered = []
    
    for line in logs:
        line = line.strip()
        if not line:
            continue
            
        # Фильтр по пользователю
        if user and user.lower() not in line.lower():
            continue
            
        # Фильтр по действию
        if action and action.lower() not in line.lower():
            continue
            
        # Фильтр по дате
        if date and date not in line:
            continue
            
        filtered.append(line)
    
    return filtered

def show_statistics(logs):
    """Показывает статистику по логам"""
    if not logs:
        print("Нет логов для анализа")
        return
    
    print("\n" + "="*60)
    print("СТАТИСТИКА ПО ЛОГАМ")
    print("="*60)
    
    # Общее количество записей
    total_entries = len(logs)
    print(f"Всего записей: {total_entries}")
    
    # Статистика по действиям
    actions = Counter()
    users = Counter()
    
    for line in logs:
        # Подсчет действий
        if "добавил штрихкод" in line:
            actions["Добавление штрихкодов"] += 1
        elif "удалил штрихкод" in line:
            actions["Удаление штрихкодов"] += 1
        elif "создал новый документ" in line:
            actions["Создание документов"] += 1
        elif "закрыл документ" in line:
            actions["Закрытие документов"] += 1
        elif "удалил документ" in line:
            actions["Удаление документов"] += 1
        elif "обновил комментарий" in line:
            actions["Обновление комментариев"] += 1
        elif "вошел в систему" in line:
            actions["Входы в систему"] += 1
        elif "АДМИНИСТРАТОР" in line:
            actions["Админские операции"] += 1
        
        # Подсчет пользователей
        if "Пользователь '" in line:
            try:
                user_start = line.find("Пользователь '") + 13
                user_end = line.find("'", user_start)
                if user_end > user_start:
                    user_name = line[user_start:user_end]
                    users[user_name] += 1
            except:
                pass
    
    print(f"\nСтатистика по действиям:")
    for action, count in actions.most_common():
        print(f"  {action}: {count}")
    
    print(f"\nСтатистика по пользователям:")
    for user, count in users.most_common(10):
        print(f"  {user}: {count} операций")

def show_recent_logs(logs, count=20):
    """Показывает последние записи логов"""
    if not logs:
        print("Нет логов для отображения")
        return
    
    print(f"\n{count} последних записей:")
    print("-" * 60)
    
    for line in logs[-count:]:
        print(line)

def search_logs(logs, query):
    """Поиск по логам"""
    if not query:
        return logs
    
    results = []
    query_lower = query.lower()
    
    for line in logs:
        if query_lower in line.lower():
            results.append(line)
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Просмотр и анализ логов документов")
    parser.add_argument("-f", "--file", default="logs/documents.log", help="Путь к файлу логов")
    parser.add_argument("-u", "--user", help="Фильтр по пользователю")
    parser.add_argument("-a", "--action", help="Фильтр по действию")
    parser.add_argument("-d", "--date", help="Фильтр по дате (YYYY-MM-DD)")
    parser.add_argument("-s", "--search", help="Поиск по тексту")
    parser.add_argument("-c", "--count", type=int, default=20, help="Количество последних записей")
    parser.add_argument("--stats", action="store_true", help="Показать статистику")
    parser.add_argument("--recent", action="store_true", help="Показать последние записи")
    
    args = parser.parse_args()
    
    # Читаем логи
    logs = read_logs(args.file)
    if not logs:
        return
    
    # Применяем фильтры
    filtered_logs = filter_logs(logs, args.user, args.action, args.date)
    
    # Поиск
    if args.search:
        filtered_logs = search_logs(filtered_logs, args.search)
    
    # Выводим результаты
    if args.stats:
        show_statistics(filtered_logs)
    
    if args.recent or not args.stats:
        show_recent_logs(filtered_logs, args.count)
    
    # Если нет аргументов, показываем последние записи
    if len(sys.argv) == 1:
        show_recent_logs(logs, 20)

if __name__ == "__main__":
    main()
