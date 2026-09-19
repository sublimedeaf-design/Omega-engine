CREATE TABLE IF NOT EXISTS fixtures (
  fixture_id VARCHAR PRIMARY KEY,
  competition VARCHAR NOT NULL,
  kickoff_utc TIMESTAMP NOT NULL,
  home_team VARCHAR NOT NULL,
  away_team VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
  observation_id VARCHAR PRIMARY KEY,
  fixture_id VARCHAR NOT NULL,
  field VARCHAR NOT NULL,
  raw_value VARCHAR,
  normalized_value DOUBLE,
  source_id VARCHAR NOT NULL,
  event_time TIMESTAMP,
  known_at TIMESTAMP NOT NULL,
  retrieved_at TIMESTAMP NOT NULL,
  source_confidence DOUBLE,
  FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  snapshot_id VARCHAR PRIMARY KEY,
  fixture_id VARCHAR NOT NULL,
  bookmaker VARCHAR NOT NULL,
  market VARCHAR NOT NULL,
  selection VARCHAR NOT NULL,
  decimal_odds DOUBLE NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  source_id VARCHAR NOT NULL,
  FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);

CREATE TABLE IF NOT EXISTS prediction_ledger (
  prediction_id VARCHAR PRIMARY KEY,
  fixture_id VARCHAR NOT NULL,
  created_at TIMESTAMP NOT NULL,
  model_version VARCHAR NOT NULL,
  market VARCHAR NOT NULL,
  selection VARCHAR NOT NULL,
  raw_probability DOUBLE NOT NULL,
  calibrated_probability DOUBLE,
  decision_probability DOUBLE,
  uncertainty DOUBLE,
  offered_odds DOUBLE,
  fair_odds DOUBLE,
  edge DOUBLE,
  ev DOUBLE,
  decision VARCHAR NOT NULL,
  input_fingerprint VARCHAR NOT NULL,
  FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);

CREATE TABLE IF NOT EXISTS model_runs (
  run_id VARCHAR PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  model_name VARCHAR NOT NULL,
  model_version VARCHAR NOT NULL,
  train_cutoff TIMESTAMP NOT NULL,
  parameters_json VARCHAR NOT NULL,
  metrics_json VARCHAR,
  input_fingerprint VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  fixture_id VARCHAR PRIMARY KEY,
  home_goals INTEGER NOT NULL,
  away_goals INTEGER NOT NULL,
  recorded_at TIMESTAMP NOT NULL,
  source_id VARCHAR NOT NULL,
  FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);

CREATE TABLE IF NOT EXISTS closing_odds (
  fixture_id VARCHAR NOT NULL,
  bookmaker VARCHAR NOT NULL,
  market VARCHAR NOT NULL,
  selection VARCHAR NOT NULL,
  decimal_odds DOUBLE NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  source_id VARCHAR NOT NULL,
  PRIMARY KEY (fixture_id, bookmaker, market, selection),
  FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id)
);
