import { useState } from 'react'
import { Layout, Menu } from 'antd'
import {
  VideoCameraOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'

const { Sider, Header, Content } = Layout

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const menuItems = [
    { key: '/', icon: <VideoCameraOutlined />, label: '录制管理' },
    { key: '/settings', icon: <SettingOutlined />, label: '设置' },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        theme="dark"
      >
        <div
          style={{
            height: 48,
            margin: 16,
            color: '#fff',
            fontSize: collapsed ? 14 : 18,
            fontWeight: 600,
            textAlign: 'center',
            lineHeight: '48px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          {collapsed ? '录制' : '快手直播录制'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: '#fff', display: 'flex', alignItems: 'center' }}>
          {collapsed ? (
            <MenuUnfoldOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => setCollapsed(false)} />
          ) : (
            <MenuFoldOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => setCollapsed(true)} />
          )}
        </Header>
        <Content style={{ margin: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  )
}
