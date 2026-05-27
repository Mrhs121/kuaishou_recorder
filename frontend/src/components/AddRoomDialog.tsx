import { useState } from 'react'
import { Modal, Input, Select, message } from 'antd'
import { addRoom } from '../api'
import type { RoomCreate } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  onAdded: () => void
}

export default function AddRoomDialog({ open, onClose, onAdded }: Props) {
  const [url, setUrl] = useState('')
  const [quality, setQuality] = useState('OD')
  const [loading, setLoading] = useState(false)

  const handleOk = async () => {
    if (!url.trim()) {
      message.warning('请输入直播间 URL')
      return
    }
    setLoading(true)
    try {
      const data: RoomCreate = { url: url.trim(), quality }
      await addRoom(data)
      message.success('添加成功')
      setUrl('')
      onAdded()
      onClose()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title="添加直播间"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={loading}
      destroyOnClose
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
        <Input
          placeholder="快手直播间 URL, 如 https://live.kuaishou.com/u/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onPressEnter={handleOk}
        />
        <Select
          value={quality}
          onChange={setQuality}
          options={[
            { value: 'OD', label: '原画' },
            { value: 'BD', label: '蓝光' },
            { value: 'UHD', label: '超清' },
            { value: 'HD', label: '高清' },
            { value: 'SD', label: '标清' },
            { value: 'LD', label: '流畅' },
          ]}
        />
      </div>
    </Modal>
  )
}
