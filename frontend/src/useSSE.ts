import { useEffect, useRef, useState, useCallback } from 'react'
import type { RoomStatus } from './types'

export function useSSE() {
  const [rooms, setRooms] = useState<RoomStatus[]>([])
  const esRef = useRef<EventSource | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const attemptRef = useRef(0)

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
    }

    const es = new EventSource('/api/events')
    esRef.current = es

    es.addEventListener('room_list', (e) => {
      try {
        const data = JSON.parse(e.data)
        setRooms(data)
      } catch {}
    })

    es.addEventListener('room_update', (e) => {
      try {
        const update: RoomStatus = JSON.parse(e.data)
        setRooms((prev) => prev.map((r) => (r.id === update.id ? update : r)))
      } catch {}
    })

    es.onopen = () => {
      attemptRef.current = 0
    }

    es.onerror = () => {
      es.close()
      const delay = Math.min(1000 * Math.pow(2, attemptRef.current), 30000)
      attemptRef.current++
      reconnectTimer.current = setTimeout(connect, delay)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      esRef.current?.close()
      clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  return { rooms, setRooms }
}
