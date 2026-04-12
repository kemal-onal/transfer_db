CREATE DATABASE IF NOT EXISTS transferdb;
USE transferdb;

CREATE TABLE Person (
    person_ID INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    surname VARCHAR(100) NOT NULL,
    nationality VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL
);

CREATE TABLE Player (
    person_ID INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    market_value DECIMAL(15 ,2) NOT NULL,
    main_position ENUM('Goalkeeper', 'Defender', 'Midfielder', 'Forward') NOT NULL,
    strong_foot ENUM('Right', 'Left', 'Both') NOT NULL,
    height INT NOT NULL,
    CHECK (market_value >= 0),
    CHECK (height > 0),
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE Manager (
    person_ID INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    preferred_formation VARCHAR(20) NOT NULL,
    experience_level VARCHAR(50) NOT NULL,
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE Referee (
    person_ID INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    license_level VARCHAR(50) NOT NULL,
    years_of_experience INT NOT NULL,
    CHECK (years_of_experience >= 0),
    FOREIGN KEY (person_ID) REFERENCES Person(person_ID)
);

CREATE TABLE DB_Manager (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE Stadium (
    stadium_ID INT PRIMARY KEY,
    stadium_name VARCHAR(200) NOT NULL,
    city VARCHAR(100) NOT NULL,
    capacity INT NOT NULL,
    CHECK (capacity > 0),
    UNIQUE (stadium_name, city)
);

CREATE TABLE Club (
    club_ID INT PRIMARY KEY,
    club_name VARCHAR(200) NOT NULL UNIQUE,
    stadium_ID INT NOT NULL,
    foundation_year INT NOT NULL,
    manager_ID INT UNIQUE,
    FOREIGN KEY (stadium_ID) REFERENCES Stadium(stadium_ID),
    FOREIGN KEY (manager_ID) REFERENCES Manager(person_ID)
);

CREATE TABLE Contract (
    contract_id INT PRIMARY KEY,
    player_id INT NOT NULL,
    club_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    weekly_wage DECIMAL(12 ,2) NOT NULL,
    contract_type ENUM('Permanent', 'Loan') NOT NULL,
    CHECK (weekly_wage > 0),
    CHECK (end_date > start_date),
    FOREIGN KEY (player_id) REFERENCES Player(person_ID),
    FOREIGN KEY (club_id) REFERENCES Club(club_ID)
);

CREATE TABLE Transfer (
    transfer_id INT PRIMARY KEY,
    player_id INT NOT NULL,
    from_club_id INT,
    to_club_id INT NOT NULL,
    transfer_date DATE NOT NULL,
    transfer_fee DECIMAL(15 ,2) NOT NULL,
    transfer_type ENUM('Free', 'Purchase', 'Loan') NOT NULL,
    CHECK (transfer_fee >= 0),
    CHECK (from_club_id <> to_club_id),
    CHECK (transfer_type <> 'Free' OR transfer_fee = 0),
    FOREIGN KEY (player_id) REFERENCES Player(person_ID),
    FOREIGN KEY (from_club_id) REFERENCES Club(club_ID),
    FOREIGN KEY (to_club_id) REFERENCES Club(club_ID)
);

CREATE TABLE Competition (
    competition_ID INT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    season VARCHAR(20) NOT NULL,
    country VARCHAR(100) NOT NULL,
    competition_type ENUM('League', 'Cup', 'International') NOT NULL,
    UNIQUE (name, season)
);

CREATE TABLE `Match` (
    match_ID INT PRIMARY KEY,
    competition_ID INT NOT NULL,
    home_club_ID INT NOT NULL,
    away_club_ID INT NOT NULL,
    stadium_ID INT NOT NULL,
    referee_ID INT NOT NULL,
    match_date DATE NOT NULL,
    match_time TIME NOT NULL,
    attendance INT,
    home_goals INT DEFAULT 0,
    away_goals INT DEFAULT 0,
    CHECK (attendance >= 0),
    CHECK (home_goals >= 0),
    CHECK (away_goals >= 0),
    CHECK (home_club_ID <> away_club_ID),
    FOREIGN KEY (competition_ID) REFERENCES Competition(competition_ID),
    FOREIGN KEY (home_club_ID) REFERENCES Club(club_ID),
    FOREIGN KEY (away_club_ID) REFERENCES Club(club_ID),
    FOREIGN KEY (stadium_ID) REFERENCES Stadium(stadium_ID),
    FOREIGN KEY (referee_ID) REFERENCES Referee(person_ID)
);

CREATE TABLE Match_Stats (
    match_ID INT NOT NULL,
    player_id INT NOT NULL,
    club_id INT NOT NULL,
    is_starter BOOLEAN NOT NULL DEFAULT FALSE,
    minutes_played INT NOT NULL DEFAULT 0,
    position_played VARCHAR(50) NOT NULL,
    goals INT NOT NULL DEFAULT 0,
    assists INT NOT NULL DEFAULT 0,
    yellow_cards INT NOT NULL DEFAULT 0,
    red_cards INT NOT NULL DEFAULT 0,
    rating DECIMAL(3 ,1),
    PRIMARY KEY (match_ID, player_id),
    CHECK (minutes_played BETWEEN 0 AND 120),
    CHECK (goals >= 0),
    CHECK (assists >= 0),
    CHECK (yellow_cards IN (0, 1, 2)),
    CHECK (red_cards IN (0, 1)),
    CHECK (yellow_cards < 2 OR red_cards = 1),
    CHECK (rating BETWEEN 1.0 AND 10.0),
    FOREIGN KEY (match_ID) REFERENCES `Match`(match_ID),
    FOREIGN KEY (player_id) REFERENCES Player(person_ID),
    FOREIGN KEY (club_id) REFERENCES Club(club_ID)
);

DELIMITER //

CREATE TRIGGER before_contract_insert
BEFORE INSERT ON Contract
FOR EACH ROW
BEGIN
    DECLARE active_perm_count INT;
    DECLARE overlap_count INT;

    SELECT COUNT(*) INTO overlap_count
    FROM Contract
    WHERE player_id = NEW.player_id
      AND contract_type = NEW.contract_type
      AND (NEW.start_date <= end_date AND NEW.end_date >= start_date);

    IF overlap_count > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'oyuncunun bu tarihlerde ayni tipte baska bir aktif sozlesmesi var';
    END IF;

    IF NEW.contract_type = 'Loan' THEN
        SELECT COUNT(*) INTO active_perm_count
        FROM Contract
        WHERE player_id = NEW.player_id
          AND contract_type = 'Permanent'
          AND start_date <= NEW.start_date
          AND end_date >= NEW.end_date;

        IF active_perm_count = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'kiralik sozlesme icin oyuncunun o tarihleri kapsayan kalici bir sozlesmesi olmali';
        END IF;
    END IF;
END //

CREATE TRIGGER before_match_insert
BEFORE INSERT ON `Match`
FOR EACH ROW
BEGIN
    DECLARE conflict_count INT;
    DECLARE max_cap INT;

    SELECT COUNT(*) INTO conflict_count
    FROM `Match`
    WHERE match_date = NEW.match_date
      AND (
           stadium_id = NEW.stadium_id OR
           referee_id = NEW.referee_id OR
           home_club_id IN (NEW.home_club_id, NEW.away_club_id) OR
           away_club_id IN (NEW.home_club_id, NEW.away_club_id)
      )
      AND ABS(TIMESTAMPDIFF(MINUTE, CONCAT(match_date, ' ', match_time), CONCAT(NEW.match_date, ' ', NEW.match_time))) < 120;

    IF conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'bu mac baska bir macla 120 dakika kuralina takiliyor';
    END IF;

    IF NEW.attendance IS NOT NULL THEN
        SELECT capacity INTO max_cap FROM Stadium WHERE stadium_id = NEW.stadium_id;
        IF NEW.attendance > max_cap THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'seyirci sayisi stadyum kapasitesini asamaz';
        END IF;
    END IF;
END //

CREATE TRIGGER before_match_stats_insert
BEFORE INSERT ON Match_Stats
FOR EACH ROW
BEGIN
    DECLARE h_club INT;
    DECLARE a_club INT;
    DECLARE starters INT;
    DECLARE squad_size INT;

    SELECT home_club_id, away_club_id INTO h_club, a_club
    FROM `Match` WHERE match_id = NEW.match_id;

    IF NEW.club_id != h_club AND NEW.club_id != a_club THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'oyuncu bu macta ev sahibi veya deplasman takiminda degil';
    END IF;

    IF NEW.is_starter = TRUE THEN
        SELECT COUNT(*) INTO starters FROM Match_Stats WHERE match_id = NEW.match_id AND club_id = NEW.club_id AND is_starter = TRUE;
        IF starters >= 11 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'bir takimda en fazla 11 ilk onbir oyuncusu olabilir';
        END IF;
    END IF;

    SELECT COUNT(*) INTO squad_size FROM Match_Stats WHERE match_id = NEW.match_id AND club_id = NEW.club_id;
    IF squad_size >= 23 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'bir takimin mac kadrosu en fazla 23 kisi olabilir';
    END IF;
END //

CREATE TRIGGER before_transfer_insert
BEFORE INSERT ON Transfer
FOR EACH ROW
BEGIN
    DECLARE parent_club INT;

    IF NEW.transfer_type = 'Free' AND NEW.transfer_fee > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'bedelsiz transferlerin ucreti 0 olmalidir';
    END IF;

    IF NEW.transfer_type = 'Loan' THEN
        SELECT club_id INTO parent_club
        FROM Contract
        WHERE player_id = NEW.player_id AND contract_type = 'Permanent'
          AND start_date <= NEW.transfer_date AND end_date >= NEW.transfer_date
        ORDER BY start_date DESC LIMIT 1;

        IF NEW.from_club_id != parent_club THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'kiralik giden oyuncunun geldigi takim ana kulubu olmalidir';
        END IF;
    END IF;
END //

DELIMITER ;
