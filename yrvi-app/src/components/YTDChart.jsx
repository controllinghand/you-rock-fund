import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import { useThemeContext } from '../ThemeProvider.jsx'

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function YTDChart({ weeks = [] }) {
  const { isDark } = useThemeContext()

  const gridColor   = isDark ? '#1f2937' : '#e5e7eb'
  const axisStroke  = isDark ? '#374151' : '#d1d5db'
  const tickColor   = isDark ? '#6b7280' : '#9ca3af'
  const tooltipBg   = isDark ? '#1f2937' : '#ffffff'
  const tooltipBdr  = isDark ? '#374151' : '#e5e7eb'
  const tooltipText = isDark ? '#ffffff'  : '#111827'
  const tooltipSub  = isDark ? '#9ca3af' : '#6b7280'

  if (!weeks.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
        No weekly data yet
      </div>
    )
  }

  const max = Math.max(...weeks.map(w => w.realized ?? 0))

  function CustomTooltip({ active, payload, label }) {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    return (
      <div style={{ background: tooltipBg, border: `1px solid ${tooltipBdr}` }}
        className="rounded-lg p-3 text-sm shadow-xl">
        <div style={{ color: tooltipSub }} className="mb-1">Week of {fmtDate(label)}</div>
        <div style={{ color: tooltipText }} className="font-bold">${d.realized?.toLocaleString()}</div>
        <div className="text-green-400">{d.yield_pct?.toFixed(3)}% yield</div>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={weeks} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
        <XAxis
          dataKey="week_start"
          tickFormatter={fmtDate}
          stroke={axisStroke}
          tick={{ fill: tickColor, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          stroke={axisStroke}
          tick={{ fill: tickColor, fontSize: 11 }}
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: isDark ? '#ffffff08' : '#00000006' }} />
        <Bar dataKey="realized" radius={[4, 4, 0, 0]}>
          {weeks.map((w, i) => (
            <Cell key={i} fill={w.realized === max ? '#3b82f6' : '#1d4ed8'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
