"""TransferDB — CMPE 321 Project 2 — Group 01
Flask app. Single file. All SQL is written manually (no ORM).
Session auth with bcrypt hashing. DB-level constraints enforced by triggers/procs in init.sql.
"""
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import bcrypt
import re
import os
from datetime import datetime, date

DB_HOST = os.environ.get('DB_HOST', 'db')
DB_PORT = int(os.environ.get('DB_PORT', '3306'))
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASS = os.environ.get('DB_PASS', 'password')
DB_NAME = os.environ.get('DB_NAME', 'transferdb')

app = Flask(__name__)
app.secret_key = 'cmpe321_group01_transferdb_secret'


# ============================================================
# DB CONNECTION + SESSION CONTEXT
# ============================================================

def get_db_connection():
    """Open a new MySQL connection and push the current user identity into
    MySQL session variables so DB triggers can enforce role-based rules
    (e.g. only the assigned referee may submit a match result).
    """
    conn = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
    )
    cur = conn.cursor()
    uid = session.get('user_id')
    role = session.get('role')
    if uid is not None and role is not None:
        cur.execute("SET @current_user_id = %s, @current_user_role = %s",
                    (uid if isinstance(uid, int) else 0, role))
    else:
        cur.execute("SET @current_user_id = NULL, @current_user_role = NULL")
    cur.close()
    return conn


# ============================================================
# HELPERS
# ============================================================

def is_password_strong(pw):
    if len(pw) < 8: return False
    if not re.search(r"[a-z]", pw): return False
    if not re.search(r"[A-Z]", pw): return False
    if not re.search(r"[0-9]", pw): return False
    if not re.search(r"[\W_]", pw): return False
    return True


def hash_pw(pw):
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_pw(pw, hashed):
    return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))


def require_role(*roles):
    """Simple guard: redirect to login if role missing."""
    if 'role' not in session or session['role'] not in roles:
        return False
    return True


ROLE_MAP = {
    'Player':    ('Player',     'person_ID'),
    'Manager':   ('Manager',    'person_ID'),
    'Referee':   ('Referee',    'person_ID'),
    'DBManager': ('DB_Manager', 'username'),
}


# ============================================================
# AUTH
# ============================================================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form.get('username', '').strip()
        pw = request.form.get('password', '')

        if role not in ROLE_MAP:
            flash("Gecersiz rol secimi.")
            return redirect(url_for('login'))

        table, id_col = ROLE_MAP[role]
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT * FROM {table} WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close(); conn.close()

        if user and check_pw(pw, user['password']):
            session['username'] = user['username']
            session['role'] = role
            session['user_id'] = user[id_col]
            return redirect(url_for('dashboard'))
        flash("Hatali kullanici adi, sifre veya rol.")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form.get('username', '').strip()
        pw = request.form.get('password', '')

        if role not in ROLE_MAP:
            flash("Gecersiz rol.")
            return redirect(url_for('register'))

        if not is_password_strong(pw):
            flash("Sifre: en az 8 karakter, buyuk+kucuk harf, rakam, ozel karakter.")
            return redirect(url_for('register'))

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            hashed = hash_pw(pw)

            if role == 'DBManager':
                cur.execute("INSERT INTO DB_Manager (username, password) VALUES (%s, %s)",
                            (username, hashed))
            else:
                # All non-DB roles share Person row
                name        = request.form.get('name', '').strip()
                surname     = request.form.get('surname', '').strip()
                nationality = request.form.get('nationality', '').strip()
                dob         = request.form.get('date_of_birth', '').strip()
                if not (name and surname and nationality and dob):
                    flash("Isim/soyisim/uyruk/dogum tarihi zorunlu.")
                    cur.close(); conn.close()
                    return redirect(url_for('register'))

                cur.execute(
                    "INSERT INTO Person (name, surname, nationality, date_of_birth) "
                    "VALUES (%s, %s, %s, %s)",
                    (name, surname, nationality, dob)
                )
                pid = cur.lastrowid

                if role == 'Player':
                    cur.execute(
                        "INSERT INTO Player (person_ID, username, password, market_value, "
                        "main_position, strong_foot, height) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (pid, username, hashed,
                         request.form.get('market_value') or 0,
                         request.form.get('main_position'),
                         request.form.get('strong_foot'),
                         request.form.get('height') or 0)
                    )
                elif role == 'Manager':
                    cur.execute(
                        "INSERT INTO Manager (person_ID, username, password, "
                        "preferred_formation, experience_level) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (pid, username, hashed,
                         request.form.get('preferred_formation', ''),
                         request.form.get('experience_level', ''))
                    )
                elif role == 'Referee':
                    cur.execute(
                        "INSERT INTO Referee (person_ID, username, password, "
                        "license_level, years_of_experience) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (pid, username, hashed,
                         request.form.get('license_level', ''),
                         request.form.get('years_of_experience') or 0)
                    )
            conn.commit()
            flash("Kayit basarili! Giris yapabilirsiniz.")
            return redirect(url_for('login'))
        except mysql.connector.Error as e:
            conn.rollback()
            flash(f"Veritabani Hatasi: {e.msg}")
        finally:
            cur.close(); conn.close()
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============================================================
# DASHBOARD DISPATCH
# ============================================================

@app.route('/dashboard')
def dashboard():
    if 'role' not in session:
        return redirect(url_for('login'))
    role = session['role']
    if role == 'Manager':   return redirect(url_for('manager_home'))
    if role == 'Referee':   return redirect(url_for('referee_home'))
    if role == 'DBManager': return redirect(url_for('db_home'))
    if role == 'Player':
        return render_template('dashboard_player.html',
                               username=session['username'])
    return redirect(url_for('login'))


# ============================================================
# PLAYER OPERATIONS
# ============================================================

@app.route('/player/profile')
def player_profile():
    if not require_role('Player'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT pe.name, pe.surname, pe.nationality, pe.date_of_birth,
               TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
               p.main_position, p.strong_foot, p.height, p.market_value,
               (SELECT c.club_name FROM Contract ct
                  JOIN Club c ON c.club_ID = ct.club_id
                 WHERE ct.player_id = p.person_ID
                   AND CURDATE() BETWEEN ct.start_date AND ct.end_date
                 ORDER BY ct.contract_type='Loan' DESC LIMIT 1) AS current_club
        FROM Player p JOIN Person pe ON pe.person_ID = p.person_ID
        WHERE p.person_ID = %s
    """, (session['user_id'],))
    profile = cur.fetchone()
    cur.close(); conn.close()
    return render_template('player_profile.html', p=profile)


@app.route('/player/performance')
def player_performance():
    if not require_role('Player'): return redirect(url_for('login'))
    season      = request.args.get('season')
    competition = request.args.get('competition_id')

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)

    where = ["ms.player_id = %s"]
    params = [session['user_id']]
    if competition:
        where.append("m.competition_ID = %s"); params.append(competition)
    if season:
        where.append("c.season = %s"); params.append(season)

    cur.execute(f"""
        SELECT COUNT(*) AS games_played,
               COALESCE(SUM(ms.goals),0)       AS goals,
               COALESCE(SUM(ms.assists),0)     AS assists,
               COALESCE(SUM(ms.yellow_cards),0) AS yellows,
               COALESCE(SUM(ms.red_cards),0)    AS reds,
               COALESCE(AVG(ms.rating),0)       AS avg_rating
          FROM Match_Stats ms
          JOIN `Match` m    ON m.match_ID = ms.match_ID
          JOIN Competition c ON c.competition_ID = m.competition_ID
         WHERE {' AND '.join(where)}
           AND m.home_goals IS NOT NULL
    """, tuple(params))
    stats = cur.fetchone()

    # dropdown data
    cur.execute("SELECT DISTINCT season FROM Competition ORDER BY season DESC")
    seasons = [r['season'] for r in cur.fetchall()]
    cur.execute("SELECT competition_ID, name, season FROM Competition ORDER BY season DESC, name")
    comps = cur.fetchall()
    cur.close(); conn.close()
    return render_template('player_performance.html',
                           stats=stats, seasons=seasons, comps=comps,
                           sel_season=season, sel_comp=competition)


@app.route('/player/matches')
def player_matches():
    if not require_role('Player'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.match_datetime, m.home_goals, m.away_goals,
               comp.name AS comp_name, comp.season,
               s.stadium_name,
               (CASE WHEN ms.club_id = m.home_club_ID THEN ha.club_name
                     ELSE hh.club_name END) AS opp_name,
               ms.minutes_played, ms.position_played, ms.goals, ms.assists,
               ms.yellow_cards, ms.red_cards, ms.rating
          FROM Match_Stats ms
          JOIN `Match` m      ON m.match_ID = ms.match_ID
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Stadium s       ON s.stadium_ID = m.stadium_ID
          JOIN Club hh         ON hh.club_ID = m.home_club_ID
          JOIN Club ha         ON ha.club_ID = m.away_club_ID
         WHERE ms.player_id = %s
         ORDER BY m.match_datetime DESC
    """, (session['user_id'],))
    matches = cur.fetchall()
    cur.close(); conn.close()
    return render_template('player_matches.html', matches=matches)


@app.route('/player/career')
def player_career():
    if not require_role('Player'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT ct.*, c.club_name FROM Contract ct
          JOIN Club c ON c.club_ID = ct.club_id
         WHERE ct.player_id = %s ORDER BY ct.start_date DESC
    """, (session['user_id'],))
    contracts = cur.fetchall()
    cur.execute("""
        SELECT tr.*, fc.club_name AS from_name, tc.club_name AS to_name
          FROM Transfer_Record tr
          LEFT JOIN Club fc ON fc.club_ID = tr.from_club_id
          JOIN Club tc ON tc.club_ID = tr.to_club_id
         WHERE tr.player_id = %s ORDER BY tr.transfer_date DESC
    """, (session['user_id'],))
    transfers = cur.fetchall()
    cur.close(); conn.close()
    return render_template('player_career.html',
                           contracts=contracts, transfers=transfers)


# ============================================================
# MANAGER OPERATIONS
# ============================================================

def _manager_club():
    """Return the club row for the currently-logged-in manager (or None)."""
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Club WHERE manager_ID = %s", (session['user_id'],))
    club = cur.fetchone()
    cur.close(); conn.close()
    return club


@app.route('/manager/home')
def manager_home():
    if not require_role('Manager'): return redirect(url_for('login'))
    club = _manager_club()
    if not club:
        return render_template('dashboard_manager.html',
                               username=session['username'], club=None,
                               matches=[], players=[])

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.*, comp.name AS comp_name,
               h.club_name AS home_name, a.club_name AS away_name
          FROM `Match` m
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Club h ON h.club_ID = m.home_club_ID
          JOIN Club a ON a.club_ID = m.away_club_ID
         WHERE (m.home_club_ID = %s OR m.away_club_ID = %s)
           AND m.home_goals IS NULL
         ORDER BY m.match_datetime
    """, (club['club_ID'], club['club_ID']))
    matches = cur.fetchall()

    cur.execute("""
        SELECT p.person_ID, pe.name, pe.surname, p.main_position,
               ct.contract_type, ct.end_date
          FROM Player p
          JOIN Person pe ON pe.person_ID = p.person_ID
          JOIN Contract ct ON ct.player_id = p.person_ID
         WHERE ct.club_id = %s AND CURDATE() BETWEEN ct.start_date AND ct.end_date
    """, (club['club_ID'],))
    players = cur.fetchall()
    cur.close(); conn.close()
    return render_template('dashboard_manager.html',
                           username=session['username'],
                           club=club, matches=matches, players=players)


@app.route('/manager/set_squad', methods=['POST'])
def set_squad():
    if not require_role('Manager'): return "Yetkisiz", 403
    match_id = request.form.get('match_id')
    club_id  = request.form.get('club_id')
    selected = request.form.getlist('players')
    starters = request.form.getlist('starters')

    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM Match_Stats WHERE match_ID=%s AND club_id=%s",
                    (match_id, club_id))
        for p_id in selected:
            is_starter = 1 if p_id in starters else 0
            cur.execute("""
                INSERT INTO Match_Stats
                  (match_ID, player_id, club_id, is_starter, position_played)
                VALUES (%s, %s, %s, %s, 'To be set')
            """, (match_id, p_id, club_id, is_starter))
        # DB-level post-insert guard: enforce 11<=squad<=23 via stored proc.
        # If it signals, the except below rolls back all the inserts above.
        cur.callproc('sp_validate_match_squad', [int(match_id), int(club_id)])
        conn.commit()
        flash("Kadro basariyla guncellendi.")
    except mysql.connector.Error as e:
        conn.rollback()
        flash(f"Kisitlama Hatasi: {e.msg}")
    finally:
        cur.close(); conn.close()
    return redirect(url_for('manager_home'))


@app.route('/manager/fixtures')
def manager_fixtures():
    if not require_role('Manager'): return redirect(url_for('login'))
    club = _manager_club()
    if not club: return redirect(url_for('manager_home'))

    comp_id = request.args.get('competition_id')
    season  = request.args.get('season')

    where = ["(m.home_club_ID = %s OR m.away_club_ID = %s)"]
    params = [club['club_ID'], club['club_ID']]
    if comp_id:
        where.append("m.competition_ID = %s"); params.append(comp_id)
    if season:
        where.append("comp.season = %s"); params.append(season)

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(f"""
        SELECT m.*, comp.name AS comp_name, comp.season,
               h.club_name AS home_name, a.club_name AS away_name,
               s.stadium_name
          FROM `Match` m
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Club h ON h.club_ID = m.home_club_ID
          JOIN Club a ON a.club_ID = m.away_club_ID
          JOIN Stadium s ON s.stadium_ID = m.stadium_ID
         WHERE {' AND '.join(where)}
         ORDER BY m.match_datetime DESC
    """, tuple(params))
    rows = cur.fetchall()

    cur.execute("SELECT DISTINCT season FROM Competition ORDER BY season DESC")
    seasons = [r['season'] for r in cur.fetchall()]
    cur.execute("SELECT competition_ID, name, season FROM Competition")
    comps = cur.fetchall()
    cur.close(); conn.close()
    return render_template('manager_fixtures.html',
                           club=club, rows=rows, seasons=seasons, comps=comps,
                           sel_comp=comp_id, sel_season=season)


@app.route('/manager/standings')
def manager_standings():
    if not require_role('Manager'): return redirect(url_for('login'))
    club = _manager_club()
    if not club: return redirect(url_for('manager_home'))

    comp_id = request.args.get('competition_id')
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)

    # Competitions the club actually participated in, type=League only
    cur.execute("""
        SELECT DISTINCT c.competition_ID, c.name, c.season
          FROM Competition c
          JOIN `Match` m ON m.competition_ID = c.competition_ID
         WHERE c.competition_type = 'League'
           AND (m.home_club_ID = %s OR m.away_club_ID = %s)
         ORDER BY c.season DESC, c.name
    """, (club['club_ID'], club['club_ID']))
    comps = cur.fetchall()

    standings = []
    if comp_id:
        cur.execute("""
            SELECT cl.club_ID, cl.club_name,
                   SUM(CASE WHEN m.home_goals IS NOT NULL THEN 1 ELSE 0 END) AS played,
                   SUM(CASE WHEN (m.home_club_ID = cl.club_ID AND m.home_goals > m.away_goals)
                             OR (m.away_club_ID = cl.club_ID AND m.away_goals > m.home_goals)
                            THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN m.home_goals IS NOT NULL AND m.home_goals = m.away_goals
                            THEN 1 ELSE 0 END) AS draws,
                   SUM(CASE WHEN (m.home_club_ID = cl.club_ID AND m.home_goals < m.away_goals)
                             OR (m.away_club_ID = cl.club_ID AND m.away_goals < m.home_goals)
                            THEN 1 ELSE 0 END) AS losses,
                   COALESCE(SUM(CASE WHEN m.home_club_ID = cl.club_ID THEN m.home_goals
                                     WHEN m.away_club_ID = cl.club_ID THEN m.away_goals
                                     ELSE 0 END), 0) AS gf,
                   COALESCE(SUM(CASE WHEN m.home_club_ID = cl.club_ID THEN m.away_goals
                                     WHEN m.away_club_ID = cl.club_ID THEN m.home_goals
                                     ELSE 0 END), 0) AS ga
              FROM Club cl
              JOIN `Match` m ON (m.home_club_ID = cl.club_ID OR m.away_club_ID = cl.club_ID)
             WHERE m.competition_ID = %s
             GROUP BY cl.club_ID, cl.club_name
             ORDER BY (
                 SUM(CASE WHEN (m.home_club_ID = cl.club_ID AND m.home_goals > m.away_goals)
                            OR (m.away_club_ID = cl.club_ID AND m.away_goals > m.home_goals)
                           THEN 3 ELSE 0 END) +
                 SUM(CASE WHEN m.home_goals IS NOT NULL AND m.home_goals = m.away_goals
                           THEN 1 ELSE 0 END)
             ) DESC,
             (SUM(CASE WHEN m.home_club_ID = cl.club_ID THEN m.home_goals
                       WHEN m.away_club_ID = cl.club_ID THEN m.away_goals ELSE 0 END)
              - SUM(CASE WHEN m.home_club_ID = cl.club_ID THEN m.away_goals
                         WHEN m.away_club_ID = cl.club_ID THEN m.home_goals ELSE 0 END)
             ) DESC
        """, (comp_id,))
        standings = cur.fetchall()
        for r in standings:
            r['points'] = r['wins']*3 + r['draws']
            r['gd']     = r['gf'] - r['ga']
    cur.close(); conn.close()
    return render_template('manager_standings.html',
                           club=club, comps=comps, standings=standings,
                           sel_comp=comp_id)


@app.route('/manager/squad_stats')
def manager_squad_stats():
    if not require_role('Manager'): return redirect(url_for('login'))
    club = _manager_club()
    if not club: return redirect(url_for('manager_home'))

    comp_id = request.args.get('competition_id')
    season  = request.args.get('season')

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)

    extra_where = []
    extra_params = []
    if comp_id:
        extra_where.append("m.competition_ID = %s"); extra_params.append(comp_id)
    if season:
        extra_where.append("c.season = %s"); extra_params.append(season)
    extra_sql = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    # Historical view: all players who appeared for this club in filtered competitions
    if comp_id or season:
        cur.execute(f"""
            SELECT pe.name, pe.surname, p.main_position, p.strong_foot,
                   p.height, p.market_value, pe.nationality,
                   TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
                   COUNT(*) AS games,
                   COALESCE(SUM(ms.goals),0)       AS goals,
                   COALESCE(SUM(ms.assists),0)     AS assists,
                   COALESCE(SUM(ms.yellow_cards),0) AS yellows,
                   COALESCE(SUM(ms.red_cards),0)    AS reds,
                   COALESCE(AVG(ms.rating),0)       AS avg_rating,
                   COALESCE(AVG(ms.minutes_played),0) AS avg_min
              FROM Match_Stats ms
              JOIN `Match` m ON m.match_ID = ms.match_ID
              JOIN Competition c ON c.competition_ID = m.competition_ID
              JOIN Player p ON p.person_ID = ms.player_id
              JOIN Person pe ON pe.person_ID = p.person_ID
             WHERE ms.club_id = %s AND m.home_goals IS NOT NULL {extra_sql}
             GROUP BY p.person_ID, pe.name, pe.surname, p.main_position,
                      p.strong_foot, p.height, p.market_value, pe.nationality, pe.date_of_birth
             ORDER BY goals DESC
        """, tuple([club['club_ID']] + extra_params))
    else:
        # Current squad view: players under active contract, stats only for this club
        cur.execute("""
            SELECT pe.name, pe.surname, p.main_position, p.strong_foot,
                   p.height, p.market_value, pe.nationality,
                   TIMESTAMPDIFF(YEAR, pe.date_of_birth, CURDATE()) AS age,
                   COALESCE((SELECT COUNT(*) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS games,
                   COALESCE((SELECT SUM(ms.goals) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS goals,
                   COALESCE((SELECT SUM(ms.assists) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS assists,
                   COALESCE((SELECT SUM(ms.yellow_cards) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS yellows,
                   COALESCE((SELECT SUM(ms.red_cards) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS reds,
                   COALESCE((SELECT AVG(ms.rating) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS avg_rating,
                   COALESCE((SELECT AVG(ms.minutes_played) FROM Match_Stats ms
                              JOIN `Match` m ON m.match_ID = ms.match_ID
                              WHERE ms.player_id = p.person_ID
                                AND ms.club_id = %s AND m.home_goals IS NOT NULL), 0) AS avg_min
              FROM Player p
              JOIN Person pe ON pe.person_ID = p.person_ID
              JOIN Contract ct ON ct.player_id = p.person_ID
             WHERE ct.club_id = %s AND CURDATE() BETWEEN ct.start_date AND ct.end_date
        """, (club['club_ID'],)*7 + (club['club_ID'],))
    stats = cur.fetchall()

    cur.execute("SELECT DISTINCT season FROM Competition ORDER BY season DESC")
    seasons = [r['season'] for r in cur.fetchall()]
    cur.execute("SELECT competition_ID, name, season FROM Competition")
    comps = cur.fetchall()
    cur.close(); conn.close()
    return render_template('manager_squad_stats.html',
                           club=club, stats=stats,
                           seasons=seasons, comps=comps,
                           sel_comp=comp_id, sel_season=season)


@app.route('/manager/leaderboards')
def manager_leaderboards():
    if not require_role('Manager'): return redirect(url_for('login'))
    club = _manager_club()
    if not club: return redirect(url_for('manager_home'))

    comp_id = request.args.get('competition_id')

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    # Competitions the manager's club has participated in
    cur.execute("""
        SELECT DISTINCT c.competition_ID, c.name, c.season
          FROM Competition c JOIN `Match` m ON m.competition_ID = c.competition_ID
         WHERE (m.home_club_ID = %s OR m.away_club_ID = %s)
         ORDER BY c.season DESC, c.name
    """, (club['club_ID'], club['club_ID']))
    comps = cur.fetchall()

    top_goals = top_assists = top_rating = []
    if comp_id:
        common_join = """
            FROM Match_Stats ms
            JOIN `Match` m ON m.match_ID = ms.match_ID
            JOIN Player p  ON p.person_ID = ms.player_id
            JOIN Person pe ON pe.person_ID = p.person_ID
            JOIN Club cl   ON cl.club_ID = ms.club_id
            WHERE m.competition_ID = %s AND m.home_goals IS NOT NULL
            GROUP BY ms.player_id, pe.name, pe.surname, cl.club_name
        """
        cur.execute(f"""
            SELECT pe.name, pe.surname, cl.club_name,
                   COUNT(*) AS played, SUM(ms.goals) AS metric
            {common_join}
            ORDER BY metric DESC, played DESC LIMIT 10
        """, (comp_id,))
        top_goals = cur.fetchall()

        cur.execute(f"""
            SELECT pe.name, pe.surname, cl.club_name,
                   COUNT(*) AS played, SUM(ms.assists) AS metric
            {common_join}
            ORDER BY metric DESC, played DESC LIMIT 10
        """, (comp_id,))
        top_assists = cur.fetchall()

        cur.execute(f"""
            SELECT pe.name, pe.surname, cl.club_name,
                   COUNT(*) AS played, ROUND(AVG(ms.rating),2) AS metric
            {common_join}
            HAVING played >= 3
            ORDER BY metric DESC LIMIT 10
        """, (comp_id,))
        top_rating = cur.fetchall()
    cur.close(); conn.close()
    return render_template('manager_leaderboards.html',
                           club=club, comps=comps, sel_comp=comp_id,
                           top_goals=top_goals, top_assists=top_assists,
                           top_rating=top_rating)


# ============================================================
# REFEREE OPERATIONS
# ============================================================

@app.route('/referee/home')
def referee_home():
    if not require_role('Referee'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.*, comp.name AS comp_name,
               h.club_name AS home_name, a.club_name AS away_name
          FROM `Match` m
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Club h ON h.club_ID = m.home_club_ID
          JOIN Club a ON a.club_ID = m.away_club_ID
         WHERE m.referee_ID = %s AND m.home_goals IS NULL
         ORDER BY m.match_datetime
    """, (session['user_id'],))
    matches = cur.fetchall()
    cur.close(); conn.close()
    return render_template('dashboard_referee.html',
                           username=session['username'], matches=matches)


@app.route('/referee/enter_stats/<int:match_id>')
def enter_stats(match_id):
    if not require_role('Referee'): return "Yetkisiz", 403
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.*, h.club_name AS home_name, a.club_name AS away_name
          FROM `Match` m
          JOIN Club h ON h.club_ID = m.home_club_ID
          JOIN Club a ON a.club_ID = m.away_club_ID
         WHERE m.match_ID = %s AND m.referee_ID = %s
    """, (match_id, session['user_id']))
    match = cur.fetchone()
    if not match:
        cur.close(); conn.close()
        return "Bu maca atanmamissin.", 403

    cur.execute("""
        SELECT ms.*, pe.name, pe.surname, c.club_name
          FROM Match_Stats ms
          JOIN Person pe ON pe.person_ID = ms.player_id
          JOIN Club c    ON c.club_ID = ms.club_id
         WHERE ms.match_ID = %s
         ORDER BY ms.club_id, ms.is_starter DESC
    """, (match_id,))
    players = cur.fetchall()
    cur.close(); conn.close()
    if not players:
        flash("Bu mac icin henuz kadro bildirilmemis.")
        return redirect(url_for('referee_home'))
    return render_template('enter_stats.html', match=match, players=players)


@app.route('/referee/save_stats', methods=['POST'])
def save_stats():
    if not require_role('Referee'): return "Yetkisiz", 403

    match_id    = request.form.get('match_id')
    home_goals  = request.form.get('home_goals')
    away_goals  = request.form.get('away_goals')
    attendance  = request.form.get('attendance')

    conn = get_db_connection(); cur = conn.cursor()
    try:
        # Write per-player stats first (they don't depend on Match update)
        for p_id in request.form.getlist('player_id'):
            cur.execute("""
                UPDATE Match_Stats
                   SET minutes_played=%s, goals=%s, assists=%s,
                       yellow_cards=%s, red_cards=%s, rating=%s,
                       position_played=%s
                 WHERE match_ID=%s AND player_id=%s
            """, (
                request.form.get(f'minutes_{p_id}') or 0,
                request.form.get(f'goals_{p_id}') or 0,
                request.form.get(f'assists_{p_id}') or 0,
                request.form.get(f'yellow_{p_id}') or 0,
                request.form.get(f'red_{p_id}') or 0,
                request.form.get(f'rating_{p_id}') or None,
                request.form.get(f'position_{p_id}') or 'Unknown',
                match_id, p_id
            ))

        # Then call the stored procedure — it updates Match, auto-serves old
        # suspensions, and creates new ones for red / 5-yellow.
        cur.callproc('sp_submit_match_result',
                     [int(match_id), int(home_goals), int(away_goals), int(attendance)])
        conn.commit()
        flash("Mac sonucu ve istatistikler kaydedildi.")
    except mysql.connector.Error as e:
        conn.rollback()
        flash(f"Hata: {e.msg}")
    finally:
        cur.close(); conn.close()
    return redirect(url_for('referee_home'))


@app.route('/referee/stats')
def referee_stats():
    if not require_role('Referee'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT COUNT(*) AS matches_officiated,
               COALESCE(SUM(yellows),0) AS total_yellows,
               COALESCE(SUM(reds),0)    AS total_reds
          FROM (
            SELECT m.match_ID,
                   COALESCE(SUM(ms.yellow_cards),0) AS yellows,
                   COALESCE(SUM(ms.red_cards),0)    AS reds
              FROM `Match` m
              LEFT JOIN Match_Stats ms ON ms.match_ID = m.match_ID
             WHERE m.referee_ID = %s AND m.home_goals IS NOT NULL
             GROUP BY m.match_ID
          ) t
    """, (session['user_id'],))
    stats = cur.fetchone()
    cur.close(); conn.close()
    return render_template('referee_stats.html', stats=stats)


@app.route('/referee/history')
def referee_history():
    if not require_role('Referee'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.match_ID, m.match_datetime, m.home_goals, m.away_goals, m.attendance,
               comp.name AS comp_name, comp.season,
               s.stadium_name,
               h.club_name AS home_name, a.club_name AS away_name,
               COALESCE((SELECT SUM(yellow_cards) FROM Match_Stats
                         WHERE match_ID = m.match_ID), 0) AS yellows,
               COALESCE((SELECT SUM(red_cards) FROM Match_Stats
                         WHERE match_ID = m.match_ID), 0) AS reds
          FROM `Match` m
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Stadium s    ON s.stadium_ID = m.stadium_ID
          JOIN Club h       ON h.club_ID = m.home_club_ID
          JOIN Club a       ON a.club_ID = m.away_club_ID
         WHERE m.referee_ID = %s
         ORDER BY m.match_datetime DESC
    """, (session['user_id'],))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template('referee_history.html', rows=rows)


# ============================================================
# DB MANAGER OPERATIONS
# ============================================================

@app.route('/db/home')
def db_home():
    if not require_role('DBManager'): return redirect(url_for('login'))
    return render_template('dashboard_dbmanager.html', username=session['username'])


@app.route('/db/stadiums', methods=['GET', 'POST'])
def db_stadiums():
    if not require_role('DBManager'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)

    if request.method == 'POST':
        # Either add a new stadium or rename an existing one
        action = request.form.get('action')
        try:
            if action == 'add':
                cur.execute(
                    "INSERT INTO Stadium (stadium_name, city, capacity) "
                    "VALUES (%s, %s, %s)",
                    (request.form['stadium_name'],
                     request.form['city'],
                     request.form['capacity'])
                )
                conn.commit(); flash("Stadyum eklendi.")
            elif action == 'rename':
                cur.execute(
                    "UPDATE Stadium SET stadium_name=%s WHERE stadium_ID=%s",
                    (request.form['new_name'], request.form['stadium_id'])
                )
                conn.commit(); flash("Stadyum adi guncellendi.")
        except mysql.connector.Error as e:
            conn.rollback(); flash(f"Hata: {e.msg}")

    cur.execute("""
        SELECT s.*, GROUP_CONCAT(c.club_name SEPARATOR ', ') AS clubs
          FROM Stadium s
          LEFT JOIN Club c ON c.stadium_ID = s.stadium_ID
         GROUP BY s.stadium_ID ORDER BY s.stadium_name
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template('db_stadiums.html', rows=rows)


@app.route('/db/clubs', methods=['GET', 'POST'])
def db_clubs():
    """Create a club + assign/update its manager."""
    if not require_role('DBManager'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cur.execute("""
                    INSERT INTO Club (club_name, stadium_ID, city,
                                      foundation_year, manager_ID)
                    VALUES (%s, %s, %s, %s, %s)
                """, (request.form['club_name'],
                      request.form['stadium_id'],
                      request.form['city'],
                      request.form['foundation_year'],
                      request.form.get('manager_id') or None))
                conn.commit(); flash("Kulup eklendi.")
            elif action == 'reassign':
                new_manager = request.form.get('manager_id') or None
                club_id = request.form['club_id']
                # If the new manager currently manages another club, free that first.
                if new_manager:
                    cur.execute("UPDATE Club SET manager_ID=NULL "
                                "WHERE manager_ID=%s AND club_ID<>%s",
                                (new_manager, club_id))
                cur.execute("UPDATE Club SET manager_ID=%s WHERE club_ID=%s",
                            (new_manager, club_id))
                conn.commit(); flash("Menajer atamasi guncellendi.")
    except mysql.connector.Error as e:
        conn.rollback(); flash(f"Hata: {e.msg}")

    cur.execute("""
        SELECT c.*, s.stadium_name, s.city AS stadium_city,
               pe.name AS mgr_name, pe.surname AS mgr_surname
          FROM Club c
          JOIN Stadium s ON s.stadium_ID = c.stadium_ID
          LEFT JOIN Manager m ON m.person_ID = c.manager_ID
          LEFT JOIN Person pe ON pe.person_ID = m.person_ID
         ORDER BY c.club_name
    """)
    clubs = cur.fetchall()
    cur.execute("SELECT stadium_ID, stadium_name, city FROM Stadium ORDER BY stadium_name")
    stadiums = cur.fetchall()
    cur.execute("""
        SELECT m.person_ID, pe.name, pe.surname,
               (SELECT club_name FROM Club WHERE manager_ID = m.person_ID) AS current_club
          FROM Manager m JOIN Person pe ON pe.person_ID = m.person_ID
         ORDER BY pe.surname
    """)
    managers = cur.fetchall()
    cur.close(); conn.close()
    return render_template('db_clubs.html',
                           clubs=clubs, stadiums=stadiums, managers=managers)


@app.route('/db/competitions', methods=['GET', 'POST'])
def db_competitions():
    if not require_role('DBManager'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            cur.execute("""
                INSERT INTO Competition (name, season, country, competition_type)
                VALUES (%s, %s, %s, %s)
            """, (request.form['name'], request.form['season'],
                  request.form['country'], request.form['competition_type']))
            conn.commit(); flash("Competition olusturuldu.")
    except mysql.connector.Error as e:
        conn.rollback(); flash(f"Hata: {e.msg}")

    cur.execute("SELECT * FROM Competition ORDER BY season DESC, name")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template('db_competitions.html', rows=rows)


@app.route('/db/matches', methods=['GET', 'POST'])
def db_matches():
    if not require_role('DBManager'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            cur.execute("""
                INSERT INTO `Match` (competition_ID, home_club_ID, away_club_ID,
                                     stadium_ID, referee_ID, match_datetime)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (request.form['competition_id'],
                  request.form['home_club_id'],
                  request.form['away_club_id'],
                  request.form['stadium_id'],
                  request.form['referee_id'],
                  request.form['match_datetime']))
            conn.commit(); flash("Mac planlandi.")
    except mysql.connector.Error as e:
        conn.rollback(); flash(f"Hata: {e.msg}")

    cur.execute("""
        SELECT m.*, comp.name AS comp_name, comp.season,
               h.club_name AS home_name, a.club_name AS away_name,
               s.stadium_name, pe.name AS ref_name, pe.surname AS ref_surname
          FROM `Match` m
          JOIN Competition comp ON comp.competition_ID = m.competition_ID
          JOIN Club h ON h.club_ID = m.home_club_ID
          JOIN Club a ON a.club_ID = m.away_club_ID
          JOIN Stadium s ON s.stadium_ID = m.stadium_ID
          JOIN Referee r ON r.person_ID = m.referee_ID
          JOIN Person pe ON pe.person_ID = r.person_ID
         ORDER BY m.match_datetime DESC LIMIT 50
    """)
    rows = cur.fetchall()

    cur.execute("SELECT competition_ID, name, season FROM Competition ORDER BY season DESC, name")
    comps = cur.fetchall()
    cur.execute("SELECT club_ID, club_name FROM Club ORDER BY club_name")
    clubs = cur.fetchall()
    cur.execute("SELECT stadium_ID, stadium_name FROM Stadium ORDER BY stadium_name")
    stadiums = cur.fetchall()
    cur.execute("""
        SELECT r.person_ID, pe.name, pe.surname FROM Referee r
          JOIN Person pe ON pe.person_ID = r.person_ID ORDER BY pe.surname
    """)
    referees = cur.fetchall()
    cur.close(); conn.close()
    return render_template('db_matches.html',
                           rows=rows, comps=comps, clubs=clubs,
                           stadiums=stadiums, referees=referees)


@app.route('/db/transfer', methods=['GET', 'POST'])
def db_transfer():
    if not require_role('DBManager'): return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            cur.callproc('sp_register_transfer', [
                int(request.form['player_id']),
                int(request.form['to_club_id']),
                request.form['contract_type'],
                float(request.form['weekly_wage']),
                float(request.form['transfer_fee']),
                request.form['end_date']
            ])
            conn.commit(); flash("Transfer ve kontrat kaydedildi.")
    except mysql.connector.Error as e:
        conn.rollback(); flash(f"Hata: {e.msg}")

    cur.execute("""
        SELECT p.person_ID, pe.name, pe.surname,
               (SELECT c.club_name FROM Contract ct
                  JOIN Club c ON c.club_ID = ct.club_id
                 WHERE ct.player_id = p.person_ID AND ct.contract_type='Permanent'
                   AND CURDATE() BETWEEN ct.start_date AND ct.end_date
                 LIMIT 1) AS cur_club
          FROM Player p JOIN Person pe ON pe.person_ID = p.person_ID
         ORDER BY pe.surname
    """)
    players = cur.fetchall()
    cur.execute("SELECT club_ID, club_name FROM Club ORDER BY club_name")
    clubs = cur.fetchall()

    cur.execute("""
        SELECT tr.*, pe.name, pe.surname,
               fc.club_name AS from_name, tc.club_name AS to_name
          FROM Transfer_Record tr
          JOIN Player p ON p.person_ID = tr.player_id
          JOIN Person pe ON pe.person_ID = p.person_ID
          LEFT JOIN Club fc ON fc.club_ID = tr.from_club_id
          JOIN Club tc ON tc.club_ID = tr.to_club_id
         ORDER BY tr.transfer_date DESC LIMIT 30
    """)
    transfers = cur.fetchall()
    cur.close(); conn.close()
    return render_template('db_transfer.html',
                           players=players, clubs=clubs, transfers=transfers)


# ============================================================
# ERROR HANDLING
# ============================================================

@app.errorhandler(500)
def internal_error(error):
    return "<h3>Sunucu Hatasi (500)</h3>", 500


@app.errorhandler(Exception)
def handle_exception(e):
    return f"<h3>Beklenmeyen hata:</h3><p>{str(e)}</p>", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
