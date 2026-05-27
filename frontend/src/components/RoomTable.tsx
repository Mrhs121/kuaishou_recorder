import { useState, useEffect } from 'react'
import { Table, Tag, Button, Space, Popconfirm, message } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { RoomStatus } from '../types'
import { deleteRoom, startRoom, stopRoom } from '../api'
import AddRoomDialog from './AddRoomDialog'

const QUALITY_MAP: Record<string, string> = {
  OD: '原画',
  BD: '蓝光',
  UHD: '超清',
  HD: '高清',
  SD: '标清',
  LD: '流畅',
}

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  idle: { color: 'default', text: '空闲' },
  live: { color: 'processing', text: '直播中' },
  recording: { color: 'success', text: '录制中' },
  error: { color: 'error', text: '错误' },
  disabled: { color: 'default', text: '已禁用' },
}

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return isMobile
}

interface Props {
  rooms: RoomStatus[]
  onRefresh: () => void
}

export default function RoomTable({ rooms, onRefresh }: Props) {
  const [addOpen, setAddOpen] = useState(false)
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set())
  const isMobile = useIsMobile()

  const setLoading = (id: string, v: boolean) => {
    setLoadingIds((prev) => {
      const next = new Set(prev)
      v ? next.add(id) : next.delete(id)
      return next
    })
  }

  const handleStart = async (id: string) => {
    setLoading(id, true)
    try {
      await startRoom(id)
      onRefresh()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '启动失败')
    } finally {
      setLoading(id, false)
    }
  }

  const handleStop = async (id: string) => {
    setLoading(id, true)
    try {
      await stopRoom(id)
      onRefresh()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '停止失败')
    } finally {
      setLoading(id, false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteRoom(id)
      message.success('已删除')
      onRefresh()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  const columns = [
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: isMobile ? 72 : 100,
      fixed: isMobile ? ('left' as const) : undefined,
      render: (status: string) => {
        const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '主播',
      dataIndex: 'anchor_name',
      key: 'anchor_name',
      width: isMobile ? 100 : 180,
      render: (name: string) => name || '-',
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      responsive: ['md'] as const,
      render: (url: string) => (
        <a href={url} target="_blank" rel="noopener noreferrer">
          {url}
        </a>
      ),
    },
    {
      title: '画质',
      dataIndex: 'quality',
      key: 'quality',
      width: isMobile ? 60 : 80,
      render: (q: string) => QUALITY_MAP[q] || q,
    },
    {
      title: '录制文件',
      dataIndex: 'file_path',
      key: 'file_path',
      ellipsis: true,
      width: 250,
      responsive: ['lg'] as const,
      render: (p: string | null) => p || '-',
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      width: 200,
      responsive: ['lg'] as const,
      render: (e: string | null) => (e ? <Tag color="error">{e}</Tag> : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: isMobile ? 120 : 180,
      fixed: isMobile ? ('right' as const) : undefined,
      render: (_: unknown, record: RoomStatus) => (
        <Space size={isMobile ? 4 : 8}>
          {record.status === 'recording' || record.status === 'live' ? (
            <Button
              type="link"
              icon={<PauseCircleOutlined />}
              loading={loadingIds.has(record.id)}
              onClick={() => handleStop(record.id)}
              size={isMobile ? 'small' : 'middle'}
            >
              {isMobile ? '' : '停止'}
            </Button>
          ) : (
            <Button
              type="link"
              icon={<PlayCircleOutlined />}
              loading={loadingIds.has(record.id)}
              onClick={() => handleStart(record.id)}
              size={isMobile ? 'small' : 'middle'}
            >
              {isMobile ? '' : '启动'}
            </Button>
          )}
          <Popconfirm title="确定删除该直播间？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger icon={<DeleteOutlined />} size={isMobile ? 'small' : 'middle'}>
              {isMobile ? '' : '删除'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ margin: 0, fontSize: isMobile ? 16 : undefined }}>录制管理</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={onRefresh} size={isMobile ? 'small' : 'middle'}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)} size={isMobile ? 'small' : 'middle'}>
            添加
          </Button>
        </Space>
      </div>
      <Table
        dataSource={rooms}
        columns={columns}
        rowKey="id"
        pagination={false}
        size={isMobile ? 'small' : 'middle'}
        scroll={isMobile ? { x: 420 } : undefined}
      />
      <AddRoomDialog open={addOpen} onClose={() => setAddOpen(false)} onAdded={onRefresh} />
    </>
  )
}
