import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardSkeleton from "../components/DashboardSkeleton";
import NotificationBell from "../components/NotificationBell";
import { api } from "../lib/api";
import { useAuth } from "../lib/AuthContext";
import { loadRazorpayScript } from "../lib/razorpayCheckout";
import { useNotify } from "../lib/useNotify";
import type { Claim, Policy, PremiumQuote } from "../lib/types";
import { WORK_ZONES, zoneById } from "../data/zones";

const PLANS = [
  {
    id: "basic" as const,
    name: "Basic",
    emoji: "🟢",
    blurb: "Part-time, calmer zones",
    base: 20,
    cap: 1000,
    perEvent: 300,
  },
  {
    id: "standard" as const,
    name: "Standard",
    emoji: "🟡",
    blurb: "Regular shifts",
    base: 35,
    cap: 1500,
    perEvent: 500,
  },
  {
    id: "pro" as const,
    name: "Pro",
    emoji: "🔴",
    blurb: "Full-time, higher-risk zones",
    base: 50,
    cap: 2500,
    perEvent: 800,
  },
];

function formatRs(n: number) {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** Poll interval; server caches env data ~5 min — hits are cheap (cache), “Refresh now” forces live APIs. */
const LIVE_POLL_MS = 120_000;

/** Razorpay Test Mode order amount (paise). 10_000 = ₹100 — no real money in test keys. */
const TEST_EARNING_PAISE = 10_000;

function formatTime(d: Date) {
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function toFiniteNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

export default function DashboardPage() {
  const { user, logout, refresh } = useAuth();
  const notify = useNotify();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [live, setLive] = useState<Record<string, unknown> | null>(null);
  const [quote, setQuote] = useState<PremiumQuote | null>(null);
  const [selected, setSelected] = useState<(typeof PLANS)[number]["id"] | null>(
    "standard"
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [evalResult, setEvalResult] = useState<Record<string, unknown> | null>(null);
  const [dailyRows, setDailyRows] = useState<
    { earn_date: string; amount: number; minutes_online?: number | null }[]
  >([]);
  const [liveUpdatedAt, setLiveUpdatedAt] = useState<Date | null>(null);
  const [liveFetching, setLiveFetching] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [workZoneId, setWorkZoneId] = useState(WORK_ZONES[0].id);
  const [rzReady, setRzReady] = useState(false);
  const [gpsCapturing, setGpsCapturing] = useState(false);
  const [gpsCaptureProgressMs, setGpsCaptureProgressMs] = useState(0);
  const [pendingGpsSamples, setPendingGpsSamples] = useState<
    {
      lat: number;
      lon: number;
      accuracy?: number;
      speed?: number;
      heading?: number;
      ts: number;
    }[]
  >([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([
        api<Policy | null>("/policies/active"),
        api<Claim[]>("/claims?limit=12"),
      ]);
      setPolicy(p);
      setClaims(c);
      if (p?.plan_type && ["basic", "standard", "pro"].includes(p.plan_type)) {
        setSelected(p.plan_type as (typeof PLANS)[number]["id"]);
      }
    } catch {
      notify("", "Could not load policy / claims.", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const refreshDailyEarnings = useCallback(async () => {
    try {
      const rows = await api<
        { earn_date: string; amount: number; minutes_online?: number | null }[]
      >("/users/me/daily-earnings?limit=21");
      setDailyRows(
        [...rows].sort((a, b) => b.earn_date.localeCompare(a.earn_date))
      );
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (loading) return;
    void refreshDailyEarnings();
  }, [loading, refreshDailyEarnings]);

  useEffect(() => {
    if (user?.zone_id && WORK_ZONES.some((z) => z.id === user.zone_id)) {
      setWorkZoneId(user.zone_id);
    }
  }, [user?.zone_id]);

  useEffect(() => {
    void api<{ razorpay_configured?: boolean }>("/health/integrations")
      .then((j) => setRzReady(Boolean(j.razorpay_configured)))
      .catch(() => setRzReady(false));
  }, []);

  const refreshLive = useCallback(async (forceRefresh = false) => {
    setLiveFetching(true);
    setLiveError(null);
    try {
      const q = forceRefresh ? "?refresh=true" : "";
      const L = await api<Record<string, unknown>>(`/monitoring/live${q}`);
      setLive(L);
      setLiveUpdatedAt(new Date());
    } catch (e) {
      setLive(null);
      setLiveError(e instanceof Error ? e.message : "Could not load live monitors");
    } finally {
      setLiveFetching(false);
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    void refreshLive();
    const id = setInterval(() => void refreshLive(), LIVE_POLL_MS);
    return () => clearInterval(id);
  }, [loading, refreshLive]);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible") void refreshLive();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [refreshLive]);

  useEffect(() => {
    if (!selected || !user) return;
    let cancelled = false;
    (async () => {
      try {
        const q = await api<PremiumQuote>("/policies/quote", {
          method: "POST",
          body: JSON.stringify({ plan_type: selected }),
        });
        if (!cancelled) setQuote(q);
      } catch {
        if (!cancelled) setQuote(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, user]);

  async function subscribe() {
    if (!selected) return;
    setBusy(true);
    try {
      await api("/policies/subscribe", {
        method: "POST",
        body: JSON.stringify({ plan_type: selected }),
      });
      await load();
      notify("", "Weekly coverage is now active.", "success");
    } catch (e) {
      notify("", e instanceof Error ? e.message : "Subscribe failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function runEvaluate(mock: boolean) {
    setBusy(true);
    setEvalResult(null);
    try {
      const r = await api<Record<string, unknown>>("/monitoring/evaluate", {
        method: "POST",
        body: JSON.stringify({ force_mock_disruption: mock }),
      });
      setEvalResult(r);
      await load();
      await refresh();
      if (r.claim_created) {
        const amt = Number(r.payout_amount);
        notify(
          "Claim recorded",
          `${formatRs(Number.isFinite(amt) ? amt : 0)} · ${String(r.status)}`,
          "success"
        );
      } else {
        notify(
          "",
          String(r.message ?? "Evaluation finished — see details below."),
          "info"
        );
      }
    } catch (e) {
      notify("", e instanceof Error ? e.message : "Evaluation failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function captureDeviceGps() {
    if (!navigator.geolocation) {
      notify(
        "",
        "Geolocation not available in this browser. Use Chrome/Edge, allow location, or HTTPS.",
        "error"
      );
      return;
    }
    setGpsCapturing(true);
    setGpsCaptureProgressMs(0);
    const samples: {
      lat: number;
      lon: number;
      accuracy?: number;
      speed?: number;
      heading?: number;
      ts: number;
    }[] = [];
    const started = Date.now();
    const duration = 22_000;
    const tick = window.setInterval(() => {
      setGpsCaptureProgressMs(Date.now() - started);
    }, 300);
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        samples.push({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy ?? undefined,
          speed: pos.coords.speed ?? undefined,
          heading: pos.coords.heading ?? undefined,
          ts: Date.now(),
        });
      },
      (err: GeolocationPositionError) => {
        clearInterval(tick);
        navigator.geolocation.clearWatch(watchId);
        setGpsCapturing(false);
        const hint =
          err.code === 1
            ? "Location permission denied — open Android Settings → Apps → SurakshaPay → Permissions → Location → Allow."
            : err.code === 3
              ? "GPS timed out — emulator: set a mock location (⋯ Extended controls → Location); real device: go outdoors or enable high accuracy."
              : err.message || "GPS unavailable";
        notify("", hint, "error");
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 20_000 }
    );
    await new Promise<void>((r) => setTimeout(r, duration));
    clearInterval(tick);
    navigator.geolocation.clearWatch(watchId);
    setGpsCapturing(false);
    setGpsCaptureProgressMs(0);
    if (samples.length < 3) {
      try {
        const one = await new Promise<{
          lat: number;
          lon: number;
          accuracy?: number;
          speed?: number;
          heading?: number;
          ts: number;
        }>((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(
            (pos) =>
              resolve({
                lat: pos.coords.latitude,
                lon: pos.coords.longitude,
                accuracy: pos.coords.accuracy ?? undefined,
                speed: pos.coords.speed ?? undefined,
                heading: pos.coords.heading ?? undefined,
                ts: Date.now(),
              }),
            reject,
            { enableHighAccuracy: false, maximumAge: 45_000, timeout: 10_000 }
          );
        });
        setPendingGpsSamples([one]);
        notify(
          "GPS fallback captured",
          "Saved a single fix fallback. You can save now (weather will use it).",
          "info"
        );
        return;
      } catch {
        notify(
          "",
          "Not enough GPS fixes — save anyway to use zone center fallback for weather.",
          "error"
        );
        return;
      }
    }
    setPendingGpsSamples(samples);
    notify(
      "Live GPS captured",
      `${samples.length} fixes — save to anchor your real position for fraud checks.`,
      "success"
    );
  }

  async function saveWorkLocation() {
    const z = zoneById(workZoneId) ?? WORK_ZONES[0];
    const trace = pendingGpsSamples;
    const hadTrace = trace.length >= 1;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { zone_id: z.id };
      if (hadTrace) {
        body.gps_attestation = {
          samples: trace,
          source: "device_geolocation",
          captured_at: new Date().toISOString(),
        };
      } else {
        body.lat = z.lat;
        body.lon = z.lon;
      }
      await api("/users/me/profile", {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      await refresh();
      await refreshLive();
      setPendingGpsSamples([]);
      notify(
        "",
        hadTrace
          ? "Work zone + GPS saved."
          : "Work location saved (zone center fallback active for weather).",
        "success"
      );
    } catch (e) {
      notify("", e instanceof Error ? e.message : "Could not update location", "error");
    } finally {
      setBusy(false);
    }
  }

  async function payTestEarning() {
    setBusy(true);
    try {
      await loadRazorpayScript();
      const o = await api<{
        order_id: string;
        amount: number;
        currency: string;
        key_id: string;
      }>("/payments/razorpay/order", {
        method: "POST",
        body: JSON.stringify({ amount_paise: TEST_EARNING_PAISE }),
      });
      await new Promise<void>((resolve) => {
        let finished = false;
        const finish = () => {
          if (!finished) {
            finished = true;
            setBusy(false);
            resolve();
          }
        };
        const rzp = new window.Razorpay({
          key: o.key_id,
          amount: o.amount,
          currency: o.currency,
          name: "SurakshaPay",
          description: "Test Mode — no real money",
          order_id: o.order_id,
          theme: { color: "#0c1222" },
          handler: async (response: {
            razorpay_payment_id: string;
            razorpay_order_id: string;
            razorpay_signature: string;
          }) => {
            try {
              await api("/payments/razorpay/verify", {
                method: "POST",
                body: JSON.stringify(response),
              });
              await refresh();
              await refreshDailyEarnings();
              if (selected) {
                const q = await api<PremiumQuote>("/policies/quote", {
                  method: "POST",
                  body: JSON.stringify({ plan_type: selected }),
                });
                setQuote(q);
              }
              notify(
                "Test payment",
                `${formatRs(TEST_EARNING_PAISE / 100)} credited to today`,
                "success"
              );
            } catch (e) {
              notify(
                "",
                e instanceof Error ? e.message : "Could not verify payment",
                "error"
              );
            } finally {
              finish();
            }
          },
          modal: {
            ondismiss: () => finish(),
          },
        });
        rzp.open();
      });
    } catch (e) {
      notify(
        "",
        e instanceof Error ? e.message : "Could not start Razorpay checkout",
        "error"
      );
      setBusy(false);
    }
  }

  async function resimulateEarnings() {
    setBusy(true);
    try {
      await api("/users/me/earnings/resimulate", { method: "POST" });
      await refresh();
      await refreshDailyEarnings();
      if (selected) {
        const q = await api<PremiumQuote>("/policies/quote", {
          method: "POST",
          body: JSON.stringify({ plan_type: selected }),
        });
        setQuote(q);
      }
      notify("", "Demo earnings updated for your zone and hours.", "success");
    } catch (e) {
      notify("", e instanceof Error ? e.message : "Could not regenerate earnings", "error");
    } finally {
      setBusy(false);
    }
  }

  const flags = live?.flags as Record<string, boolean> | undefined;
  const liveDetails = live?.details as
    | {
        weather_api?: Record<string, unknown>;
        aqi_api?: Record<string, unknown>;
        rss?: Record<string, unknown>;
      }
    | undefined;
  const wApi = liveDetails?.weather_api;
  const aApi = liveDetails?.aqi_api;

  const rain24Val = toFiniteNumber(wApi?.forecast_rain_24h_mm);
  const tempNowVal = toFiniteNumber(wApi?.temp_c);
  const aqiNowVal = toFiniteNumber(aApi?.aqi_us);
  const rain24 = rain24Val ?? 0;
  const tempNow = tempNowVal ?? 32;
  const aqiNow = aqiNowVal ?? 70;
  const activeFlagCount = flags ? Object.values(flags).filter(Boolean).length : 0;

  // "AI Shift Coach" score (0-100): higher => safer to stay online now.
  const shiftSafetyScore = clamp(
    Math.round(
      100 -
        rain24 * 0.8 -
        Math.max(0, tempNow - 34) * 1.7 -
        Math.max(0, aqiNow - 90) * 0.22 -
        activeFlagCount * 9
    ),
    8,
    95
  );
  const coachTone =
    shiftSafetyScore >= 72 ? "good" : shiftSafetyScore >= 48 ? "watch" : "risk";
  const coachHeadline =
    coachTone === "good"
      ? "High-confidence earning window"
      : coachTone === "watch"
        ? "Caution window — optimize route + breaks"
        : "High disruption risk — keep exposure low";
  const coachAction =
    coachTone === "good"
      ? "Best next 2h: stay active in your primary zone; keep refresh on."
      : coachTone === "watch"
        ? "Best next 2h: prefer short trips, avoid low-visibility stretches."
        : "Best next 2h: pause long routes; re-check in 30-45 minutes.";
  const coachPillClass =
    coachTone === "good"
      ? "bg-emerald-100 text-emerald-900"
      : coachTone === "watch"
        ? "bg-amber-100 text-amber-900"
        : "bg-rose-100 text-rose-900";
  const scoreStroke =
    coachTone === "good" ? "#059669" : coachTone === "watch" ? "#d97706" : "#e11d48";
  const scoreOffset = 251.2 - (251.2 * shiftSafetyScore) / 100; // circumference for r=40
  const currentHour = new Date().getHours();
  const hourRiskBias = (h: number) => {
    if (h >= 12 && h <= 16) return 6; // mid-day heat risk
    if ((h >= 19 && h <= 22) || (h >= 7 && h <= 10)) return -6; // stronger demand windows
    if (h >= 0 && h <= 5) return 8; // late-night risk
    return 0;
  };
  const timeline = Array.from({ length: 6 }, (_, i) => {
    const hour = (currentHour + i) % 24;
    const score = clamp(
      shiftSafetyScore - (i > 2 ? (rain24 > 18 ? 7 : 3) : 0) - hourRiskBias(hour),
      5,
      97
    );
    return {
      hour,
      score,
      label: `${String(hour).padStart(2, "0")}:00`,
      risky: score < 45,
    };
  });
  const bestWindow = timeline.reduce((best, cur) => (cur.score > best.score ? cur : best), timeline[0]);
  const trendDelta = timeline[timeline.length - 1].score - timeline[0].score;
  const trendText =
    trendDelta >= 8
      ? "Risk easing over next hours"
      : trendDelta <= -8
        ? "Risk increasing over next hours"
        : "Risk mostly stable next hours";
  const trendClass =
    trendDelta >= 8 ? "text-emerald-300" : trendDelta <= -8 ? "text-rose-300" : "text-slate-300";
  const sparklinePoints = timeline
    .map((t, i) => {
      const x = 8 + i * 56;
      const y = 84 - (t.score / 100) * 64;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div
      className="min-h-[100dvh] pb-safe safe-pb max-w-lg mx-auto px-4 pt-6 text-slate-100 relative z-10"
      aria-busy={busy}
    >
      <header className="flex items-start justify-between gap-3 mb-6">
        <div>
          <p className="font-display text-2xl font-bold text-white tracking-tight">SurakshaPay</p>
          <p className="text-brand text-sm mt-0.5 font-medium">
            Hi {user?.full_name?.split(" ")[0] ?? "partner"} — food delivery cover
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <NotificationBell />
          <button
            type="button"
            onClick={() => {
              logout();
              window.location.href = "/login";
            }}
            className="text-sm text-slate-400 font-bold min-h-[44px] min-w-[44px] px-3 rounded-2xl bg-surface/30 border border-glass-border hover:bg-surface/60 hover:text-white transition-all"
          >
            Log out
          </button>
        </div>
      </header>

      {loading ? (
        <DashboardSkeleton />
      ) : (
        <>
          <section className="glass-card rounded-3xl p-5 mb-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent to-brand" />
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">
              This week&apos;s coverage
            </p>
            {policy ? (
              <div className="mt-2">
                <p className="font-display text-xl font-bold capitalize text-white mt-1">
                  {policy.plan_type} plan
                </p>
                <p className="text-accent font-bold mt-1 text-sm bg-accent/10 w-fit px-3 py-1 rounded-full border border-accent/20">
                  Active · {formatRs(policy.weekly_premium)}/week
                </p>
                <p className="text-sm text-slate-400 mt-3 font-medium">
                  Coverage up to <span className="text-white">{formatRs(policy.max_weekly_coverage)}</span>/wk ·{" "}
                  Max <span className="text-white">{formatRs(policy.max_per_event)}</span>/event
                </p>
              </div>
            ) : (
              <p className="text-warn font-bold mt-3 bg-warn/10 border border-warn/20 rounded-xl px-4 py-3 text-sm">
                No active policy — choose a plan below.
              </p>
            )}
          </section>

          <section className="glass-card rounded-3xl border border-brand/30 p-5 mb-6 relative overflow-hidden bg-gradient-to-br from-brand/10 to-transparent">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
                  AI Shift Coach
                </p>
                <h2 className="font-display text-lg leading-tight mt-1">{coachHeadline}</h2>
                <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">{coachAction}</p>
              </div>
              <div className="relative h-24 w-24 shrink-0">
                <svg viewBox="0 0 100 100" className="h-24 w-24">
                  <circle cx="50" cy="50" r="40" stroke="rgba(148,163,184,0.25)" strokeWidth="8" fill="none" />
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    stroke={scoreStroke}
                    strokeWidth="8"
                    fill="none"
                    strokeLinecap="round"
                    transform="rotate(-90 50 50)"
                    strokeDasharray="251.2"
                    strokeDashoffset={scoreOffset}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="font-display text-xl font-bold">{shiftSafetyScore}</span>
                  <span className="text-[10px] text-slate-300">/ 100</span>
                </div>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <span className={`text-[11px] px-2 py-1 rounded-full font-medium ${coachPillClass}`}>
                {coachTone === "good"
                  ? "Suggested mode: Aggressive earnings"
                  : coachTone === "watch"
                    ? "Suggested mode: Balanced safety"
                    : "Suggested mode: Capital protection"}
              </span>
              <span className="text-[11px] text-slate-300">
                Policy: {policy ? `${policy.plan_type} active` : "No active coverage"}
              </span>
            </div>
            <div className="mt-3 rounded-xl bg-white/5 border border-white/10 p-3">
              <div className="flex items-center justify-between gap-2 mb-2">
                <p className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
                  Next 6h risk timeline
                </p>
                <p className={`text-[11px] font-medium ${trendClass}`}>{trendText}</p>
              </div>
              <svg viewBox="0 0 300 92" className="w-full h-20">
                <polyline
                  points={sparklinePoints}
                  fill="none"
                  stroke="rgba(148,163,184,0.35)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <polyline
                  points={sparklinePoints}
                  fill="none"
                  stroke={scoreStroke}
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                {timeline.map((t, i) => {
                  const cx = 8 + i * 56;
                  const cy = 84 - (t.score / 100) * 64;
                  return (
                    <circle
                      key={t.label}
                      cx={cx}
                      cy={cy}
                      r="3.6"
                      fill={t.risky ? "#fb7185" : scoreStroke}
                    />
                  );
                })}
              </svg>
              <div className="mt-1 grid grid-cols-6 gap-1 text-[10px] text-slate-300">
                {timeline.map((t) => (
                  <div key={t.label} className="text-center">
                    <p>{t.label}</p>
                    <p className={t.risky ? "text-rose-300 font-medium" : ""}>{t.score}</p>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-200">
                Best window: <span className="font-semibold">{bestWindow.label}</span> (score {bestWindow.score})
              </p>
            </div>
          </section>

          <section className="mb-6">
            <h2 className="font-display text-xl font-bold text-white mb-4 tracking-tight">Weekly coverage tiers</h2>
            <div className="space-y-2">
              {PLANS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSelected(p.id)}
                  className={`w-full text-left rounded-2xl border p-5 transition-all ${
                    selected === p.id
                      ? "border-brand bg-brand/10 shadow-glow ring-1 ring-brand/30"
                      : "border-glass-border bg-surface/30 hover:bg-surface/50"
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-white text-lg">
                      {p.emoji} {p.name}
                    </span>
                    <span className="text-slate-400 text-sm font-medium">
                      from {formatRs(p.base)}/wk
                    </span>
                  </div>
                  <p className="text-sm text-slate-400 mt-1.5">{p.blurb}</p>
                </button>
              ))}
            </div>
            {quote && (
              <div className="mt-4 rounded-3xl bg-surface/40 border border-brand/20 backdrop-blur-md p-6 shadow-[inset_0_0_20px_rgba(56,189,248,0.05)] animate-slide-up relative overflow-hidden">
                <div className="absolute top-0 right-0 w-32 h-32 bg-brand/10 blur-[50px] rounded-full" />
                <p className="text-[11px] uppercase tracking-widest text-brand font-bold">
                  AI-Adjusted Premium
                </p>
                <p className="text-xs text-slate-400 mt-1 capitalize">
                  Quote for: <span className="text-slate-200">{selected}</span> tier
                  {policy && policy.plan_type !== selected ? (
                    <span className="text-amber-300">
                      {" "}
                      (active plan is {policy.plan_type} — tap a tier to compare)
                    </span>
                  ) : null}
                </p>
                <p className="font-display text-3xl font-bold mt-2 text-white">
                  {formatRs(quote.final_weekly_premium)}
                  <span className="text-lg font-medium text-slate-400"> / week</span>
                </p>
                <p className="text-sm text-slate-300 mt-2">
                  Base {formatRs(quote.base_weekly_premium)} + ML risk{" "}
                  {quote.ml_risk_adjustment >= 0 ? "+" : ""}
                  {formatRs(quote.ml_risk_adjustment)}
                  {quote.zone_safety_premium_credit !== 0 ? (
                    <span className="text-emerald-300">
                      {" "}
                      · zone safety {formatRs(quote.zone_safety_premium_credit)}
                    </span>
                  ) : null}{" "}
                  → total adj.{" "}
                  {quote.risk_adjustment >= 0 ? "+" : ""}
                  {formatRs(quote.risk_adjustment)}
                </p>
                {typeof quote.dynamic_coverage?.extra_coverage_hours === "number" &&
                quote.dynamic_coverage.extra_coverage_hours > 0 ? (
                  <p className="text-xs text-amber-200 mt-2 leading-relaxed">
                    Predictive weather: +{String(quote.dynamic_coverage.extra_coverage_hours)}h
                    coverage window · caps {formatRs(quote.max_per_event)} / event
                  </p>
                ) : (
                  <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                    {String(quote.dynamic_coverage?.rationale ?? "")}
                  </p>
                )}
                <details className="mt-3 text-xs text-slate-400">
                  <summary className="cursor-pointer">ML explainability &amp; features</summary>
                  <p className="mt-2 text-slate-500">
                    {String(
                      (quote.pricing_explainability as { explainability_note?: string })
                        ?.explainability_note ?? ""
                    )}
                  </p>
                  <pre className="mt-2 whitespace-pre-wrap break-all overflow-x-auto">
                    {JSON.stringify(quote.pricing_explainability, null, 2)}
                  </pre>
                  <pre className="mt-2 whitespace-pre-wrap break-all overflow-x-auto text-slate-500">
                    {JSON.stringify(quote.feature_snapshot, null, 2)}
                  </pre>
                </details>
              </div>
            )}
            {policy ? (
              <p className="mt-4 text-sm text-slate-600 text-center">
                You already have an active plan for this calendar week. Premium quotes
                refresh when you change zone/hours or regenerate demo earnings.
              </p>
            ) : (
              <button
                type="button"
                disabled={busy || !selected}
                onClick={subscribe}
                className="w-full mt-6 rounded-2xl bg-gradient-to-r from-accent to-brand text-white font-bold text-base py-4 shadow-glow disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98] transition-all"
              >
                Activate Coverage Now
              </button>
            )}
          </section>

          <section className="glass-card rounded-3xl p-5 mb-6">
            <h2 className="font-display font-bold text-lg text-white mb-1 tracking-tight">Work Area (GPS)</h2>
            <p className="text-sm text-slate-400 mb-4 leading-relaxed">
              Pick your delivery hub, then use <strong className="text-slate-200">real device GPS</strong> so
              payouts can run fraud checks (zone match + MSTS anti-spoofing from the README).
            </p>
            <select
              className="w-full rounded-2xl border border-glass-border bg-surface/50 text-white px-4 py-3.5 outline-none focus:ring-2 focus:ring-brand/50 mb-3 font-medium transition-all"
              value={workZoneId}
              onChange={(e) => setWorkZoneId(e.target.value)}
            >
              {WORK_ZONES.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.label}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 font-mono mb-3">
              Zone center: {(zoneById(workZoneId) ?? WORK_ZONES[0]).lat.toFixed(4)}°,{" "}
              {(zoneById(workZoneId) ?? WORK_ZONES[0]).lon.toFixed(4)}°
            </p>
            {user?.gps_sample_count != null && user.gps_sample_count > 0 ? (
              <p className="text-[11px] text-emerald-600 mb-2">
                On file: {user.gps_sample_count} GPS fixes
                {user.gps_captured_at
                  ? ` · ${new Date(user.gps_captured_at).toLocaleString()}`
                  : ""}
              </p>
            ) : (
              <p className="text-[11px] text-amber-700/90 mb-2">
                No live GPS trace yet — capture below so Isolation Forest + MSTS are fully informed.
              </p>
            )}
            {pendingGpsSamples.length > 0 && (
              <p className="text-[11px] text-brand font-semibold mb-2">
                Ready to save: {pendingGpsSamples.length} fixes buffered
              </p>
            )}
            {gpsCapturing && (
              <p className="text-xs text-brand mb-2 animate-pulse">
                Scanning GPS… {Math.round(gpsCaptureProgressMs / 1000)}s / 22s — keep the app open
              </p>
            )}
            <div className="flex flex-col gap-2">
              <button
                type="button"
                disabled={busy || gpsCapturing}
                onClick={() => void captureDeviceGps()}
                className="w-full rounded-2xl border border-brand/40 bg-brand/10 text-white font-semibold py-3.5 disabled:opacity-50 hover:bg-brand/20 transition-all"
              >
                {gpsCapturing ? "Capturing live GPS…" : "Capture live GPS (~22s)"}
              </button>
              <button
                type="button"
                disabled={busy || gpsCapturing}
                onClick={() => void saveWorkLocation()}
                className="w-full rounded-2xl bg-gradient-to-r from-accent/90 to-brand text-white font-bold py-3.5 disabled:opacity-50 shadow-glow hover:scale-[1.01] active:scale-[0.99] transition-all"
              >
                Save work location
              </button>
            </div>
          </section>

          <section className="glass-card rounded-3xl p-5 mb-6">
            <div className="flex justify-between items-center mb-3 gap-2">
              <div>
                <h2 className="font-display font-bold text-lg text-white tracking-tight">Active Monitors</h2>
                <p className="text-[11px] font-bold tracking-widest mt-1 flex items-center gap-1.5 flex-wrap">
                  <span
                    className={`inline-flex items-center gap-1 ${liveFetching ? "text-brand" : "text-emerald-700"}`}
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${liveFetching ? "bg-brand animate-pulse" : "bg-emerald-500"}`}
                    />
                    {liveFetching
                      ? "Fetching OpenWeather + WAQI + RSS…"
                      : "Auto-refresh every 2 min + when you return to this tab"}
                  </span>
                </p>
                {liveUpdatedAt && (
                  <p className="text-[11px] text-slate-400 mt-1">
                    Last UI pull: {formatTime(liveUpdatedAt)}
                  </p>
                )}
                {live &&
                typeof live.data_freshness === "object" &&
                live.data_freshness !== null ? (
                  <p className="text-[11px] text-emerald-700/90 mt-1 font-mono">
                    Snapshot:{" "}
                    {String(
                      (live.data_freshness as { fetched_at?: string }).fetched_at ?? "—"
                    )}
                    {" · "}
                    age{" "}
                    {(live.data_freshness as { age_seconds?: number }).age_seconds ?? "—"}s
                    {(live.data_freshness as { cache_hit?: boolean }).cache_hit
                      ? " · served from cache"
                      : " · fresh fetch"}
                    {(live.data_freshness as { stale_fallback?: boolean }).stale_fallback
                      ? " (stale — APIs failed)"
                      : ""}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                disabled={liveFetching}
                onClick={() => void refreshLive(true)}
                className="text-sm text-brand font-medium shrink-0 disabled:opacity-50"
              >
                Refresh now
              </button>
            </div>
            <p className="text-xs text-slate-500 mb-3">
              Weather/AQI/RSS are cached server-side (TTL ~5 min); auto-refresh uses cache when
              fresh. &quot;Refresh now&quot; bypasses cache and pulls live APIs.
            </p>
            {liveError && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">
                {liveError}
              </p>
            )}
            {wApi && (
              <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Temp (now)</p>
                  <p className="font-semibold text-slate-900">
                    {tempNowVal !== null ? `${tempNowVal.toFixed(2)}°C` : "N/A"}
                  </p>
                  <p className="text-slate-400 mt-0.5">
                    src: {String(wApi.source ?? "—")}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Rain (24h fcst)</p>
                  <p className="font-semibold text-slate-900">
                    {rain24Val !== null ? `${rain24Val.toFixed(2)} mm` : "N/A"}
                  </p>
                </div>
              </div>
            )}
            {aApi && (
              <div className="rounded-lg bg-slate-50 px-3 py-2 mb-3 text-xs">
                <span className="text-slate-500">Air quality </span>
                {aApi.source === "waqi_no_station" ? (
                  <span className="text-slate-600">
                    No WAQI station — using OpenWeather air pollution if available on refresh
                  </span>
                ) : (
                  <>
                    <span className="font-semibold text-slate-900">
                      {aqiNowVal !== null ? `~${Math.round(aqiNowVal)} US AQI scale` : "N/A"}
                    </span>
                    <span className="text-slate-400">
                      {" "}
                      · {String(aApi.source ?? "")}
                    </span>
                  </>
                )}
              </div>
            )}
            {!live && !liveError && !liveFetching ? (
              <p className="text-sm text-slate-500">Waiting for first live pull…</p>
            ) : live ? (
              <div className="flex flex-wrap gap-2">
                {flags &&
                  Object.entries(flags).map(([k, v]) => (
                    <span
                      key={k}
                      className={`text-xs px-2 py-1 rounded-full ${
                        v ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {k.replace(/_/g, " ")}: {v ? "on" : "off"}
                    </span>
                  ))}
              </div>
            ) : null}
          </section>

          <section className="glass-card rounded-3xl border border-dashed border-brand/30 bg-brand/5 p-5 mb-6">
            <h2 className="font-display font-bold text-xl text-white tracking-tight">Zero-Touch Claim Demo</h2>
            <p className="text-sm text-slate-400 mt-2 leading-relaxed">
              Dual-gate check: external disruption + your income drop vs baseline. No
              forms — we simulate a covered event.
            </p>
            <div className="flex flex-col gap-2 mt-4">
              <button
                type="button"
                disabled={busy}
                onClick={() => void runEvaluate(true)}
                className="rounded-2xl bg-gradient-to-r from-brand to-brand2 shadow-glow text-white font-bold py-4 disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98] transition-all"
              >
                Simulate Disruption (Guaranteed demo)
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void runEvaluate(false)}
                className="rounded-2xl bg-surface/50 border border-glass-border text-white font-bold py-4 disabled:opacity-50 hover:bg-surface/80 transition-all font-medium"
              >
                Run Live APIs Only
              </button>
            </div>
            {evalResult && (
              <div className="mt-4 space-y-3">
                {typeof evalResult.fraud_msts === "object" &&
                  evalResult.fraud_msts !== null && (
                    <div className="rounded-2xl border border-emerald-200/40 bg-emerald-950/30 p-4">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400/90 mb-2">
                        Fraud &amp; MSTS (evaluator view)
                      </p>
                      <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] text-slate-300">
                        {Object.entries(evalResult.fraud_msts as Record<string, unknown>).map(
                          ([k, v]) => (
                            <div key={k} className="contents">
                              <dt className="text-slate-500 font-mono truncate">{k}</dt>
                              <dd className="text-white font-medium text-right">
                                {typeof v === "number" ? v.toFixed(4) : String(v)}
                              </dd>
                            </div>
                          )
                        )}
                      </dl>
                    </div>
                  )}
                <pre className="text-xs bg-white/80 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap text-slate-800">
                  {JSON.stringify(evalResult, null, 2)}
                </pre>
              </div>
            )}
          </section>

          <section className="mb-6">
            <h2 className="font-display font-bold text-xl text-white tracking-tight mb-4">Claims</h2>
            {claims.length === 0 ? (
              <div className="rounded-3xl border border-dashed border-glass-border bg-surface/30 px-5 py-8 text-center">
                <p className="text-slate-300 text-sm font-bold tracking-wide uppercase">No claims yet</p>
                <p className="text-slate-400 text-xs mt-2.5 leading-relaxed max-w-[80%] mx-auto">
                  When a covered disruption hits and the dual-gate passes, payouts show up here
                  automatically.
                </p>
              </div>
            ) : (
              <ul className="space-y-2">
                {claims.map((c) => (
                  <li
                    key={c.id}
                    className="rounded-2xl bg-surface/40 border border-glass-border p-4 text-sm hover:border-brand/30 transition-colors"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white text-lg">{formatRs(c.payout_amount)}</span>
                      <span
                        className={
                          c.status === "paid"
                            ? "text-emerald-700"
                            : c.status === "rejected"
                              ? "text-red-600"
                              : "text-amber-700"
                        }
                      >
                        {c.status}
                      </span>
                    </div>
                    <p className="text-slate-500 text-xs mt-1">{c.disruption_type}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="glass-card rounded-3xl p-5 mb-8">
            <h2 className="font-display font-bold text-lg text-white mb-2 tracking-tight">
              Daily earnings baseline
            </h2>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Amounts start as <strong>model-generated</strong> (zone + hours). With Razorpay{" "}
              <strong>Test mode</strong> keys, you can run a real Checkout flow and
              we <strong>add the payment to today&apos;s row</strong>. Baseline blends{" "}
              <strong>same weekday median</strong> + <strong>7-day MA</strong>.
            </p>
            {rzReady ? (
              <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50/80 px-3 py-2">
                <p className="text-xs text-emerald-900 font-medium">Razorpay Test Mode ready</p>
                <p className="text-[11px] text-emerald-800 mt-1">
                  In Checkout, use UPI with Razorpay test VPAs (e.g.{" "}
                  <span className="font-mono">success@razorpay</span> for success).
                </p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void payTestEarning()}
                  className="mt-2 w-full rounded-lg bg-emerald-700 text-white text-sm font-semibold py-2.5 disabled:opacity-50"
                >
                  Pay {formatRs(TEST_EARNING_PAISE / 100)} (test) → credit today
                </button>
              </div>
            ) : (
              <p className="text-[11px] text-slate-400 mb-3">
                Add <span className="font-mono">RAZORPAY_KEY_ID</span> and{" "}
                <span className="font-mono">RAZORPAY_KEY_SECRET</span> (Test) in{" "}
                <span className="font-mono">backend/.env</span> to enable Checkout.
              </p>
            )}
            <div className="max-h-56 overflow-y-auto space-y-2 mb-4 rounded-xl border border-glass-border bg-surface/30 p-3">
              {dailyRows.length === 0 ? (
                <p className="text-xs text-slate-400 py-3 text-center">Loading history…</p>
              ) : (
                dailyRows.map((r) => (
                  <div
                    key={r.earn_date}
                    className="flex justify-between items-center text-sm gap-2 px-2 py-1.5 border-b border-glass-border/50 last:border-0"
                  >
                    <span className="text-slate-400 font-mono text-xs shrink-0">
                      {r.earn_date}
                    </span>
                    <span className="font-bold text-white">{formatRs(r.amount)}</span>
                  </div>
                ))
              )}
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void resimulateEarnings()}
              className="text-sm font-bold text-brand hover:text-brand2 transition-colors w-full text-center pb-2"
            >
              Regenerate demo earnings
            </button>
          </section>

          <p className="text-center text-xs text-slate-400 pb-4">
            Install this app: use your browser &quot;Add to Home Screen&quot; (PWA).
          </p>
          <p className="text-center text-xs pb-6">
            <Link to="/login" className="text-brand">
              Switch account
            </Link>
          </p>
        </>
      )}
    </div>
  );
}
