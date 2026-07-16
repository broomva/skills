type Mode = "purchase_rate" | "winner_timestamps";
type PurchaseModel = "global" | "per_lane";
type CadenceModel = "regular" | "mixed" | "random";

type Inputs = {
  mode: Mode;
  is_weekend_or_holiday?: boolean;
  model?: PurchaseModel;
  observed_purchases?: number;
  observed_minutes?: number;
  observed_lanes?: number;
  total_open_lanes?: number | null;
  winner_timestamps?: string[];
  elapsed_since_last_winner_minutes?: number;
  target_hit_probability?: number;
  confidence_buffer?: number;
  max_wait_minutes?: number;
  time_value_per_minute?: number | null;
  expected_bonus_value?: number | null;
};

type WaitEstimates = {
  mean_interval_between_winners: number;
  expected_wait_to_next_winner: number;
  p50_wait_to_next_winner: number;
  p75_wait_to_next_winner: number;
  p90_wait_to_next_winner: number;
};

type Output = {
  mode: Mode;
  k_threshold_clients?: number;
  probability_win_per_attempt?: number;
  assumptions: string[];
  rates?: {
    purchases_per_minute_observed: number;
    purchases_per_minute_estimated: number;
    purchases_per_minute_conservative: number;
    lane_scale_factor: number;
  };
  cadence_analysis?: {
    intervals_minutes: number[];
    interval_mean_minutes: number;
    interval_std_minutes: number;
    interval_cv: number;
    cadence_model: CadenceModel;
  };
  wait_estimates_minutes: WaitEstimates;
  recommendation: {
    optimal_wait_minutes: number;
    probability_next_winner_within_optimal_wait: number;
    decision_rule: string;
    rationale: string[];
  };
  economics?: {
    expected_value_for_optimal_wait: number;
    expected_time_cost_for_optimal_wait: number;
    net_expected_value_for_optimal_wait: number;
    value_expected_per_minute: number;
    break_even_wait_minutes: number;
    rationale: string[];
  };
};

const HMS_RE = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
const EPSILON = 1e-9;

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function round(value: number, decimals = 2): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function mean(values: number[]): number {
  assert(values.length > 0, "No se puede calcular promedio de lista vacia.");
  return values.reduce((acc, value) => acc + value, 0) / values.length;
}

function sampleStd(values: number[]): number {
  if (values.length < 2) {
    return 0;
  }
  const m = mean(values);
  const variance =
    values.reduce((acc, value) => acc + (value - m) ** 2, 0) /
    (values.length - 1);
  return Math.sqrt(variance);
}

function thresholdFromDay(isWeekendOrHoliday: boolean): number {
  return isWeekendOrHoliday ? 50 : 25;
}

function uniformWaitStats(intervalMinutes: number): WaitEstimates {
  const t = Math.max(intervalMinutes, 0);
  return {
    mean_interval_between_winners: round(t),
    expected_wait_to_next_winner: round(0.5 * t),
    p50_wait_to_next_winner: round(0.5 * t),
    p75_wait_to_next_winner: round(0.75 * t),
    p90_wait_to_next_winner: round(0.9 * t),
  };
}

function expWaitStats(meanIntervalMinutes: number): WaitEstimates {
  const m = Math.max(meanIntervalMinutes, EPSILON);
  return {
    mean_interval_between_winners: round(m),
    expected_wait_to_next_winner: round(m),
    p50_wait_to_next_winner: round(-m * Math.log(1 - 0.5)),
    p75_wait_to_next_winner: round(-m * Math.log(1 - 0.75)),
    p90_wait_to_next_winner: round(-m * Math.log(1 - 0.9)),
  };
}

function parseHmsToSeconds(timestamp: string): number | null {
  const match = timestamp.match(HMS_RE);
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = Number(match[3] ?? "0");
  if (
    Number.isNaN(hour) ||
    Number.isNaN(minute) ||
    Number.isNaN(second) ||
    hour < 0 ||
    hour > 23 ||
    minute < 0 ||
    minute > 59 ||
    second < 0 ||
    second > 59
  ) {
    return null;
  }
  return hour * 3600 + minute * 60 + second;
}

function parseTimestampsToMonotonicMinutes(timestamps: string[]): number[] {
  assert(
    timestamps.length >= 2,
    "Necesitas al menos 2 timestamps para estimar intervalos."
  );

  const hmsSeconds = timestamps.map(parseHmsToSeconds);
  const allHms = hmsSeconds.every((value) => typeof value === "number");

  if (allHms) {
    const absoluteSeconds: number[] = [];
    let current = hmsSeconds[0] as number;
    absoluteSeconds.push(current);

    for (let i = 1; i < hmsSeconds.length; i += 1) {
      let candidate = hmsSeconds[i] as number;
      while (candidate <= current) {
        candidate += 24 * 3600;
      }
      absoluteSeconds.push(candidate);
      current = candidate;
    }

    return absoluteSeconds.map((seconds) => seconds / 60);
  }

  const parsed = timestamps.map((timestamp) => Date.parse(timestamp));
  assert(
    parsed.every((value) => Number.isFinite(value)),
    "Formato de timestamp invalido. Usa HH:MM[:SS] o ISO datetime."
  );
  for (let i = 1; i < parsed.length; i += 1) {
    assert(
      parsed[i] > parsed[i - 1],
      "Los timestamps ISO deben venir ordenados de menor a mayor."
    );
  }
  return parsed.map((value) => value / 60000);
}

function intervalsFromTimelineMinutes(timelineMinutes: number[]): number[] {
  const intervals: number[] = [];
  for (let i = 1; i < timelineMinutes.length; i += 1) {
    intervals.push(timelineMinutes[i] - timelineMinutes[i - 1]);
  }
  return intervals;
}

function probabilityWithinUniform(interval: number, wait: number): number {
  if (interval <= 0) {
    return 1;
  }
  return clamp(wait / interval, 0, 1);
}

function probabilityWithinExponential(meanInterval: number, wait: number): number {
  if (meanInterval <= 0) {
    return 1;
  }
  return 1 - Math.exp(-wait / meanInterval);
}

function withEconomics(
  output: Output,
  expectedBonusValue: number | null | undefined,
  timeValuePerMinute: number | null | undefined,
  probabilityWithinWait: number,
  meanInterval: number,
  maxWait: number
): void {
  if (
    typeof expectedBonusValue !== "number" ||
    expectedBonusValue < 0 ||
    typeof timeValuePerMinute !== "number" ||
    timeValuePerMinute < 0
  ) {
    return;
  }

  const wait = output.recommendation.optimal_wait_minutes;
  const expectedValue = probabilityWithinWait * expectedBonusValue;
  const timeCost = wait * timeValuePerMinute;
  const netValue = expectedValue - timeCost;
  const valuePerMinute = expectedBonusValue / Math.max(meanInterval, EPSILON);
  const breakEvenWait =
    timeValuePerMinute === 0
      ? maxWait
      : clamp(expectedBonusValue / timeValuePerMinute, 0, maxWait);

  output.economics = {
    expected_value_for_optimal_wait: round(expectedValue),
    expected_time_cost_for_optimal_wait: round(timeCost),
    net_expected_value_for_optimal_wait: round(netValue),
    value_expected_per_minute: round(valuePerMinute),
    break_even_wait_minutes: round(breakEvenWait),
    rationale: [
      "EV(W) = P(evento en W) * valor_del_bono.",
      "Costo(W) = W * valor_tiempo_por_minuto.",
      "Si EV/min < costo/min, recorta espera o no esperes.",
    ],
  };
}

function runPurchaseRateMode(inputs: Inputs): Output {
  assert(
    typeof inputs.is_weekend_or_holiday === "boolean",
    "is_weekend_or_holiday es obligatorio en mode=purchase_rate."
  );
  assert(inputs.model === "global" || inputs.model === "per_lane", "model invalido.");
  assert(
    typeof inputs.observed_purchases === "number" && inputs.observed_purchases > 0,
    "observed_purchases debe ser > 0."
  );
  assert(
    typeof inputs.observed_minutes === "number" && inputs.observed_minutes > 0,
    "observed_minutes debe ser > 0."
  );
  assert(
    typeof inputs.observed_lanes === "number" && inputs.observed_lanes > 0,
    "observed_lanes debe ser > 0."
  );

  const isWeekendOrHoliday = inputs.is_weekend_or_holiday as boolean;
  const model = inputs.model as PurchaseModel;
  const observedPurchases = inputs.observed_purchases as number;
  const observedMinutes = inputs.observed_minutes as number;
  const observedLanes = inputs.observed_lanes as number;

  const maxWait = Math.max(inputs.max_wait_minutes ?? 30, 1);
  const confidenceBuffer = clamp(inputs.confidence_buffer ?? 0.2, 0, 0.9);
  const probabilityTarget = clamp(inputs.target_hit_probability ?? 0.75, 0.5, 0.99);
  const kThreshold = thresholdFromDay(isWeekendOrHoliday);

  const lambdaObserved = observedPurchases / observedMinutes;
  let laneScale = 1;

  if (model === "global" && typeof inputs.total_open_lanes === "number") {
    if (inputs.total_open_lanes >= observedLanes) {
      laneScale = inputs.total_open_lanes / observedLanes;
    }
  }

  const lambdaEstimated =
    model === "global"
      ? lambdaObserved * laneScale
      : lambdaObserved / observedLanes;
  const lambdaConservative = lambdaEstimated * (1 - confidenceBuffer);
  const meanInterval = kThreshold / Math.max(lambdaConservative, EPSILON);
  const waitStats = uniformWaitStats(meanInterval);

  const waitForTarget = meanInterval * probabilityTarget;
  const optimalWait = clamp(waitForTarget, 1, maxWait);
  const probabilityWithinOptimal = probabilityWithinUniform(meanInterval, optimalWait);

  const result: Output = {
    mode: "purchase_rate",
    k_threshold_clients: kThreshold,
    probability_win_per_attempt: round(1 / kThreshold, 4),
    assumptions: [
      "El intervalo entre ganadores se estima con K/lambda.",
      "Se usa buffer conservador para absorber variabilidad de cajas y tamano de carrito.",
      "Llegada aleatoria al ciclo de K clientes => espera restante uniforme entre 0 e intervalo.",
    ],
    rates: {
      purchases_per_minute_observed: round(lambdaObserved),
      purchases_per_minute_estimated: round(lambdaEstimated),
      purchases_per_minute_conservative: round(lambdaConservative),
      lane_scale_factor: round(laneScale),
    },
    wait_estimates_minutes: waitStats,
    recommendation: {
      optimal_wait_minutes: round(optimalWait),
      probability_next_winner_within_optimal_wait: round(probabilityWithinOptimal, 4),
      decision_rule:
        "Si no sale ganador en ese tiempo, re-mide 2 minutos y recalcula. Si vuelve a quedar alto, no sigas esperando.",
      rationale: [
        `K=${kThreshold} clientes segun dia (25 entre semana, 50 fin de semana/festivo).`,
        `Tasa conservadora=${round(lambdaConservative)} compras/min.`,
        `Objetivo de captura=${round(probabilityTarget * 100)}%.`,
      ],
    },
  };

  withEconomics(
    result,
    inputs.expected_bonus_value,
    inputs.time_value_per_minute,
    probabilityWithinOptimal,
    meanInterval,
    maxWait
  );

  return result;
}

function runWinnerTimestampsMode(inputs: Inputs): Output {
  assert(
    Array.isArray(inputs.winner_timestamps) && inputs.winner_timestamps.length >= 2,
    "winner_timestamps debe tener al menos 2 elementos en mode=winner_timestamps."
  );

  const winnerTimestamps = inputs.winner_timestamps as string[];
  const maxWait = Math.max(inputs.max_wait_minutes ?? 30, 1);
  const probabilityTarget = clamp(inputs.target_hit_probability ?? 0.75, 0.5, 0.99);
  const elapsed = Math.max(inputs.elapsed_since_last_winner_minutes ?? 0, 0);
  const timeline = parseTimestampsToMonotonicMinutes(winnerTimestamps);
  const intervals = intervalsFromTimelineMinutes(timeline);
  const intervalMean = mean(intervals);
  const intervalStd = sampleStd(intervals);
  const intervalCv = intervalStd / Math.max(intervalMean, EPSILON);

  let cadenceModel: CadenceModel = "mixed";
  if (intervalCv < 0.4) {
    cadenceModel = "regular";
  } else if (intervalCv > 0.7) {
    cadenceModel = "random";
  }

  const regularRemaining = Math.max(intervalMean - elapsed, 0);
  const randomExpectedRemaining = intervalMean;

  const waitStatsRegular: WaitEstimates = {
    mean_interval_between_winners: round(intervalMean),
    expected_wait_to_next_winner: round(regularRemaining),
    p50_wait_to_next_winner: round(regularRemaining),
    p75_wait_to_next_winner: round(regularRemaining),
    p90_wait_to_next_winner: round(regularRemaining),
  };
  const waitStatsRandom = expWaitStats(intervalMean);

  let waitStats = waitStatsRegular;
  if (cadenceModel === "random") {
    waitStats = waitStatsRandom;
  } else if (cadenceModel === "mixed") {
    waitStats = {
      mean_interval_between_winners: round(intervalMean),
      expected_wait_to_next_winner: round(
        (waitStatsRegular.expected_wait_to_next_winner + randomExpectedRemaining) / 2
      ),
      p50_wait_to_next_winner: round(
        (waitStatsRegular.p50_wait_to_next_winner +
          waitStatsRandom.p50_wait_to_next_winner) /
          2
      ),
      p75_wait_to_next_winner: round(
        (waitStatsRegular.p75_wait_to_next_winner +
          waitStatsRandom.p75_wait_to_next_winner) /
          2
      ),
      p90_wait_to_next_winner: round(
        (waitStatsRegular.p90_wait_to_next_winner +
          waitStatsRandom.p90_wait_to_next_winner) /
          2
      ),
    };
  }

  const randomWaitForTarget = -intervalMean * Math.log(1 - probabilityTarget);
  const mixedWaitForTarget = (regularRemaining + randomWaitForTarget) / 2;

  let optimalWait = regularRemaining;
  if (cadenceModel === "random") {
    optimalWait = randomWaitForTarget;
  } else if (cadenceModel === "mixed") {
    optimalWait = mixedWaitForTarget;
  }
  optimalWait = clamp(optimalWait, 0, maxWait);

  const regularProbability =
    regularRemaining <= EPSILON
      ? 1
      : clamp(optimalWait / Math.max(regularRemaining, EPSILON), 0, 1);
  const randomProbability = probabilityWithinExponential(intervalMean, optimalWait);

  let probabilityWithinOptimal = regularProbability;
  if (cadenceModel === "random") {
    probabilityWithinOptimal = randomProbability;
  } else if (cadenceModel === "mixed") {
    probabilityWithinOptimal = (regularProbability + randomProbability) / 2;
  }

  const result: Output = {
    mode: "winner_timestamps",
    assumptions: [
      "Se estima cadencia solo con intervalos entre anuncios de ganadores.",
      "CV<0.4 sugiere comportamiento casi regular; CV>0.7 sugiere comportamiento aleatorio.",
      "En cadencia aleatoria se usa modelo exponencial para P(ganador en W minutos).",
    ],
    cadence_analysis: {
      intervals_minutes: intervals.map((value) => round(value)),
      interval_mean_minutes: round(intervalMean),
      interval_std_minutes: round(intervalStd),
      interval_cv: round(intervalCv),
      cadence_model: cadenceModel,
    },
    wait_estimates_minutes: waitStats,
    recommendation: {
      optimal_wait_minutes: round(optimalWait),
      probability_next_winner_within_optimal_wait: round(probabilityWithinOptimal, 4),
      decision_rule:
        "Si no escuchas ganador en ese tiempo, captura 2-3 timestamps adicionales y recalcula.",
      rationale: [
        `Intervalo promedio observado=${round(intervalMean)} min.`,
        `CV=${round(intervalCv)} (${cadenceModel}).`,
        `Probabilidad objetivo=${round(probabilityTarget * 100)}%.`,
      ],
    },
  };

  if (typeof inputs.is_weekend_or_holiday === "boolean") {
    const kThreshold = thresholdFromDay(inputs.is_weekend_or_holiday);
    result.k_threshold_clients = kThreshold;
    result.probability_win_per_attempt = round(1 / kThreshold, 4);
  }

  withEconomics(
    result,
    inputs.expected_bonus_value,
    inputs.time_value_per_minute,
    probabilityWithinOptimal,
    intervalMean,
    maxWait
  );

  return result;
}

export default async function run(inputs: Inputs): Promise<Output> {
  if (inputs.mode === "purchase_rate") {
    return runPurchaseRateMode(inputs);
  }
  if (inputs.mode === "winner_timestamps") {
    return runWinnerTimestampsMode(inputs);
  }
  throw new Error(`mode invalido: ${String(inputs.mode)}`);
}
