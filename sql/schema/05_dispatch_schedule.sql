-- Per-step power schedule behind a dispatch_solution: the 96 15-min set-points
-- for the micro-turbine, battery, grid tie-line, and the battery state of charge.
-- 1-to-many with dispatch_solution (FK id, cascade delete).
-- Apply with:  psql -d microgrid -f sql/schema/05_dispatch_schedule.sql

CREATE TABLE IF NOT EXISTS dispatch_schedule (
    solution_id bigint      NOT NULL REFERENCES dispatch_solution(id) ON DELETE CASCADE,
    step        integer     NOT NULL,
    target_time timestamptz NOT NULL,
    p_mt_mw     double precision,
    p_bat_mw    double precision,
    p_grid_mw   double precision,
    soc         double precision,
    PRIMARY KEY (solution_id, step)
);

COMMENT ON TABLE  dispatch_schedule             IS '调度功率曲线表：某个 dispatch_solution 对应的 96 个 15 分钟时段的设备出力设定与储能荷电状态。';
COMMENT ON COLUMN dispatch_schedule.solution_id IS '外键，指向 dispatch_solution.id。';
COMMENT ON COLUMN dispatch_schedule.step        IS '时段序号（0..95），对应当日第 step 个 15 分钟。';
COMMENT ON COLUMN dispatch_schedule.target_time IS '该时段起始时间戳，UTC。';
COMMENT ON COLUMN dispatch_schedule.p_mt_mw     IS '燃气/微型燃气轮机出力（MW）。';
COMMENT ON COLUMN dispatch_schedule.p_bat_mw    IS '储能功率（MW，正为放电、负为充电）。';
COMMENT ON COLUMN dispatch_schedule.p_grid_mw   IS '并网点功率（MW，正为购电）。';
COMMENT ON COLUMN dispatch_schedule.soc         IS '储能荷电状态（SoC，0..1）。';
