import { useCallback, useEffect } from 'react'
import { useSSE } from '../useSSE'
import { getRooms } from '../api'
import RoomTable from '../components/RoomTable'

export default function HomePage() {
  const { rooms, setRooms } = useSSE()

  // 页面加载时主动拉取一次，不依赖 SSE 初始事件
  useEffect(() => {
    getRooms().then(setRooms).catch(() => {})
  }, [setRooms])

  const refresh = useCallback(async () => {
    try {
      const data = await getRooms()
      setRooms(data)
    } catch {}
  }, [setRooms])

  return <RoomTable rooms={rooms} onRefresh={refresh} />
}
