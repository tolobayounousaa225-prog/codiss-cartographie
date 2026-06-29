-- ============================================================
-- CODISS - Schéma de base de données PostgreSQL (Supabase)
-- Cartographie de la représentativité nationale
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Régions administratives de Côte d'Ivoire
CREATE TABLE regions (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(10) UNIQUE NOT NULL,
    name_fr     VARCHAR(100) NOT NULL,
    name_en     VARCHAR(100) NOT NULL,
    district    VARCHAR(100),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Départements
CREATE TABLE departments (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(10) UNIQUE NOT NULL,
    name_fr     VARCHAR(100) NOT NULL,
    name_en     VARCHAR(100) NOT NULL,
    region_id   INTEGER REFERENCES regions(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Utilisateurs (admin national, secrétaires de branche, viewers)
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(200) NOT NULL,
    phone           VARCHAR(20),
    role            VARCHAR(20) NOT NULL DEFAULT 'branch'
                    CHECK (role IN ('superadmin', 'admin', 'branch', 'viewer')),
    language        VARCHAR(5) DEFAULT 'fr' CHECK (language IN ('fr', 'en')),
    is_active       BOOLEAN DEFAULT TRUE,
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Représentations locales CODISS
CREATE TABLE branches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(20) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    city            VARCHAR(100) NOT NULL,
    address         TEXT,
    region_id       INTEGER REFERENCES regions(id),
    department_id   INTEGER REFERENCES departments(id),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    status          VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('active', 'pending', 'suspended', 'inactive')),
    is_verified     BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMPTZ,
    verified_by     UUID REFERENCES users(id),
    president_name  VARCHAR(200),
    president_phone VARCHAR(20),
    president_email VARCHAR(255),
    member_count    INTEGER DEFAULT 0,
    founded_date    DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Lien utilisateur <-> branche
CREATE TABLE branch_users (
    id          SERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    branch_id   UUID REFERENCES branches(id) ON DELETE CASCADE,
    role        VARCHAR(20) DEFAULT 'secretary'
                CHECK (role IN ('president', 'secretary', 'treasurer', 'member')),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, branch_id)
);

-- Rapports de présence soumis par chaque branche
CREATE TABLE presence_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    branch_id           UUID REFERENCES branches(id) ON DELETE CASCADE,
    submitted_by        UUID REFERENCES users(id),
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    location_accuracy   DOUBLE PRECISION,
    location_address    TEXT,
    report_type         VARCHAR(30) DEFAULT 'presence'
                        CHECK (report_type IN ('presence', 'activity', 'update', 'event')),
    title               VARCHAR(255) NOT NULL,
    description         TEXT,
    activity_count      INTEGER DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'submitted'
                        CHECK (status IN ('submitted', 'reviewed', 'approved', 'rejected')),
    reviewed_by         UUID REFERENCES users(id),
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    period_start        DATE,
    period_end          DATE,
    photos_urls         TEXT[],
    documents_urls      TEXT[],
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Réponses aux questions du formulaire
CREATE TABLE report_form_answers (
    id          SERIAL PRIMARY KEY,
    report_id   UUID REFERENCES presence_reports(id) ON DELETE CASCADE,
    question    VARCHAR(500) NOT NULL,
    answer      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Journal d'activité
CREATE TABLE activity_logs (
    id          SERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    branch_id   UUID REFERENCES branches(id),
    action      VARCHAR(100) NOT NULL,
    details     JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Notifications internes
CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    title_fr    VARCHAR(255) NOT NULL,
    title_en    VARCHAR(255),
    body_fr     TEXT,
    body_en     TEXT,
    type        VARCHAR(30) DEFAULT 'info'
                CHECK (type IN ('info', 'success', 'warning', 'error', 'report')),
    is_read     BOOLEAN DEFAULT FALSE,
    link        VARCHAR(500),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index de performance
CREATE INDEX idx_branches_region   ON branches(region_id);
CREATE INDEX idx_branches_status   ON branches(status);
CREATE INDEX idx_branches_location ON branches(latitude, longitude);
CREATE INDEX idx_reports_branch    ON presence_reports(branch_id);
CREATE INDEX idx_reports_status    ON presence_reports(status);
CREATE INDEX idx_reports_created   ON presence_reports(created_at DESC);
CREATE INDEX idx_notif_user        ON notifications(user_id, is_read);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users    BEFORE UPDATE ON users    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_branches BEFORE UPDATE ON branches FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_reports  BEFORE UPDATE ON presence_reports FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Régions de Côte d'Ivoire (31 régions)
INSERT INTO regions (code, name_fr, name_en, district) VALUES
('ABJ', 'Abidjan',           'Abidjan',           'District Autonome d''Abidjan'),
('LAG', 'Lagunes',           'Lagoons',            'District des Lagunes'),
('COM', 'Comoé',             'Comoé',              'District de Comoé'),
('MON', 'Montagnes',         'Mountains',          'District des Montagnes'),
('BAF', 'Bafing',            'Bafing',             'District de Woroba'),
('BAG', 'Bagoué',            'Bagoué',             'District des Savanes'),
('BER', 'Béré',              'Béré',               'District de Woroba'),
('BOU', 'Bounkani',          'Bounkani',           'District de Zanzan'),
('FOL', 'Folon',             'Folon',              'District des Savanes'),
('GBK', 'Gbôklé',            'Gbôklé',             'District du Bas-Sassandra'),
('GOH', 'Gôh',               'Gôh',                'District du Gôh-Djiboua'),
('GON', 'Gontougo',          'Gontougo',           'District de Zanzan'),
('GPO', 'Grands-Ponts',      'Grands-Ponts',       'District des Lagunes'),
('GUE', 'Guémon',            'Guémon',             'District des Montagnes'),
('HAM', 'Hambol',            'Hambol',             'District de la Vallée du Bandama'),
('HSA', 'Haut-Sassandra',    'Haut-Sassandra',     'District du Sassandra-Marahoué'),
('IFF', 'Iffou',             'Iffou',              'District de la Vallée du Bandama'),
('IND', 'Indénié-Djuablin',  'Indénié-Djuablin',   'District du Comoé'),
('KAB', 'Kabadougou',        'Kabadougou',         'District du Denguélé'),
('LAM', 'La Mé',             'La Mé',              'District des Lagunes'),
('LOH', 'Lôh-Djiboua',      'Lôh-Djiboua',        'District du Gôh-Djiboua'),
('MAR', 'Marahoué',          'Marahoué',           'District du Sassandra-Marahoué'),
('MOR', 'Moronou',           'Moronou',            'District des Lacs'),
('NZI', 'N''Zi',             'N''Zi',              'District de la Vallée du Bandama'),
('POR', 'Poro',              'Poro',               'District des Savanes'),
('SAN', 'San-Pédro',         'San-Pédro',          'District du Bas-Sassandra'),
('SUD', 'Sud-Comoé',         'Sud-Comoé',          'District du Comoé'),
('TON', 'Tonkpi',            'Tonkpi',             'District des Montagnes'),
('WOR', 'Worodougou',        'Worodougou',         'District de Woroba'),
('YAM', 'Yamoussoukro',      'Yamoussoukro',       'District Autonome de Yamoussoukro'),
('ZUE', 'Zuénoula',          'Zuénoula',           'District du Sassandra-Marahoué');
