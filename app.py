from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import bcrypt
import re

app = Flask(__name__)
app.secret_key = 'cmpe321_super_secret_key' # sessionlar icin gerekli

# veritabani baglantisi fonksiyonu
def get_db_connection():
    return mysql.connector.connect(
        host='db',
        user='root', # kendi mysql kullanici adin
        password='password', # kendi mysql sifren
        database='transferdb'
    )

# backend seviyesinde sifre politikasi kontrolu
def is_password_strong(password):
    if len(password) < 8: return False
    if not re.search(r"[a-z]", password): return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"[0-9]", password): return False
    if not re.search(r"[\W_]", password): return False
    return True

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username']
        raw_password = request.form['password']
        
        # diger form verilerini de role gore alman gerekecek (name, surname, dob vb.)
        # burada ornek olarak sadece kimlik dogrulama kismina odaklaniyoruz
        
        if not is_password_strong(raw_password):
            flash("sifre en az 8 karakter olmali buyuk/kucuk harf rakam ve ozel karakter icermelidir")
            return redirect(url_for('register'))
            
        # sifreyi bcrypt ile hashliyoruz
        hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt())
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # kullaniciyi veritabanina ekleme (ornek olarak Player ekliyoruz)
            # part 2 dokumanina gore once Person tablosuna sonra ilgili role ekleme yapilmalidir
            # burada sql injection onlemek icin %s (parameterized queries) kullaniyoruz
            
            # not: gercek senaryoda once person tablosuna insert yapip son id'yi almalisin
            # ornek: cursor.execute("INSERT INTO Person (name, surname...) VALUES (%s, %s)", (name, surname))
            # new_id = cursor.lastrowid
            
            # asagidaki sorgu varsayimsal bir guncellemedir kendi tablonun kolonlarina gore uyarla
            if role == 'Player':
                query = "INSERT INTO Player (username, password) VALUES (%s, %s)"
                cursor.execute(query, (username, hashed_password.decode('utf-8')))
            
            conn.commit()
            flash("kayit basarili giris yapabilirsiniz")
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f"veritabani hatasi: {err}")
        finally:
            cursor.close()
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username']
        password_attempt = request.form['password']
        
        # tablo ismini dinamik alamayacagimiz icin (sql injection riski) if else ile yapiyoruz
        table_name = ""
        id_column = ""
        if role == 'Player':
            table_name = "Player"
            id_column = "person_ID"
        elif role == 'Manager':
            table_name = "Manager"
            id_column = "person_ID"
        elif role == 'Referee':
            table_name = "Referee"
            id_column = "person_ID"
        elif role == 'DBManager':
            table_name = "DB_Manager" # db manager tablosunun adi boyleyse
            id_column = "username" # db managerin int idsi yoksa username olabilir
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # parameterli sorgu (guvenli)
        query = f"SELECT * FROM {table_name} WHERE username = %s"
        cursor.execute(query, (username,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # kullanici bulundu mu ve sifre dogru mu kontrolu
        if user and bcrypt.checkpw(password_attempt.encode('utf-8'), user['password'].encode('utf-8')):
            session['username'] = user['username']
            session['role'] = role
            session['user_id'] = user[id_column]
            return redirect(url_for('dashboard'))
        else:
            flash("hatali kullanici adi veya sifre veya yanlis rol secimi")
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    role = session['role']
    # kullanici rolune gore farkli bilgiler gonderebiliriz
    return f"hosgeldin {session['username']} sen bir {role}sin! burasi ana ekranin olacak."

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
