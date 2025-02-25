import sqlite3
from contextlib import contextmanager
import os
from typing import Generator

DATABASE_URL = "app.db"

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        cursor = db.cursor()
        
        # 检查表是否存在的函数
        def table_exists(table_name):
            cursor.execute('''
                SELECT count(name) FROM sqlite_master 
                WHERE type='table' AND name=?
            ''', (table_name,))
            return cursor.fetchone()[0] > 0

        # 检查列是否存在的函数
        def column_exists(table_name, column_name):
            cursor.execute(f'PRAGMA table_info({table_name})')
            columns = cursor.fetchall()
            return any(column['name'] == column_name for column in columns)

        # 添加列的函数
        def add_column_if_not_exists(table_name, column_name, column_type):
            if not column_exists(table_name, column_name):
                print(f"Adding {column_name} column to {table_name} table...")
                cursor.execute(f'''
                ALTER TABLE {table_name}
                ADD COLUMN {column_name} {column_type}
                ''')
        
        # 创建用户表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建模型表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            alias TEXT NOT NULL,
            mapping_name TEXT,
            original_price REAL DEFAULT 0,
            current_price REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建图片存储表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            file_type TEXT,
            width INTEGER,
            height INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建文生图生成历史表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS text_to_image_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            model_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            seed INTEGER,
            width INTEGER DEFAULT 1024,
            height INTEGER DEFAULT 1024,
            enhance BOOLEAN DEFAULT FALSE,
            image_id INTEGER,
            status TEXT DEFAULT 'pending',
            cache_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users (username),
            FOREIGN KEY (model_id) REFERENCES models (id),
            FOREIGN KEY (image_id) REFERENCES images (id)
        )
        ''')
        
        # 添加图生图缓存表
        if not table_exists('image_to_image_cache'):
            print("Creating image_to_image_cache table...")
            cursor.execute('''
            CREATE TABLE image_to_image_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url TEXT NOT NULL,
                prompt TEXT,
                gen_seed INTEGER,
                enhanced_prompt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(image_url, prompt, gen_seed)
            )
            ''')
        
        # 检查并创建或更新图生图生成历史表
        if not table_exists('image_to_image_generations'):
            print("Creating image_to_image_generations table...")
            cursor.execute('''
            CREATE TABLE image_to_image_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                model_id INTEGER NOT NULL,
                prompt TEXT,
                enhanced_prompt TEXT,
                prompt_image_id INTEGER NOT NULL,
                result_image_id INTEGER,
                seed INTEGER,
                width INTEGER DEFAULT 1024,
                height INTEGER DEFAULT 1024,
                enhance BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending',
                image_url TEXT,
                gen_seed INTEGER,
                cache_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users (username),
                FOREIGN KEY (model_id) REFERENCES models (id),
                FOREIGN KEY (prompt_image_id) REFERENCES images (id),
                FOREIGN KEY (result_image_id) REFERENCES images (id)
            )
            ''')
        else:
            # 检查并添加所有必要的列
            columns_to_add = {
                'enhanced_prompt': 'TEXT',
                'prompt_image_id': 'INTEGER',
                'result_image_id': 'INTEGER',
                'image_url': 'TEXT',
                'gen_seed': 'INTEGER',
                'cache_key': 'TEXT'
            }
            
            for column_name, column_type in columns_to_add.items():
                add_column_if_not_exists('image_to_image_generations', column_name, column_type)
            
            # 如果存在旧的 image_id 列，重命名为 result_image_id
            if column_exists('image_to_image_generations', 'image_id') and not column_exists('image_to_image_generations', 'result_image_id'):
                print("Renaming image_id to result_image_id in image_to_image_generations table...")
                cursor.execute('''
                ALTER TABLE image_to_image_generations RENAME COLUMN image_id TO result_image_id
                ''')
        
        # 创建图片描述缓存表
        if not table_exists('image_description_cache'):
            print("Creating image_description_cache table...")
            cursor.execute('''
            CREATE TABLE image_description_cache (
                cache_key TEXT PRIMARY KEY,
                original_prompt TEXT,
                enhanced_prompt TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
        else:
            # 检查并添加必要的列
            columns_to_add = {
                'width': 'INTEGER',
                'height': 'INTEGER'
            }
            
            for column_name, column_type in columns_to_add.items():
                add_column_if_not_exists('image_description_cache', column_name, column_type)
        
        # 检查并插入默认模型
        cursor.execute('SELECT COUNT(*) FROM models')
        model_count = cursor.fetchone()[0]
        
        if model_count == 0:
            print("Inserting default models...")
            # 插入默认模型
            models = [
                ("black-forest-labs/FLUX-1-schnell", "FLUX Schnell", "turbo", 0, 0),
                ("black-forest-labs/FLUX-1-dev", "FLUX Dev", "flux", 0, 0)
            ]
            
            cursor.executemany('''
                INSERT INTO models 
                (name, alias, mapping_name, original_price, current_price) 
                VALUES (?, ?, ?, ?, ?)
            ''', models)
        
        # 创建统一的图片生成历史记录表
        if not table_exists('image_generations'):
            print("Creating image_generations table...")
            cursor.execute('''
            CREATE TABLE image_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                model_id INTEGER NOT NULL,
                generation_type TEXT NOT NULL CHECK (generation_type IN ('text_to_image', 'image_to_image')),
                prompt TEXT,
                enhanced_prompt TEXT,
                source_image_id INTEGER,
                result_image_id INTEGER,
                seed INTEGER,
                width INTEGER DEFAULT 1024,
                height INTEGER DEFAULT 1024,
                enhance BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending',
                image_url TEXT,
                cache_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users (username),
                FOREIGN KEY (model_id) REFERENCES models (id),
                FOREIGN KEY (source_image_id) REFERENCES images (id),
                FOREIGN KEY (result_image_id) REFERENCES images (id)
            )
            ''')
            
            # 创建索引以提高查询性能
            cursor.execute('''
            CREATE INDEX idx_image_generations_username ON image_generations(username);
            CREATE INDEX idx_image_generations_type ON image_generations(generation_type);
            CREATE INDEX idx_image_generations_created_at ON image_generations(created_at);
            ''')
        
        db.commit() 