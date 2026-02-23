"use client";

import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceDot,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const DEMO_MATCH_ID = 3869685;

type Match = any;

type Sub = {
  event_id: string;
  minute: number;
  second: number;
  team: string;
  player_off: string | null;
  player_on: string | null;
};

type WPPoint = { minute: number; W: number; D: number; L: number };
type ChartPoint = { minute: number; wBase: number; wCf: number; delta: number };

type TurningPoint = {
  minute: number;
  event_type: string;
  swing_home: number;
  impact: number;
  one_liner: string;
};

function cn(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(" ");
}

export default function Page() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [matchId, setMatchId] = useState<number | null>(null);

  const [subs, setSubs] = useState<Sub[]>([]);
  const [subId, setSubId] = useState<string>("");

  const selectedSub = useMemo(
    () => subs.find((s) => s.event_id === subId),
    [subs, subId]
  );

  // Debounced slider: draft updates instantly; altMinute triggers API call
  const [altMinuteDraft, setAltMinuteDraft] = useState<number>(60);
  const [altMinute, setAltMinute] = useState<number>(60);

  const [sim, setSim] = useState<any>(null);
  const [err, setErr] = useState<string>("");

  const [turningPoints, setTurningPoints] = useState<TurningPoint[]>([]);
  const [isSimLoading, setIsSimLoading] = useState(false);

  const [showRaw, setShowRaw] = useState(false);

  // Load matches
  useEffect(() => {
    fetch(`${API}/matches`)
      .then((r) => r.json())
      .then((d) => {
        const ms = d.matches ?? [];
        setMatches(ms);

        setMatchId((prev) =>
          prev === null && ms.length
            ? ms.some((x: any) => Number(x.match_id) === DEMO_MATCH_ID)
              ? DEMO_MATCH_ID
              : ms[0].match_id
            : prev
        );
      })
      .catch(() => setErr("Failed to load matches"));
  }, []);

  // Load subs + turning points on match change
  useEffect(() => {
    if (!matchId) return;

    setErr("");
    setSubs([]);
    setSubId("");
    setSim(null);
    setTurningPoints([]);

    fetch(`${API}/matches/${matchId}/subs`)
      .then((r) => r.json())
      .then((d) => {
        const s: Sub[] = d.subs ?? [];
        setSubs(s);

        if (s.length) {
          setSubId(s[0].event_id);
          setAltMinuteDraft(s[0].minute);
          setAltMinute(s[0].minute);
        } else {
          setAltMinuteDraft(60);
          setAltMinute(60);
        }
      })
      .catch(() => setErr("Failed to load substitutions"));

    fetch(`${API}/matches/${matchId}/turning_points?top_n=5`)
      .then((r) => r.json())
      .then((d) => {
        const tps: TurningPoint[] = d.turning_points ?? [];
        setTurningPoints(tps);

        // Auto-jump to biggest turning point (great for demos)
        if (tps.length) setAltMinuteDraft(Number(tps[0].minute));
      })
      .catch(() => {});
  }, [matchId]);

  // Debounce draft -> altMinute used by API
  useEffect(() => {
    const t = setTimeout(() => setAltMinute(altMinuteDraft), 180);
    return () => clearTimeout(t);
  }, [altMinuteDraft]);

  // Simulate on (match, sub, minute)
  useEffect(() => {
    if (!matchId || !subId) return;

    setIsSimLoading(true);
    setErr("");

    fetch(`${API}/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        match_id: matchId,
        sub_event_id: subId,
        alt_minute: altMinute,
      }),
    })
      .then((r) => r.json())
      .then(setSim)
      .catch(() => setErr("Simulation call failed"))
      .finally(() => setIsSimLoading(false));
  }, [matchId, subId, altMinute]);

  const sliderMin = selectedSub ? Math.max(0, selectedSub.minute - 15) : 0;
  const sliderMax = selectedSub ? Math.min(90, selectedSub.minute + 15) : 90;
  const deltaMin = selectedSub ? altMinuteDraft - selectedSub.minute : 0;

  const shiftLabel =
    !selectedSub
      ? ""
      : deltaMin === 0
      ? "same time"
      : deltaMin < 0
      ? `${deltaMin} min`
      : `+${deltaMin} min`;

  const shiftTone =
    !selectedSub || deltaMin === 0
      ? "bg-zinc-100 text-zinc-700 border-zinc-200"
      : deltaMin < 0
      ? "bg-blue-50 text-blue-700 border-blue-200"
      : "bg-amber-50 text-amber-800 border-amber-200";

const wpSeries = useMemo<ChartPoint[]>(() => {
  // backend sends full curves
  const base: WPPoint[] = sim?.wp_base ?? [];
  const cf: WPPoint[] = sim?.wp_cf ?? [];

  if (base.length && cf.length) {
    const cfByMin = new Map<number, WPPoint>(
      cf.map((pt: WPPoint) => [Number(pt.minute), pt])
    );

    return base.map((b: WPPoint) => {
      const minute = Number(b.minute);
      const c = cfByMin.get(minute);

      const wBase = Number(b.W ?? 0) * 100;
      const wCf = Number(c?.W ?? 0) * 100;

      return { minute, wBase, wCf, delta: wCf - wBase };
    });
  }

  const wA = Number(sim?.probs_actual?.W ?? 0) * 100;
  const wB = Number(sim?.probs_alt?.W ?? 0) * 100;

  if (!Number.isFinite(wA) || !Number.isFinite(wB)) return [];

  const out: ChartPoint[] = [];
  for (let m = 0; m <= 90; m++) {
    out.push({ minute: m, wBase: wA, wCf: wB, delta: wB - wA });
  }
  return out;
}, [sim]);


const deltaEndPct = useMemo(() => {
  // If backend provides delta_wp_end, use it.
  if (sim?.delta_wp_end !== undefined && sim?.delta_wp_end !== null) {
    return (Number(sim.delta_wp_end) * 100).toFixed(1);
  }
  // Otherwise fall back to delta.W
  const dW = Number(sim?.delta?.W ?? 0);
  return (dW * 100).toFixed(1);
}, [sim]);


const peak = sim?.peak_delta ?? null;
const peakMinute: number | null =
  peak?.minute !== undefined && peak?.minute !== null ? Number(peak.minute) : null;

const peakDeltaPct: string | null =
  peak ? (Number(peak.delta_W ?? 0) * 100).toFixed(1) : null;


  const currentMatch = useMemo(() => {
    if (!matchId) return null;
    return matches.find((m) => Number(m.match_id) === Number(matchId)) ?? null;
  }, [matches, matchId]);

  // Auto-detect hero chips (Final + iconic teams) from local data
  const heroMatches = useMemo(() => {
    const out: Array<{ id: number; label: string; hint?: string }> = [];

    for (const m of matches) {
      const id = Number(m.match_id);
      const home = m.home_team?.home_team_name ?? "";
      const away = m.away_team?.away_team_name ?? "";
      const stage = m.competition_stage?.name ?? m.competition_stage ?? "";
      const label = `${home} vs ${away}`;
      if (String(stage).toLowerCase() === "final") {
        out.push({ id, label: "🏆 Final: " + label, hint: "Final" });
      }
    }

    const prefers = [
      "Argentina",
      "France",
      "Netherlands",
      "Germany",
      "Japan",
      "Saudi Arabia",
      "Morocco",
      "Croatia",
      "Brazil",
    ];

    for (const team of prefers) {
      const m = matches.find((x) => {
        const h = x.home_team?.home_team_name;
        const a = x.away_team?.away_team_name;
        return h === team || a === team;
      });
      if (m) {
        const id = Number(m.match_id);
        const home = m.home_team?.home_team_name ?? "";
        const away = m.away_team?.away_team_name ?? "";
        const stage = m.competition_stage?.name ?? "";
        const lbl = `${home} vs ${away}`;
        const tag = stage ? ` • ${stage}` : "";
        if (!out.some((o) => o.id === id)) {
          out.push({ id, label: `⭐ ${lbl}${tag}`, hint: team });
        }
      }
      if (out.length >= 6) break;
    }

    if (!out.length) {
      for (const m of matches.slice(0, 4)) {
        const id = Number(m.match_id);
        const home = m.home_team?.home_team_name ?? "";
        const away = m.away_team?.away_team_name ?? "";
        out.push({ id, label: `${home} vs ${away}` });
      }
    }

    return out.slice(0, 6);
  }, [matches]);

  const matchTitle = useMemo(() => {
    if (!currentMatch) return "—";
    const home = currentMatch.home_team?.home_team_name ?? "";
    const away = currentMatch.away_team?.away_team_name ?? "";
    const stage = currentMatch.competition_stage?.name ?? "";
    const date = currentMatch.match_date ?? "";
    const tail = [stage, date].filter(Boolean).join(" • ");
    return `${home} vs ${away}${tail ? ` — ${tail}` : ""}`;
  }, [currentMatch]);

  return (
    <main className="min-h-screen bg-gradient-to-b from-zinc-50 via-white to-white">
      <div className="mx-auto max-w-6xl px-6 py-10">
        {/* Header */}
        <div className="rounded-3xl border bg-white/80 p-6 shadow-sm backdrop-blur">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1 text-xs text-zinc-700">
                <span className="font-medium">World Cup 2022</span>
                <span className="text-zinc-400">•</span>
                <span className="text-zinc-600">
                  Turning Points + Counterfactual Subs
                </span>
              </div>

              <h1 className="mt-3 text-3xl font-semibold tracking-tight">
                DecisionMirror
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-zinc-600">
                Find match turning points and simulate “what-if” substitution
                timing. Built on StatsBomb event data.
              </p>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setMatchId(DEMO_MATCH_ID)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                    Number(matchId) === Number(DEMO_MATCH_ID)
                      ? "border-zinc-900 bg-zinc-900 text-white"
                      : "bg-white text-zinc-800 hover:bg-zinc-50"
                  )}
                  title="Argentina vs France — Final"
                >
                  ▶ Demo: WC Final
                </button>

                {heroMatches.map((h) => (
                  <button
                    key={h.id}
                    onClick={() => setMatchId(h.id)}
                    className={cn(
                      "rounded-full border bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm transition hover:bg-zinc-50",
                      Number(matchId) === Number(h.id) &&
                        "border-zinc-900 text-zinc-900"
                    )}
                    title={h.hint ?? ""}
                  >
                    {h.label}
                  </button>
                ))}

                {selectedSub ? (
                  <span
                    className={cn(
                      "ml-1 rounded-full border px-3 py-1.5 text-xs font-medium",
                      shiftTone
                    )}
                  >
                    Shift: {shiftLabel}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl border bg-zinc-50 p-4">
              <div className="text-xs text-zinc-500">Selected match</div>
              <div className="mt-1 text-sm font-medium text-zinc-900">
                {matchTitle}
              </div>
              <div className="mt-2 flex items-center gap-2 text-xs text-zinc-600">
                <span className="rounded-full border bg-white px-2 py-1">
                  Match ID: {matchId ?? "—"}
                </span>
                {isSimLoading ? (
                  <span className="rounded-full border bg-white px-2 py-1">
                    Simulating…
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {err ? (
          <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {err}
          </div>
        ) : null}

        {/* Main grid */}
        <div className="mt-8 grid gap-6 lg:grid-cols-5">
          {/* Left: controls */}
          <section className="lg:col-span-2">
            <div className="rounded-3xl border bg-white p-6 shadow-sm">
              <div className="text-sm font-semibold text-zinc-900">Controls</div>
              <div className="mt-1 text-xs text-zinc-500">
                Pick a match, then a substitution, then move it.
              </div>

              <div className="mt-6 grid gap-5">
                <div className="grid gap-2">
                  <label className="text-sm font-medium text-zinc-800">
                    Match
                  </label>
                  <select
                    className="w-full rounded-xl border bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-zinc-900"
                    value={matchId ?? ""}
                    onChange={(e) => setMatchId(Number(e.target.value))}
                  >
                    {matches.map((m) => (
                      <option key={m.match_id} value={m.match_id}>
                        {m.home_team?.home_team_name} vs{" "}
                        {m.away_team?.away_team_name} —{" "}
                        {m.competition_stage?.name ?? ""}{" "}
                        {m.match_date ? `• ${m.match_date}` : ""} (id {m.match_id})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-2">
                  <label className="text-sm font-medium text-zinc-800">
                    Substitution
                  </label>
                  <select
                    className="w-full rounded-xl border bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-zinc-900 disabled:opacity-60"
                    value={subId}
                    onChange={(e) => {
                      const id = e.target.value;
                      setSubId(id);
                      const s = subs.find((x) => x.event_id === id);
                      if (s) {
                        setAltMinuteDraft(s.minute);
                        setAltMinute(s.minute);
                      }
                    }}
                    disabled={!subs.length}
                  >
                    {!subs.length ? <option>No substitutions found</option> : null}
                    {subs.map((s) => (
                      <option key={s.event_id} value={s.event_id}>
                        {s.minute}' {s.team}: {s.player_off ?? "?"} →{" "}
                        {s.player_on ?? "?"}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-zinc-800">
                      Move sub minute
                    </label>
                    <div className="text-sm text-zinc-700">
                      <span className="font-semibold">{altMinuteDraft}'</span>{" "}
                      {selectedSub ? (
                        <span className="text-zinc-500">
                          (actual: {selectedSub.minute}')
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <input
                    type="range"
                    min={sliderMin}
                    max={sliderMax}
                    value={altMinuteDraft}
                    onChange={(e) => setAltMinuteDraft(Number(e.target.value))}
                    className="w-full accent-zinc-900"
                    disabled={!selectedSub}
                  />

                  <div className="flex items-center justify-between text-xs text-zinc-500">
                    <span>Drag within ±15 minutes.</span>
                    {isSimLoading ? <span>Simulating…</span> : null}
                  </div>
                </div>

                <div className="rounded-2xl border bg-zinc-50 p-4">
                  <div className="text-xs font-semibold text-zinc-800">Tip</div>
                  <div className="mt-1 text-xs text-zinc-600">
                    Click a turning point on the right to jump to that minute, then
                    move the substitution to see the “mirror” outcome.
                  </div>
                </div>
              </div>
            </div>

            {/* Debug */}
            <div className="mt-6 rounded-3xl border bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-zinc-900">Debug</div>
                <button
                  className="rounded-xl border bg-white px-3 py-1.5 text-xs text-zinc-700 shadow-sm hover:bg-zinc-50"
                  onClick={() => setShowRaw((s) => !s)}
                >
                  {showRaw ? "Hide JSON" : "Show JSON"}
                </button>
              </div>

              {showRaw ? (
                <pre className="mt-3 max-h-72 overflow-auto rounded-2xl border bg-zinc-50 p-3 text-xs text-zinc-700">
                  {JSON.stringify(sim, null, 2)}
                </pre>
              ) : (
                <div className="mt-2 text-xs text-zinc-600">
                  Raw API response hidden for presentation.
                </div>
              )}
            </div>
          </section>

          {/* Right: results */}
          <section className="lg:col-span-3">
            <div className="rounded-3xl border bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-sm font-semibold text-zinc-900">
                    Mirror Timeline
                  </div>
                  <div className="mt-1 text-sm text-zinc-600">
                    {sim?.explainer ??
                      "Move a substitution to see the counterfactual impact."}
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-2xl border bg-white p-4">
                      <div className="text-xs text-zinc-500">Δ Win% (end)</div>
                      <div className="mt-1 text-3xl font-semibold text-zinc-900">
                        {sim ? `${deltaEndPct}%` : "—"}
                      </div>
                    </div>

                    <div className="rounded-2xl border bg-white p-4">
                      <div className="text-xs text-zinc-500">Peak swing</div>
                      <div className="mt-1 text-3xl font-semibold text-zinc-900">
                        {sim && peakDeltaPct ? `${peakDeltaPct}%` : "—"}
                      </div>
                      <div className="text-xs text-zinc-500">
                        {sim && peakMinute !== null ? `${peakMinute}'` : ""}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border bg-zinc-50 p-4 text-right">
                  <div className="text-xs text-zinc-500">Model confidence</div>
                  <div className="mt-1 text-sm text-zinc-800">
                    <span className="font-semibold">
                      {sim?.confidence?.level ?? "—"}
                    </span>{" "}
                    {sim?.confidence?.score !== undefined
                      ? `(${(sim.confidence.score * 100).toFixed(0)}%)`
                      : ""}
                  </div>
                  <div className="mt-2 text-xs text-zinc-500">
                    Shift applied at{" "}
                    <span className="font-semibold">{altMinute}'</span>
                  </div>
                </div>
              </div>

              {/* Win prob chart */}
              <div className="mt-6 rounded-3xl border bg-zinc-50 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-sm font-semibold text-zinc-900">
                    Win probability
                  </div>
                  <div className="text-xs text-zinc-600">
                    Actual vs Mirror • team perspective
                  </div>
                </div>

                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={wpSeries}
                      margin={{ top: 10, right: 16, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="minute"
                        tick={{ fontSize: 12 }}
                        domain={[0, 90]}
                        type="number"
                      />
                      <YAxis
                        tick={{ fontSize: 12 }}
                        domain={[0, 100]}
                        tickFormatter={(v) => `${v}%`}
                      />

                      <Tooltip
                        formatter={(value: any, name: any) => {
                          if (name === "wBase")
                            return [
                              `${Number(value).toFixed(1)}%`,
                              "Actual timeline",
                            ];
                          if (name === "wCf")
                            return [
                              `${Number(value).toFixed(1)}%`,
                              "Mirror timeline",
                            ];
                          if (name === "delta")
                            return [`${Number(value).toFixed(1)}%`, "Δ win%"];
                          return [value, name];
                        }}
                        labelFormatter={(label) => `${label}'`}
                      />

                      <Line
                        type="monotone"
                        dataKey="wBase"
                        dot={false}
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="wCf"
                        dot={false}
                        strokeWidth={2}
                      />

                      {/* Turning points markers (on base curve) */}
                      {turningPoints.map((tp: TurningPoint) => {
                        const m = Number(tp.minute);
                        const row = wpSeries.find(
                          (p: ChartPoint) => p.minute === m
                        );
                        if (!row) return null;

                        return (
                          <ReferenceDot
                            key={`${tp.event_type}-${tp.minute}`}
                            x={m}
                            y={row.wBase}
                            r={6}
                            strokeWidth={2}
                            label={{
                              value: tp.event_type,
                              position: "top",
                              fontSize: 10,
                            }}
                          />
                        );
                      })}

                      {/* Alt minute marker (on mirror curve) */}
                      <ReferenceDot
                        x={altMinute}
                        y={
                          wpSeries.find((p: ChartPoint) => p.minute === altMinute)
                            ?.wCf ?? 0
                        }
                        r={7}
                        strokeWidth={2}
                        label={{ value: "ALT", position: "right", fontSize: 10 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Turning points list */}
              {turningPoints.length ? (
                <div className="mt-6">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-zinc-900">
                      Turning points
                    </div>
                    <div className="text-xs text-zinc-600">
                      Click to jump minute
                    </div>
                  </div>

                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {turningPoints.map((tp: TurningPoint) => (
                      <button
                        key={`${tp.event_type}-${tp.minute}-btn`}
                        onClick={() => setAltMinuteDraft(Number(tp.minute))}
                        className="group flex items-center justify-between rounded-2xl border bg-white px-4 py-3 text-left text-sm shadow-sm transition hover:-translate-y-0.5 hover:bg-zinc-50 hover:shadow"
                        title={tp.one_liner}
                      >
                        <div>
                          <div className="font-semibold text-zinc-900">
                            {tp.minute}'{" "}
                            <span className="text-zinc-700">
                              {tp.event_type}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-zinc-500">
                            {tp.one_liner}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs text-zinc-500">impact</div>
                          <div className="font-semibold text-zinc-900">
                            {Number(tp.impact ?? 0).toFixed(2)}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mt-6 rounded-2xl border bg-zinc-50 p-4 text-sm text-zinc-600">
                  No turning points detected for this match (or data missing).
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
