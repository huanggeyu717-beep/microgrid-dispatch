-- Dispatch method benchmark: realized objectives per (day, method, forecast
-- tier, perturbation mechanism, factor, noise seed, optimiser seed) from the
-- dispatch comparison (rule / NSGA-III / RL).
-- One row per method per cache item under models/comparison/cache/.
-- Apply with:  psql -d microgrid -f sql/schema/03_dispatch_results.sql
--
-- The cache-key axes (task 08, mirrored by
-- src/microgrid/pipeline/dispatch_cache.py):
--   tier      — which forecast source is being degraded (task-04 sweep:
--               'lstm_dispatch').
--   mechanism — how the forecast is perturbed: 'whitenoise' adds seeded
--               Gaussian noise scaled by forecast_factor (0 = nominal,
--               1/2/3 = increasingly noisy); 'residual' scales the REAL
--               forecast error (0 = perfect foresight, 1 = nominal); plus
--               the single-series variants residual_load / residual_wind /
--               residual_solar and 'perfect_biased'. NOTE the two factor
--               axes run in opposite directions — never average
--               forecast_factor across mechanisms.
--   noise_seed— the noise realization (meaningful for whitenoise factor > 0).
--   opt_seed  — the NSGA-III optimiser seed; rule/rl do not consume it but
--               are stored per seed so each cache entry is self-contained.
-- Every method is scored against the SAME measured actuals through one
-- shared physics path.

CREATE TABLE IF NOT EXISTS dispatch_results (
    day                 date             NOT NULL,
    method              text             NOT NULL,
    tier                text             NOT NULL,
    mechanism           text             NOT NULL,
    forecast_factor     real             NOT NULL,
    noise_seed          integer          NOT NULL,
    opt_seed            integer          NOT NULL,
    cost_eur            double precision,
    co2_tco2            double precision,
    peak_mw             double precision,
    terminal_soc_dev    double precision,
    tie_violation_steps integer,
    tie_violation_mw    double precision,
    projection_mw       double precision,
    decision_latency_s  double precision,
    per_step_ms         double precision,
    CONSTRAINT dispatch_results_key
        UNIQUE (day, method, tier, mechanism, forecast_factor, noise_seed, opt_seed)
);

-- In-place migration (task S2) for a database whose dispatch_results predates
-- the task-08 cache key: CREATE ... IF NOT EXISTS above never alters an
-- existing table, so the three axis columns are added here. Old rows are
-- exactly the task-04 sweep — tier 'lstm_dispatch', mechanism 'whitenoise',
-- optimiser seed 42 — so the backfill is a statement of fact, not a guess.
-- Safe to re-run: every step is IF (NOT) EXISTS or a no-op the second time.
ALTER TABLE dispatch_results ADD COLUMN IF NOT EXISTS tier      text;
ALTER TABLE dispatch_results ADD COLUMN IF NOT EXISTS mechanism text;
ALTER TABLE dispatch_results ADD COLUMN IF NOT EXISTS opt_seed  integer;
UPDATE dispatch_results SET tier      = 'lstm_dispatch' WHERE tier      IS NULL;
UPDATE dispatch_results SET mechanism = 'whitenoise'    WHERE mechanism IS NULL;
UPDATE dispatch_results SET opt_seed  = 42              WHERE opt_seed  IS NULL;
ALTER TABLE dispatch_results ALTER COLUMN tier      SET NOT NULL;
ALTER TABLE dispatch_results ALTER COLUMN mechanism SET NOT NULL;
ALTER TABLE dispatch_results ALTER COLUMN opt_seed  SET NOT NULL;
-- The old four-column unique key would let the idempotent upsert overwrite
-- rows ACROSS tiers/mechanisms/optimiser seeds without any error; re-key it
-- over all seven columns (drop + re-add is a no-op when already seven-column).
ALTER TABLE dispatch_results DROP CONSTRAINT IF EXISTS dispatch_results_key;
ALTER TABLE dispatch_results ADD CONSTRAINT dispatch_results_key
    UNIQUE (day, method, tier, mechanism, forecast_factor, noise_seed, opt_seed);

COMMENT ON TABLE  dispatch_results                     IS '调度方法对比表：三种方法（rule 规则 / nsga3 多目标优化 / rl 强化学习）在相同实测数据上执行后的实现指标，按 (日期, 方法, 预测档位, 扰动机制, 扰动因子, 噪声种子, 优化器种子) 唯一。';
COMMENT ON COLUMN dispatch_results.day                 IS '调度日（该日 96 个 15 分钟时段）。';
COMMENT ON COLUMN dispatch_results.method              IS '调度方法：rule / nsga3 / rl。';
COMMENT ON COLUMN dispatch_results.tier                IS '预测档位：本条目所退化的预测来源；任务 04 的发布数据均为 lstm_dispatch（LSTM 中位数预测驱动调度）。';
COMMENT ON COLUMN dispatch_results.mechanism           IS '预测扰动机制：whitenoise 为加性白噪声（factor 0 为原始预测）；residual 为真实误差缩放（factor 0 为完美预见、1 为原始预测）；另有单序列变体 residual_load / residual_wind / residual_solar 及 perfect_biased。两种机制的 factor 方向相反，不可跨机制混合统计。';
COMMENT ON COLUMN dispatch_results.forecast_factor     IS '扰动因子：含义取决于 mechanism（见 mechanism 列注释），whitenoise 下 0/1/2/3 为逐级加大的高斯噪声。';
COMMENT ON COLUMN dispatch_results.noise_seed          IS '噪声实现种子（仅 whitenoise 且 factor>0 时有意义）。';
COMMENT ON COLUMN dispatch_results.opt_seed            IS 'NSGA-III 优化器随机种子；rule / rl 不使用该种子，但按种子各存一份以保证缓存条目自洽。';
COMMENT ON COLUMN dispatch_results.cost_eur            IS '实现的运行成本（欧元）。';
COMMENT ON COLUMN dispatch_results.co2_tco2            IS '实现的碳排放（吨 CO2）。';
COMMENT ON COLUMN dispatch_results.peak_mw             IS '并网点峰值功率（MW）。';
COMMENT ON COLUMN dispatch_results.terminal_soc_dev    IS '储能末端 SoC 相对目标的偏差。';
COMMENT ON COLUMN dispatch_results.tie_violation_steps IS '联络线约束越限的时段数。';
COMMENT ON COLUMN dispatch_results.tie_violation_mw    IS '联络线约束越限的累计功率（MW）。';
COMMENT ON COLUMN dispatch_results.projection_mw       IS '为满足约束所做投影修正的累计功率（MW）。';
COMMENT ON COLUMN dispatch_results.decision_latency_s  IS '单日决策耗时（秒）：NSGA-III 为当日求解墙钟时间。';
COMMENT ON COLUMN dispatch_results.per_step_ms         IS '单个时段的平均决策耗时（毫秒）。';
