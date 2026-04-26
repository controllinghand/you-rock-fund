import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { RefreshCw, Clock, TrendingUp, AlertCircle } from 'lucide-react'

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

function fmtDate(s) {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
  } catch { return s }
}

export default function ThisWeek() {
  const [screener, setScreener] = useState(null)
  const [status, setStatus]     = useState(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const [runAt, setRunAt]       = useState(null)

  useEffect(() => {
    axios.get('/api/status').then(r => setStatus(r.data)).catch(() => {})
  }, [])

  const countdown = useCountdown(status?.next_execution)

  const runScreener = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.get('/api/screener', { timeout: 60000 })
      setScreener(res.data)
      setRunAt(new Date())
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const positions = screener?.positions ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white mb-1">This Week</h1>
        <div className="text-gray-500 text-sm">Preview next Monday's targets</div>
      </div>

      {/* Next execution */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-gray-500 text-sm mb-1">Next Execution</div>
            <div className="text-3xl font-bold text-white font-mono">{countdown || '—'}</div>
            <div className="text-gray-600 text-sm mt-1">Monday 10:00 AM PST</div>
          </div>
          <div className="flex flex-col items-end gap-3">
            <Clock size={40} className="text-blue-600/30" />
            <button
              onClick={runScreener}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 disabled:cursor-wait text-white text-sm font-medium rounded-lg transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Running...' : 'Run Screener'}
            </button>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4" />
          <div className="text-gray-400">Running screener + position sizer...</div>
          <div className="text-gray-600 text-sm mt-1">This takes ~10 seconds</div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 flex gap-3">
          <AlertCircle size={18} className="text-red-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-red-400 font-medium text-sm">Screener error</div>
            <div className="text-red-400/70 text-sm mt-1">{error}</div>
          </div>
        </div>
      )}

      {/* Results */}
      {screener && !loading && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Positions',       value: positions.length },
              { label: 'Total Premium',   value: `$${(screener.total_premium ?? 0).toLocaleString()}`, accent: 'text-green-400' },
              { label: 'Blended Yield',   value: `${(screener.blended_yield ?? 0).toFixed(2)}%`, accent: 'text-blue-400' },
            ].map(({ label, value, accent = 'text-white' }) => (
              <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <div className="text-gray-500 text-xs mb-2">{label}</div>
                <div className={`text-2xl font-bold ${accent}`}>{value}</div>
              </div>
            ))}
          </div>

          {/* Targets table */}
          {positions.length > 0 ? (
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
                <div className="text-white font-semibold text-sm">Top {positions.length} Targets</div>
                <div className="text-gray-600 text-xs">Budget: ${(screener.budget ?? 0).toLocaleString()}</div>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs border-b border-gray-800">
                    {['#', 'Ticker', 'Strike', 'Contracts', 'Capital', 'Premium', 'Yield', 'Buffer', 'Delta', 'Expiry'].map(h => (
                      <th key={h} className={`${h === '#' || h === 'Ticker' ? 'text-left' : 'text-right'} px-4 py-3`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => {
                    const bufPct = p.buffer_pct ?? 0
                    return (
                      <tr key={p.ticker} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                        <td className="px-4 py-3 text-gray-600 text-xs">{i + 1}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="text-white font-semibold">{p.ticker}</span>
                            {p.buyzone && (
                              <span className="text-xs text-blue-400 border border-blue-800 bg-blue-900/30 px-1.5 py-0.5 rounded">bz</span>
                            )}
                          </div>
                          <div className="text-gray-600 text-xs">{p.sector}</div>
                        </td>
                        <td className="px-4 py-3 text-right text-white">${p.strike}</td>
                        <td className="px-4 py-3 text-right text-white">{p.contracts}</td>
                        <td className="px-4 py-3 text-right text-gray-300">${(p.capital_used ?? 0).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-green-400 font-medium">${(p.premium_total ?? 0).toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-green-400">{(p.yield_pct ?? 0).toFixed(2)}%</td>
                        <td className={`px-4 py-3 text-right font-medium ${
                          bufPct >= 10 ? 'text-green-400' : bufPct >= 5 ? 'text-yellow-400' : 'text-red-400'
                        }`}>
                          {bufPct.toFixed(1)}%
                        </td>
                        <td className="px-4 py-3 text-right text-gray-400">{p.delta?.toFixed(3)}</td>
                        <td className="px-4 py-3 text-right text-gray-400 text-xs">{fmtDate(p.expiry)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-10 text-center">
              <TrendingUp size={32} className="text-gray-700 mx-auto mb-3" />
              <div className="text-gray-500">No positions sized — screener returned 0 qualified targets</div>
            </div>
          )}

          {runAt && (
            <div className="text-gray-700 text-xs text-right">
              Screener run at {runAt.toLocaleTimeString()}
            </div>
          )}
        </>
      )}

      {/* Idle state */}
      {!screener && !loading && !error && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <TrendingUp size={40} className="text-gray-700 mx-auto mb-4" />
          <div className="text-gray-500 text-lg mb-2">No screener results</div>
          <div className="text-gray-600 text-sm mb-6">
            Click "Run Screener" to fetch and size this week's targets
          </div>
          <button
            onClick={runScreener}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Run Screener Now
          </button>
        </div>
      )}
    </div>
  )
}
