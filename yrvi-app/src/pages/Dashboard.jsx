import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { Clock, DollarSign, TrendingUp, RefreshCw } from 'lucide-react'
import PositionCard from '../components/PositionCard.jsx'
import YTDChart from '../components/YTDChart.jsx'

function useCountdown(isoStr) {
  const [label, setLabel] = useState('')
  useEffect(() => {
    if (!isoStr) return
    const update = () => {
      const diff = new Date(isoStr) - Date.now()
      if (diff <= 0) { setLabel('Executing now!'); return }
      const d = Math.floor(diff / 86400000)
      const h = Math.floor((diff % 86400000) / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setLabel(d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m ${s}s`)
    }
    update()
    const t = setInterval(update, 1000)
    return () => clearInterval(t)
  }, [isoStr])
  return label
}

function StatCard({ label, value, sub, accent = 'text-white' }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="text-gray-500 text-xs mb-2">{label}</div>
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      {sub && <div className="text-gray-600 text-xs mt-1">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [positions, setPositions]   = useState(null)
  const [status, setStatus]         = useState(null)
  const [performance, setPerformance] = useState(null)
  const [loading, setLoading]       = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const [pos, stat, perf] = await Promise.all([
        axios.get('/api/positions'),
        axios.get('/api/status'),
        axios.get('/api/performance'),
      ])
      setPositions(pos.data)
      setStatus(stat.data)
      setPerformance(perf.data)
      setLastRefresh(new Date())
    } catch (err) {
      console.error('[Dashboard] fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 30000)
    return () => clearInterval(t)
  }, [fetchAll])

  const countdown = useCountdown(status?.next_execution)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    )
  }

  const pnl         = positions?.weekly_pnl ?? {}
  const ytdTotal    = performance?.total_premium ?? 0
  const ytdTarget   = performance?.annual_target ?? 100_000
  const progressPct = Math.min(100, (ytdTotal / ytdTarget) * 100)

  const runDate = positions?.run_date
    ? new Date(positions.run_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
    : null

  const openPositions = (positions?.positions ?? []).filter(
    p => ['filled', 'dry_run', 'partial_fill'].includes(p.status)
  )
  const failedPositions = (positions?.positions ?? []).filter(
    p => !['filled', 'dry_run', 'partial_fill'].includes(p.status)
  )

  return (
    <div className="space-y-6">
      {/* Header row: countdown + refresh */}
      <div className="flex items-start gap-4">
        <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-gray-500 text-sm mb-1">Next Execution</div>
              <div className="text-4xl font-bold text-white font-mono tracking-tight">{countdown}</div>
              <div className="text-gray-600 text-sm mt-1.5">Monday 10:00 AM PST</div>
            </div>
            <Clock size={52} className="text-blue-600/30" />
          </div>
        </div>

        <button
          onClick={fetchAll}
          title="Refresh"
          className="mt-2 p-3 bg-gray-900 border border-gray-800 rounded-xl text-gray-500 hover:text-white hover:border-gray-700 transition-colors"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* This week P&L */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="CSP Premium"
          value={`$${(pnl.csp_premium ?? 0).toLocaleString()}`}
          accent="text-green-400"
        />
        <StatCard
          label="CC Premium"
          value={`$${(pnl.cc_premium ?? 0).toLocaleString()}`}
          accent="text-blue-400"
        />
        <StatCard
          label="Total Realized"
          value={`$${(pnl.total_realized ?? 0).toLocaleString()}`}
          accent="text-white"
        />
        <StatCard
          label="YTD Premium"
          value={`$${ytdTotal.toLocaleString()}`}
          sub={`${progressPct.toFixed(1)}% of $${ytdTarget.toLocaleString()} goal`}
          accent="text-white"
        />
      </div>

      {/* YTD progress bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="text-white font-semibold text-sm">Annual Goal Progress</div>
          <div className="text-gray-500 text-xs">
            ${ytdTotal.toLocaleString()} / ${ytdTarget.toLocaleString()}
          </div>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2.5">
          <div
            className="bg-gradient-to-r from-blue-600 to-green-500 h-2.5 rounded-full transition-all duration-700"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-600">
          <span>{progressPct.toFixed(1)}%</span>
          <span>${(ytdTarget - ytdTotal).toLocaleString()} to go</span>
        </div>
      </div>

      {/* YTD chart */}
      {(performance?.weeks?.length ?? 0) > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-white font-semibold text-sm mb-4">Weekly Premium</div>
          <YTDChart weeks={performance.weeks} />
        </div>
      )}

      {/* Open positions */}
      {openPositions.length > 0 && (
        <div>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-white font-semibold">Open Positions</h2>
            {runDate && <span className="text-gray-600 text-xs">week of {runDate}</span>}
            <span className="text-xs bg-gray-800 text-gray-400 border border-gray-700 px-2 py-0.5 rounded-full">
              {openPositions.length}
            </span>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {openPositions.map(p => <PositionCard key={p.ticker} position={p} />)}
          </div>
        </div>
      )}

      {/* Failed/skipped */}
      {failedPositions.length > 0 && (
        <div>
          <h2 className="text-gray-500 font-semibold text-sm mb-3">Failed / Skipped</h2>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {failedPositions.map(p => <PositionCard key={p.ticker} position={p} />)}
          </div>
        </div>
      )}

      {/* Wheel holdings */}
      {(positions?.wheel_holdings?.length ?? 0) > 0 && (
        <div>
          <h2 className="text-white font-semibold mb-3">Wheel Holdings</h2>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {positions.wheel_holdings.map(h => (
              <div key={h.ticker} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <div className="text-xl font-bold text-white">{h.ticker}</div>
                    <div className="text-gray-500 text-sm">
                      {h.shares} shares assigned @ ${h.assigned_strike}
                    </div>
                  </div>
                  <span className={`text-xs px-2.5 py-1 rounded-full border font-medium capitalize ${
                    h.cc_status === 'open'
                      ? 'bg-green-900/40 text-green-400 border-green-800'
                      : h.cc_status === 'pending'
                      ? 'bg-yellow-900/40 text-yellow-400 border-yellow-800'
                      : 'bg-gray-800 text-gray-400 border-gray-700'
                  }`}>
                    CC: {h.cc_status ?? '—'}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  {[
                    { label: 'CC Strike', value: h.current_cc_strike ? `$${h.current_cc_strike}` : '—' },
                    { label: 'CC Premium', value: `$${(h.current_cc_premium ?? 0).toLocaleString()}`, accent: 'text-green-400' },
                    { label: 'Expiry', value: h.current_cc_expiry ?? '—' },
                    { label: 'Week #', value: h.weeks_held ?? 1 },
                    { label: 'Stop Loss', value: h.assigned_strike ? `$${(h.assigned_strike * 0.9).toFixed(2)}` : '—', accent: 'text-red-400' },
                    { label: 'Last Check', value: h.last_checked ? new Date(h.last_checked).toLocaleDateString() : '—' },
                  ].map(({ label, value, accent = 'text-white' }) => (
                    <div key={label}>
                      <div className="text-gray-600 text-xs mb-0.5">{label}</div>
                      <div className={`font-semibold ${accent}`}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!positions?.positions?.length && !positions?.wheel_holdings?.length && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-16 text-center">
          <DollarSign size={40} className="text-gray-700 mx-auto mb-3" />
          <div className="text-gray-500 text-lg">No open positions this week</div>
          <div className="text-gray-700 text-sm mt-1">Positions appear after Monday 10AM execution</div>
        </div>
      )}

      {lastRefresh && (
        <div className="text-gray-700 text-xs text-right">
          Last updated {lastRefresh.toLocaleTimeString()} · auto-refreshes every 30s
        </div>
      )}
    </div>
  )
}
