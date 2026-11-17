import os
import re
from datetime import datetime
try:
    from flask import Flask, render_template, request, redirect, url_for, flash
    from flask_sqlalchemy import SQLAlchemy
    from flask_migrate import Migrate, upgrade
    from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
    from werkzeug.security import generate_password_hash, check_password_hash
except ImportError:
    print('Не установлены библиотеки flask, flask-sqlalchemy, flask-migrate и flask-login. Чтобы установить используйте pip3 install -U -r requirements.txt')
    raise SystemExit

POSTS_PER_PAGE = 5

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Войдите, чтобы открыть эту страницу'
login_manager.login_message_category = 'warning'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    posts = db.relationship('Post', backref='author', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created = db.Column(db.DateTime, nullable=False, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Post {self.title}>'

@login_manager.user_loader
def load_user(user_id:str):
    return db.session.get(User, int(user_id))

def validate_user(username:str, email:str, password:str):
    if len(username) < 3 or len(username) > 30:
        raise ValueError('Имя пользователя должно быть от 3 до 30 символов')
    if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) is None or len(email) > 120:
        raise ValueError(f'Некорректный e-mail: {email}')
    if len(password) < 8:
        raise ValueError('Пароль должен быть не короче 8 символов')
    if re.search(r'\d', password) is None or re.search(r'[^\W\d_]', password) is None:
        raise ValueError('Пароль должен содержать буквы и цифры')
    if User.query.filter_by(username=username).first() is not None:
        raise ValueError(f'Имя пользователя уже занято: {username}')
    if User.query.filter_by(email=email).first() is not None:
        raise ValueError(f'Пользователь с таким e-mail уже есть: {email}')

def validate_post(title:str, text:str):
    if title == '':
        raise ValueError('Заголовок поста не может быть пустым')
    if len(title) > 100:
        raise ValueError('Заголовок поста не может быть длиннее 100 символов')
    if len(text) < 10:
        raise ValueError('Текст поста должен быть не короче 10 символов')

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created.desc()).paginate(page=page, per_page=POSTS_PER_PAGE, error_out=False)
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template('register.html', username='', email='')

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    try:
        validate_user(username, email, password)
    except ValueError as err:
        flash(str(err), 'danger')
        return render_template('register.html', username=username, email=email)

    user = User(username=username, email=email, password=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    flash('Регистрация прошла успешно, теперь можно войти', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template('login.html', username='')

    username = request.form.get('username', '').strip()
    user = User.query.filter_by(username=username).first()

    if user is None or not check_password_hash(user.password, request.form.get('password', '')):
        flash('Неверное имя пользователя или пароль', 'danger')
        return render_template('login.html', username=username)

    login_user(user)
    flash(f'Вы вошли как {user.username}', 'success')
    return redirect(url_for('index'))

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route('/post/<int:post_id>')
def show_post(post_id:int):
    post = db.get_or_404(Post, post_id)
    return render_template('post.html', post=post)

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'GET':
        return render_template('post_form.html', heading='Новый пост', title='', text='')

    title = request.form.get('title', '').strip()
    text = request.form.get('text', '').strip()

    try:
        validate_post(title, text)
    except ValueError as err:
        flash(str(err), 'danger')
        return render_template('post_form.html', heading='Новый пост', title=title, text=text)

    post = Post(title=title, text=text, user_id=current_user.id)
    db.session.add(post)
    db.session.commit()
    flash('Пост опубликован', 'success')
    return redirect(url_for('show_post', post_id=post.id))

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id:int):
    post = db.get_or_404(Post, post_id)
    if post.author != current_user:
        flash('Редактировать пост может только его автор', 'danger')
        return redirect(url_for('show_post', post_id=post.id))
    if request.method == 'GET':
        return render_template('post_form.html', heading='Редактирование поста', title=post.title, text=post.text)

    title = request.form.get('title', '').strip()
    text = request.form.get('text', '').strip()

    try:
        validate_post(title, text)
    except ValueError as err:
        flash(str(err), 'danger')
        return render_template('post_form.html', heading='Редактирование поста', title=title, text=text)

    post.title = title
    post.text = text
    db.session.commit()
    flash('Пост изменен', 'success')
    return redirect(url_for('show_post', post_id=post.id))

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id:int):
    post = db.get_or_404(Post, post_id)
    if post.author != current_user:
        flash('Удалить пост может только его автор', 'danger')
        return redirect(url_for('show_post', post_id=post.id))

    db.session.delete(post)
    db.session.commit()
    flash('Пост удален', 'success')
    return redirect(url_for('index'))

@app.errorhandler(404)
def not_found(err):
    return render_template('404.html'), 404

with app.app_context():
    upgrade()

app.run(debug=True, port=5001)
