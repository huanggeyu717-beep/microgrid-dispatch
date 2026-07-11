-- practice-environment draft; to be reworked in Phase 1
-- Table for raw (measured) grid time-series, long format.
-- Target database: microgrid. Apply with:  psql -d microgrid -f sql/schema/raw_measurements.sql

CREATE TABLE IF NOT EXISTS raw_measurements (
    timestamp_utc timestamptz       NOT NULL,
    series        text              NOT NULL,
    value         double precision  NOT NULL,
    quality       text,
    CONSTRAINT raw_measurements_series_ts_key UNIQUE (series, timestamp_utc)
);

-- Chinese domain comments (table + every column).
COMMENT ON TABLE  raw_measurements               IS '原始量测时序表（长格式）：比利时 Elia 电网 2024 年实测数据，每 15 分钟一条记录。';
COMMENT ON COLUMN raw_measurements.timestamp_utc IS '量测时间戳，UTC 时区（timestamptz），15 分钟分辨率。';
COMMENT ON COLUMN raw_measurements.series        IS '序列名称，取值 wind / solar / load，分别为风电、光伏、负荷。';
COMMENT ON COLUMN raw_measurements.value         IS '量测数值，单位兆瓦（MW）。';
COMMENT ON COLUMN raw_measurements.quality       IS '数据质量标记（文本）；本练习环境统一填 measured 表示清洗后的实测值。';
