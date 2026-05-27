import { useEffect, useState } from 'react'
import { Form, Input, Select, InputNumber, Button, message, Card } from 'antd'
import { getSettings, updateSettings } from '../api'
import type { Settings } from '../types'

const { TextArea } = Input

export default function SettingsForm() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    getSettings()
      .then((s) => form.setFieldsValue(s))
      .catch((e) => message.error('加载设置失败: ' + e.message))
      .finally(() => setFetching(false))
  }, [form])

  const handleSave = async () => {
    setLoading(true)
    try {
      const values = await form.validateFields()
      await updateSettings(values as Settings)
      message.success('保存成功')
    } catch (e: unknown) {
      if (e instanceof Error) message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="设置" loading={fetching} style={{ maxWidth: 600, width: '100%' }}>
      <Form form={form} layout="vertical">
        <Form.Item label="录制保存路径" name="save_path">
          <Input placeholder="~/kuaishou_live" />
        </Form.Item>
        <Form.Item label="录制格式" name="save_format">
          <Select
            options={[
              { value: 'ts', label: 'TS' },
              { value: 'flv', label: 'FLV' },
              { value: 'mp4', label: 'MP4' },
              { value: 'mkv', label: 'MKV' },
            ]}
          />
        </Form.Item>
        <Form.Item label="默认画质" name="default_quality">
          <Select
            options={[
              { value: 'OD', label: '原画' },
              { value: 'BD', label: '蓝光' },
              { value: 'UHD', label: '超清' },
              { value: 'HD', label: '高清' },
              { value: 'SD', label: '标清' },
              { value: 'LD', label: '流畅' },
            ]}
          />
        </Form.Item>
        <Form.Item label="Cookie 来源浏览器" name="browser_for_cookies">
          <Select
            options={[
              { value: 'chrome', label: 'Chrome' },
              { value: 'firefox', label: 'Firefox' },
              { value: 'safari', label: 'Safari' },
              { value: 'edge', label: 'Edge' },
              { value: 'brave', label: 'Brave' },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="手动 Cookie"
          name="cookies"
          extra="填写后优先使用，适用于无浏览器的服务器环境。格式: key1=value1; key2=value2"
        >
          <TextArea rows={3} placeholder="从浏览器开发者工具复制 Cookie 粘贴到这里" />
        </Form.Item>
        <Form.Item label="代理地址" name="proxy">
          <Input placeholder="http://127.0.0.1:7890 (留空不使用)" />
        </Form.Item>
        <Form.Item label="轮询间隔 (秒)" name="poll_interval">
          <InputNumber min={30} max={3600} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" loading={loading} onClick={handleSave}>
            保存设置
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}
