-- Dispatch method benchmark: realized objectives per (day, method, forecast
-- noise factor, noise seed) from the three-way comparison (rule / NSGA-III / RL).
-- One row per method per cache item under models/comparison/cache/.
-- Apply with:  psql -d microgrid -f sql/schema/03_dispatch_results.sql
--
-- forecast_factor scales seeded Gaussian noise added to the forecast fed to the
-- optimizers (0 = nominal forecast; 1/2/3 = increasingly noisy). noise_seed is
-- the noise realization (only meaningful for factor > 0). Every method is scored
-- against the SAME measured actuals through one shared physics path.

CREATE TABLE IF NOT EXISTS dispatch_results (
    day                 date             NOT NULL,
    method              text             NOT NULL,
    forecast_factor     real             NOT NULL,
    noise_seed          integer          NOT NULL,
    cost_eur            double precision,
    co2_tco2            double precision,
    peak_mw             double precision,
    terminal_soc_dev    double precision,
    tie_violation_steps integer,
    tie_violation_mw    double precision,
    projection_mw       double precision,
    decision_latency_s  double precision,
    per_step_ms         double precision,
    CONSTRAINT dispatch_results_key UNIQUE (day, method, forecast_factor, noise_seed)
);

COMMENT ON TABLE  dispatch_results                     IS '调度方法对比表：三种方法（rule 规则 / nsga3 多目标优化 / rl 强化学习）在相同实测数据上执行后的实现指标，按 (日期, 方法, 预测噪声因子, 噪声种子) 唯一。';
COMMENT ON COLUMN dispatch_results.day                 IS '调度日（该日 96 个 15 分钟时段）。';
COMMENT ON COLUMN dispatch_results.method              IS '调度方法：rule / nsga3 / rl。';
COMMENT ON COLUMN dispatch_results.forecast_factor     IS '预测误差放大因子：0 为原始预测，1/2/3 为逐级加大的高斯噪声。';
COMMENT ON COLUMN dispatch_results.noise_seed          IS '噪声实现种子（仅 factor>0 时有意义）。';
COMMENT ON COLUMN dispatch_results.cost_eur            IS '实现的运行成本（欧元）。';
COMMENT ON COLUMN dispatch_results.co2_tco2            IS '实现的碳排放（吨 CO2）。';
COMMENT ON COLUMN dispatch_results.peak_mw             IS '并网点峰值功率（MW）。';
COMMENT ON COLUMN dispatch_results.terminal_soc_dev    IS '储能末端 SoC 相对目标的偏差。';
COMMENT ON COLUMN dispatch_results.tie_violation_steps IS '联络线约束越限的时段数。';
COMMENT ON COLUMN dispatch_results.tie_violation_mw    IS '联络线约束越限的累计功率（MW）。';
COMMENT ON COLUMN dispatch_results.projection_mw       IS '为满足约束所做投影修正的累计功率（MW）。';
COMMENT ON COLUMN dispatch_results.decision_latency_s  IS '单日决策耗时（秒）：NSGA-III 为当日求解墙钟时间。';
COMMENT ON COLUMN dispatch_results.per_step_ms         IS '单个时段的平均决策耗时（毫秒）。';
