import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-sm shadow-xl">
      <div className="text-gray-400 mb-1">Week of {fmtDate(label)}</div>
      <div className="text-white font-bold">${d.realized?.toLocaleString()}</div>
      <div className="text-green-400">{d.yield_pct?.toFixed(3)}% yield</div>
    </div>
  )
}

export default function YTDChart({ weeks = [] }) {
  if (!weeks.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
        No weekly data yet
      </div>
    )
  }

  const max = Math.max(...weeks.map(w => w.realized ?? 0))

  return (
    <ResponsiveContainer width="100%" height={220}>
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
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: '#ffffff08' }} />
        <Bar dataKey="realized" radius={[4, 4, 0, 0]}>
          {weeks.map((w, i) => (
            <Cell
              key={i}
              fill={w.realized === max ? '#3b82f6' : '#1d4ed8'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
