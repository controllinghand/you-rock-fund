import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { Save, AlertTriangle, CheckCircle, Bell, Send } from 'lucide-react'

function SliderRow({ label, value, min, max, step = 1, format = v => v, onChange }) {
  return (
    <div className="flex items-center gap-4">
      <div className="w-40 shrink-0">
        <div className="text-gray-300 text-sm">{label}</div>
        <div className="text-blue-400 font-medium text-sm">{format(value)}</div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1 accent-blue-500 h-1.5"
      />
      <div className="flex gap-1 text-xs text-gray-600 w-28 shrink-0 justify-end">
        <span>{format(min)}</span>
        <span>–</span>
        <span>{format(max)}</span>
      </div>
    </div>
  )
}

function Section({ title, emoji, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
      <div className="text-white font-semibold text-sm flex items-center gap-2">
        <span>{emoji}</span>
        {title}
      </div>
      {children}
    </div>
  )
}

function Toggle({ label, sub, checked, onChange }) {
  return (
    <label className="flex items-center justify-between cursor-pointer select-none">
      <div>
        <div className="text-gray-300 text-sm">{label}</div>
        {sub && <div className="text-gray-600 text-xs mt-0.5">{sub}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
          checked ? 'bg-blue-600' : 'bg-gray-700'
        }`}
      >
        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-4' : 'translate-x-1'
        }`} />
      </button>
    </label>
  )
}

export default function SettingsPage() {
  const [settings, setSettings]   = useState(null)
  const [original, setOriginal]   = useState(null)
  const [saving, setSaving]       = useState(false)
  const [testing, setTesting]     = useState(false)
  const [msg, setMsg]             = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [confirm, setConfirm]     = useState('')
  const [switching, setSwitching] = useState(false)

  useEffect(() => {
    axios.get('/api/settings').then(r => {
      setSettings(r.data)
      setOriginal(r.data)
    })
  }, [])

  const set = useCallback((key, val) => {
    setSettings(prev => ({ ...prev, [key]: val }))
  }, [])

  const showMsg = (type, text) => {
    setMsg({ type, text })
    setTimeout(() => setMsg(null), 4000)
  }

  const save = async () => {
    setSaving(true)
    try {
      const res = await axios.post('/api/settings', settings)
      setSettings(res.data)
      setOriginal(res.data)
      showMsg('success', 'Settings saved')
    } catch (err) {
      showMsg('error', err.response?.data?.detail ?? err.message)
    } finally {
      setSaving(false)
    }
  }

  const testDiscord = async () => {
    setTesting(true)
    try {
      await axios.post('/api/discord-test')
      showMsg('success', 'Test notification sent to Discord')
    } catch (err) {
      showMsg('error', err.response?.data?.detail ?? err.message)
    } finally {
      setTesting(false)
    }
  }

  const switchMode = async () => {
    if (confirm !== 'CONFIRM') return
    const target = settings.trading_mode === 'live' ? 'paper' : 'live'
    setSwitching(true)
    try {
      await axios.post('/api/trading-mode', { mode: target, confirmation: 'CONFIRM' })
      setSettings(prev => ({ ...prev, trading_mode: target, ibkr_port: target === 'live' ? 4001 : 4002 }))
      setOriginal(prev => ({ ...prev, trading_mode: target }))
      setShowModal(false)
      setConfirm('')
      showMsg('success', `Switched to ${target.toUpperCase()} mode`)
    } catch (err) {
      showMsg('error', err.response?.data?.detail ?? err.message)
    } finally {
      setSwitching(false)
    }
  }

  const isDirty = JSON.stringify(settings) !== JSON.stringify(original)

  if (!settings) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
    </div>
  )

  const isLive = settings.trading_mode === 'live'

  return (
    <div className="max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Settings</h1>
          <div className="text-gray-500 text-sm">Hot-reloads on every API call — no restart needed</div>
        </div>
        <button
          onClick={save}
          disabled={saving || !isDirty}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Save size={14} />
          {saving ? 'Saving...' : isDirty ? 'Save Changes' : 'Saved'}
        </button>
      </div>

      {/* Toast message */}
      {msg && (
        <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
          msg.type === 'success'
            ? 'bg-green-900/30 border border-green-800 text-green-400'
            : 'bg-red-900/30 border border-red-800 text-red-400'
        }`}>
          {msg.type === 'success' ? <CheckCircle size={15} /> : <AlertTriangle size={15} />}
          {msg.text}
        </div>
      )}

      {/* Fund Settings */}
      <Section title="Fund Settings" emoji="💰">
        <SliderRow
          label="Fund Budget"
          value={settings.fund_budget}
          min={10000}
          max={2000000}
          step={10000}
          format={v => `$${v.toLocaleString()}`}
          onChange={v => set('fund_budget', v)}
        />
        <SliderRow
          label="# Positions"
          value={settings.num_positions}
          min={1}
          max={10}
          format={v => `${v} positions`}
          onChange={v => set('num_positions', v)}
        />
        <SliderRow
          label="Min Position"
          value={settings.min_position_size}
          min={5000}
          max={100000}
          step={5000}
          format={v => `$${v.toLocaleString()}`}
          onChange={v => set('min_position_size', v)}
        />
        <SliderRow
          label="Max Position"
          value={settings.max_position_size}
          min={10000}
          max={200000}
          step={5000}
          format={v => `$${v.toLocaleString()}`}
          onChange={v => set('max_position_size', v)}
        />
      </Section>

      {/* Screener Filters */}
      <Section title="Screener Filters" emoji="📐">
        <SliderRow
          label="Max Delta"
          value={settings.max_delta}
          min={0.10}
          max={0.30}
          step={0.01}
          format={v => v.toFixed(2)}
          onChange={v => set('max_delta', v)}
        />
        <SliderRow
          label="Min Buffer %"
          value={settings.min_buffer_pct}
          min={0.03}
          max={0.20}
          step={0.01}
          format={v => `${(v * 100).toFixed(0)}%`}
          onChange={v => set('min_buffer_pct', v)}
        />
        <SliderRow
          label="Earnings Filter"
          value={settings.earnings_filter_days}
          min={0}
          max={30}
          format={v => `${v} days`}
          onChange={v => set('earnings_filter_days', v)}
        />
      </Section>

      {/* Execution */}
      <Section title="Execution" emoji="⚙️">
        <Toggle
          label="Dry Run"
          sub="Simulate orders — no real trades placed"
          checked={settings.dry_run}
          onChange={v => set('dry_run', v)}
        />
      </Section>

      {/* Trading Mode — prominent */}
      <div className={`border-2 rounded-xl p-5 space-y-4 ${
        isLive ? 'border-red-700 bg-red-900/10' : 'border-gray-700 bg-gray-900'
      }`}>
        <div className="text-white font-semibold text-sm flex items-center gap-2">
          <span>🔄</span> Trading Mode
        </div>

        <div className="flex items-center justify-between">
          <div>
            <div className="text-gray-400 text-sm mb-1">Current mode</div>
            <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold border ${
              isLive
                ? 'bg-red-900/50 text-red-400 border-red-700'
                : 'bg-blue-900/40 text-blue-400 border-blue-800'
            }`}>
              {isLive ? '🔴 LIVE TRADING' : '📄 PAPER TRADING'}
            </span>
            <div className="text-gray-600 text-xs mt-2">
              IBKR port: {settings.ibkr_port} ({isLive ? '4001 = live' : '4002 = paper'})
            </div>
          </div>
          <button
            onClick={() => { setShowModal(true); setConfirm('') }}
            className={`px-4 py-2 text-sm font-medium rounded-lg border transition-colors ${
              isLive
                ? 'border-blue-700 text-blue-400 hover:bg-blue-900/30'
                : 'border-red-700 text-red-400 hover:bg-red-900/30'
            }`}
          >
            Switch to {isLive ? 'Paper' : 'Live'}
          </button>
        </div>

        {isLive && (
          <div className="flex items-center gap-2 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            <AlertTriangle size={14} className="text-red-400 shrink-0" />
            <span className="text-red-400 text-xs">
              Live mode active — all trades use real money
            </span>
          </div>
        )}
      </div>

      {/* Notifications */}
      <Section title="Notifications" emoji="🔔">
        <Toggle
          label="Discord Webhook"
          sub="Post trade results and alerts to Discord"
          checked={settings.discord_webhook_enabled}
          onChange={v => set('discord_webhook_enabled', v)}
        />
        <button
          onClick={testDiscord}
          disabled={testing}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-600 px-3 py-2 rounded-lg transition-colors w-full"
        >
          <Send size={13} />
          {testing ? 'Sending...' : 'Send test notification'}
        </button>
      </Section>

      {/* Trading Mode Modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={e => e.target === e.currentTarget && setShowModal(false)}
        >
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle size={22} className={isLive ? 'text-yellow-400' : 'text-red-400'} />
              <h3 className="text-lg font-bold text-white">
                Switch to {isLive ? 'Paper' : 'Live'} Trading
              </h3>
            </div>

            {!isLive && (
              <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-5">
                <div className="text-red-400 font-medium text-sm mb-1">⚠️ WARNING</div>
                <div className="text-red-300 text-sm">
                  This will switch to IBKR port 4001 (live gateway). All subsequent trades
                  will execute with <strong>REAL MONEY</strong>. Ensure IB Gateway is running
                  in live mode before confirming.
                </div>
              </div>
            )}

            {isLive && (
              <p className="text-gray-300 text-sm mb-5">
                This will switch back to IBKR port 4002 (paper gateway). No real trades will be placed.
              </p>
            )}

            <div className="mb-5">
              <label className="text-gray-400 text-sm block mb-2">
                Type <code className="text-yellow-400 bg-gray-800 px-1 py-0.5 rounded">CONFIRM</code> to proceed:
              </label>
              <input
                autoFocus
                type="text"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && confirm === 'CONFIRM' && switchMode()}
                placeholder="CONFIRM"
                className="w-full bg-gray-800 border border-gray-700 text-white px-3 py-2.5 rounded-lg text-sm focus:outline-none focus:border-blue-600"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => { setShowModal(false); setConfirm('') }}
                className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={switchMode}
                disabled={confirm !== 'CONFIRM' || switching}
                className={`flex-1 px-4 py-2 text-white rounded-lg text-sm font-bold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  isLive
                    ? 'bg-blue-600 hover:bg-blue-500'
                    : 'bg-red-600 hover:bg-red-500'
                }`}
              >
                {switching ? 'Switching...' : `Switch to ${isLive ? 'Paper' : 'Live'}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
