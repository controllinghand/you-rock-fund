import { useEffect, useState, useRef } from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'
import axios from 'axios'
import { useThemeContext } from '../ThemeProvider.jsx'

function Indicator({ ok, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-500'}`} />
      <span className={`text-xs ${ok ? 'text-gray-700 dark:text-gray-300' : 'text-red-400'}`}>{label}</span>
    </div>
  )
}

function fmt(n) {
  if (n == null) return '—'
  return '$' + Math.round(n).toLocaleString()
}

const THEME_CYCLE = { dark: 'light', light: 'system', system: 'dark' }
const THEME_ICONS = {
  dark:   <Moon size={14} />,
  light:  <Sun size={14} />,
  system: <Monitor size={14} />,
}

export default function StatusBar() {
  const [status, setStatus] = useState(null)
  const [pidFlash, setPidFlash] = useState(false)
  const prevPid = useRef(null)
  const { theme, setTheme } = useThemeContext()

  useEffect(() => {
    const fetch = () => axios.get('/api/status').then(r => {
      setStatus(r.data)
      const newPid = r.data?.scheduler_pid
      if (prevPid.current != null && newPid != null && newPid !== prevPid.current) {
        setPidFlash(true)
        setTimeout(() => setPidFlash(false), 2000)
      }
      prevPid.current = newPid
    }).catch(() => {})
    fetch()
    const t = setInterval(fetch, 30000)
    return () => clearInterval(t)
  }, [])

  const isLive = status?.trading_mode === 'live'

  return (
    <div className="h-12 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center px-6 gap-6 shrink-0">
      {/* Status indicators */}
      <div className="flex items-center gap-4">
        <Indicator ok={status?.gateway_running} label="Gateway" />
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full transition-colors duration-500 ${
            pidFlash ? 'bg-green-300 shadow-[0_0_6px_2px_rgba(74,222,128,0.6)]' :
            status?.scheduler_pid != null ? 'bg-green-400' : 'bg-red-500'
          }`} />
          <span className={`text-xs transition-colors duration-500 ${
            pidFlash ? 'text-green-400 font-semibold' :
            status?.scheduler_pid != null ? 'text-gray-700 dark:text-gray-300' : 'text-red-400'
          }`}>Scheduler</span>
        </div>
        <Indicator ok={status?.ibkr_connected} label="IBKR" />
      </div>

      <div className="w-px h-5 bg-gray-200 dark:bg-gray-800" />

      {/* Account info */}
      <div className="flex items-center gap-4 text-xs">
        <span className="text-gray-500">Account</span>
        <span className="text-gray-900 dark:text-white font-medium font-mono">{fmt(status?.account_value)}</span>
        {status?.unrealized_pnl != null && (
          <>
            <span className="text-gray-500">Unrealized</span>
            <span className={`font-medium font-mono ${status.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {status.unrealized_pnl >= 0 ? '+' : '−'}${Math.round(Math.abs(status.unrealized_pnl)).toLocaleString()}
            </span>
          </>
        )}
        <span className="text-gray-500">Buying Power</span>
        <span className="text-gray-900 dark:text-white font-medium font-mono">{fmt(status?.buying_power)}</span>
        {(status?.wheel_count ?? 0) > 0 && (
          <span className="text-yellow-400 font-medium">🔄 {status.wheel_count} wheel{status.wheel_count !== 1 ? 's' : ''}</span>
        )}
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
        <span className="text-xs text-gray-500 dark:text-gray-600">{status.account}</span>
      )}

      {/* Theme toggle */}
      <button
        onClick={() => setTheme(THEME_CYCLE[theme])}
        title={`Theme: ${theme} (click to cycle)`}
        className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        {THEME_ICONS[theme]}
      </button>
    </div>
  )
}
