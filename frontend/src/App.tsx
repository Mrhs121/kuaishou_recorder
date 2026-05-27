import { HashRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
import HomePage from './pages/HomePage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <HashRouter>
        <AppLayout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </AppLayout>
      </HashRouter>
    </ConfigProvider>
  )
}
