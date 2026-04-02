import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import MainLayout from './components/MainLayout'

const Home = lazy(() => import('./pages/Home'))
const Market = lazy(() => import('./pages/Market'))
const Trading = lazy(() => import('./pages/Trading'))
const Strategy = lazy(() => import('./pages/Strategy'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Monitor = lazy(() => import('./pages/Monitor'))
const LiveTrading = lazy(() => import('./pages/LiveTrading'))
const DataManager = lazy(() => import('./pages/DataManager'))
const AILab = lazy(() => import('./pages/AILab'))

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="min-h-screen bg-[#0b0f1a] text-gray-300 flex items-center justify-center">Loading...</div>}>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Home />} />
            <Route path="market" element={<Market />} />
            <Route path="trading" element={<Trading />} />
            <Route path="strategy" element={<Strategy />} />
            <Route path="backtest" element={<Backtest />} />
            <Route path="live" element={<LiveTrading />} />
            <Route path="monitor" element={<Monitor />} />
            <Route path="data" element={<DataManager />} />
            <Route path="ai-lab" element={<AILab />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
