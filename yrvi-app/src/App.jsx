import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Calendar, History, Settings } from 'lucide-react'
import StatusBar from './components/StatusBar.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Performance from './pages/Performance.jsx'
import ThisWeek from './pages/ThisWeek.jsx'
import TradeHistory from './pages/TradeHistory.jsx'
import SettingsPage from './pages/Settings.jsx'

const NAV = [
  { path: '/',             label: 'Dashboard',     icon: LayoutDashboard, end: true },
  { path: '/performance',  label: 'Performance',   icon: TrendingUp },
  { path: '/this-week',    label: 'This Week',     icon: Calendar },
  { path: '/trade-history',label: 'Trade History', icon: History },
  { path: '/settings',     label: 'Settings',      icon: Settings },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
        {/* Sidebar */}
        <nav className="w-52 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
          <div className="px-5 py-4 border-b border-gray-800">
            <div className="text-blue-400 font-bold text-lg tracking-widest">YRVI</div>
            <div className="text-gray-600 text-xs mt-0.5">Volatility Income Fund</div>
          </div>

          <div className="flex-1 p-2 space-y-0.5 overflow-y-auto">
            {NAV.map(({ path, label, icon: Icon, end }) => (
              <NavLink
                key={path}
                to={path}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-500 hover:bg-gray-800 hover:text-gray-200'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </div>

          <div className="px-5 py-3 border-t border-gray-800 text-xs text-gray-700">
            Dashboard v1.0
          </div>
        </nav>

        {/* Main */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <StatusBar />
          <main className="flex-1 overflow-y-auto p-6">
            <Routes>
              <Route path="/"              element={<Dashboard />} />
              <Route path="/performance"   element={<Performance />} />
              <Route path="/this-week"     element={<ThisWeek />} />
              <Route path="/trade-history" element={<TradeHistory />} />
              <Route path="/settings"      element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
