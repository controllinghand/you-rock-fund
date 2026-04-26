import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine
} from 'recharts'
import { TrendingUp, Award, AlertTriangle, Target } from 'lucide-react'

function fmtDate(s) {
  if (!s) return ''
  return new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-sm shadow-xl">
      <div className="text-gray-400 mb-1">Week of {fmtDate(d.week_start)}</div>
      <div className="text-white font-bold text-base">${d.realized?.toLocaleString()}</div>
      <div className="text-green-400">{d.yield_pct?.toFixed(3)}% yield</div>
    </div>
  )
}

function StatCard({ label, value, sub, icon: Icon, accent = 'text-white' }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-gray-500 text-xs">{label}</div>
        {Icon && <Icon size={16} className="text-gray-700" />}
      </div>
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      {sub && <div className="text-gray-600 text-xs mt-1">{sub}</div>}
    </div>
  )
}

export default function Performance() {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    axios.get('/api/performance')
      .then(r => setData(r.data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
    </div>
  )
  if (error) return (
    <div className="bg-red-900/20 border border-red-800 rounded-xl p-6 text-red-400">{error}</div>
  )

  const {
    weeks = [], total_premium = 0, weeks_traded = 0,
    avg_yield_pct = 0, best_week, worst_week,
    annual_target = 100_000, progress_pct = 0
  } = data ?? {}

  const maxRealized = weeks.length ? Math.max(...weeks.map(w => w.realized ?? 0)) : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white mb-1">Performance</h1>
        <div className="text-gray-500 text-sm">Year-to-date results</div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Premium"
          value={`$${total_premium.toLocaleString()}`}
          icon={TrendingUp}
          accent="text-green-400"
        />
        <StatCard
          label="Weeks Traded"
          value={weeks_traded}
          sub="weeks executed"
          icon={Target}
        />
        <StatCard
          label="Avg Weekly Yield"
          value={`${avg_yield_pct.toFixed(2)}%`}
          sub="of fund budget"
          icon={TrendingUp}
          accent={avg_yield_pct >= 1 ? 'text-green-400' : avg_yield_pct >= 0.5 ? 'text-yellow-400' : 'text-red-400'}
        />
        <StatCard
          label="Annual Goal"
          value={`${progress_pct.toFixed(1)}%`}
          sub={`$${total_premium.toLocaleString()} of $${annual_target.toLocaleString()}`}
          icon={Target}
          accent="text-blue-400"
        />
      </div>

      {/* Best / worst */}
      <div className="grid grid-cols-2 gap-4">
        {best_week && (
          <div className="bg-green-900/10 border border-green-800/40 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <Award size={16} className="text-green-400" />
              <span className="text-green-400 text-xs font-medium">Best Week</span>
            </div>
            <div className="text-2xl font-bold text-white">${best_week.realized?.toLocaleString()}</div>
            <div className="text-gray-500 text-sm mt-1">
              {fmtDate(best_week.week_start)} · {best_week.yield_pct?.toFixed(2)}% yield
            </div>
          </div>
        )}
        {worst_week && best_week?.week_start !== worst_week?.week_start && (
          <div className="bg-red-900/10 border border-red-800/40 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={16} className="text-red-400" />
              <span className="text-red-400 text-xs font-medium">Worst Week</span>
            </div>
            <div className="text-2xl font-bold text-white">${worst_week.realized?.toLocaleString()}</div>
            <div className="text-gray-500 text-sm mt-1">
              {fmtDate(worst_week.week_start)} · {worst_week.yield_pct?.toFixed(2)}% yield
            </div>
          </div>
        )}
      </div>

      {/* Annual progress bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="text-white font-semibold text-sm">Annual Goal: $100,000</div>
          <div className="text-gray-500 text-xs">{progress_pct.toFixed(1)}% complete</div>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-3">
          <div
            className="bg-gradient-to-r from-blue-600 to-green-500 h-3 rounded-full transition-all duration-700"
            style={{ width: `${progress_pct}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-600">
          <span>${total_premium.toLocaleString()} earned</span>
          <span>${(annual_target - total_premium).toLocaleString()} remaining</span>
        </div>
      </div>

      {/* Bar chart */}
      {weeks.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-white font-semibold text-sm mb-5">Weekly Premium by Week</div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={weeks} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="week_start"
                tickFormatter={fmtDate}
                stroke="#374151"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                stroke="#374151"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickFormatter={v => `$${(v / 1000).toFixed(1)}k`}
                axisLine={false}
                tickLine={false}
                width={50}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: '#ffffff06' }} />
              <Bar dataKey="realized" radius={[4, 4, 0, 0]}>
                {weeks.map((w, i) => (
                  <Cell
                    key={i}
                    fill={w.realized === maxRealized ? '#10b981' : '#2563eb'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Weekly table */}
      {weeks.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800">
            <div className="text-white font-semibold text-sm">Weekly Breakdown</div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-800">
                <th className="text-left px-5 py-3">Week Of</th>
                <th className="text-right px-5 py-3">Realized</th>
                <th className="text-right px-5 py-3">Yield</th>
              </tr>
            </thead>
            <tbody>
              {[...weeks].reverse().map((w, i) => (
                <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="px-5 py-3 text-gray-300">{fmtDate(w.week_start)}</td>
                  <td className="px-5 py-3 text-right font-medium text-green-400">
                    ${w.realized?.toLocaleString()}
                  </td>
                  <td className={`px-5 py-3 text-right font-medium ${
                    (w.yield_pct ?? 0) >= 1 ? 'text-green-400'
                    : (w.yield_pct ?? 0) >= 0.5 ? 'text-yellow-400'
                    : 'text-red-400'
                  }`}>
                    {w.yield_pct?.toFixed(3)}%
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-gray-700">
                <td className="px-5 py-3 text-gray-400 font-medium">Total</td>
                <td className="px-5 py-3 text-right font-bold text-white">
                  ${total_premium.toLocaleString()}
                </td>
                <td className="px-5 py-3 text-right font-medium text-gray-400">
                  {avg_yield_pct.toFixed(3)}% avg
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {weeks.length === 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <div className="text-gray-600">No weekly data yet — data populates after first execution</div>
        </div>
      )}
    </div>
  )
}
