import { useState, useEffect } from 'react'
import { Layout, Menu, Drawer } from 'antd'
import {
  VideoCameraOutlined,
  SettingOutlined,
  MenuOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'

const { Sider, Header, Content } = Layout

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return isMobile
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const isMobile = useIsMobile()

  const menuItems = [
    { key: '/', icon: <VideoCameraOutlined />, label: '录制管理' },
    { key: '/settings', icon: <SettingOutlined />, label: '设置' },
  ]

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
    if (isMobile) setDrawerOpen(false)
  }

  const siderMenu = (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[location.pathname]}
      items={menuItems}
      onClick={handleMenuClick}
    />
  )

  if (isMobile) {
    return (
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            padding: '0 16px',
            background: '#001529',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'sticky',
            top: 0,
            zIndex: 100,
          }}
        >
          <MenuOutlined
            style={{ fontSize: 20, color: '#fff', cursor: 'pointer' }}
            onClick={() => setDrawerOpen(true)}
          />
          <span style={{ color: '#fff', fontSize: 16, fontWeight: 600 }}>快手直播录制</span>
          <div style={{ width: 20 }} />
        </Header>
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={220}
          styles={{ body: { padding: 0, background: '#001529' } }}
          title={null}
          closable={false}
        >
          <div
            style={{
              height: 48,
              margin: '16px 16px 0',
              color: '#fff',
              fontSize: 18,
              fontWeight: 600,
              textAlign: 'center',
              lineHeight: '48px',
            }}
          >
            快手直播录制
          </div>
          {siderMenu}
        </Drawer>
        <Content style={{ margin: 12 }}>{children}</Content>
      </Layout>
    )
  }

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
        {siderMenu}
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: '#fff', display: 'flex', alignItems: 'center' }}>
          {collapsed ? (
            <VideoCameraOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => setCollapsed(false)} />
          ) : (
            <MenuOutlined style={{ fontSize: 18, cursor: 'pointer' }} onClick={() => setCollapsed(true)} />
          )}
        </Header>
        <Content style={{ margin: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  )
}
