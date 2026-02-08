import { BrowserRouter, Routes, Route } from 'react-router-dom'
import MainLayout from './components/MainLayout'
import Home from './pages/Home'
import Market from './pages/Market'
import Trading from './pages/Trading'
import Strategy from './pages/Strategy'
import Backtest from './pages/Backtest'
import Monitor from './pages/Monitor'
import LiveTrading from './pages/LiveTrading'
import DataManager from './pages/DataManager'

function App() {
  return (
    <BrowserRouter>
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
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
