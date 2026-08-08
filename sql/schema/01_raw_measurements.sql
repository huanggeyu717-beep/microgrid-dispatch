-- Raw (measured) grid time-series, long format. Span: 2019-01-01 .. 2024-12-31.
-- An absent measurement is an absent row (never NULL, never imputed); the
-- loader reports the per-series dropped counts. Solar starts mid-2020.
-- Target database: microgrid. Apply with:
--   psql -d microgrid -f sql/schema/01_raw_measurements.sql
-- Idempotent: CREATE TABLE IF NOT EXISTS; the loader upserts on the unique key.

CREATE TABLE IF NOT EXISTS raw_measurements (
    timestamp_utc timestamptz       NOT NULL,
    series        text              NOT NULL,
    value         double precision  NOT NULL,
    quality       text,
    CONSTRAINT raw_measurements_series_ts_key UNIQUE (series, timestamp_utc)
);

COMMENT ON TABLE  raw_measurements               IS '原始量测时序表（长格式）：比利时 Elia 电网 2019-01-01 至 2024-12-31 实测数据，每 15 分钟一条记录。缺测即缺行：某序列在某时刻无量测时该行不存在（不写 NULL、不插补）；光伏（solar）序列约 2020 年年中才开始，此前完全缺失，跨序列按时间戳连接时样本量会随之缩小。';
COMMENT ON COLUMN raw_measurements.timestamp_utc IS '量测时间戳，UTC 时区（timestamptz），15 分钟分辨率。';
COMMENT ON COLUMN raw_measurements.series        IS '序列名称，取值 wind / solar / load，分别为风电、光伏、负荷。各序列覆盖范围不同：solar 自约 2020 年年中起才有数据。';
COMMENT ON COLUMN raw_measurements.value         IS '量测数值，单位兆瓦（MW）；非空——缺测以整行缺失表示，而非 NULL。';
COMMENT ON COLUMN raw_measurements.quality       IS '数据质量标记（文本）；清洗后的实测值统一填 measured。';
