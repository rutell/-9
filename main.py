import os
import sqlite3
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils.executor import set_webhook, start_webhook
import uvicorn

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "7739590241:AAHp83Td4uluzJw1upAYi-0zqnxPuPSHNdg")
# При деплое на Render переменная RENDER_EXTERNAL_URL автоматически подставится
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", os.getenv("BASE_URL", "https://your-app.onrender.com"))
# Убираем слеш в конце, если есть
BASE_URL = BASE_URL.rstrip('/')

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect("teamfinder.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            category TEXT NOT NULL,
            hours INTEGER,
            age INTEGER,
            experience TEXT,
            description TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ========== FASTAPI ==========
app = FastAPI()

# HTML-шаблон веб-приложения (стеклянный стиль, полный CRUD)
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>TeamFinder — поиск тиммейтов</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--tg-theme-bg-color, #000000);
            color: var(--tg-theme-text-color, #ffffff);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            padding: 20px;
            min-height: 100vh;
        }
        .glass {
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(12px);
            border-radius: 32px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 20px;
            margin-bottom: 20px;
        }
        .glass-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(8px);
            border-radius: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 16px;
            margin-bottom: 12px;
        }
        .btn {
            background: rgba(255, 255, 255, 0.15);
            border: none;
            border-radius: 40px;
            padding: 12px 20px;
            font-size: 16px;
            font-weight: 500;
            color: white;
            width: 100%;
            margin-top: 8px;
            cursor: pointer;
        }
        .btn-primary { background: #3390ec; }
        .btn-primary:active { background: #2b7bcf; }
        .btn-small {
            width: auto;
            padding: 6px 14px;
            font-size: 13px;
            display: inline-block;
            margin-right: 8px;
            margin-top: 8px;
        }
        .btn-danger { background: rgba(255, 80, 80, 0.7); }
        select, input, textarea {
            width: 100%;
            padding: 12px 16px;
            margin-top: 8px;
            margin-bottom: 16px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 20px;
            color: white;
            font-size: 15px;
            outline: none;
        }
        label { font-size: 14px; opacity: 0.7; margin-left: 8px; }
        h2, h3 { font-weight: 600; margin-bottom: 14px; }
        .row { margin-bottom: 6px; }
        .badge {
            background: rgba(255,255,255,0.2);
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 12px;
            display: inline-block;
            margin-right: 8px;
        }
        .post-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
        .edit-form { margin-top: 12px; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 12px; }
        .flex-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .back-button { background: none; border: 1px solid rgba(255,255,255,0.3); margin-bottom: 16px; }
    </style>
</head>
<body>
    <div id="app">
        <div class="glass">
            <h2>🎮 Поиск тиммейтов</h2>
            <div v-if="step === 'selectGame'">
                <h3>Выбери игру</h3>
                <button class="btn" @click="selectGame('rust')">🦀 Rust</button>
                <button class="btn" @click="selectGame('cs')">🔫 Counter-Strike</button>
                <button class="btn" @click="selectGame('dota')">🌿 Dota 2</button>
            </div>
            <div v-if="step === 'selectCategory'">
                <button class="btn back-button" @click="step='selectGame'">← Назад</button>
                <h3>{{ gameName }}</h3>
                <button v-for="cat in categories" :key="cat.value" class="btn" @click="selectCategory(cat.value)">{{ cat.label }}</button>
            </div>
            <div v-if="step === 'main'">
                <button class="btn back-button" @click="step='selectCategory'">← Назад</button>
                <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <button class="btn" :class="{ 'btn-primary': mode === 'list' }" @click="mode='list'">📋 Объявления</button>
                    <button class="btn" :class="{ 'btn-primary': mode === 'create' }" @click="mode='create'">✏️ Создать</button>
                </div>
                <div v-if="mode === 'list'">
                    <div v-if="loading">Загрузка...</div>
                    <div v-else-if="posts.length === 0" class="glass-card">Пока нет объявлений. Стань первым!</div>
                    <div v-else>
                        <div v-for="post in posts" :key="post.id" class="glass-card">
                            <div class="post-meta">
                                <span class="badge">🎮 {{ post.game }}</span>
                                <span class="badge">📂 {{ post.category_label }}</span>
                            </div>
                            <template v-if="editingId === post.id">
                                <div class="edit-form">
                                    <label>🕒 Часы в игре</label>
                                    <input type="number" v-model="editForm.hours">
                                    <label>🎂 Возраст</label>
                                    <input type="number" v-model="editForm.age">
                                    <label>💪 Опыт / звание</label>
                                    <input v-model="editForm.experience">
                                    <label>📝 Описание</label>
                                    <textarea v-model="editForm.description"></textarea>
                                    <div class="flex-row">
                                        <button class="btn btn-primary btn-small" @click="saveEdit(post.id)">💾 Сохранить</button>
                                        <button class="btn btn-small" @click="cancelEdit">❌ Отмена</button>
                                    </div>
                                </div>
                            </template>
                            <template v-else>
                                <div class="row">⏱ Часов: {{ post.hours || 'не указано' }}</div>
                                <div class="row">🎂 Возраст: {{ post.age || 'не указано' }}</div>
                                <div class="row">💪 Опыт: {{ post.experience || '—' }}</div>
                                <div class="row">📝 {{ post.description || 'нет описания' }}</div>
                                <div class="flex-row" v-if="post.user_id === userId">
                                    <button class="btn-small btn" @click="startEdit(post)">✏️ Редактировать</button>
                                    <button class="btn-small btn btn-danger" @click="deletePost(post.id)">🗑 Удалить</button>
                                </div>
                                <div style="font-size:12px; margin-top:8px; opacity:0.5;" v-else>👤 Автор: ID {{ post.user_id }}</div>
                            </template>
                        </div>
                    </div>
                </div>
                <div v-if="mode === 'create'">
                    <div class="glass-card">
                        <label>🕒 Часы в игре</label>
                        <input type="number" v-model="newPost.hours" placeholder="Например: 500">
                        <label>🎂 Возраст</label>
                        <input type="number" v-model="newPost.age" placeholder="18">
                        <label>💪 Опыт / звание</label>
                        <input v-model="newPost.experience" placeholder="Глобал / Лем / Топ-100">
                        <label>📝 Описание</label>
                        <textarea v-model="newPost.description" placeholder="Кого ищем, какой стиль игры..."></textarea>
                        <button class="btn btn-primary" @click="createPost" :disabled="creating">📤 Опубликовать</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/vue@2.7.14/dist/vue.js"></script>
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.enableClosingConfirmation();
        const userId = tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : null;
        if (!userId) alert("Ошибка: не удалось получить ID. Запустите из бота.");
        new Vue({
            el: '#app',
            data: {
                step: 'selectGame',
                game: null,
                category: null,
                mode: 'list',
                posts: [],
                loading: false,
                creating: false,
                editingId: null,
                editForm: { hours: '', age: '', experience: '', description: '' },
                newPost: { hours: '', age: '', experience: '', description: '' },
                gameNames: { rust: 'Rust', cs: 'Counter-Strike', dota: 'Dota 2' },
                categoriesMap: {
                    rust: [{ value: 'clans', label: '🏰 Кланы' }, { value: 'partners', label: '🤝 Напарники' }],
                    cs: [{ value: 'team', label: '👥 Поиск команды' }, { value: 'partner', label: '🎯 Поиск напарника' }],
                    dota: [{ value: 'team', label: '👥 Поиск команды' }, { value: 'partner', label: '🎯 Поиск напарника' }]
                }
            },
            computed: {
                gameName() { return this.gameNames[this.game] || this.game; },
                categories() { return this.categoriesMap[this.game] || []; }
            },
            methods: {
                selectGame(game) { this.game = game; this.step = 'selectCategory'; },
                selectCategory(cat) {
                    this.category = cat;
                    this.step = 'main';
                    this.mode = 'list';
                    this.loadPosts();
                },
                async loadPosts() {
                    if (!this.game || !this.category) return;
                    this.loading = true;
                    try {
                        const res = await fetch(`/api/posts?game=${this.game}&category=${this.category}`);
                        const data = await res.json();
                        this.posts = data.map(p => ({ ...p, category_label: this.getCategoryLabel(p.category) }));
                    } catch(e) { console.error(e); }
                    finally { this.loading = false; }
                },
                getCategoryLabel(cat) {
                    const found = this.categories.find(c => c.value === cat);
                    return found ? found.label : cat;
                },
                startEdit(post) {
                    this.editingId = post.id;
                    this.editForm = {
                        hours: post.hours || '',
                        age: post.age || '',
                        experience: post.experience || '',
                        description: post.description || ''
                    };
                },
                cancelEdit() { this.editingId = null; },
                async saveEdit(id) {
                    try {
                        const payload = {
                            user_id: userId,
                            hours: this.editForm.hours ? parseInt(this.editForm.hours) : null,
                            age: this.editForm.age ? parseInt(this.editForm.age) : null,
                            experience: this.editForm.experience.trim() || null,
                            description: this.editForm.description.trim() || null
                        };
                        const res = await fetch(`/api/post/${id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        if (res.ok) {
                            this.cancelEdit();
                            this.loadPosts();
                        } else { const err = await res.json(); alert("Ошибка: " + (err.detail || "неизвестная")); }
                    } catch(e) { alert("Сетевая ошибка"); }
                },
                async deletePost(id) {
                    if (!confirm("Удалить объявление навсегда?")) return;
                    try {
                        const res = await fetch(`/api/post/${id}`, {
                            method: 'DELETE',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ user_id: userId })
                        });
                        if (res.ok) this.loadPosts();
                        else { const err = await res.json(); alert("Ошибка: " + (err.detail || "неизвестная")); }
                    } catch(e) { alert("Ошибка сети"); }
                },
                async createPost() {
                    if (!userId) return alert("Ошибка авторизации");
                    if (!this.newPost.hours && !this.newPost.age && !this.newPost.experience && !this.newPost.description) {
                        alert("Заполните хотя бы одно поле");
                        return;
                    }
                    this.creating = true;
                    try {
                        const payload = {
                            user_id: userId,
                            game: this.game,
                            category: this.category,
                            hours: this.newPost.hours ? parseInt(this.newPost.hours) : null,
                            age: this.newPost.age ? parseInt(this.newPost.age) : null,
                            experience: this.newPost.experience.trim() || null,
                            description: this.newPost.description.trim() || null
                        };
                        const res = await fetch('/api/post', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        if (res.ok) {
                            this.newPost = { hours: '', age: '', experience: '', description: '' };
                            alert("Объявление создано!");
                            this.mode = 'list';
                            this.loadPosts();
                        } else { const err = await res.json(); alert("Ошибка: " + (err.detail || "неизвестная")); }
                    } catch(e) { alert("Ошибка сети"); }
                    finally { this.creating = false; }
                }
            }
        });
    </script>
</body>
</html>
"""

@app.get("/webapp")
async def get_webapp():
    return HTMLResponse(HTML_PAGE)

@app.get("/api/posts")
async def get_posts(game: str, category: str):
    conn = sqlite3.connect("teamfinder.db")
    c = conn.cursor()
    c.execute("SELECT id, user_id, game, category, hours, age, experience, description, created_at FROM posts WHERE game=? AND category=? ORDER BY id DESC", (game, category))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "game": r[2], "category": r[3], "hours": r[4], "age": r[5], "experience": r[6], "description": r[7], "created_at": r[8]} for r in rows]

@app.post("/api/post")
async def create_post(request: Request):
    data = await request.json()
    if data["game"] not in ["rust", "cs", "dota"]:
        raise HTTPException(400, "Invalid game")
    if data["game"] == "rust" and data["category"] not in ["clans", "partners"]:
        raise HTTPException(400, "Invalid category for Rust")
    if data["game"] in ["cs", "dota"] and data["category"] not in ["team", "partner"]:
        raise HTTPException(400, "Invalid category")
    conn = sqlite3.connect("teamfinder.db")
    c = conn.cursor()
    c.execute('''INSERT INTO posts (user_id, game, category, hours, age, experience, description, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (data["user_id"], data["game"], data["category"], data.get("hours"), data.get("age"), data.get("experience"), data.get("description"), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.put("/api/post/{post_id}")
async def update_post(post_id: int, request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id required")
    conn = sqlite3.connect("teamfinder.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post not found")
    if row[0] != user_id:
        conn.close()
        raise HTTPException(403, "You can edit only your own posts")
    c.execute('''UPDATE posts SET hours = ?, age = ?, experience = ?, description = ? WHERE id = ?''',
              (data.get("hours"), data.get("age"), data.get("experience"), data.get("description"), post_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/api/post/{post_id}")
async def delete_post(post_id: int, request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id required")
    conn = sqlite3.connect("teamfinder.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Post not found")
    if row[0] != user_id:
        conn.close()
        raise HTTPException(403, "You can delete only your own posts")
    c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# ========== TELEGRAM БОТ (aiogram 2.x, webhook) ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    webapp_url = f"{BASE_URL}/webapp"
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Открыть приложение", web_app=WebAppInfo(url=webapp_url))]],
        resize_keyboard=True
    )
    await message.answer(
        "🎮 *TeamFinder* — найди тиммейтов для Rust, CS, Dota!\n\n"
        "Теперь можно *редактировать* и *удалять* свои объявления.\n"
        "Нажми на кнопку ниже, чтобы открыть приложение.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Настройка webhook при старте приложения
@app.on_event("startup")
async def on_startup():
    webhook_url = f"{BASE_URL}/webhook"
    await bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.close()
    print("Webhook удалён, бот остановлен")

@app.post("/webhook")
async def webhook(request: Request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
