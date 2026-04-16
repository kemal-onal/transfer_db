"""Seed the transferdb database from initial_data.xlsx.

Loads all eleven sheets in FK-safe order with @DISABLE_TRIGGERS = 1 so
the intentionally-invalid historical records described in spec §2.3 can
be inserted without tripping validation triggers.
"""
import os
import pandas as pd
import bcrypt
import mysql.connector
from datetime import datetime


def conn():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'db'),
        port=int(os.environ.get('DB_PORT', '3306')),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASS', 'password'),
        database=os.environ.get('DB_NAME', 'transferdb'),
    )


def hash_pw(pw):
    return bcrypt.hashpw(str(pw).encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def df(xls, sheet):
    d = pd.read_excel(xls, sheet)
    # Coerce NaN / NaT to actual None so mysql-connector binds NULL
    return d.astype(object).where(d.notna(), None)


def main():
    xls = pd.ExcelFile('initial_data.xlsx')
    c = conn(); cur = c.cursor()
    # Turn off triggers + FK checks during bulk load
    cur.execute("SET @DISABLE_TRIGGERS = 1")
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")

    try:
        # ---- Stadiums ----
        print("Stadiums...")
        for _, r in df(xls, 'Stadiums').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Stadium (stadium_ID, stadium_name, city, capacity) "
                "VALUES (%s, %s, %s, %s)",
                (r['stadium_id'], r['stadium_name'], r['city'], r['capacity'])
            )

        # ---- DB Managers ----
        print("DB Managers...")
        for _, r in df(xls, 'DB Managers').iterrows():
            cur.execute(
                "INSERT IGNORE INTO DB_Manager (username, password) VALUES (%s, %s)",
                (r['username'], hash_pw(r['password']))
            )

        # ---- Persons + Managers ----
        print("Managers...")
        for _, r in df(xls, 'Managers').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Person (person_ID, name, surname, nationality, date_of_birth) "
                "VALUES (%s, %s, %s, %s, %s)",
                (r['manager_id'], r['name'], r['surname'], r['nationality'], r['date_of_birth'])
            )
            cur.execute(
                "INSERT IGNORE INTO Manager (person_ID, username, password, "
                "preferred_formation, experience_level) VALUES (%s, %s, %s, %s, %s)",
                (r['manager_id'], r['username'], hash_pw(r['password']),
                 r['preferred_formation'], r['experience_level'])
            )

        # ---- Persons + Referees ----
        print("Referees...")
        for _, r in df(xls, 'Referees').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Person (person_ID, name, surname, nationality, date_of_birth) "
                "VALUES (%s, %s, %s, %s, %s)",
                (r['referee_id'], r['name'], r['surname'], r['nationality'], r['date_of_birth'])
            )
            cur.execute(
                "INSERT IGNORE INTO Referee (person_ID, username, password, "
                "license_level, years_of_experience) VALUES (%s, %s, %s, %s, %s)",
                (r['referee_id'], r['username'], hash_pw(r['password']),
                 r['license_level'], r['years_of_experience'])
            )

        # ---- Persons + Players ----
        print("Players...")
        for _, r in df(xls, 'Players').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Person (person_ID, name, surname, nationality, date_of_birth) "
                "VALUES (%s, %s, %s, %s, %s)",
                (r['player_id'], r['name'], r['surname'], r['nationality'], r['date_of_birth'])
            )
            cur.execute(
                "INSERT IGNORE INTO Player (person_ID, username, password, market_value, "
                "main_position, strong_foot, height) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (r['player_id'], r['username'], hash_pw(r['password']),
                 r['market_value'], r['main_position'], r['strong_foot'], r['height'])
            )

        # ---- Clubs (city derived from stadium; skip rows with no stadium) ----
        print("Clubs...")
        skipped = 0
        for _, r in df(xls, 'Clubs').iterrows():
            if r['stadium_id'] is None:
                skipped += 1
                continue
            cur.execute("SELECT city FROM Stadium WHERE stadium_ID = %s",
                        (int(r['stadium_id']),))
            row = cur.fetchone()
            club_city = row[0] if row else 'Unknown'
            cur.execute(
                "INSERT IGNORE INTO Club (club_ID, club_name, stadium_ID, city, "
                "foundation_year, manager_ID) VALUES (%s, %s, %s, %s, %s, %s)",
                (r['club_id'], r['club_name'], int(r['stadium_id']), club_city,
                 r['foundation_year'],
                 int(r['manager_id']) if r['manager_id'] is not None else None)
            )
        if skipped:
            print(f"  (stadyumsuz {skipped} kulup atlandi)")

        # ---- Competitions ----
        print("Competitions...")
        for _, r in df(xls, 'Competitions').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Competition (competition_ID, name, season, country, "
                "competition_type) VALUES (%s, %s, %s, %s, %s)",
                (r['competition_id'], r['name'], r['season'], r['country'], r['competition_type'])
            )

        # ---- Contracts ----
        print("Contracts...")
        for _, r in df(xls, 'Contracts').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Contract (contract_id, player_id, club_id, start_date, "
                "end_date, weekly_wage, contract_type) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (r['contract_id'], r['player_id'], r['club_id'], r['start_date'],
                 r['end_date'], r['weekly_wage'], r['contract_type'])
            )

        # ---- Matches (combine match_date + match_time into datetime) ----
        print("Matches...")
        for _, r in df(xls, 'Matches').iterrows():
            md = r['match_date']
            mt = r['match_time']
            # Pandas gives Timestamp for date, timedelta for time
            if hasattr(md, 'date'): md_part = md.date()
            else: md_part = md
            if hasattr(mt, 'total_seconds'):
                secs = int(mt.total_seconds())
                mt_part = f"{secs//3600:02d}:{(secs%3600)//60:02d}:{secs%60:02d}"
            else:
                mt_part = str(mt)
            match_dt = f"{md_part} {mt_part}"
            cur.execute(
                "INSERT IGNORE INTO `Match` (match_ID, competition_ID, home_club_ID, "
                "away_club_ID, stadium_ID, referee_ID, match_datetime, attendance, "
                "home_goals, away_goals) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (r['match_id'], r['competition_id'], r['home_club_id'], r['away_club_id'],
                 r['stadium_id'], r['referee_id'], match_dt, r['attendance'],
                 r['home_goals'], r['away_goals'])
            )

        # ---- Match Stats ----
        print("Match Stats...")
        for _, r in df(xls, 'Match Stats').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Match_Stats (match_ID, player_id, club_id, is_starter, "
                "minutes_played, position_played, goals, assists, yellow_cards, red_cards, "
                "rating) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (r['match_id'], r['player_id'], r['club_id'], bool(r['is_starter']),
                 r['minutes_played'], r['position_played'], r['goals'], r['assists'],
                 r['yellow_cards'], r['red_cards'], r['rating'])
            )

        # ---- Transfer Records ----
        print("Transfer Records...")
        for _, r in df(xls, 'Transfer Records').iterrows():
            cur.execute(
                "INSERT IGNORE INTO Transfer_Record (transfer_id, player_id, from_club_id, "
                "to_club_id, transfer_date, transfer_fee, transfer_type) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (r['transfer_id'], r['player_id'], r['from_club_id'], r['to_club_id'],
                 r['transfer_date'], r['transfer_fee'], r['transfer_type'])
            )

        c.commit()
        print("Tum baslangic verileri yuklendi.")
    except Exception as e:
        c.rollback()
        print(f"HATA: {e}")
        raise
    finally:
        cur.execute("SET @DISABLE_TRIGGERS = 0")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cur.close(); c.close()


if __name__ == '__main__':
    main()
