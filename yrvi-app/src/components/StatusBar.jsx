import { useEffect, useState } from 'react'
import axios from 'axios'

function Indicator({ ok, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-500'}`} />
      <span className={`text-xs ${ok ? 'text-gray-300' : 'text-red-400'}`}>{label}</span>
    </div>
  )
}

function fmt(n) {
  if (n == null) return '—'
  return '$' + Math.round(n).toLocaleString()
}

export default function StatusBar() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    const fetch = () => axios.get('/api/status').then(r => setStatus(r.data)).catch(() => {})
    fetch()
    const t = setInterval(fetch, 30000)
    return () => clearInterval(t)
  }, [])

  const isLive = status?.trading_mode === 'live'

  return (
    <div className="h-12 bg-gray-900 border-b border-gray-800 flex items-center px-6 gap-6 shrink-0">
      {/* Status indicators */}
      <div className="flex items-center gap-4">
        <Indicator ok={status?.gateway_running} label="Gateway" />
        <Indicator ok={status?.scheduler_pid != null} label="Scheduler" />
        <Indicator ok={status?.ibkr_connected} label="IBKR" />
      </div>

      <div className="w-px h-5 bg-gray-800" />

      {/* Account info */}
      <div className="flex items-center gap-4 text-xs">
        <span className="text-gray-500">Account</span>
        <span className="text-white font-medium font-mono">{fmt(status?.account_value)}</span>
        <span className="text-gray-500">Buying Power</span>
        <span className="text-white font-medium font-mono">{fmt(status?.buying_power)}</span>
      </div>

      <div className="flex-1" />

      {/* Mode badge */}
      <span className={`text-xs font-bold px-3 py-1 rounded-full border ${
        isLive
          ? 'bg-red-900/50 text-red-400 border-red-700 animate-pulse'
          : 'bg-blue-900/40 text-blue-400 border-blue-800'
      }`}>
        {isLive ? '🔴 LIVE' : '📄 PAPER'}
      </span>

      {status?.account && (
        <span className="text-xs text-gray-600">{status.account}</span>
      )}
    </div>
  )
}
