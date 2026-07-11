-- Forecast time-series, long format: both the TSO day-ahead POINT forecast and
-- the LSTM day-ahead QUANTILE predictions, keyed so the two are directly
-- comparable against raw_measurements actuals (join on series + timestamp).
-- Apply with:  psql -d microgrid -f sql/schema/02_forecasts.sql
--
-- Design notes:
--  * The TSO forecast is a single point value, so it is stored honestly with
--    quantile = NULL (not faked as a median). PostgreSQL 17's
--    UNIQUE ... NULLS NOT DISTINCT makes (series, model, target_time, NULL) a
--    real key, so a TSO row still upserts cleanly.
--  * The LSTM value is the day-ahead forecast issued at 00:00 UTC for that day
--    (one forecast per 15-min slot); horizon_min = target_time - issued_at.

CREATE TABLE IF NOT EXISTS forecasts (
    target_time timestamptz      NOT NULL,
    series      text             NOT NULL,
    model       text             NOT NULL,
    quantile    numeric(3,2),
    value_mw    double precision NOT NULL,
    issued_at   timestamptz,
    horizon_min integer,
    CONSTRAINT forecasts_key
        UNIQUE NULLS NOT DISTINCT (series, model, target_time, quantile)
);

CREATE INDEX IF NOT EXISTS forecasts_lookup_idx ON forecasts (series, model, target_time);

COMMENT ON TABLE  forecasts             IS '预测时序表（长格式）：TSO 日前点预测（model=tso，quantile 为空）与 LSTM 日前分位数预测（model=lstm，quantile=0.10/0.50/0.90）；可按 series + 时间戳与 raw_measurements 实测值对齐比较。';
COMMENT ON COLUMN forecasts.target_time IS '被预测的目标时间戳，UTC，15 分钟分辨率。';
COMMENT ON COLUMN forecasts.series      IS '序列名称：wind / solar / load。';
COMMENT ON COLUMN forecasts.model       IS '预测来源：tso（电网运营商日前预测）或 lstm（本项目 LSTM 模型）。';
COMMENT ON COLUMN forecasts.quantile    IS '分位数：LSTM 取 0.10/0.50/0.90；TSO 为点预测，此列为空（NULL）。';
COMMENT ON COLUMN forecasts.value_mw    IS '预测数值，单位兆瓦（MW）。';
COMMENT ON COLUMN forecasts.issued_at   IS '预测发布时间：LSTM 为当日 00:00 UTC 的日前发布时刻；TSO 为空。';
COMMENT ON COLUMN forecasts.horizon_min IS '预测提前量（分钟）= target_time − issued_at；仅 LSTM 有值（0 至 1425）。';
