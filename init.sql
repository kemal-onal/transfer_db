-- ==================================================================
-- TransferDB — CMPE 321 Project 2 — Group 01
-- Full schema + DB-level constraint enforcement (triggers + procs)
-- ==================================================================

DROP DATABASE IF EXISTS transferdb;
CREATE DATABASE transferdb;
USE transferdb;

-- ==================================================================
-- 1. TABLES
-- ==================================================================

CREATE TABLE Person (
    person_ID      INT PRIMARY KEY AUTO_INCREMENT,
    name           VARCHAR(100) NOT NULL,
    surname        VARCHAR(100) NOT NULL,
    nationality    VARCHAR(100) NOT NULL,
    date_of_birth  DATE NOT NULL
);

CREATE TABLE Player (
    person_ID      INT PRIMARY KEY,
    username       VARCHAR(50) NOT NULL UNIQUE,
    password       VARCHAR(255) NOT NULL,
    market_value   DECIMAL(15,2) NOT NULL,
    main_position  ENUM('Goalkeeper','Defender','Midfielder','Forward') NOT NULL,
    strong_foot    ENUM('Right','Left','Both') NOT NULL,
    height         INT NOT NULL,
    CHECK (market_value >= 0),
    CHECK (height > 0),
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE Manager (
    person_ID            INT PRIMARY KEY,
    username             VARCHAR(50) NOT NULL UNIQUE,
    password             VARCHAR(255) NOT NULL,
    preferred_formation  VARCHAR(20) NOT NULL,
    experience_level     VARCHAR(50) NOT NULL,
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE Referee (
    person_ID            INT PRIMARY KEY,
    username             VARCHAR(50) NOT NULL UNIQUE,
    password             VARCHAR(255) NOT NULL,
    license_level        VARCHAR(50) NOT NULL,
    years_of_experience  INT NOT NULL,
    CHECK (years_of_experience >= 0),
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE DB_Manager (
    username  VARCHAR(50) PRIMARY KEY,
    password  VARCHAR(255) NOT NULL
);

CREATE TABLE Stadium (
    stadium_ID    INT PRIMARY KEY AUTO_INCREMENT,
    stadium_name  VARCHAR(200) NOT NULL,
    city          VARCHAR(100) NOT NULL,
    capacity      INT NOT NULL,
    CHECK (capacity > 0),
    UNIQUE (stadium_name, city)
);

CREATE TABLE Club (
    club_ID          INT PRIMARY KEY AUTO_INCREMENT,
    club_name        VARCHAR(200) NOT NULL UNIQUE,
    stadium_ID       INT NOT NULL,
    city             VARCHAR(100) NOT NULL,
    foundation_year  INT NOT NULL,
    manager_ID       INT UNIQUE,
    FOREIGN KEY (stadium_ID) REFERENCES Stadium(stadium_ID),
    FOREIGN KEY (manager_ID) REFERENCES Manager(person_ID)
);

CREATE TABLE Contract (
    contract_id    INT PRIMARY KEY AUTO_INCREMENT,
    player_id      INT NOT NULL,
    club_id        INT NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    weekly_wage    DECIMAL(12,2) NOT NULL,
    contract_type  ENUM('Permanent','Loan') NOT NULL,
    CHECK (weekly_wage > 0),
    CHECK (end_date > start_date),
    FOREIGN KEY (player_id) REFERENCES Player(person_ID),
    FOREIGN KEY (club_id)   REFERENCES Club(club_ID)
);

CREATE TABLE Transfer_Record (
    transfer_id    INT PRIMARY KEY AUTO_INCREMENT,
    player_id      INT NOT NULL,
    from_club_id   INT NULL,
    to_club_id     INT NOT NULL,
    transfer_date  DATE NOT NULL,
    transfer_fee   DECIMAL(15,2) NOT NULL,
    transfer_type  ENUM('Free','Purchase','Loan') NOT NULL,
    CHECK (transfer_fee >= 0),
    CHECK (from_club_id IS NULL OR from_club_id <> to_club_id),
    CHECK (transfer_type <> 'Free' OR transfer_fee = 0),
    CHECK (transfer_type =  'Free' OR transfer_fee > 0),
    FOREIGN KEY (player_id)    REFERENCES Player(person_ID),
    FOREIGN KEY (from_club_id) REFERENCES Club(club_ID),
    FOREIGN KEY (to_club_id)   REFERENCES Club(club_ID)
);

CREATE TABLE Competition (
    competition_ID    INT PRIMARY KEY AUTO_INCREMENT,
    name              VARCHAR(200) NOT NULL,
    season            VARCHAR(20) NOT NULL,
    country           VARCHAR(100) NOT NULL,
    competition_type  ENUM('League','Cup','International') NOT NULL,
    UNIQUE (name, season)
);

CREATE TABLE `Match` (
    match_ID        INT PRIMARY KEY AUTO_INCREMENT,
    competition_ID  INT NOT NULL,
    home_club_ID    INT NOT NULL,
    away_club_ID    INT NOT NULL,
    stadium_ID      INT NOT NULL,
    referee_ID      INT NOT NULL,
    match_datetime  DATETIME NOT NULL,
    attendance      INT NULL,
    home_goals      INT NULL,
    away_goals      INT NULL,
    CHECK (attendance IS NULL OR attendance >= 0),
    CHECK (home_goals IS NULL OR home_goals >= 0),
    CHECK (away_goals IS NULL OR away_goals >= 0),
    CHECK (home_club_ID <> away_club_ID),
    FOREIGN KEY (competition_ID) REFERENCES Competition(competition_ID),
    FOREIGN KEY (home_club_ID)   REFERENCES Club(club_ID),
    FOREIGN KEY (away_club_ID)   REFERENCES Club(club_ID),
    FOREIGN KEY (stadium_ID)     REFERENCES Stadium(stadium_ID),
    FOREIGN KEY (referee_ID)     REFERENCES Referee(person_ID)
);

CREATE TABLE Match_Stats (
    match_ID         INT NOT NULL,
    player_id        INT NOT NULL,
    club_id          INT NOT NULL,
    is_starter       BOOLEAN NOT NULL DEFAULT FALSE,
    minutes_played   INT NOT NULL DEFAULT 0,
    position_played  VARCHAR(50) NOT NULL,
    goals            INT NOT NULL DEFAULT 0,
    assists          INT NOT NULL DEFAULT 0,
    yellow_cards     INT NOT NULL DEFAULT 0,
    red_cards        INT NOT NULL DEFAULT 0,
    rating           DECIMAL(3,1) NULL,
    PRIMARY KEY (match_ID, player_id),
    CHECK (minutes_played BETWEEN 0 AND 120),
    CHECK (goals >= 0),
    CHECK (assists >= 0),
    CHECK (yellow_cards IN (0,1,2)),
    CHECK (red_cards IN (0,1)),
    CHECK (yellow_cards < 2 OR red_cards = 1),
    CHECK (rating IS NULL OR rating BETWEEN 1.0 AND 10.0),
    FOREIGN KEY (match_ID)  REFERENCES `Match`(match_ID),
    FOREIGN KEY (player_id) REFERENCES Player(person_ID),
    FOREIGN KEY (club_id)   REFERENCES Club(club_ID)
);

CREATE TABLE Suspension (
    suspension_id        INT PRIMARY KEY AUTO_INCREMENT,
    player_id            INT NOT NULL,
    competition_ID       INT NOT NULL,
    triggering_match_ID  INT NOT NULL,
    reason               ENUM('red','5-yellow','combined') NOT NULL,
    status               ENUM('pending','served') NOT NULL DEFAULT 'pending',
    served_match_ID      INT NULL,
    UNIQUE (player_id, triggering_match_ID),
    FOREIGN KEY (player_id)           REFERENCES Player(person_ID),
    FOREIGN KEY (competition_ID)      REFERENCES Competition(competition_ID),
    FOREIGN KEY (triggering_match_ID) REFERENCES `Match`(match_ID),
    FOREIGN KEY (served_match_ID)     REFERENCES `Match`(match_ID)
);

-- ==================================================================
-- 2. TRIGGERS  (DB-level enforcement of every non-CHECK constraint)
-- ==================================================================

DELIMITER //

-- Bulk-import bypass: setting @DISABLE_TRIGGERS = 1 lets the seed script
-- load intentionally-invalid historical records (spec §2.3) without tripping
-- any of the below triggers. @DISABLE_TRIGGERS must be 0 in normal use.

-- C8: Club.city must equal its home Stadium.city
CREATE TRIGGER trg_club_city_ins
BEFORE INSERT ON Club
FOR EACH ROW
lbl: BEGIN
    DECLARE sc VARCHAR(100);
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;
    SELECT city INTO sc FROM Stadium WHERE stadium_ID = NEW.stadium_ID;
    IF sc IS NULL OR sc <> NEW.city THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'kulubun sehri ev sahasi stadyumunun sehriyle ayni olmali';
    END IF;
END //

CREATE TRIGGER trg_club_city_upd
BEFORE UPDATE ON Club
FOR EACH ROW
lbl: BEGIN
    DECLARE sc VARCHAR(100);
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;
    SELECT city INTO sc FROM Stadium WHERE stadium_ID = NEW.stadium_ID;
    IF sc IS NULL OR sc <> NEW.city THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'kulubun sehri ev sahasi stadyumunun sehriyle ayni olmali';
    END IF;
END //

-- C1 + C9 + "at most one active Permanent" on Contract insert
CREATE TRIGGER trg_contract_ins
BEFORE INSERT ON Contract
FOR EACH ROW
lbl: BEGIN
    DECLARE overlap_cnt INT;
    DECLARE cover_cnt   INT;
    DECLARE active_perm INT;
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;

    -- C9: no overlapping contract of the same type for this player
    --     (strict comparison allows end_date == start_date touching for mid-day transfer)
    SELECT COUNT(*) INTO overlap_cnt
      FROM Contract
     WHERE player_id     = NEW.player_id
       AND contract_type = NEW.contract_type
       AND NEW.start_date < end_date
       AND NEW.end_date   > start_date;
    IF overlap_cnt > 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'oyuncunun ayni tipte aktif bir sozlesmesi bu donemde zaten var';
    END IF;

    -- C1: a Loan requires an active Permanent at a DIFFERENT club covering the whole loan period
    IF NEW.contract_type = 'Loan' THEN
        SELECT COUNT(*) INTO cover_cnt
          FROM Contract
         WHERE player_id     = NEW.player_id
           AND contract_type = 'Permanent'
           AND club_id      <> NEW.club_id
           AND start_date   <= NEW.start_date
           AND end_date     >= NEW.end_date;
        IF cover_cnt = 0 THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'kiralik sozlesme icin farkli bir kulupte tum donemi kapsayan kalici sozlesme gerekli';
        END IF;
    END IF;

    -- At most 2 simultaneous contracts: one Permanent + one Loan.
    -- A second active Permanent is forbidden (must be terminated via sp_register_transfer first).
    IF NEW.contract_type = 'Permanent' THEN
        SELECT COUNT(*) INTO active_perm
          FROM Contract
         WHERE player_id     = NEW.player_id
           AND contract_type = 'Permanent'
           AND NEW.start_date < end_date
           AND NEW.end_date   > start_date;
        IF active_perm > 0 THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'oyuncunun aktif kalici sozlesmesi var - once sonlandirilmali';
        END IF;
    END IF;
END //

-- Match INSERT: future datetime, 120-min gap, attendance<=capacity
CREATE TRIGGER trg_match_ins
BEFORE INSERT ON `Match`
FOR EACH ROW
lbl: BEGIN
    DECLARE conflict_cnt INT;
    DECLARE max_cap      INT;
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;

    IF NEW.match_datetime <= NOW() THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'mac gelecek bir tarih ve saate planlanmali';
    END IF;

    SELECT COUNT(*) INTO conflict_cnt
      FROM `Match`
     WHERE (
             stadium_ID = NEW.stadium_ID
          OR referee_ID = NEW.referee_ID
          OR home_club_ID IN (NEW.home_club_ID, NEW.away_club_ID)
          OR away_club_ID IN (NEW.home_club_ID, NEW.away_club_ID)
           )
       AND ABS(TIMESTAMPDIFF(MINUTE, match_datetime, NEW.match_datetime)) < 120;
    IF conflict_cnt > 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'stadyum/hakem/kulup icin 120 dakika kurali ihlali';
    END IF;

    IF NEW.attendance IS NOT NULL THEN
        SELECT capacity INTO max_cap FROM Stadium WHERE stadium_ID = NEW.stadium_ID;
        IF NEW.attendance > max_cap THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'seyirci sayisi stadyum kapasitesini asamaz';
        END IF;
    END IF;
END //

-- Match UPDATE: referee auth (session var), time-passed, squad>=11, attendance<=cap
CREATE TRIGGER trg_match_upd
BEFORE UPDATE ON `Match`
FOR EACH ROW
lbl: BEGIN
    DECLARE max_cap    INT;
    DECLARE home_squad INT;
    DECLARE away_squad INT;
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;

    -- Attendance cap check (whenever set)
    IF NEW.attendance IS NOT NULL THEN
        SELECT capacity INTO max_cap FROM Stadium WHERE stadium_ID = NEW.stadium_ID;
        IF NEW.attendance > max_cap THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'seyirci sayisi stadyum kapasitesini asamaz';
        END IF;
    END IF;

    -- Result-submission checks: triggered only when home_goals transitions NULL -> NOT NULL
    IF OLD.home_goals IS NULL AND NEW.home_goals IS NOT NULL THEN
        -- Only the assigned referee may submit (app sets @current_user_id/@current_user_role).
        -- Direct MySQL client bypass will have the vars NULL => rejected.
        IF @current_user_role IS NULL
           OR @current_user_role <> 'Referee'
           OR @current_user_id  IS NULL
           OR @current_user_id  <> NEW.referee_ID THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'mac sonucu sadece atanan hakem tarafindan girilebilir';
        END IF;

        -- Match time must have already passed
        IF NEW.match_datetime > NOW() THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'mac sonucu ancak planlanan saat gectikten sonra girilebilir';
        END IF;

        -- Attendance must be provided at submission
        IF NEW.attendance IS NULL THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'seyirci sayisi girilmeli';
        END IF;

        -- Squad size >= 11 for both clubs
        SELECT COUNT(*) INTO home_squad FROM Match_Stats
         WHERE match_ID = NEW.match_ID AND club_id = NEW.home_club_ID;
        SELECT COUNT(*) INTO away_squad FROM Match_Stats
         WHERE match_ID = NEW.match_ID AND club_id = NEW.away_club_ID;
        IF home_squad < 11 OR away_squad < 11 THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'her iki takimin kadrosu en az 11 kisi olmali';
        END IF;
    END IF;
END //

-- Match_Stats INSERT: home/away check (C7), active-contract check,
--   loan-vs-parent ban, starter<=11 / squad<=23 (C4), suspension block (C5)
CREATE TRIGGER trg_match_stats_ins
BEFORE INSERT ON Match_Stats
FOR EACH ROW
lbl: BEGIN
    DECLARE h_club        INT;
    DECLARE a_club        INT;
    DECLARE comp_id       INT;
    DECLARE m_dt          DATETIME;
    DECLARE starters_cnt  INT;
    DECLARE squad_cnt     INT;
    DECLARE has_contract  INT;
    DECLARE loan_club     INT;
    DECLARE permanent_cl  INT;
    DECLARE pending_susp  INT;
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;

    SELECT home_club_ID, away_club_ID, competition_ID, match_datetime
      INTO h_club, a_club, comp_id, m_dt
      FROM `Match` WHERE match_ID = NEW.match_ID;

    -- C7: player's club must match one of the two sides
    IF NEW.club_id <> h_club AND NEW.club_id <> a_club THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'oyuncu bu macta ev sahibi ya da deplasman takiminda olmali';
    END IF;

    -- Player must have an active contract with this club on the match date
    SELECT COUNT(*) INTO has_contract
      FROM Contract
     WHERE player_id = NEW.player_id
       AND club_id   = NEW.club_id
       AND DATE(m_dt) BETWEEN start_date AND end_date;
    IF has_contract = 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'oyuncunun bu kulup ile aktif bir sozlesmesi yok';
    END IF;

    -- Loan restriction: if player is currently on Loan, they cannot play for parent Permanent club
    SELECT club_id INTO loan_club FROM Contract
     WHERE player_id = NEW.player_id
       AND contract_type = 'Loan'
       AND DATE(m_dt) BETWEEN start_date AND end_date
     LIMIT 1;
    IF loan_club IS NOT NULL THEN
        SELECT club_id INTO permanent_cl FROM Contract
         WHERE player_id = NEW.player_id
           AND contract_type = 'Permanent'
           AND DATE(m_dt) BETWEEN start_date AND end_date
         LIMIT 1;
        IF NEW.club_id = permanent_cl THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'kiralik oyuncu ana kulubu icin oynayamaz';
        END IF;
    END IF;

    -- C4: max 11 starters per club per match
    IF NEW.is_starter = TRUE THEN
        SELECT COUNT(*) INTO starters_cnt
          FROM Match_Stats
         WHERE match_ID = NEW.match_ID AND club_id = NEW.club_id AND is_starter = TRUE;
        IF starters_cnt >= 11 THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'bir takimda en fazla 11 ilk onbir oyuncusu olabilir';
        END IF;
    END IF;

    -- C4: max 23 total per club per match
    SELECT COUNT(*) INTO squad_cnt
      FROM Match_Stats WHERE match_ID = NEW.match_ID AND club_id = NEW.club_id;
    IF squad_cnt >= 23 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'bir takimin mac kadrosu en fazla 23 kisi olabilir';
    END IF;

    -- C5: block suspended players (pending suspension in this competition from an earlier match)
    SELECT COUNT(*) INTO pending_susp
      FROM Suspension s
      JOIN `Match` m ON m.match_ID = s.triggering_match_ID
     WHERE s.player_id      = NEW.player_id
       AND s.competition_ID = comp_id
       AND s.status         = 'pending'
       AND m.match_datetime < m_dt;
    IF pending_susp > 0 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'oyuncu cezali - bu macin kadrosuna alinamaz';
    END IF;
END //

-- Transfer_Record INSERT: Free=>fee=0 (C6a), Loan=>from_club must be active Permanent club (C6b)
CREATE TRIGGER trg_transfer_ins
BEFORE INSERT ON Transfer_Record
FOR EACH ROW
lbl: BEGIN
    DECLARE parent_club INT;
    IF COALESCE(@DISABLE_TRIGGERS, 0) = 1 THEN LEAVE lbl; END IF;

    IF NEW.transfer_type = 'Loan' THEN
        SELECT club_id INTO parent_club
          FROM Contract
         WHERE player_id     = NEW.player_id
           AND contract_type = 'Permanent'
           AND start_date   <= NEW.transfer_date
           AND end_date     >= NEW.transfer_date
         ORDER BY start_date DESC LIMIT 1;
        IF parent_club IS NULL OR NEW.from_club_id <> parent_club THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'kiralik transferde from_club oyuncunun ana kulubu olmalidir';
        END IF;
    END IF;
END //

-- ==================================================================
-- 3. STORED PROCEDURES  (multi-step operations that triggers cannot
--    express, because MySQL forbids a trigger from modifying the
--    table it fires on — e.g. auto-terminating an old Permanent.)
-- ==================================================================

-- sp_register_transfer — DB Manager "register a transfer and contract" op
--   * Permanent: auto-terminates previous Permanent (end_date = today).
--   * Loan: requires active Permanent (the trigger also re-checks).
--   * Purchase: updates Player.market_value = transfer_fee.
--   * Free: must have transfer_fee = 0.
CREATE PROCEDURE sp_register_transfer(
    IN  p_player_id     INT,
    IN  p_to_club_id    INT,
    IN  p_contract_type ENUM('Permanent','Loan'),
    IN  p_weekly_wage   DECIMAL(12,2),
    IN  p_transfer_fee  DECIMAL(15,2),
    IN  p_end_date      DATE
)
BEGIN
    DECLARE v_from_club INT DEFAULT NULL;
    DECLARE v_ttype     ENUM('Free','Purchase','Loan');
    DECLARE v_today     DATE DEFAULT CURDATE();

    -- Resolve from_club and transfer_type based on contract_type
    IF p_contract_type = 'Permanent' THEN
        SELECT club_id INTO v_from_club
          FROM Contract
         WHERE player_id     = p_player_id
           AND contract_type = 'Permanent'
           AND v_today BETWEEN start_date AND end_date
         LIMIT 1;

        -- Auto-terminate previous Permanent so the new one does not overlap
        IF v_from_club IS NOT NULL THEN
            UPDATE Contract
               SET end_date = v_today
             WHERE player_id     = p_player_id
               AND contract_type = 'Permanent'
               AND v_today BETWEEN start_date AND end_date;
        END IF;

        IF p_transfer_fee = 0 THEN SET v_ttype = 'Free';
        ELSE                       SET v_ttype = 'Purchase';
        END IF;
    ELSEIF p_contract_type = 'Loan' THEN
        SELECT club_id INTO v_from_club
          FROM Contract
         WHERE player_id     = p_player_id
           AND contract_type = 'Permanent'
           AND v_today BETWEEN start_date AND end_date
         LIMIT 1;
        IF v_from_club IS NULL THEN
            SIGNAL SQLSTATE '45000'
              SET MESSAGE_TEXT = 'kiralik transfer icin aktif kalici sozlesme gerekli';
        END IF;
        SET v_ttype = 'Loan';
    END IF;

    -- Write Transfer_Record
    INSERT INTO Transfer_Record (player_id, from_club_id, to_club_id,
                                 transfer_date, transfer_fee, transfer_type)
    VALUES (p_player_id, v_from_club, p_to_club_id,
            v_today, p_transfer_fee, v_ttype);

    -- Write new Contract (start_date = today per spec)
    INSERT INTO Contract (player_id, club_id, start_date, end_date,
                          weekly_wage, contract_type)
    VALUES (p_player_id, p_to_club_id, v_today, p_end_date,
            p_weekly_wage, p_contract_type);

    -- Purchase => update player's market_value to the fee
    IF v_ttype = 'Purchase' THEN
        UPDATE Player SET market_value = p_transfer_fee
         WHERE person_ID = p_player_id;
    END IF;
END //

-- sp_submit_match_result — Referee "submit result" op.
--   Updates the Match row (trigger enforces auth + time + squad),
--   then (a) marks any pending suspensions as served for players
--   whose club played in this match but who were NOT in its squad,
--   (b) creates new Suspension rows for red-carded players and for
--   players who reached 5 yellows *since their last served ban*
--   in the same competition (forum #4 reset rule).
CREATE PROCEDURE sp_submit_match_result(
    IN p_match_id    INT,
    IN p_home_goals  INT,
    IN p_away_goals  INT,
    IN p_attendance  INT
)
BEGIN
    DECLARE v_comp     INT;
    DECLARE v_home_cl  INT;
    DECLARE v_away_cl  INT;
    DECLARE v_dt       DATETIME;

    SELECT competition_ID, home_club_ID, away_club_ID, match_datetime
      INTO v_comp, v_home_cl, v_away_cl, v_dt
      FROM `Match` WHERE match_ID = p_match_id;

    -- Apply the result (trg_match_upd enforces all the result-time rules)
    UPDATE `Match`
       SET home_goals = p_home_goals,
           away_goals = p_away_goals,
           attendance = p_attendance
     WHERE match_ID = p_match_id;

    -- (a) Mark pending suspensions served for players who were expected to play
    --     (their club is in this match) but were kept out of the squad.
    UPDATE Suspension
       SET status = 'served', served_match_ID = p_match_id
     WHERE status         = 'pending'
       AND competition_ID = v_comp
       AND triggering_match_ID IN (
            SELECT match_ID FROM `Match`
             WHERE competition_ID = v_comp AND match_datetime < v_dt
       )
       AND player_id NOT IN (
            SELECT player_id FROM Match_Stats WHERE match_ID = p_match_id
       )
       AND player_id IN (
            -- must be a player who has (at some point) represented either side
            -- in this competition; safer: anyone with an active contract for
            -- home or away club at the match date.
            SELECT player_id FROM Contract
             WHERE (club_id = v_home_cl OR club_id = v_away_cl)
               AND DATE(v_dt) BETWEEN start_date AND end_date
       );

    -- (b.1) Red card => suspension
    INSERT IGNORE INTO Suspension (player_id, competition_ID,
                                   triggering_match_ID, reason)
    SELECT player_id, v_comp, p_match_id, 'red'
      FROM Match_Stats
     WHERE match_ID = p_match_id AND red_cards = 1;

    -- (b.2) 5-yellow accumulation (forum #4: counted from the match AFTER the
    --       most recent served suspension in this competition).
    --       If the player also got a red in this match, upgrade reason.
    INSERT INTO Suspension (player_id, competition_ID,
                            triggering_match_ID, reason)
    SELECT ms.player_id, v_comp, p_match_id,
           CASE WHEN ms.red_cards = 1 THEN 'combined' ELSE '5-yellow' END
      FROM Match_Stats ms
     WHERE ms.match_ID = p_match_id
       AND (
           SELECT COALESCE(SUM(ms2.yellow_cards), 0)
             FROM Match_Stats ms2
             JOIN `Match` m2 ON m2.match_ID = ms2.match_ID
            WHERE ms2.player_id      = ms.player_id
              AND m2.competition_ID  = v_comp
              AND m2.match_datetime <= v_dt
              AND m2.match_datetime > COALESCE((
                  SELECT MAX(m3.match_datetime)
                    FROM Suspension s3
                    JOIN `Match` m3 ON m3.match_ID = s3.served_match_ID
                   WHERE s3.player_id      = ms.player_id
                     AND s3.competition_ID = v_comp
                     AND s3.status         = 'served'
              ), '1900-01-01 00:00:00')
       ) >= 5
    ON DUPLICATE KEY UPDATE reason = 'combined';
END //

-- sp_validate_match_squad — called by manager's set_squad flow after the
-- per-player INSERTs.  The BEFORE-INSERT trigger already bounds the squad
-- above (11 starters / 23 total), but the minimum size of 11 cannot be
-- checked per-row (the count grows as rows are inserted).  This procedure
-- runs as a post-insert guard: if the final squad for this (match, club)
-- has fewer than 11 players, it raises SQLSTATE 45000 so the surrounding
-- transaction rolls back.  Spec §2.2/5: "the total squad must be between
-- 11 and 23 players".
CREATE PROCEDURE sp_validate_match_squad(
    IN p_match_id INT,
    IN p_club_id  INT
)
BEGIN
    DECLARE v_count INT;
    SELECT COUNT(*) INTO v_count
      FROM Match_Stats
     WHERE match_ID = p_match_id AND club_id = p_club_id;
    IF v_count < 11 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'kadro en az 11 oyuncu icermelidir';
    END IF;
    IF v_count > 23 THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'kadro en fazla 23 oyuncu icerebilir';
    END IF;
END //

DELIMITER ;
